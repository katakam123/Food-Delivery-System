
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeliveryOffer(Base):
    __tablename__ = "delivery_offers"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "partner_id",
            name="uq_delivery_offer_order_partner",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    partner_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_partners.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), default="Pending", nullable=False, index=True
    )
    offered_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
