from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base



class Restaurant(Base):
    __tablename__ = "restaurants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    cuisine_type: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    opening_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(9, 0)
    )
    closing_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(22, 0)
    )
    is_temporarily_closed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    delivery_radius_km: Mapped[float] = mapped_column(
        Float, nullable=False, default=5.0
    )
    min_order_value: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )
    avg_preparation_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )
    average_rating: Mapped[float] = mapped_column(
        Float, nullable=False, default=0
    )

    # Retain the existing database column for migration compatibility.
    _legacy_is_open: Mapped[bool] = mapped_column(
        "is_open", Boolean, nullable=False, default=False
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

    owner: Mapped["User"] = relationship(
        "User", back_populates="restaurants"
    )
    categories: Mapped[list["MenuCategory"]] = relationship(
        "MenuCategory",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )
    menu_items: Mapped[list["MenuItem"]] = relationship(
        "MenuItem",
        back_populates="restaurant",
        cascade="all, delete-orphan",
    )

    @property
    def is_open(self) -> bool:
        """Calculate whether the restaurant is open at the current local time."""
        if not self.is_active or self.is_temporarily_closed:
            return False

        now = datetime.now().time()
        opening = self.opening_time
        closing = self.closing_time

        # Supports restaurants open past midnight.
        if opening <= closing:
            return opening <= now < closing

        return now >= opening or now < closing