
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.models import (
    WaitlistEntry,
    TicketCategory,
    Booking
)

from app.messaging.message import (
    AgentMessageSchema,
    Performative
)


class WaitlistAgent:

    def __init__(self, db: Session, message_bus=None):
        self.agent_name = "WaitlistAgent"
        self.db = db
        self.message_bus = message_bus

        # Hold tickets for 10 minutes
        self.hold_minutes = 10

    # Create response message
    def create_response(self, original_message, performative, content):

        return AgentMessageSchema(
            sender=self.agent_name,
            receiver=original_message.sender,
            performative=performative,
            content=content,
            conversation_id=original_message.conversation_id
        )

    # Send notification to NotificationAgent
    def notify_user(self, attendee_id, content, conversation_id):

        if self.message_bus:
            message = AgentMessageSchema(
                sender=self.agent_name,
                receiver="NotificationAgent",
                performative=Performative.INFORM,
                content={
                    "attendee_id": attendee_id,
                    **content
                },
                conversation_id=conversation_id
            )

            self.message_bus.send(message)

    # Join the waiting list
    def join_waitlist(self, message):

        content = message.content

        attendee_id = content["attendee_id"]
        event_id = content["event_id"]
        category_id = content["ticket_category_id"]

        category = self.db.query(TicketCategory).filter(
            TicketCategory.id == category_id,
            TicketCategory.event_id == event_id
        ).first()

        if not category:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Invalid ticket category."}
            )

        if category.sold_count < category.quantity:
            return self.create_response(
                message,
                Performative.REFUSE,
                {
                    "reason": "Tickets are still available. Please book directly."
                }
            )

        # Prevent duplicate active entries
        existing = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.attendee_id == attendee_id,
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.ticket_category_id == category_id,
            WaitlistEntry.status.in_(["waiting", "offered"])
        ).first()

        if existing:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "You are already in this waiting list."}
            )

        entry = WaitlistEntry(
            attendee_id=attendee_id,
            event_id=event_id,
            ticket_category_id=category_id,
            status="waiting"
        )

        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)

        return self.create_response(
            message,
            Performative.AGREE,
            {
                "waitlist_entry_id": entry.id,
                "status": "waiting",
                "message": "Successfully joined the waiting list."
            }
        )

    # Offer available seats to waiting customers
    def offer_available_seats(
        self, event_id, category_id, conversation_id
    ):

        category = self.db.query(TicketCategory).filter(
            TicketCategory.id == category_id,
            TicketCategory.event_id == event_id
        ).with_for_update().first()

        if not category:
            return 0

        available = category.quantity - category.sold_count

        if available <= 0:
            return 0

        waiting_entries = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.ticket_category_id == category_id,
            WaitlistEntry.status == "waiting"
        ).order_by(
            WaitlistEntry.created_at.asc(),
            WaitlistEntry.id.asc()
        ).limit(available).with_for_update().all()

        offered_count = 0

        for entry in waiting_entries:

            entry.status = "offered"
            entry.hold_expires_at = (
                datetime.utcnow() +
                timedelta(minutes=self.hold_minutes)
            )

            # Reserve the offered seat
            category.sold_count += 1
            offered_count += 1

            self.notify_user(
                entry.attendee_id,
                {
                    "action": "WAITLIST_OFFER",
                    "entry_id": entry.id,
                    "event_id": event_id,
                    "category_id": category_id,
                    "expires_at": entry.hold_expires_at.isoformat()
                },
                conversation_id
            )

        self.db.commit()

        return offered_count

    # Claim an offered ticket
    def claim_offer(self, message):

        content = message.content

        entry_id = content["entry_id"]
        attendee_id = content["attendee_id"]

        if not self.message_bus:
            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Agent communication is unavailable."}
            )

        entry = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.id == entry_id,
            WaitlistEntry.attendee_id == attendee_id
        ).with_for_update().first()

        if not entry:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Waitlist entry not found."}
            )

        if entry.status != "offered":
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "No active ticket offer found."}
            )

        if (
            not entry.hold_expires_at
            or entry.hold_expires_at <= datetime.utcnow()
        ):
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Ticket offer has expired."}
            )

        # Ask BookingAgent to complete the reserved booking
        booking_message = AgentMessageSchema(
            sender=self.agent_name,
            receiver="BookingAgent",
            performative=Performative.REQUEST,
            content={
                "action": "CLAIM_WAITLIST_OFFER",
                "entry_id": entry.id,
                "attendee_id": attendee_id,
                "event_id": entry.event_id,
                "ticket_category_id": entry.ticket_category_id
            },
            conversation_id=message.conversation_id
        )

        response = self.message_bus.send(booking_message)

        if (
            response is None
            or response.performative != Performative.AGREE
        ):
            return self.create_response(
                message,
                Performative.FAILURE,
                {
                    "reason": "Booking could not be completed.",
                    "booking_response": (
                        response.content if response else None
                    )
                }
            )

        # Mark the offer as claimed
        entry.status = "claimed"
        entry.hold_expires_at = None
        self.db.commit()

        return self.create_response(
            message,
            Performative.AGREE,
            {
                "message": "Waitlist offer successfully claimed.",
                "entry_id": entry.id,
                "booking_response": response.content
            }
        )

    # Handle booking cancellation notification
    def handle_booking_cancelled(self, message):

        booking_id = message.content["booking_id"]

        booking = self.db.query(Booking).filter(
            Booking.id == booking_id
        ).first()

        if not booking:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Cancelled booking not found."}
            )

        offered = self.offer_available_seats(
            booking.event_id,
            booking.ticket_category_id,
            message.conversation_id
        )

        return self.create_response(
            message,
            Performative.AGREE,
            {
                "message": "Waiting list processed.",
                "offers_created": offered
            }
        )

    # Proactive timer task: expire old holds
    def sweep_expired_holds(self):

        now = datetime.utcnow()

        expired_entries = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.status == "offered",
            WaitlistEntry.hold_expires_at <= now
        ).all()

        expired_count = 0
        released_seats = []

        try:
            for entry in expired_entries:

                category = self.db.query(TicketCategory).filter(
                    TicketCategory.id == entry.ticket_category_id
                ).with_for_update().first()

                if category:
                    category.sold_count = max(
                        0, category.sold_count - 1
                    )

                entry.status = "expired"
                entry.hold_expires_at = None

                released_seats.append((
                    entry.event_id,
                    entry.ticket_category_id
                ))

                expired_count += 1

            self.db.commit()

            # Offer expired seats to the next waiting customers
            for event_id, category_id in released_seats:

                self.offer_available_seats(
                    event_id,
                    category_id,
                    "waitlist-timer"
                )

            return {
                "expired_count": expired_count,
                "message": "Expired holds processed."
            }

        except Exception:
            self.db.rollback()
            raise

    # Main message handler
    def handle_message(self, message):

        try:
            if message.performative == Performative.REQUEST:

                action = message.content.get("action")

                if action == "JOIN_WAITLIST":
                    return self.join_waitlist(message)

                elif action == "CLAIM_OFFER":
                    return self.claim_offer(message)

                return self.create_response(
                    message,
                    Performative.REFUSE,
                    {"reason": "Unknown waitlist request."}
                )

            elif message.performative == Performative.INFORM:

                action = message.content.get("action")

                if action == "BOOKING_CANCELLED":
                    return self.handle_booking_cancelled(message)

                return self.create_response(
                    message,
                    Performative.REFUSE,
                    {"reason": "Unknown notification."}
                )

            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Unsupported message type."}
            )

        except (KeyError, ValueError, TypeError) as error:

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": f"Invalid request: {str(error)}"}
            )
