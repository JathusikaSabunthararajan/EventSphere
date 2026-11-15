
from datetime import datetime
from app.database.database import SessionLocal
from app.models.models import User, Venue, Event, TicketCategory

db = SessionLocal()

try:
    # Create sample organiser
    organiser = db.query(User).filter(User.email == "organiser@eventsphere.com").first()

    if not organiser:
        organiser = User(
            username="Test Organiser",
            email="organiser@eventsphere.com",
            password_hash="temporary_test_hash",
            role="organiser"
        )
        db.add(organiser)
        db.commit()
        db.refresh(organiser)

    # Create sample attendee
    attendee = db.query(User).filter(User.email == "attendee@eventsphere.com").first()

    if not attendee:
        attendee = User(
            username="Test Attendee",
            email="attendee@eventsphere.com",
            password_hash="temporary_test_hash",
            role="attendee"
        )
        db.add(attendee)
        db.commit()
        db.refresh(attendee)

    # Get existing venue
    venue = db.query(Venue).filter(Venue.id == 1).first()

    # Create sample event
    event = db.query(Event).filter(Event.title == "EventSphere Test Event").first()

    if not event:
        event = Event(
            title="EventSphere Test Event",
            category="Technology",
            description="Sample event for agent testing",
            venue_id=venue.id,
            organiser_id=organiser.id,
            start_time=datetime(2026, 11, 14, 8, 0),
            end_time=datetime(2026, 11, 14, 23, 59),
            status="published"
        )
        db.add(event)
        db.commit()
        db.refresh(event)
    else:
        event.start_time = datetime(2026, 11, 14, 8, 0)
        event.end_time = datetime(2026, 11, 14, 23, 59)
        db.commit()
        db.refresh(event)


       

    # Create ticket category
    category = db.query(TicketCategory).filter(
        TicketCategory.event_id == event.id
    ).first()

    if not category:
        category = TicketCategory(
            event_id=event.id,
            name="Standard",
            price=1000,
            quantity=100,
            sold_count=0
        )
        db.add(category)
        db.commit()
        db.refresh(category)
    else:
        category.quantity = category.sold_count
        db.commit()
        db.refresh(category)
        
    print("Test data created successfully!")
    print("Organiser ID:", organiser.id)
    print("Attendee ID:", attendee.id)
    print("Venue ID:", venue.id)
    print("Event ID:", event.id)
    print("Ticket Category ID:", category.id)

finally:
    db.close()
