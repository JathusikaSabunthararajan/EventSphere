
import pytest

from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base
from app.models import models
from app.models.models import User, Venue, Event, AgentMessage
from app.messaging.message import AgentMessageSchema, Performative
from app.messaging.message_bus import MessageBus
from app.agents.venue_agent import VenueAgent


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
def setup_venue(db):

    user = User(
        username="admin",
        email="admin@test.com",
        password_hash="test_hash",
        role="admin"
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    venue = Venue(
        name="Main Auditorium",
        location="University Campus",
        capacity=500,
        hourly_hire_rate=5000,
        is_open_for_private_hire=True
    )

    db.add(venue)
    db.commit()
    db.refresh(venue)

    return user, venue


def test_venue_available(db, setup_venue):

    user, venue = setup_venue

    agent = VenueAgent(db)
    bus = MessageBus(db)

    bus.register("VenueAgent", agent.handle_message)

    message = AgentMessageSchema(
        sender="Admin",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_EVENT_SLOT",
            "venue_id": venue.id,
            "start_time": "2030-01-01T10:00:00",
            "end_time": "2030-01-01T12:00:00"
        }
    )

    response = bus.send(message)

    assert response.performative == Performative.AGREE


def test_venue_schedule_conflict(db, setup_venue):

    user, venue = setup_venue

    existing_event = Event(
        title="Existing Concert",
        category="Music",
        venue_id=venue.id,
        organiser_id=user.id,
        start_time=datetime(2030, 1, 1, 10, 0),
        end_time=datetime(2030, 1, 1, 12, 0),
        status="published"
    )

    db.add(existing_event)
    db.commit()

    agent = VenueAgent(db)
    bus = MessageBus(db)

    bus.register("VenueAgent", agent.handle_message)

    message = AgentMessageSchema(
        sender="Admin",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_EVENT_SLOT",
            "venue_id": venue.id,
            "start_time": "2030-01-01T10:30:00",
            "end_time": "2030-01-01T11:30:00"
        }
    )

    response = bus.send(message)

    assert response.performative == Performative.PROPOSE

    assert "alternatives" in response.content


def test_message_is_logged(db, setup_venue):

    user, venue = setup_venue

    agent = VenueAgent(db)
    bus = MessageBus(db)

    bus.register("VenueAgent", agent.handle_message)

    message = AgentMessageSchema(
        sender="Admin",
        receiver="VenueAgent",
        performative=Performative.REQUEST,
        content={
            "action": "CHECK_EVENT_SLOT",
            "venue_id": venue.id,
            "start_time": "2030-01-01T10:00:00",
            "end_time": "2030-01-01T12:00:00"
        }
    )

    bus.send(message)

    saved_message = db.query(AgentMessage).first()

    assert saved_message is not None
    assert saved_message.sender == "Admin"
    assert saved_message.receiver == "VenueAgent"
    assert saved_message.conversation_id == message.conversation_id
