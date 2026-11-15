
from app.database.database import SessionLocal
from app.models.models import TicketCategory

db = SessionLocal()

try:
    category = db.query(TicketCategory).filter(
        TicketCategory.id == 2,
        TicketCategory.event_id == 3
    ).first()

    if category:
        category.sold_count = category.quantity
        db.commit()
        print("Event 3, Category 2 is now SOLD OUT.")
    else:
        print("Ticket category not found.")

finally:
    db.close()
