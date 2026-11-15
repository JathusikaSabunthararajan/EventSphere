
from pydantic import BaseModel, Field
from datetime import datetime


class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    category: str
    description: str
    venue_id: int
    start_time: datetime
    end_time: datetime
