
from sqlalchemy.orm import Session

from app.models.models import Notification
from app.messaging.message import (
    AgentMessageSchema,
    Performative
)


class NotificationAgent:

    def __init__(self, db: Session):
        self.agent_name = "NotificationAgent"
        self.db = db

    # Create response message
    def create_response(self, original_message, performative, content):

        return AgentMessageSchema(
            sender=self.agent_name,
            receiver=original_message.sender,
            performative=performative,
            content=content,
            conversation_id=original_message.conversation_id
        )

    # Convert agent events into user notifications
    def create_notification(self, message):

        content = message.content

        attendee_id = content.get("attendee_id")

        if not attendee_id:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Attendee ID is missing."}
            )

        action = content.get("action")

        notification_details = {

            "BOOKING_CONFIRMED": (
                "Booking Confirmed",
                "Your event booking has been confirmed.",
                "booking"
            ),

            "TICKET_ISSUED": (
                "Digital Ticket Issued",
                "Your digital ticket is ready.",
                "ticket"
            ),

            "BOOKING_CANCELLED": (
                "Booking Cancelled",
                "Your booking has been cancelled. Check your refund details.",
                "booking"
            ),

            "WAITLIST_OFFER": (
                "Ticket Available",
                "A ticket is available for you. Please claim it before the expiry time.",
                "waitlist"
            ),

            "VENUE_HIRE_CONFIRMED": (
                "Venue Hire Confirmed",
                "Your private venue hire request has been confirmed.",
                "venue"
            ),

            "VENUE_HIRE_PENDING": (
                "Venue Hire Pending",
                "Your venue hire request is waiting for admin approval.",
                "venue"
            )
        }

        if action not in notification_details:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Unknown notification event."}
            )

        title, notification_message, notification_type = (
            notification_details[action]
        )

        # Add event details where available
        if content.get("event_id"):
            notification_message += (
                f" Event ID: {content['event_id']}."
            )

        try:
            notification = Notification(
                user_id=attendee_id,
                title=title,
                message=notification_message,
                notification_type=notification_type
            )

            self.db.add(notification)
            self.db.commit()
            self.db.refresh(notification)

            return self.create_response(
                message,
                Performative.AGREE,
                {
                    "notification_id": notification.id,
                    "attendee_id": attendee_id,
                    "title": title,
                    "message": notification_message,
                    "status": "saved"
                }
            )

        except Exception:

            self.db.rollback()

            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": "Notification could not be saved."}
            )

    # Handle messages from other agents
    def handle_message(self, message):

        if message.performative not in [
            Performative.INFORM,
            Performative.REQUEST
        ]:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Unsupported notification message."}
            )

        return self.create_notification(message)

    # Retrieve notifications for an attendee
    def get_user_notifications(self, attendee_id):

        notifications = self.db.query(Notification).filter(
            Notification.user_id == attendee_id
        ).order_by(
            Notification.created_at.desc()
        ).all()

        return [
            {
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "type": item.notification_type,
                "is_read": item.is_read,
                "created_at": item.created_at.isoformat()
            }
            for item in notifications
        ]
