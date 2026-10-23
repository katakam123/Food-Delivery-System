
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base



class MenuCategory(Base):
    __tablename__ = "menu_categories"

    __table_args__ = (
        UniqueConstraint(
            "restaurant_id",
            "name",
            name="uq_menu_category_restaurant_name",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )

    restaurant_id: Mapped[int] = mapped_column(
        ForeignKey("restaurants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    restaurant: Mapped["Restaurant"] = relationship(
        "Restaurant",
        back_populates="categories",
    )

    items: Mapped[list["MenuItem"]] = relationship(
        "MenuItem",
        back_populates="category",
    )
restaurant = relationship("Restaurant", back_populates="categories")
items = relationship("MenuItem", back_populates="category")