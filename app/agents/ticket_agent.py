
import os
import secrets
import qrcode

from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.models import Ticket, Booking, Event
from app.messaging.message import (
    AgentMessageSchema,
    Performative
)


class TicketAgent:

    def __init__(self, db: Session,message_bus=None):
        self.agent_name = "TicketAgent"
        self.db = db
        self.message_bus = message_bus

        # Check-in opens 2 hours before event starts
        self.checkin_early_minutes = 120

    # Create response message
    def create_response(self, original_message, performative, content):

        return AgentMessageSchema(
            sender=self.agent_name,
            receiver=original_message.sender,
            performative=performative,
            content=content,
            conversation_id=original_message.conversation_id
        )

    # Generate a QR code image
    def generate_qr(self, ticket_code, ticket_id):

        folder = "static/images/tickets"
        os.makedirs(folder, exist_ok=True)

        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=4
        )

        qr.add_data(ticket_code)
        qr.make(fit=True)

        image = qr.make_image(
            fill_color="black",
            back_color="white"
        )

        file_path = os.path.join(
            folder, f"ticket_{ticket_id}.png"
        )

        image.save(file_path)

        return file_path


    # Issue unique tickets
    def issue_tickets(self, message):

        content = message.content

        booking_id = content["booking_id"]
        event_id = content["event_id"]
        quantity = content["quantity"]

        booking = self.db.query(Booking).filter(
            Booking.id == booking_id,
            Booking.event_id == event_id,
            Booking.status == "confirmed"
        ).first()

        if not booking or booking.quantity != quantity:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Valid confirmed booking not found."}
            )

        event = self.db.query(Event).filter(
            Event.id == event_id
        ).first()

        if not event:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Event not found."}
            )

        # Check whether tickets were already issued
        existing_tickets = self.db.query(Ticket).filter(
            Ticket.booking_id == booking_id
        ).all()

        if existing_tickets:
            if len(existing_tickets) == quantity:
                return self.create_response(
                    message,
                    Performative.AGREE,
                    {
                        "booking_id": booking_id,
                        "issued_count": len(existing_tickets),
                        "message": "Tickets were already issued.",
                        "tickets": [
                            {
                                "ticket_id": ticket.id,
                                "qr_code": ticket.qr_code
                            }
                            for ticket in existing_tickets
                        ]
                    }
                )

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Existing ticket count does not match booking quantity."}
            )

        try:
            issued_tickets = []

            for _ in range(quantity):

                ticket_code = secrets.token_urlsafe(32)

                ticket = Ticket(
                    booking_id=booking_id,
                    event_id=event_id,
                    qr_code=ticket_code,
                    status="valid"
                )

                self.db.add(ticket)
                self.db.flush()

                qr_path = self.generate_qr(
                    ticket_code, ticket.id
                )

                issued_tickets.append({
                    "ticket_id": ticket.id,
                    "qr_code": ticket_code,
                    "qr_image": qr_path
                })

            self.db.commit()

                        # Notify attendee that digital tickets are ready
            notification_message = AgentMessageSchema(
                sender=self.agent_name,
                receiver="NotificationAgent",
                performative=Performative.INFORM,
                content={
                    "action": "TICKET_ISSUED",
                    "attendee_id": booking.attendee_id,
                    "booking_id": booking_id,
                    "event_id": event_id,
                    "quantity": quantity
                },
                conversation_id=message.conversation_id
            )

            # Send notification through the message bus
            if hasattr(self, "message_bus") and self.message_bus:
                self.message_bus.send(notification_message)

            return self.create_response(
                message,
                Performative.AGREE,
                {
                    "booking_id": booking_id,
                    "issued_count": len(issued_tickets),
                    "tickets": issued_tickets
                }
            )

        except Exception as error:

            self.db.rollback()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": f"Ticket generation failed: {str(error)}"}
            )


    # Verify and check in a ticket
    def check_in(self, message):

        content = message.content

        ticket_code = content["qr_code"]
        requested_event_id = content["event_id"]


        ticket = self.db.query(Ticket).filter(
            Ticket.qr_code == ticket_code
        ).first()

        if not ticket:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Invalid ticket code."}
            )

        if ticket.event_id != requested_event_id:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Ticket belongs to another event."}
            )

        if ticket.status == "cancelled":
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "This ticket has been cancelled."}
            )

        if ticket.status != "valid":
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Ticket is not valid."}
            )

        if ticket.checked_in_at is not None:
            return self.create_response(
                message,
                Performative.REFUSE,
                {
                    "reason": "Ticket has already been used.",
                    "checked_in_at": ticket.checked_in_at.isoformat()
                }
            )

        event = self.db.query(Event).filter(
            Event.id == ticket.event_id
        ).first()

        if not event:
            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Associated event not found."}
            )

        now = datetime.now()

        checkin_open = (
            event.start_time - timedelta(
                minutes=self.checkin_early_minutes
            )
        )

        if now < checkin_open or now > event.end_time:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Outside the permitted check-in time."}
            )

        try:
            ticket.checked_in_at = now
            ticket.status = "used"

            self.db.commit()

            return self.create_response(
                message,
                Performative.AGREE,
                {
                    "reason": "Ticket admitted successfully.",
                    "ticket_id": ticket.id,
                    "event_id": ticket.event_id,
                    "checked_in_at": now.isoformat()
                }
            )

        except Exception:

            self.db.rollback()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Check-in could not be completed."}
            )

    # Handle booking cancellation notifications
    def handle_inform(self, message):

        content = message.content

        if content.get("action") == "BOOKING_CANCELLED":

            booking_id = content.get("booking_id")

            try:
                self.db.query(Ticket).filter(
                    Ticket.booking_id == booking_id,
                    Ticket.status == "valid"
                ).update(
                    {"status": "cancelled"},
                    synchronize_session=False
                )

                self.db.commit()

                return self.create_response(
                    message,
                    Performative.AGREE,
                    {
                        "reason": "Booking tickets cancelled.",
                        "booking_id": booking_id
                    }
                )

            except Exception:
                self.db.rollback()

                return self.create_response(
                    message,
                    Performative.FAILURE,
                    {"reason": "Ticket cancellation update failed."}
                )

        return self.create_response(
            message,
            Performative.REFUSE,
            {"reason": "Unknown notification."}
        )

    # Main message handler
    def handle_message(self, message):

        try:
            if message.performative == Performative.REQUEST:

                action = message.content.get("action")

                if action == "ISSUE_TICKETS":
                    return self.issue_tickets(message)

                elif action == "CHECK_IN":
                    return self.check_in(message)

                return self.create_response(
                    message,
                    Performative.REFUSE,
                    {"reason": "Unknown ticket action."}
                )

            elif message.performative == Performative.INFORM:
                return self.handle_inform(message)

            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Unsupported message performative."}
            )

        except (KeyError, ValueError, TypeError) as error:

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": f"Invalid request: {str(error)}"}
            )
