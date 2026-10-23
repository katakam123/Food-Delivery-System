from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    cuisine_type: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=5, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    opening_time: time = time(9, 0)
    closing_time: time = time(22, 0)
    delivery_radius_km: float = Field(default=5.0, gt=0, le=100)
    min_order_value: Decimal = Field(default=Decimal("0"), ge=0)
    avg_preparation_minutes: int = Field(default=30, ge=1, le=360)
    description: str | None = None
    phone: str | None = None


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    cuisine_type: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = None
    phone: str | None = None
    address: str | None = Field(default=None, min_length=5, max_length=255)
    city: str | None = Field(default=None, min_length=2, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    opening_time: time | None = None
    closing_time: time | None = None
    delivery_radius_km: float | None = Field(default=None, gt=0, le=100)
    min_order_value: Decimal | None = Field(default=None, ge=0)
    avg_preparation_minutes: int | None = Field(default=None, ge=1, le=360)
    is_active: bool | None = None


class OpenStatusUpdate(BaseModel):
    is_temporarily_closed: bool


class RestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    cuisine_type: str
    description: str | None
    phone: str | None
    address: str
    city: str
    latitude: float
    longitude: float
    opening_time: time
    closing_time: time
    is_temporarily_closed: bool
    delivery_radius_km: float
    min_order_value: Decimal
    avg_preparation_minutes: int
    average_rating: float
    is_active: bool
    is_open: bool
    created_at: datetime
    updated_at: datetime
class NearbyRestaurantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    cuisine_type: str
    address: str
    city: str
    latitude: float
    longitude: float
    delivery_radius_km: float
    avg_preparation_minutes: int
    average_rating: float
    is_open: bool
    distance_km: float
    estimated_delivery_minutes: int

    
from datetime import time

from pydantic import model_validator


# Add this method inside your existing RestaurantCreate class.
@model_validator(mode="after")
def validate_opening_hours(self):
    if self.opening_time >= self.closing_time:
        raise ValueError(
            "Opening time must be before closing time"
        )
    return self
