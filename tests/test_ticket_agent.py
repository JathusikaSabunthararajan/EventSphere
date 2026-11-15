
import pytest

from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models import models
from app.models.models import (
    User, Venue, Event, Booking, Ticket
)
from app.messaging.message import AgentMessageSchema, Performative
from app.agents.ticket_agent import TicketAgent


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
def ticket_setup(db):
    attendee = User(
        username="attendee",
        email="ticket@test.com",
        password_hash="test_hash",
        role="attendee"
    )

    organiser = User(
        username="organiser",
        email="organiser_ticket@test.com",
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
        title="Ticket Test Event",
        category="Music",
        venue_id=venue.id,
        organiser_id=organiser.id,
        start_time=datetime.now() - timedelta(hours=1),
        end_time=datetime.now() + timedelta(hours=3),
        status="published"
    )

    db.add(event)
    db.commit()

    category = models.TicketCategory(
        event_id=event.id,
        name="Standard",
        price=1000,
        quantity=100,
        sold_count=1
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    booking = Booking(
    attendee_id=attendee.id,
    event_id=event.id,
    ticket_category_id=category.id,
    quantity=1,
    total_amount=1000,
    status="confirmed"
)

    db.add(booking)
    db.commit()

    db.add(booking)
    db.commit()

    return attendee, event, booking


@pytest.fixture
def ticket_agent(db):
    agent = TicketAgent(db)

    # Avoid creating actual QR image files during tests
    agent.generate_qr = lambda ticket_code, ticket_id: (
        f"test_ticket_{ticket_id}.png"
    )

    return agent


def create_issue_message(booking, event):
    return AgentMessageSchema(
        sender="BookingAgent",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={
            "action": "ISSUE_TICKETS",
            "booking_id": booking.id,
            "event_id": event.id,
            "quantity": booking.quantity
        }
    )


def create_checkin_message(ticket_code, event_id):
    return AgentMessageSchema(
        sender="GateStaff",
        receiver="TicketAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_IN",
            "qr_code": ticket_code,
            "event_id": event_id
        }
    )


def test_issue_ticket_successfully(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    message = create_issue_message(booking, event)
    response = ticket_agent.handle_message(message)

    assert response.performative == Performative.AGREE
    assert response.content["issued_count"] == 1

    ticket = db.query(Ticket).filter(
        Ticket.booking_id == booking.id
    ).first()

    assert ticket is not None
    assert ticket.status == "valid"
    assert ticket.qr_code is not None


def test_prevent_duplicate_ticket_issuance(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    message = create_issue_message(booking, event)

    first_response = ticket_agent.handle_message(message)
    second_response = ticket_agent.handle_message(message)

    assert first_response.performative == Performative.AGREE
    assert second_response.performative == Performative.AGREE

    assert db.query(Ticket).filter(
        Ticket.booking_id == booking.id
    ).count() == 1


def test_reject_invalid_qr_code(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    message = create_checkin_message(
        "invalid-qr-code",
        event.id
    )

    response = ticket_agent.handle_message(message)

    assert response.performative == Performative.REFUSE
    assert response.content["reason"] == "Invalid ticket code."


def test_reject_ticket_for_wrong_event(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    issue_response = ticket_agent.handle_message(
        create_issue_message(booking, event)
    )

    ticket_code = issue_response.content["tickets"][0]["qr_code"]

    message = create_checkin_message(
        ticket_code,
        event.id + 100
    )

    response = ticket_agent.handle_message(message)

    assert response.performative == Performative.REFUSE
    assert response.content["reason"] == "Ticket belongs to another event."


def test_successful_check_in(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    issue_response = ticket_agent.handle_message(
        create_issue_message(booking, event)
    )

    ticket_code = issue_response.content["tickets"][0]["qr_code"]

    message = create_checkin_message(ticket_code, event.id)
    response = ticket_agent.handle_message(message)

    ticket = db.query(Ticket).first()

    assert response.performative == Performative.AGREE
    assert response.content["reason"] == "Ticket admitted successfully."
    assert ticket.status == "used"
    assert ticket.checked_in_at is not None


def test_prevent_double_check_in(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    issue_response = ticket_agent.handle_message(
        create_issue_message(booking, event)
    )

    ticket_code = issue_response.content["tickets"][0]["qr_code"]

    first_scan = ticket_agent.handle_message(
        create_checkin_message(ticket_code, event.id)
    )

    second_scan = ticket_agent.handle_message(
        create_checkin_message(ticket_code, event.id)
    )

    assert first_scan.performative == Performative.AGREE
    assert second_scan.performative == Performative.REFUSE


def test_cancelled_ticket_cannot_be_used(
    db, ticket_setup, ticket_agent
):
    attendee, event, booking = ticket_setup

    issue_response = ticket_agent.handle_message(
        create_issue_message(booking, event)
    )

    ticket_code = issue_response.content["tickets"][0]["qr_code"]

    cancellation_message = AgentMessageSchema(
        sender="BookingAgent",
        receiver="TicketAgent",
        performative=Performative.INFORM,
        content={
            "action": "BOOKING_CANCELLED",
            "booking_id": booking.id
        }
    )

    cancel_response = ticket_agent.handle_message(
        cancellation_message
    )

    checkin_response = ticket_agent.handle_message(
        create_checkin_message(ticket_code, event.id)
    )

    assert cancel_response.performative == Performative.AGREE
    assert checkin_response.performative == Performative.REFUSE
    assert checkin_response.content["reason"] == (
        "This ticket has been cancelled."
    )
