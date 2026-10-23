
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RatingCreate(BaseModel):
    restaurant_rating: int = Field(ge=1, le=5)
    partner_rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class RatingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    restaurant_id: int
    customer_id: int
    restaurant_rating: int
    partner_rating: int
    comment: str | None
    created_at: datetime


class RestaurantRatingsResponse(BaseModel):
    restaurant_id: int
    average_rating: float
    total_ratings: int
    ratings: list[RatingResponse]
