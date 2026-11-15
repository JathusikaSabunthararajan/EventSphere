
from datetime import datetime, timedelta
from math import ceil

from sqlalchemy.orm import Session

from app.models.models import Venue, Event, VenueHireRequest
from app.messaging.message import AgentMessageSchema, Performative


class VenueAgent:

    def __init__(self, db: Session):
        self.agent_name = "VenueAgent"
        self.db = db

        # 30-minute turnaround buffer between activities
        self.turnaround_minutes = 30

    # Create a response message
    def create_response(self, original_message, performative, content):

        return AgentMessageSchema(
            sender=self.agent_name,
            receiver=original_message.sender,
            performative=performative,
            content=content,
            conversation_id=original_message.conversation_id
        )

    # Check whether a venue is available
    def is_slot_available(self, venue_id, start_time, end_time):

        buffer = timedelta(minutes=self.turnaround_minutes)

        buffered_start = start_time - buffer
        buffered_end = end_time + buffer

        # Check existing events
        existing_events = self.db.query(Event).filter(
            Event.venue_id == venue_id,
            Event.status != "cancelled",
            Event.start_time < buffered_end,
            Event.end_time > buffered_start
        ).first()

        if existing_events:
            return False

        # Check existing private venue bookings
        existing_hire = self.db.query(VenueHireRequest).filter(
            VenueHireRequest.venue_id == venue_id,
            VenueHireRequest.status.in_(["pending", "confirmed", "approved"]),
            VenueHireRequest.start_time < buffered_end,
            VenueHireRequest.end_time > buffered_start
        ).first()

        if existing_hire:
            return False

        return True

    # Find alternative venues and times
    def find_alternatives(
        self, venue_id, start_time, end_time, guest_count
    ):

        alternatives = []

        duration = end_time - start_time

        # Check other suitable venues
        venues = self.db.query(Venue).filter(
            Venue.id != venue_id,
            Venue.is_open_for_private_hire == True,
            Venue.capacity >= guest_count
        ).all()

        for venue in venues:

            if self.is_slot_available(
                venue.id, start_time, end_time
            ):
                alternatives.append({
                    "venue_id": venue.id,
                    "venue_name": venue.name,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat()
                })

        # Check alternative dates for the requested venue
        for days in [1, 2, 3]:

            alternative_start = start_time + timedelta(days=days)
            alternative_end = alternative_start + duration

            if self.is_slot_available(
                venue_id, alternative_start, alternative_end
            ):
                alternatives.append({
                    "venue_id": venue_id,
                    "venue_name": "Requested venue",
                    "start_time": alternative_start.isoformat(),
                    "end_time": alternative_end.isoformat()
                })

        return alternatives

    # Process event scheduling requests
    def check_event_slot(self, message):

        content = message.content

        venue_id = content["venue_id"]
        start_time = datetime.fromisoformat(content["start_time"])
        end_time = datetime.fromisoformat(content["end_time"])

        venue = self.db.query(Venue).filter(
            Venue.id == venue_id
        ).first()

        if not venue:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Venue does not exist."}
            )

        if end_time <= start_time:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Invalid event time range."}
            )

        if self.is_slot_available(
            venue_id, start_time, end_time
        ):
            return self.create_response(
                message,
                Performative.AGREE,
                {
                    "reason": "Venue slot is available.",
                    "venue_id": venue_id
                }
            )

        alternatives = self.find_alternatives(
            venue_id, start_time, end_time, 0
        )

        return self.create_response(
            message,
            Performative.PROPOSE,
            {
                "reason": "Venue schedule conflict detected.",
                "alternatives": alternatives
            }
        )

    # Process private venue hire requests
    def request_private_hire(self, message):

        content = message.content

        venue_id = content["venue_id"]
        attendee_id = content["attendee_id"]
        start_time = datetime.fromisoformat(content["start_time"])
        end_time = datetime.fromisoformat(content["end_time"])

        purpose = content["purpose"]
        guest_count = content["guest_count"]

        venue = self.db.query(Venue).filter(
            Venue.id == venue_id
        ).first()

        if not venue:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Venue does not exist."}
            )

        if not venue.is_open_for_private_hire:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Venue is not open for private hire."}
            )

        if end_time <= start_time or guest_count <= 0:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Invalid booking details."}
            )

        if guest_count > venue.capacity:
            return self.create_response(
                message,
                Performative.REFUSE,
                {
                    "reason": "Guest count exceeds venue capacity.",
                    "capacity": venue.capacity
                }
            )

        if not self.is_slot_available(
            venue_id, start_time, end_time
        ):

            alternatives = self.find_alternatives(
                venue_id,
                start_time,
                end_time,
                guest_count
            )

            return self.create_response(
                message,
                Performative.PROPOSE,
                {
                    "reason": "Requested venue or time is unavailable.",
                    "alternatives": alternatives
                }
            )

        # Calculate venue hire price
        duration = (end_time - start_time).total_seconds() / 3600

        total_price = (
            ceil(duration) * venue.hourly_hire_rate
        )

        # Check whether admin approval is required
        if content.get("requires_admin_review", False):
            booking_status = "pending"
            decision = Performative.PROPOSE
            reason = "Request escalated for admin approval."
        else:
            booking_status = "confirmed"
            decision = Performative.AGREE
            reason = "Private venue hire confirmed automatically."

        # Save the hire request
        hire_request = VenueHireRequest(
            attendee_id=attendee_id,
            venue_id=venue_id,
            start_time=start_time,
            end_time=end_time,
            purpose=purpose,
            guest_count=guest_count,
            estimated_price=total_price,
            status=booking_status
        )

        self.db.add(hire_request)
        self.db.commit()
        self.db.refresh(hire_request)

        return self.create_response(
            message,
            decision,
            {
                "hire_request_id": hire_request.id,
                "venue": venue.name,
                "estimated_price": total_price,
                "status": booking_status,
                "reason": reason
            }
        )

    # Main message handler
    def handle_message(self, message):

        if message.performative != Performative.REQUEST:
            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "VenueAgent expects a REQUEST message."}
            )

        action = message.content.get("action")

        try:
            if action == "CHECK_EVENT_SLOT":
                return self.check_event_slot(message)

            elif action == "PRIVATE_HIRE_REQUEST":
                return self.request_private_hire(message)

            return self.create_response(
                message,
                Performative.REFUSE,
                {"reason": "Unknown request action."}
            )

        except (KeyError, ValueError, TypeError) as error:
            return self.create_response(
                message,
                Performative.FAILURE,
                {"reason": f"Invalid request data: {str(error)}"}
            )
