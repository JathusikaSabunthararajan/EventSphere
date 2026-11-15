
import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models import models
from app.models.models import User, Notification
from app.messaging.message import AgentMessageSchema, Performative
from app.agents.notification_agent import NotificationAgent


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
def notification_setup(db):
    attendee = User(
        username="notification_user",
        email="notification@test.com",
        password_hash="test_hash",
        role="attendee"
    )

    db.add(attendee)
    db.commit()
    db.refresh(attendee)

    agent = NotificationAgent(db)

    return attendee, agent


def create_notification_message(attendee_id, action):
    return AgentMessageSchema(
        sender="BookingAgent",
        receiver="NotificationAgent",
        performative=Performative.INFORM,
        content={
            "action": action,
            "attendee_id": attendee_id,
            "event_id": 1
        }
    )


def test_booking_notification_success(
    db, notification_setup
):
    attendee, agent = notification_setup

    message = create_notification_message(
        attendee.id,
        "BOOKING_CONFIRMED"
    )

    response = agent.handle_message(message)

    assert response.performative == Performative.AGREE

    notification = db.query(Notification).first()

    assert notification is not None
    assert notification.user_id == attendee.id
    assert notification.title == "Booking Confirmed"
    assert notification.notification_type == "booking"


def test_ticket_issued_notification(
    db, notification_setup
):
    attendee, agent = notification_setup

    message = create_notification_message(
        attendee.id,
        "TICKET_ISSUED"
    )

    response = agent.handle_message(message)

    assert response.performative == Performative.AGREE

    notification = db.query(Notification).first()

    assert notification.title == "Digital Ticket Issued"
    assert notification.notification_type == "ticket"


def test_reject_notification_without_attendee_id(
    db, notification_setup
):
    attendee, agent = notification_setup

    message = AgentMessageSchema(
        sender="BookingAgent",
        receiver="NotificationAgent",
        performative=Performative.INFORM,
        content={
            "action": "BOOKING_CONFIRMED"
        }
    )

    response = agent.handle_message(message)

    assert response.performative == Performative.REFUSE
    assert db.query(Notification).count() == 0


def test_reject_unknown_notification_event(
    db, notification_setup
):
    attendee, agent = notification_setup

    message = create_notification_message(
        attendee.id,
        "UNKNOWN_ACTION"
    )

    response = agent.handle_message(message)

    assert response.performative == Performative.REFUSE
    assert db.query(Notification).count() == 0


def test_reject_unsupported_performative(
    db, notification_setup
):
    attendee, agent = notification_setup

    message = AgentMessageSchema(
        sender="BookingAgent",
        receiver="NotificationAgent",
        performative=Performative.REFUSE,
        content={
            "action": "BOOKING_CONFIRMED",
            "attendee_id": attendee.id
        }
    )

    response = agent.handle_message(message)

    assert response.performative == Performative.REFUSE
    assert db.query(Notification).count() == 0


def test_retrieve_user_notifications(
    db, notification_setup
):
    attendee, agent = notification_setup

    message = create_notification_message(
        attendee.id,
        "BOOKING_CONFIRMED"
    )

    agent.handle_message(message)

    notifications = agent.get_user_notifications(attendee.id)

    assert len(notifications) == 1
    assert notifications[0]["title"] == "Booking Confirmed"
    assert notifications[0]["type"] == "booking"
