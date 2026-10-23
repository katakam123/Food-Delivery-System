import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.address import Address
from app.models.restaurant import Restaurant
from app.schemas.address import (
    AddressCreate,
    AddressUpdate,
    AddressResponse,
)
from app.schemas.restaurant import NearbyRestaurantResponse
from app.utils.geo import haversine_distance_km
from datetime import datetime
from sqlalchemy import exists, func
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException, Query

from app.models import Restaurant, MenuItem, Coupon

router = APIRouter(tags=["Addresses & Nearby Restaurants"])


def require_customer(user: User) -> None:
    if user.role != "Customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only customers can manage delivery addresses",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is inactive",
        )


def get_customer_address(
    address_id: int,
    user: User,
    db: Session,
) -> Address:
    address = db.get(Address, address_id)

    if address is None or address.customer_id != user.id:
        # Avoid revealing whether another customer's address exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found",
        )

    return address


def make_default_address(
    db: Session,
    customer_id: int,
    address_id: int,
) -> None:
    """Ensure the selected address is the customer's only default."""
    db.query(Address).filter(
        Address.customer_id == customer_id,
        Address.is_default.is_(True),
    ).update(
        {Address.is_default: False},
        synchronize_session=False,
    )

    address = db.get(Address, address_id)
    if address is None:
        raise HTTPException(404, "Address not found")

    address.is_default = True


@router.get(
    "/restaurants/nearby",
    response_model=list[NearbyRestaurantResponse],
)
def nearby_restaurants(
    latitude: float = Query(..., ge=-90, le=90),
    longitude: float = Query(..., ge=-180, le=180),
    db: Session = Depends(get_db),
):
    """Return open restaurants within their own delivery radius."""
    restaurants = (
        db.query(Restaurant)
        .filter(
            Restaurant.is_active.is_(True),
            Restaurant.is_temporarily_closed.is_(False),
        )
        .all()
    )

    results = []

    for restaurant in restaurants:
        distance = haversine_distance_km(
            latitude,
            longitude,
            restaurant.latitude,
            restaurant.longitude,
        )

        # Check each restaurant's individual delivery radius.
        if distance > restaurant.delivery_radius_km:
            continue

        # The model's is_open property also checks its opening hours.
        if not restaurant.is_open:
            continue

        travel_minutes = math.ceil((distance / 20.0) * 60)

        results.append(
            {
                "id": restaurant.id,
                "owner_id": restaurant.owner_id,
                "name": restaurant.name,
                "cuisine_type": restaurant.cuisine_type,
                "address": restaurant.address,
                "city": restaurant.city,
                "latitude": restaurant.latitude,
                "longitude": restaurant.longitude,
                "delivery_radius_km": restaurant.delivery_radius_km,
                "avg_preparation_minutes": (
                    restaurant.avg_preparation_minutes
                ),
                "average_rating": restaurant.average_rating,
                "is_open": restaurant.is_open,
                "distance_km": distance,
                "estimated_delivery_minutes": (
                    restaurant.avg_preparation_minutes + travel_minutes
                ),
            }
        )
        name: str | None = Query(default=None, min_length=1),
    cuisine_type: str | None = Query(default=None),
    veg_only: bool = Query(default=False),
    min_rating: float | None = Query(default=None, ge=0, le=5),
    has_offers: bool = Query(default=False),
    sort_by: str = Query(default="distance"),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    # Nearest restaurant first.
    results.sort(key=lambda item: item["distance_km"])

    return results


@router.post(
    "/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_address(
    payload: AddressCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)

    address_data = payload.model_dump()

    existing_count = (
        db.query(Address)
        .filter(Address.customer_id == user.id)
        .count()
    )

    # Make the first address the default automatically.
    should_be_default = payload.is_default or existing_count == 0

    if should_be_default:
        db.query(Address).filter(
            Address.customer_id == user.id,
            Address.is_default.is_(True),
        ).update(
            {Address.is_default: False},
            synchronize_session=False,
        )

    address_data["is_default"] = should_be_default

    address = Address(
        customer_id=user.id,
        **address_data,
    )

    db.add(address)
    db.commit()
    db.refresh(address)

    return address


@router.get("/addresses", response_model=list[AddressResponse])
def list_addresses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)

    return (
        db.query(Address)
        .filter(Address.customer_id == user.id)
        .order_by(Address.is_default.desc(), Address.id.asc())
        .all()
    )


@router.put(
    "/addresses/{address_id}",
    response_model=AddressResponse,
)
def update_address(
    address_id: int,
    payload: AddressUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)

    address = get_customer_address(address_id, user, db)
    updates = payload.model_dump(exclude_unset=True)

    # Do not allow explicit null values for required address fields.
    required_fields = {
        "label",
        "address_line",
        "city",
        "pincode",
        "latitude",
        "longitude",
    }

    for field, value in updates.items():
        if value is None and field in required_fields:
            raise HTTPException(
                status_code=422,
                detail=f"{field} cannot be null",
            )
        if value is not None:
            setattr(address, field, value)

    db.commit()
    db.refresh(address)

    return address


@router.delete("/addresses/{address_id}")
def delete_address(
    address_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)

    address = get_customer_address(address_id, user, db)
    was_default = address.is_default

    db.delete(address)
    db.flush()

    # If the default was deleted, promote another saved address.
    if was_default:
        replacement = (
            db.query(Address)
            .filter(Address.customer_id == user.id)
            .order_by(Address.id.asc())
            .first()
        )

        if replacement is not None:
            replacement.is_default = True

    db.commit()

    return {"message": "Address deleted successfully"}


@router.put(
    "/addresses/{address_id}/default",
    response_model=AddressResponse,
)
def set_default_address(
    address_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)

    address = get_customer_address(address_id, user, db)

    make_default_address(db, user.id, address.id)

    db.commit()
    db.refresh(address)

    return address