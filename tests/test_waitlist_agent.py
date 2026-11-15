
import pytest

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models import models
from app.models.models import (
    User, Venue, Event, TicketCategory, WaitlistEntry
)
from app.messaging.message import AgentMessageSchema, Performative
from app.messaging.message_bus import MessageBus
from app.agents.waitlist_agent import WaitlistAgent


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )

    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )

    session = TestingSession()
    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def waitlist_setup(db):
    attendee = User(
        username="waitlist_user",
        email="waitlist@test.com",
        password_hash="test_hash",
        role="attendee"
    )

    organiser = User(
        username="waitlist_organiser",
        email="waitlist_organiser@test.com",
        password_hash="test_hash",
        role="organiser"
    )

    db.add_all([attendee, organiser])
    db.commit()

    venue = Venue(
        name="Waitlist Hall",
        location="University",
        capacity=100,
        hourly_hire_rate=1000,
        is_open_for_private_hire=True
    )

    db.add(venue)
    db.commit()

    event = Event(
        title="Waitlist Test Event",
        category="Music",
        venue_id=venue.id,
        organiser_id=organiser.id,
        start_time=datetime.now() + timedelta(days=10),
        end_time=datetime.now() + timedelta(days=10, hours=3),
        status="published"
    )

    db.add(event)
    db.commit()

    category = TicketCategory(
        event_id=event.id,
        name="Standard",
        price=1000,
        quantity=3,
        sold_count=3
    )

    db.add(category)
    db.commit()

    return attendee, event, category



@pytest.fixture
def waitlist_system(db):
    bus = MessageBus(db)
    agent = WaitlistAgent(db, bus)

    def notification_handler(message):
        return AgentMessageSchema(
            sender="NotificationAgent",
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"message": "Notification sent"},
            conversation_id=message.conversation_id
        )

    bus.register("NotificationAgent", notification_handler)

    # Important: Register WaitlistAgent itself
    bus.register("WaitlistAgent", agent.handle_message)

    return agent, bus


def create_join_message(attendee, event, category):
    return AgentMessageSchema(
        sender="Attendee",
        receiver="WaitlistAgent",
        performative=Performative.REQUEST,
        content={
            "action": "JOIN_WAITLIST",
            "attendee_id": attendee.id,
            "event_id": event.id,
            "ticket_category_id": category.id
        }
    )


def test_join_waitlist_successfully(
    db, waitlist_setup, waitlist_system
):
    attendee, event, category = waitlist_setup
    agent, bus = waitlist_system

    response = bus.send(
        create_join_message(attendee, event, category)
    )

    assert response.performative == Performative.AGREE

    entry = db.query(WaitlistEntry).first()

    assert entry is not None
    assert entry.status == "waiting"
    assert entry.attendee_id == attendee.id


def test_prevent_duplicate_waitlist_entry(
    db, waitlist_setup, waitlist_system
):
    attendee, event, category = waitlist_setup
    agent, bus = waitlist_system

    first_response = bus.send(
        create_join_message(attendee, event, category)
    )

    second_response = bus.send(
        create_join_message(attendee, event, category)
    )

    assert first_response.performative == Performative.AGREE
    assert second_response.performative == Performative.REFUSE

    assert db.query(WaitlistEntry).count() == 1


def test_reject_waitlist_when_tickets_available(
    db, waitlist_setup, waitlist_system
):
    attendee, event, category = waitlist_setup
    agent, bus = waitlist_system

    category.sold_count = 1
    db.commit()

    response = bus.send(
        create_join_message(attendee, event, category)
    )

    assert response.performative == Performative.REFUSE
    assert db.query(WaitlistEntry).count() == 0


def test_offer_available_seat(
    db, waitlist_setup, waitlist_system
):
    attendee, event, category = waitlist_setup
    agent, bus = waitlist_system

    join_response = bus.send(
        create_join_message(attendee, event, category)
    )

    assert join_response.performative == Performative.AGREE

    # Simulate one released seat
    category.sold_count -= 1
    db.commit()

    offered_count = agent.offer_available_seats(
        event.id,
        category.id,
        "waitlist-offer-test"
    )

    entry = db.query(WaitlistEntry).first()

    assert offered_count == 1
    assert entry.status == "offered"
    assert entry.hold_expires_at is not None
    assert category.sold_count == category.quantity


def test_expire_unclaimed_offer(
    db, waitlist_setup, waitlist_system
):
    attendee, event, category = waitlist_setup
    agent, bus = waitlist_system

    entry = WaitlistEntry(
        attendee_id=attendee.id,
        event_id=event.id,
        ticket_category_id=category.id,
        status="offered",
        hold_expires_at=datetime.utcnow() - timedelta(minutes=1)
    )

    db.add(entry)
    db.commit()

    result = agent.sweep_expired_holds()

    db.refresh(entry)
    db.refresh(category)

    assert result["expired_count"] == 1
    assert entry.status == "expired"
    assert entry.hold_expires_at is None
    assert category.sold_count == 2


def test_claim_active_waitlist_offer(
    db, waitlist_setup
):
    attendee, event, category = waitlist_setup

    bus = MessageBus(db)
    agent = WaitlistAgent(db, bus)
    bus.register("WaitlistAgent", agent.handle_message)

    entry = WaitlistEntry(
        attendee_id=attendee.id,
        event_id=event.id,
        ticket_category_id=category.id,
        status="offered",
        hold_expires_at=datetime.utcnow() + timedelta(minutes=10)
    )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    # Simulate successful BookingAgent response
    def booking_handler(message):
        return AgentMessageSchema(
            sender="BookingAgent",
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"booking_id": 100, "status": "confirmed"},
            conversation_id=message.conversation_id
        )

    bus.register("BookingAgent", booking_handler)

    message = AgentMessageSchema(
        sender="Attendee",
        receiver="WaitlistAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CLAIM_OFFER",
            "entry_id": entry.id,
            "attendee_id": attendee.id
        }
    )

    response = bus.send(message)

    db.refresh(entry)

    assert response.performative == Performative.AGREE
    assert entry.status == "claimed"
    assert entry.hold_expires_at is None
