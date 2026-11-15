
from pydantic import BaseModel, Field


class TicketCategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)
