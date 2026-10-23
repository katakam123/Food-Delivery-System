from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Coupon(Base):
    __tablename__ = "coupons"

    __table_args__ = (
        CheckConstraint(
            "discount_value > 0",
            name="ck_coupon_discount_positive",
        ),
        CheckConstraint(
            "min_order_value >= 0",
            name="ck_coupon_min_order_nonnegative",
        ),
        CheckConstraint(
            "total_usage_limit IS NULL OR total_usage_limit > 0",
            name="ck_coupon_total_limit_positive",
        ),
        CheckConstraint(
            "per_user_limit > 0",
            name="ck_coupon_per_user_limit_positive",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    # Stored uppercase so codes are case-insensitive.
    code: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )

    description: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    discount_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    max_discount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )

    min_order_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
    )

    restaurant_id: Mapped[int | None] = mapped_column(
        ForeignKey("restaurants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    valid_from: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )

    valid_to: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )

    total_usage_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    per_user_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    first_order_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )