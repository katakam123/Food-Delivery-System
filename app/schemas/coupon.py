from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CouponCreate(BaseModel):
    code: str = Field(min_length=3, max_length=50)
    description: str | None = Field(default=None, max_length=255)
    discount_type: Literal["Percentage", "Flat"]
    discount_value: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    max_discount: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    min_order_value: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
    )
    restaurant_id: int | None = Field(default=None, gt=0)
    valid_from: datetime
    valid_to: datetime
    total_usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int = Field(default=1, ge=1)
    first_order_only: bool = False

    @model_validator(mode="after")
    def validate_coupon(self):
        self.code = self.code.strip().upper()

        if not self.code or not self.code.replace("_", "").isalnum():
            raise ValueError(
                "Coupon code can contain only letters, numbers, and underscores"
            )

        if self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be later than valid_from")

        if self.discount_type == "Percentage":
            if self.discount_value > 100:
                raise ValueError("Percentage discount cannot exceed 100")
        elif self.max_discount is not None:
            raise ValueError(
                "max_discount is only applicable to Percentage coupons"
            )

        return self


class CouponUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    discount_type: Literal["Percentage", "Flat"] | None = None
    discount_value: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    max_discount: Decimal | None = Field(
        default=None, gt=0, max_digits=10, decimal_places=2
    )
    min_order_value: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    total_usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, ge=1)
    first_order_only: bool | None = None

    @model_validator(mode="after")
    def validate_dates_and_discount(self):
        if self.valid_from and self.valid_to:
            if self.valid_to <= self.valid_from:
                raise ValueError("valid_to must be later than valid_from")

        if self.discount_type == "Percentage":
            if self.discount_value is not None and self.discount_value > 100:
                raise ValueError("Percentage discount cannot exceed 100")

        if self.discount_type == "Flat" and self.max_discount is not None:
            raise ValueError(
                "max_discount is only applicable to Percentage coupons"
            )

        return self


class CouponResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    description: str | None
    discount_type: str
    discount_value: Decimal
    max_discount: Decimal | None
    min_order_value: Decimal
    restaurant_id: int | None
    valid_from: datetime
    valid_to: datetime
    total_usage_limit: int | None
    per_user_limit: int
    first_order_only: bool
    created_by: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AvailableCouponResponse(CouponResponse):
    discount_you_get: Decimal


class ApplyCouponRequest(BaseModel):
    code: str = Field(min_length=3, max_length=50)


from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class CouponValidationMixin(BaseModel):
    discount_type: str
    discount_value: float = Field(gt=0)
    valid_from: datetime
    valid_to: datetime

    @model_validator(mode="after")
    def validate_coupon_rules(self):
        if self.discount_type not in ("Percentage", "Flat"):
            raise ValueError(
                "discount_type must be Percentage or Flat"
            )

        if self.discount_type == "Percentage":
            if not 1 <= self.discount_value <= 100:
                raise ValueError(
                    "Percentage discount must be between 1 and 100"
                )

        if self.valid_to <= self.valid_from:
            raise ValueError(
                "valid_to must be after valid_from"
            )

        return self
