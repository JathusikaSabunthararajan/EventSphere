
from typing import Callable, Optional
from sqlalchemy.orm import Session

from app.messaging.message import AgentMessageSchema
from app.models.models import AgentMessage


class MessageBus:

    def __init__(self, db: Session):
        self.db = db
        self.handlers: dict[str, Callable] = {}

    # Register an agent with the message bus
    def register(self, agent_name: str, handler: Callable):
        self.handlers[agent_name] = handler

        print(f"{agent_name} registered successfully.")

    # Save and deliver a message
    def send(self, message: AgentMessageSchema):

        # 1. Save message in database
        message_record = AgentMessage(
            sender=message.sender,
            receiver=message.receiver,
            performative=message.performative.value,
            content=message.content,
            conversation_id=message.conversation_id
        )

        self.db.add(message_record)
        self.db.commit()
        self.db.refresh(message_record)

        print(
            f"Message: {message.sender} -> "
            f"{message.receiver} "
            f"[{message.performative.value}]"
        )

        # 2. Find the receiver
        receiver_handler = self.handlers.get(message.receiver)

        # 3. Deliver message to receiver
        if receiver_handler:
            return receiver_handler(message)

        print(
            f"Receiver {message.receiver} is not registered."
        )

        return None
