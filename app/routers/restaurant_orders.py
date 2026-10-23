
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models import (
    CouponUsage,
    Order,
    Restaurant,
)
from app.schemas.order import OrderResponse
from app.schemas.restaurant_order import (
    AcceptOrderRequest,
    RejectOrderRequest,
)
from app.services.orders import record_status_change
from app.websockets.events import publish_order_update

router = APIRouter(tags=["Restaurant Order Handling"])


def require_approved_owner(user):
    if (
        user.role != "Restaurant Owner"
        or not user.is_active
        or not user.is_approved
    ):
        raise HTTPException(
            status_code=403,
            detail="An active, approved restaurant owner account is required",
        )


def get_owned_order(
    db: Session,
    order_id: int,
    owner_id: int,
) -> Order:
    order = (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.status_history),
        )
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    restaurant = (
        db.query(Restaurant)
        .filter(
            Restaurant.id == order.restaurant_id,
            Restaurant.owner_id == owner_id,
        )
        .first()
    )

    if not restaurant:
        raise HTTPException(
            status_code=403,
            detail="You do not own the restaurant for this order",
        )

    return order


@router.get(
    "/restaurants/me/orders",
    response_model=list[OrderResponse],
)
def list_restaurant_orders(
    status: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_approved_owner(current_user)

    restaurant_ids = [
        restaurant_id
        for (restaurant_id,) in (
            db.query(Restaurant.id)
            .filter(
                Restaurant.owner_id == current_user.id,
                Restaurant.is_active.is_(True),
            )
            .all()
        )
    ]

    if not restaurant_ids:
        return []

    query = (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.status_history),
        )
        .filter(Order.restaurant_id.in_(restaurant_ids))
    )

    if status:
        query = query.filter(Order.status == status)

    return (
        query.order_by(Order.placed_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.put(
    "/orders/{order_id}/accept",
    response_model=OrderResponse,
)
async def accept_order(
    order_id: int,
    payload: AcceptOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_approved_owner(current_user)

    try:
        order = get_owned_order(db, order_id, current_user.id)

        if order.status != "Placed":
            raise HTTPException(
                status_code=400,
                detail="Only Placed orders can be accepted",
            )

        old_status = order.status
        order.status = "Accepted"
        order.estimated_preparation_minutes = (
            payload.estimated_preparation_minutes
        )
        order.rejection_reason = None

        record_status_change(
            db,
            order,
            old_status,
            "Accepted",
            current_user.id,
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    # Broadcast only after the database transaction succeeds.
    await publish_order_update(db, order.id)

    # Delivery partner assignment can be triggered here once
    # the assignment service is fully integrated.
    return order


@router.put(
    "/orders/{order_id}/reject",
    response_model=OrderResponse,
)
async def reject_order(
    order_id: int,
    payload: RejectOrderRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_approved_owner(current_user)

    try:
        order = get_owned_order(db, order_id, current_user.id)

        if order.status != "Placed":
            raise HTTPException(
                status_code=400,
                detail="Only Placed orders can be rejected",
            )

        old_status = order.status
        order.status = "Rejected"
        order.rejection_reason = payload.reason.strip()

        if (
            order.payment_method == "Online"
            and order.payment_status == "Paid"
        ):
            # Mock refund only; this does not refund a real payment.
            order.payment_status = "Refunded"

        usages = (
            db.query(CouponUsage)
            .filter(
                CouponUsage.order_id == order.id,
                CouponUsage.status == "Used",
            )
            .with_for_update()
            .all()
        )

        for usage in usages:
            usage.status = "Released"
            usage.released_at = datetime.utcnow()

        record_status_change(
            db,
            order,
            old_status,
            "Rejected",
            current_user.id,
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    await publish_order_update(db, order.id)
    return order


async def move_order_forward(
    db: Session,
    order_id: int,
    owner_id: int,
    expected_status: str,
    new_status: str,
) -> Order:
    try:
        order = get_owned_order(db, order_id, owner_id)

        if order.status != expected_status:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot move order from {order.status} to {new_status}. "
                    f"Expected current status: {expected_status}"
                ),
            )

        old_status = order.status
        order.status = new_status

        record_status_change(
            db,
            order,
            old_status,
            new_status,
            owner_id,
        )

        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise

    await publish_order_update(db, order.id)
    return order


@router.put(
    "/orders/{order_id}/preparing",
    response_model=OrderResponse,
)
async def mark_preparing(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_approved_owner(current_user)

    return await move_order_forward(
        db,
        order_id,
        current_user.id,
        "Accepted",
        "Preparing",
    )


@router.put(
    "/orders/{order_id}/ready",
    response_model=OrderResponse,
)
async def mark_ready_for_pickup(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_approved_owner(current_user)

    return await move_order_forward(
        db,
        order_id,
        current_user.id,
        "Preparing",
        "Ready for Pickup",
    )
    if status:
        query = query.filter(Order.status == status)

    return (
        query.order_by(Order.placed_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )