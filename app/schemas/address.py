from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AddressCreate(BaseModel):
    label: Literal["Home", "Work", "Other"] = "Home"
    address_line: str = Field(min_length=5, max_length=255)
    city: str = Field(min_length=2, max_length=100)
    pincode: str = Field(min_length=4, max_length=10)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    is_default: bool = False


class AddressUpdate(BaseModel):
    label: Literal["Home", "Work", "Other"] | None = None
    address_line: str | None = Field(
        default=None, min_length=5, max_length=255
    )
    city: str | None = Field(
        default=None, min_length=2, max_length=100
    )
    pincode: str | None = Field(
        default=None, min_length=4, max_length=10
    )
    latitude: float | None = Field(
        default=None, ge=-90, le=90
    )
    longitude: float | None = Field(
        default=None, ge=-180, le=180
    )


class AddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    label: str
    address_line: str
    city: str
    pincode: str
    latitude: float
    longitude: float
    is_default: bool
    created_at: datetime
    updated_at: datetime

from app.utils.validators import PhoneNumber, Pincode

phone: PhoneNumber
pincode: Pincode