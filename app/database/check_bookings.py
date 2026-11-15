from app.database.database import SessionLocal
from app.models.models import Booking, TicketCategory

db = SessionLocal()

try:
    bookings = db.query(Booking).filter(
        Booking.event_id == 1
    ).all()

    for booking in bookings:
        print(
            "Booking ID:", booking.id,
            "| Status:", booking.status,
            "| Quantity:", booking.quantity
        )

    category = db.query(TicketCategory).filter(
        TicketCategory.id == 1
    ).first()

    print("Sold:", category.sold_count)
    print("Capacity:", category.quantity)

finally:
    db.close()