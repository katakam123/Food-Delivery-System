
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint("item_total >= 0", name="ck_order_item_total"),
        CheckConstraint("discount_amount >= 0", name="ck_order_discount"),
        CheckConstraint("grand_total >= 0", name="ck_order_grand_total"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # A temporary unique number is replaced after the order receives its ID.
    order_number: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False, index=True
    )

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id"), nullable=False, index=True
    )
    address_id: Mapped[int] = mapped_column(
        ForeignKey("addresses.id"), nullable=False
    )
    delivery_partner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    item_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    coupon_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    packaging_charges: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    delivery_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    platform_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tip_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    grand_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_status: Mapped[str] = mapped_column(
        String(20), default="Pending", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="Placed", nullable=False, index=True
    )

    distance_km: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    delivery_otp: Mapped[str] = mapped_column(String(4), nullable=False)

    placed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusHistory.changed_at",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    __table_args__ = (
        UniqueConstraint(
            "order_id", "menu_item_id", name="uq_order_item_menu_item"
        ),
        CheckConstraint("quantity >= 1", name="ck_order_item_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_order_item_unit_price"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    menu_item_id: Mapped[int] = mapped_column(
        ForeignKey("menu_items.id"), nullable=False
    )

    # Snapshot fields: later menu changes must not alter an old bill.
    item_name: Mapped[str] = mapped_column(String(150), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    packaging_charge: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), default=Decimal("0.00"), nullable=False
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship()

estimated_preparation_minutes: Mapped[int | None] = mapped_column(
    Integer, nullable=True
)

rejection_reason: Mapped[str | None] = mapped_column(
    String(500), nullable=True
)

otp_failed_attempts: Mapped[int] = mapped_column(
    Integer, default=0, nullable=False
)

delivery_locked: Mapped[bool] = mapped_column(
    Boolean, default=False, nullable=False
)

picked_up_at: Mapped[datetime | None] = mapped_column(
    DateTime, nullable=True
)

out_for_delivery_at: Mapped[datetime | None] = mapped_column(
    DateTime, nullable=True
)