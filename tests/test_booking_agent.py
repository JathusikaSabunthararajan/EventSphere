
import pytest

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models import models
from app.models.models import User, Venue, Event, TicketCategory, Booking, Payment
from app.messaging.message import AgentMessageSchema, Performative
from app.messaging.message_bus import MessageBus
from app.agents.booking_agent import BookingAgent


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
def setup_booking(db):
    attendee = User(
        username="attendee",
        email="attendee@test.com",
        password_hash="test_hash",
        role="attendee"
    )

    organiser = User(
        username="organiser",
        email="organiser@test.com",
        password_hash="test_hash",
        role="organiser"
    )

    db.add_all([attendee, organiser])
    db.commit()

    venue = Venue(
        name="Test Hall",
        location="University",
        capacity=100,
        hourly_hire_rate=1000,
        is_open_for_private_hire=True
    )

    db.add(venue)
    db.commit()

    event = Event(
        title="Test Event",
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
        quantity=5,
        sold_count=0
    )

    db.add(category)
    db.commit()

    return attendee, event, category


@pytest.fixture
def booking_system(db):
    bus = MessageBus(db)
    agent = BookingAgent(db, bus)

    # Simulate successful TicketAgent response
    def ticket_handler(message):
        return AgentMessageSchema(
            sender="TicketAgent",
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"issued_count": message.content["quantity"]},
            conversation_id=message.conversation_id
        )

    # Simulate NotificationAgent response
    def notification_handler(message):
        return AgentMessageSchema(
            sender="NotificationAgent",
            receiver=message.sender,
            performative=Performative.AGREE,
            content={"message": "Notification processed"},
            conversation_id=message.conversation_id
        )

    bus.register("TicketAgent", ticket_handler)
    bus.register("NotificationAgent", notification_handler)
    bus.register("BookingAgent", agent.handle_message)

    return agent, bus


def create_booking_message(attendee, event, category, quantity):
    return AgentMessageSchema(
        sender="Attendee",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "BOOK_TICKETS",
            "attendee_id": attendee.id,
            "event_id": event.id,
            "ticket_category_id": category.id,
            "quantity": quantity
        }
    )


def test_successful_booking(db, setup_booking, booking_system):
    attendee, event, category = setup_booking
    agent, bus = booking_system

    message = create_booking_message(attendee, event, category, 2)
    response = bus.send(message)

    assert response.performative == Performative.AGREE

    booking = db.query(Booking).first()
    payment = db.query(Payment).first()

    assert booking is not None
    assert booking.quantity == 2
    assert booking.status == "confirmed"
    assert payment.status == "completed"
    assert category.sold_count == 2


def test_reject_booking_when_sold_out(
    db, setup_booking, booking_system
):
    attendee, event, category = setup_booking
    agent, bus = booking_system

    category.sold_count = category.quantity
    db.commit()

    message = create_booking_message(attendee, event, category, 1)
    response = bus.send(message)

    assert response.performative == Performative.REFUSE
    assert db.query(Booking).count() == 0


def test_prevent_overbooking(
    db, setup_booking, booking_system
):
    attendee, event, category = setup_booking
    agent, bus = booking_system

    message = create_booking_message(attendee, event, category, 6)
    response = bus.send(message)

    assert response.performative == Performative.REFUSE
    assert category.sold_count == 0
    assert db.query(Booking).count() == 0


def test_reject_invalid_quantity(
    db, setup_booking, booking_system
):
    attendee, event, category = setup_booking
    agent, bus = booking_system

    message = create_booking_message(attendee, event, category, 0)
    response = bus.send(message)

    assert response.performative == Performative.REFUSE
    assert db.query(Booking).count() == 0


def test_reject_quantity_above_limit(
    db, setup_booking, booking_system
):
    attendee, event, category = setup_booking
    agent, bus = booking_system

    message = create_booking_message(attendee, event, category, 7)
    response = bus.send(message)

    assert response.performative == Performative.REFUSE
    assert db.query(Booking).count() == 0


def test_cancel_booking_with_full_refund(
    db, setup_booking, booking_system
):
    attendee, event, category = setup_booking
    agent, bus = booking_system

    # First create a booking
    booking_message = create_booking_message(
        attendee, event, category, 2
    )
    booking_response = bus.send(booking_message)

    assert booking_response.performative == Performative.AGREE

    booking = db.query(Booking).first()

    # Cancel the booking because the event is cancelled
    cancel_message = AgentMessageSchema(
        sender="Attendee",
        receiver="BookingAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CANCEL_BOOKING",
            "booking_id": booking.id,
            "event_cancelled": True
        }
    )

    response = bus.send(cancel_message)

    db.refresh(booking)
    payment = db.query(Payment).filter(
        Payment.booking_id == booking.id
    ).first()

    assert response.performative == Performative.AGREE
    assert response.content["refund_percentage"] == 100
    assert booking.status == "cancelled"
    assert payment.status == "refunded"
    assert category.sold_count == 0
