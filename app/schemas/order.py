
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    address_id: int = Field(gt=0)
    payment_method: Literal["COD", "Online"]
    tip_amount: Decimal = Field(default=Decimal("0.00"), ge=0, le=10000)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int
    item_name: str
    quantity: int
    unit_price: Decimal
    packaging_charge: Decimal
    line_total: Decimal


class OrderStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    old_status: str | None
    new_status: str
    changed_by: int | None
    changed_at: datetime


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    customer_id: int
    restaurant_id: int
    address_id: int
    delivery_partner_id: int | None

    item_total: Decimal
    coupon_code: str | None
    discount_amount: Decimal
    packaging_charges: Decimal
    delivery_fee: Decimal
    platform_fee: Decimal
    gst_amount: Decimal
    tip_amount: Decimal
    grand_total: Decimal

    payment_method: str
    payment_status: str
    status: str
    distance_km: Decimal
    placed_at: datetime
    delivered_at: datetime | None

    items: list[OrderItemResponse] = Field(default_factory=list)
    status_history: list[OrderStatusHistoryResponse] = Field(
        default_factory=list
    )
    estimated_preparation_minutes: int | None = None
    rejection_reason: str | None = None

class OrderCreatedResponse(OrderResponse):
    # Return the OTP only in the customer's order-creation response.
    delivery_otp: str


class OrderCancelResponse(BaseModel):
    message: str
    order_id: int
    order_number: str
    status: str
    payment_status: str


class ReorderResponse(BaseModel):
    message: str
    order_id: int
    added_items: int
    skipped_items: list[str]
