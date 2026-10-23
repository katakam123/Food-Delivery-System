from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    name: str
    is_active: bool


class MenuItemCreate(BaseModel):
    category_id: int
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None
    price: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    is_veg: bool = True
    packaging_charge: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
    )


class MenuItemUpdate(BaseModel):
    category_id: int | None = None
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
    price: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    is_veg: bool | None = None
    packaging_charge: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )


class AvailabilityUpdate(BaseModel):
    is_available: bool


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    restaurant_id: int
    category_id: int
    name: str
    description: str | None
    price: Decimal
    is_veg: bool
    packaging_charge: Decimal
    is_available: bool
    created_at: datetime
    updated_at: datetime