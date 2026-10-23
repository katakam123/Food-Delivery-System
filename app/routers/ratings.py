
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import Order, Rating, Restaurant
from app.schemas.rating import (
    RatingCreate,
    RatingResponse,
    RestaurantRatingsResponse,
)

router = APIRouter(tags=["Ratings"])


@router.post(
    "/orders/{order_id}/rating",
    response_model=RatingResponse,
    status_code=201,
)
def create_order_rating(
    order_id: int,
    payload: RatingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    # Only the customer who placed the order may rate it.
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    if order.customer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only rate your own orders",
        )

    if order.status != "Delivered":
        raise HTTPException(
            status_code=400,
            detail="Only Delivered orders can be rated",
        )

    existing_rating = (
        db.query(Rating)
        .filter(Rating.order_id == order_id)
        .first()
    )

    if existing_rating:
        raise HTTPException(
            status_code=409,
            detail="This order has already been rated",
        )

    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == order.restaurant_id)
        .first()
    )

    if restaurant is None:
        raise HTTPException(
            status_code=404,
            detail="Restaurant not found",
        )

    rating = Rating(
        order_id=order.id,
        restaurant_id=order.restaurant_id,
        customer_id=current_user.id,
        restaurant_rating=payload.restaurant_rating,
        partner_rating=payload.partner_rating,
        comment=payload.comment.strip() if payload.comment else None,
    )

    try:
        db.add(rating)
        db.flush()

        # Recalculate the average using all restaurant ratings.
        average = (
            db.query(func.avg(Rating.restaurant_rating))
            .filter(Rating.restaurant_id == restaurant.id)
            .scalar()
        )

        restaurant.average_rating = (
            round(float(average), 2) if average is not None else 0.0
        )

        db.commit()
        db.refresh(rating)

        return rating

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This order has already been rated",
        )
    except Exception:
        db.rollback()
        raise


@router.get(
    "/restaurants/{restaurant_id}/ratings",
    response_model=RestaurantRatingsResponse,
)
def get_restaurant_ratings(
    restaurant_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == restaurant_id)
        .first()
    )

    if restaurant is None:
        raise HTTPException(
            status_code=404,
            detail="Restaurant not found",
        )

    total_ratings = (
        db.query(func.count(Rating.id))
        .filter(Rating.restaurant_id == restaurant_id)
        .scalar()
    ) or 0

    average = (
        db.query(func.avg(Rating.restaurant_rating))
        .filter(Rating.restaurant_id == restaurant_id)
        .scalar()
    )

    ratings = (
        db.query(Rating)
        .filter(Rating.restaurant_id == restaurant_id)
        .order_by(Rating.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return RestaurantRatingsResponse(
        restaurant_id=restaurant_id,
        average_rating=(
            round(float(average), 2) if average is not None else 0.0
        ),
        total_ratings=total_ratings,
        ratings=ratings,
    )
