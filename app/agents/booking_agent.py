
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import update

from app.models.models import (
    Event,
    Booking,
    TicketCategory,
    Payment,
    WaitlistEntry
)

from app.messaging.message import (
    AgentMessageSchema,
    Performative
)


class BookingAgent:

    def __init__(self, db: Session, message_bus=None):
        self.agent_name = "BookingAgent"
        self.db = db
        self.message_bus = message_bus

        # Maximum tickets per booking
        self.max_tickets_per_booking = 6

    # Create response messages
    def create_response(self, original_message, performative, content):

        return AgentMessageSchema(
            sender=self.agent_name,
            receiver=original_message.sender,
            performative=performative,
            content=content,
            conversation_id=original_message.conversation_id
        )

    # Process ticket booking requests
    def book_tickets(self, message):

        content = message.content

        attendee_id = content["attendee_id"]
        event_id = content["event_id"]
        category_id = content["ticket_category_id"]
        quantity = content["quantity"]

        if not isinstance(quantity, int) or isinstance(quantity, bool):
            return self.create_response(
                message, Performative.REFUSE,
                {"reason": "Ticket quantity must be an integer."}
            )

        if quantity <= 0 or quantity > self.max_tickets_per_booking:
            return self.create_response(
                message, Performative.REFUSE,
                {"reason": "Booking quantity must be between 1 and 6."}
            )

        # Check event
        event = self.db.query(Event).filter(
            Event.id == event_id
        ).first()

        if not event or event.status != "published":
            return self.create_response(
                message, Performative.REFUSE,
                {"reason": "Event does not exist or is not published."}
            )

        if event.start_time <= datetime.now():
            return self.create_response(
                message, Performative.REFUSE,
                {"reason": "Ticket booking is closed for this event."}
            )

        # Check ticket category
        category = self.db.query(TicketCategory).filter(
            TicketCategory.id == category_id,
            TicketCategory.event_id == event_id
        ).first()

        if not category:
            return self.create_response(
                message, Performative.REFUSE,
                {"reason": "Invalid ticket category."}
            )

        # Atomically reserve available tickets
        reservation = self.db.execute(
            update(TicketCategory)
            .where(
                TicketCategory.id == category_id,
                TicketCategory.sold_count + quantity
                <= TicketCategory.quantity
            )
            .values(
                sold_count=TicketCategory.sold_count + quantity
            )
        )

        if reservation.rowcount != 1:
            self.db.rollback()

            return self.create_response(
                message, Performative.REFUSE,
                {"reason": "Not enough tickets available."}
            )

        try:
            total_amount = category.price * quantity

            booking = Booking(
                attendee_id=attendee_id,
                event_id=event_id,
                ticket_category_id=category_id,
                quantity=quantity,
                total_amount=total_amount,
                status="confirmed"
            )

            self.db.add(booking)
            self.db.flush()

            # Simulated payment only
            payment_reference = "PAY-" + str(uuid4())

            payment = Payment(
                booking_id=booking.id,
                amount=total_amount,
                payment_reference=payment_reference,
                status="completed"
            )

            self.db.add(payment)
            self.db.commit()
            self.db.refresh(booking)

        except Exception:
            self.db.rollback()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Booking could not be completed."}
            )

        
    
        # Request unique QR tickets from TicketAgent
        if not self.message_bus:
            booking.status = "cancelled"
            category.sold_count = max(
                0, category.sold_count - quantity
            )
            payment.status = "refunded"
            self.db.commit()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "TicketAgent communication is unavailable."}
            )

        ticket_message = AgentMessageSchema(
            sender=self.agent_name,
            receiver="TicketAgent",
            performative=Performative.REQUEST,
            content={
                "action": "ISSUE_TICKETS",
                "booking_id": booking.id,
                "event_id": event_id,
                "quantity": quantity
            },
            conversation_id=message.conversation_id
        )

        ticket_response = self.message_bus.send(ticket_message)

        if (
            ticket_response is None
            or ticket_response.performative != Performative.AGREE
        ):
            booking.status = "cancelled"
            category.sold_count = max(
                0, category.sold_count - quantity
            )
            payment.status = "refunded"
            self.db.commit()

            return self.create_response(
                message,
                Performative.FAILURE,
                {
                    "reason": "Ticket issuance failed. Booking cancelled and simulated payment refunded.",
                    "booking_id": booking.id
                }
            )

        
        # Notify attendee about successful booking
        notification_message = AgentMessageSchema(
            sender=self.agent_name,
            receiver="NotificationAgent",
            performative=Performative.INFORM,
            content={
                "action": "BOOKING_CONFIRMED",
                "attendee_id": attendee_id,
                "booking_id": booking.id,
                "event_id": event_id,
                "quantity": quantity
            },
            conversation_id=message.conversation_id
        )

        self.message_bus.send(notification_message)


        # Booking and ticket issuance successful
        return self.create_response(
            message,
            Performative.AGREE,
            {
                "booking_id": booking.id,
                "quantity": quantity,
                "total_amount": total_amount,
                "payment_reference": payment_reference,
                "status": "confirmed",
                "ticket_response": ticket_response.content,
                "message": "Booking and ticket issuance completed successfully."
            }
        )

    
    # Complete a booking using an already reserved waitlist seat
    def claim_waitlist_offer(self, message):

        content = message.content

        entry_id = content["entry_id"]
        attendee_id = content["attendee_id"]
        event_id = content["event_id"]
        category_id = content["ticket_category_id"]

        if not self.message_bus:
            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Agent communication is unavailable."}
            )

        entry = self.db.query(WaitlistEntry).filter(
            WaitlistEntry.id == entry_id,
            WaitlistEntry.attendee_id == attendee_id,
            WaitlistEntry.event_id == event_id,
            WaitlistEntry.ticket_category_id == category_id
        ).with_for_update().first()

        if not entry or entry.status != "offered":
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "No valid waitlist offer found."}
            )

        if (
            not entry.hold_expires_at
            or entry.hold_expires_at <= datetime.utcnow()
        ):
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Waitlist offer has expired."}
            )

        event = self.db.query(Event).filter(
            Event.id == event_id,
            Event.status == "published"
        ).first()

        category = self.db.query(TicketCategory).filter(
            TicketCategory.id == category_id,
            TicketCategory.event_id == event_id
        ).first()

        if not event or not category:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Event or ticket category not found."}
            )

        # The seat was already reserved by WaitlistAgent.
        # Do NOT increase category.sold_count again.

        try:
            total_amount = category.price

            booking = Booking(
                attendee_id=attendee_id,
                event_id=event_id,
                ticket_category_id=category_id,
                quantity=1,
                total_amount=total_amount,
                status="confirmed"
            )

            self.db.add(booking)
            self.db.flush()

            payment_reference = "PAY-" + str(uuid4())

            payment = Payment(
                booking_id=booking.id,
                amount=total_amount,
                payment_reference=payment_reference,
                status="completed"
            )

            self.db.add(payment)
            self.db.commit()
            self.db.refresh(booking)

        except Exception:
            self.db.rollback()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Waitlist booking creation failed."}
            )

        # Request QR ticket from TicketAgent
        ticket_message = AgentMessageSchema(
            sender=self.agent_name,
            receiver="TicketAgent",
            performative=Performative.REQUEST,
            content={
                "action": "ISSUE_TICKETS",
                "booking_id": booking.id,
                "event_id": event_id,
                "quantity": 1
            },
            conversation_id=message.conversation_id
        )

        ticket_response = self.message_bus.send(ticket_message)

        if (
            ticket_response is None
            or ticket_response.performative != Performative.AGREE
        ):
            booking.status = "cancelled"
            category.sold_count = max(
                0, category.sold_count - 1
            )
            payment.status = "refunded"
            self.db.commit()

            return self.create_response(
                message,
                Performative.FAILURE,
                {
                    "reason": "Ticket issuance failed. Reserved seat released.",
                    "booking_id": booking.id
                }
            )

        # Notify attendee
        notification_message = AgentMessageSchema(
            sender=self.agent_name,
            receiver="NotificationAgent",
            performative=Performative.INFORM,
            content={
                "action": "BOOKING_CONFIRMED",
                "attendee_id": attendee_id,
                "booking_id": booking.id,
                "event_id": event_id,
                "quantity": 1
            },
            conversation_id=message.conversation_id
        )

        self.message_bus.send(notification_message)

        return self.create_response(
            message,
            Performative.AGREE,
            {
                "booking_id": booking.id,
                "quantity": 1,
                "total_amount": total_amount,
                "payment_reference": payment_reference,
                "status": "confirmed",
                "ticket_response": ticket_response.content,
                "message": "Waitlist offer successfully converted into a booking."
            }
        )




    # Calculate cancellation refund
    def cancel_booking(self, message):

        content = message.content
        booking_id = content["booking_id"]
        event_cancelled = content.get("event_cancelled", False)

        booking = self.db.query(Booking).filter(
            Booking.id == booking_id
        ).with_for_update().first()

        if not booking:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Booking not found."}
            )

        if booking.status == "cancelled":
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Booking is already cancelled."}
            )

        # Full refund for cancelled events
        if event_cancelled:
            refund_percentage = 100

        else:
            event = self.db.query(Event).filter(
                Event.id == booking.event_id
            ).first()

            if not event or event.start_time <= datetime.now():
                return self.create_response(
                    message,
                    Performative.REFUSE,
                    {"reason": "Cancellation is not permitted."}
                )

            hours_remaining = (
                event.start_time - datetime.now()
            ).total_seconds() / 3600

            # Example refund policy:
            # 24 hours or more: 100%
            # Less than 24 hours: 50%
            refund_percentage = (
                100 if hours_remaining >= 24 else 50
            )

        refund_amount = (
            booking.total_amount * refund_percentage / 100
        )

        try:
            booking.status = "cancelled"

            category = self.db.query(TicketCategory).filter(
                TicketCategory.id == booking.ticket_category_id
            ).first()

            if category:
                category.sold_count = max(
                    0, category.sold_count - booking.quantity
                )

            payment = self.db.query(Payment).filter(
                Payment.booking_id == booking.id
            ).first()

            if payment:
                payment.status = "refunded"

            self.db.commit()

        except Exception:
            self.db.rollback()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Cancellation failed."}
            )

        # Inform other agents about freed seats
        if self.message_bus:

            for receiver in ["TicketAgent", "WaitlistAgent",
                             "NotificationAgent"]:

                notification = AgentMessageSchema(
                    sender=self.agent_name,
                    receiver=receiver,
                    performative=Performative.INFORM,
                    content={
                        "action": "BOOKING_CANCELLED",
                        "booking_id": booking_id,
                        "event_id": booking.event_id,
                        "attendee_id": booking.attendee_id,
                        "quantity": booking.quantity,
                        "refund_amount": refund_amount
                    },
                    conversation_id=message.conversation_id
                )

                self.message_bus.send(notification)

        return self.create_response(
            message,
            Performative.AGREE,
            {
                "booking_id": booking_id,
                "refund_percentage": refund_percentage,
                "refund_amount": refund_amount,
                "status": "cancelled"
            }
        )

    # Main message handler
    def handle_message(self, message):

        try:
            if message.performative == Performative.REQUEST:

                action = message.content.get("action")

                if action == "BOOK_TICKETS":
                    return self.book_tickets(message)

                elif action == "CANCEL_BOOKING":
                    return self.cancel_booking(message)

                elif action == "CLAIM_WAITLIST_OFFER":
                    return self.claim_waitlist_offer(message)

                return self.create_response(
                    message,
                    Performative.REFUSE,
                    {"reason": "Unknown booking action."}
                )

            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "BookingAgent expects REQUEST messages."}
            )

        except (KeyError, ValueError, TypeError) as error:

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": f"Invalid request: {str(error)}"}
            )
