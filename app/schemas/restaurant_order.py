
from pydantic import BaseModel, Field


class AcceptOrderRequest(BaseModel):
    estimated_preparation_minutes: int = Field(ge=1, le=600)


class RejectOrderRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
