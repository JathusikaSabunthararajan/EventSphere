
from sqlalchemy.orm import Session

from app.messaging.message_bus import MessageBus

from app.agents.venue_agent import VenueAgent
from app.agents.booking_agent import BookingAgent
from app.agents.ticket_agent import TicketAgent
from app.agents.waitlist_agent import WaitlistAgent
from app.agents.notification_agent import NotificationAgent


def create_agent_system(db: Session):

    # Create one shared Message Bus
    message_bus = MessageBus(db)

    # Initialize all five agents
    venue_agent = VenueAgent(db)

    booking_agent = BookingAgent(
        db,
        message_bus
    )

    ticket_agent = TicketAgent(db,message_bus)

    waitlist_agent = WaitlistAgent(
        db,
        message_bus
    )

    notification_agent = NotificationAgent(db)

    # Register all agents
    message_bus.register(
        "VenueAgent",
        venue_agent.handle_message
    )

    message_bus.register(
        "BookingAgent",
        booking_agent.handle_message
    )

    message_bus.register(
        "TicketAgent",
        ticket_agent.handle_message
    )

    message_bus.register(
        "WaitlistAgent",
        waitlist_agent.handle_message
    )

    message_bus.register(
        "NotificationAgent",
        notification_agent.handle_message
    )

    return {
        "message_bus": message_bus,
        "VenueAgent": venue_agent,
        "BookingAgent": booking_agent,
        "TicketAgent": ticket_agent,
        "WaitlistAgent": waitlist_agent,
        "NotificationAgent": notification_agent
    }
