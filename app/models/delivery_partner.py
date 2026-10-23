
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DeliveryPartner(Base):
    __tablename__ = "delivery_partners"

    __table_args__ = (
        CheckConstraint(
            "current_latitude IS NULL OR "
            "(current_latitude >= -90 AND current_latitude <= 90)",
            name="ck_partner_latitude",
        ),
        CheckConstraint(
            "current_longitude IS NULL OR "
            "(current_longitude >= -180 AND current_longitude <= 180)",
            name="ck_partner_longitude",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    vehicle_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle_number: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )

    is_online: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    current_latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7), nullable=True
    )
    current_longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 7), nullable=True
    )
    last_location_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    is_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    user = relationship("User")
