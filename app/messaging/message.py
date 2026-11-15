
from pydantic import BaseModel, Field
from enum import Enum
from typing import Any
from uuid import uuid4


# Supported communication performatives
class Performative(str, Enum):
    REQUEST = "REQUEST"
    AGREE = "AGREE"
    REFUSE = "REFUSE"
    PROPOSE = "PROPOSE"
    INFORM = "INFORM"
    FAILURE = "FAILURE"


# Structured JSON message
class AgentMessageSchema(BaseModel):

    sender: str
    receiver: str
    performative: Performative
    content: dict[str, Any] = Field(default_factory=dict)

    conversation_id: str = Field(
        default_factory=lambda: str(uuid4())
    )
