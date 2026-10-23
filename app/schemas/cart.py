
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class CartItemAdd(BaseModel):
    menu_item_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=10)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, le=10)


class CartLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    name: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    is_veg: bool


class CartResponse(BaseModel):
    id: int
    customer_id: int
    restaurant_id: int | None
    items: list[CartLineResponse]
    item_total: Decimal
    applied_coupon: str | None
    discount: Decimal
    total_after_discount: Decimal
    created_at: datetime
    updated_at: datetime
