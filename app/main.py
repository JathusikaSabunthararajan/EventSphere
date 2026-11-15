
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db, Base, engine
from app.models import models

from app.messaging.message import AgentMessageSchema
from app.agents.agent_manager import create_agent_system

from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler

from app.database.database import SessionLocal

from app.routers import auth

from app.services.auth_dependencies import get_current_user

from app.services.auth_dependencies import require_role

from fastapi import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.schemas.event import EventCreate
from datetime import datetime

from app.schemas.ticket import TicketCategoryCreate
# Background scheduler
scheduler = BackgroundScheduler()


def check_expired_waitlist_holds():

    db = SessionLocal()

    try:
        agent_system = create_agent_system(db)

        waitlist_agent = agent_system["WaitlistAgent"]

        result = waitlist_agent.sweep_expired_holds()

        print("Waitlist expiry check:", result)

    except Exception as error:
        print("Waitlist scheduler error:", error)

    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):

    scheduler.add_job(
        check_expired_waitlist_holds,
        trigger="interval",
        seconds=30,
        id="waitlist_expiry",
        replace_existing=True,
        max_instances=1,
        coalesce=True
    )

    scheduler.start()

    print("Waitlist scheduler started.")

    yield

    scheduler.shutdown()

    print("Waitlist scheduler stopped.")


# Create database tables
Base.metadata.create_all(bind=engine)


# Initialize FastAPI
app = FastAPI(
    title="EventSphere API",
    description="University Event Booking and Digital Ticketing Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Static files configuration
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

# HTML templates configuration
templates = Jinja2Templates(
    directory="app/templates"
)

app.include_router(auth.router)


# List of available agents
AGENT_NAMES = [
    "VenueAgent",
    "BookingAgent",
    "TicketAgent",
    "WaitlistAgent",
    "NotificationAgent"
]


AGENT_PERMISSIONS = {
    "VenueAgent": ["admin", "organiser"],
    "BookingAgent": ["admin", "organiser", "attendee"],
    "TicketAgent": ["admin", "gate_staff", "attendee"],
    "WaitlistAgent": ["admin", "organiser", "attendee"],
    "NotificationAgent": ["admin", "organiser", "gate_staff", "attendee"]
}



# Home endpoint
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    )

# Login page
@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

# Registration page
@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={}
    )


# Dashboard page
@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )


# My Digital Tickets page
@app.get("/my-tickets")
def my_tickets_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="my_tickets.html",
        context={}
    )


# Health check
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "EventSphere"
    }


# View available agents
@app.get("/agents")
def get_agents():
    return {
        "total_agents": len(AGENT_NAMES),
        "agents": AGENT_NAMES
    }



# Send a message to an agent
@app.post("/agents/message")
def send_agent_message(
    message: AgentMessageSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Only authorised roles can send agent messages
    allowed_roles = ["admin", "organiser", "gate_staff", "attendee"]

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to contact agents."
        )

    if message.receiver not in AGENT_NAMES:
        raise HTTPException(
            status_code=404,
            detail="Requested agent does not exist."
        )
    allowed_roles = AGENT_PERMISSIONS[message.receiver]

    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"{current_user.role} is not allowed to contact {message.receiver}."
        )

    try:
        agent_system = create_agent_system(db)

        message_bus = agent_system["message_bus"]

        response = message_bus.send(message)

        if response is None:
            raise HTTPException(
                status_code=404,
                detail="Agent could not process the message."
            )

        return {
            "success": True,
            "response": response.model_dump(mode="json")
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

# Get notifications of the logged-in attendee
@app.get("/notifications/my")
def get_my_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    agent_system = create_agent_system(db)

    notification_agent = agent_system["NotificationAgent"]

    notifications = (
        notification_agent.get_user_notifications(
            current_user.id
        )
    )

    return {
        "total_notifications": len(notifications),
        "notifications": notifications
    }


# Get attendee notifications
@app.get("/notifications/{attendee_id}")
def get_notifications(
    attendee_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Users can only view their own notifications.
    # Admin can view any attendee's notifications.
    if current_user.id != attendee_id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="You cannot access another user's notifications."
        )

    agent_system = create_agent_system(db)

    notification_agent = agent_system["NotificationAgent"]

    notifications = notification_agent.get_user_notifications(
        attendee_id
    )

    return {
        "attendee_id": attendee_id,
        "total_notifications": len(notifications),
        "notifications": notifications
    }

# Get waitlist entries of the logged-in attendee
@app.get("/waitlist/my")
def get_my_waitlist(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    entries = (
        db.query(models.WaitlistEntry)
        .filter(
            models.WaitlistEntry.attendee_id == current_user.id
        )
        .order_by(models.WaitlistEntry.created_at.desc())
        .all()
    )

    return {
        "total_entries": len(entries),
        "waitlist": [
            {
                "entry_id": entry.id,
                "event_id": entry.event_id,
                "ticket_category_id": entry.ticket_category_id,
                "status": entry.status,
                "hold_expires_at": (
                    entry.hold_expires_at.isoformat()
                    if entry.hold_expires_at else None
                )
            }
            for entry in entries
        ]
    }


# Get waitlist entries for an event
@app.get("/waitlist/{event_id}")
def get_waitlist(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    # Only Admin and Organiser can view waitlist details
    if current_user.role not in ["admin", "organiser"]:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view waitlist entries."
        )

    entries = (
        db.query(models.WaitlistEntry)
        .filter(models.WaitlistEntry.event_id == event_id)
        .order_by(models.WaitlistEntry.created_at.asc())
        .all()
    )

    return {
        "event_id": event_id,
        "total_entries": len(entries),
        "waitlist": [
            {
                "entry_id": entry.id,
                "attendee_id": entry.attendee_id,
                "ticket_category_id": entry.ticket_category_id,
                "status": entry.status,
                "hold_expires_at": (
                    entry.hold_expires_at.isoformat()
                    if entry.hold_expires_at else None
                )
            }
            for entry in entries
        ]
    }







# Get bookings of the logged-in attendee
@app.get("/bookings/my")
def get_my_bookings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    bookings = (
        db.query(models.Booking)
        .filter(
            models.Booking.attendee_id == current_user.id
        )
        .order_by(models.Booking.id.desc())
        .all()
    )

    return {
        "total_bookings": len(bookings),
        "bookings": [
            {
                "booking_id": booking.id,
                "event_id": booking.event_id,
                "quantity": booking.quantity,
                "total_amount": booking.total_amount,
                "status": booking.status
            }
            for booking in bookings
        ]
    }



# Get tickets belonging to the logged-in attendee
@app.get("/tickets/my")
def get_my_tickets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    bookings = (
        db.query(models.Booking)
        .filter(
            models.Booking.attendee_id == current_user.id
        )
        .all()
    )

    booking_ids = [booking.id for booking in bookings]

    tickets = (
        db.query(models.Ticket)
        .filter(models.Ticket.booking_id.in_(booking_ids))
        .all()
    ) if booking_ids else []

    return {
        "total_tickets": len(tickets),
        "tickets": [
            {
                "ticket_id": ticket.id,
                "booking_id": ticket.booking_id,
                "qr_code": ticket.qr_code,
                "qr_image": (
                    f"/static/images/tickets/ticket_{ticket.id}.png"
                ),
                "status": ticket.status
            }
            for ticket in tickets
        ]
    }



# Get all events for organisers
@app.get("/organiser/events")
def get_organiser_events(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("organiser"))
):
    events = db.query(models.Event).all()

    return {
        "total_events": len(events),
        "events": [
            {
                "event_id": event.id,
                "title": event.title,
                "venue_id": event.venue_id,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat(),
                "status": event.status
            }
            for event in events
        ]
    }



@app.post("/organiser/events")
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("organiser"))
):

    venue = db.query(models.Venue).filter(
        models.Venue.id == event_data.venue_id
    ).first()

    if not venue:
        raise HTTPException(
            status_code=404,
            detail="Venue not found."
        )

    if event_data.end_time <= event_data.start_time:
        raise HTTPException(
            status_code=400,
            detail="End time must be after start time."
        )

    new_event = models.Event(
        title=event_data.title,
        category=event_data.category,
        description=event_data.description,
        venue_id=event_data.venue_id,
        organiser_id=current_user.id,
        start_time=event_data.start_time,
        end_time=event_data.end_time,
        status="draft"
    )

    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    return {
        "message": "Event created successfully.",
        "event_id": new_event.id,
        "title": new_event.title,
        "category": new_event.category,
        "organiser_id": new_event.organiser_id,
        "status": new_event.status
    }


