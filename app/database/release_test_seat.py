
from app.database.database import SessionLocal
from app.models.models import TicketCategory
from app.agents.agent_manager import create_agent_system

db = SessionLocal()

try:
    category = db.query(TicketCategory).filter(
        TicketCategory.id == 2,
        TicketCategory.event_id == 3
    ).first()

    if not category:
        print("Ticket category not found.")
    elif category.sold_count <= 0:
        print("No sold tickets available to release.")
    else:
        category.sold_count -= 1
        db.commit()

        agents = create_agent_system(db)
        waitlist_agent = agents["WaitlistAgent"]

        offered = waitlist_agent.offer_available_seats(
            event_id=3,
            category_id=2,
            conversation_id="waitlist-claim-test-004"
        )

        print("Offers created:", offered)

finally:
    db.close()
