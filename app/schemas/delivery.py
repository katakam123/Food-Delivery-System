
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PartnerProfileCreate(BaseModel):
    vehicle_type: Literal["Bike", "Scooter", "Bicycle"]
    vehicle_number: str = Field(min_length=3, max_length=30)


class AvailabilityUpdate(BaseModel):
    is_online: bool


class LocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DeliveryOfferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    status: str
    offered_at: datetime
    expires_at: datetime


class DeliveryResult(BaseModel):
    message: str
    order_id: int
    status: str
    payment_status: str


class EarningsItem(BaseModel):
    order_id: int
    order_number: str
    delivered_at: datetime
    distance_km: Decimal
    base_amount: Decimal
    distance_amount: Decimal
    tip_amount: Decimal
    total_earnings: Decimal


class EarningsSummary(BaseModel):
    start_date: datetime
    end_date: datetime
    deliveries: int
    total_earnings: Decimal
    items: list[EarningsItem]

class DeliverRequest(BaseModel):
    otp: str = Field(pattern=r"^[0-9]{4}$")