# Publish an event
@app.patch("/organiser/events/{event_id}/publish")
def publish_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("organiser"))
):

    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.organiser_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found or you do not own this event."
        )

    if event.status == "published":
        raise HTTPException(
            status_code=400,
            detail="Event is already published."
        )

    event.status = "published"

    db.commit()
    db.refresh(event)

    return {
        "message": "Event published successfully.",
        "event_id": event.id,
        "title": event.title,
        "status": event.status
    }


# Get all published events (Public API)
@app.get("/events")
def get_public_events(
    db: Session = Depends(get_db)
):
    events = (
        db.query(models.Event)
        .filter(models.Event.status == "published")
        .order_by(models.Event.start_time.asc())
        .all()
    )

    return {
        "total_events": len(events),
        "events": [
            {
                "event_id": event.id,
                "title": event.title,
                "category": event.category,
                "description": event.description,
                "venue_id": event.venue_id,
                "start_time": event.start_time.isoformat(),
                "end_time": event.end_time.isoformat(),
                "status": event.status
            }
            for event in events
        ]
    }


# Get ticket categories for a specific event
@app.get("/events/{event_id}/ticket-categories")
def get_event_ticket_categories(
    event_id: int,
    db: Session = Depends(get_db)
):
    event = (
        db.query(models.Event)
        .filter(
            models.Event.id == event_id,
            models.Event.status == "published"
        )
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Published event not found."
        )

    categories = (
        db.query(models.TicketCategory)
        .filter(
            models.TicketCategory.event_id == event_id
        )
        .all()
    )

    return {
        "event_id": event.id,
        "event_title": event.title,
        "total_categories": len(categories),
        "categories": [
            {
                "category_id": category.id,
                "name": category.name,
                "price": category.price,
                "quantity": category.quantity,
                "sold_count": category.sold_count,
                "available_tickets": (
                    category.quantity - category.sold_count
                )
            }
            for category in categories
        ]
    }


# Create ticket category for an organiser's event
@app.post("/organiser/events/{event_id}/ticket-categories")
def create_ticket_category(
    event_id: int,
    category_data: TicketCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_role("organiser"))
):

    event = db.query(models.Event).filter(
        models.Event.id == event_id,
        models.Event.organiser_id == current_user.id
    ).first()

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found or you do not own this event."
        )

    if event.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Ticket categories can only be added to draft events."
        )

    new_category = models.TicketCategory(
        event_id=event.id,
        name=category_data.name,
        price=category_data.price,
        quantity=category_data.quantity,
        sold_count=0
    )

    db.add(new_category)
    db.commit()
    db.refresh(new_category)

    return {
        "message": "Ticket category created successfully.",
        "category_id": new_category.id,
        "event_id": event.id,
        "name": new_category.name,
        "price": new_category.price,
        "quantity": new_category.quantity
    }
