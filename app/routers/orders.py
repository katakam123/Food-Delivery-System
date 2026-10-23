
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from app.utils.pricing import calculate_delivery_fee
from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models import (
    Cart,
    CartItem,
    CouponUsage,
    Order,
    OrderItem,
)
from app.schemas.order import (
    OrderCancelResponse,
    OrderCreate,
    OrderCreatedResponse,
    OrderResponse,
    ReorderResponse,
)
from app.services import orders
from app.services.orders import (
    get_customer_order,
    place_order,
    record_status_change,
)
from app.websockets.events import (
    publish_new_order,
    publish_order_update,
)
from datetime import datetime
from fastapi import Query, HTTPException

router = APIRouter(prefix="/orders", tags=["Orders"])


def require_customer(user):
    if user.role != "Customer":
        raise HTTPException(
            status_code=403,
            detail="Only customers can use this endpoint",
        )
    return user


@router.post("", response_model=OrderCreatedResponse, status_code=201)
async def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_customer(current_user)

    order = place_order(
        db=db,
        customer_id=current_user.id,
        address_id=payload.address_id,
        payment_method=payload.payment_method,
        tip_amount=payload.tip_amount,
    )

    await publish_new_order(db, order.id)
    await publish_order_update(db, order.id)

    return order
    
    


@router.get("", response_model=list[OrderResponse])
def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_customer(current_user)

    return (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.status_history),
        )
        .filter(Order.customer_id == current_user.id)
        .order_by(Order.placed_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_customer(current_user)
    return get_customer_order(db, order_id, current_user.id)


@router.put("/{order_id}/cancel", response_model=OrderCancelResponse)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_customer(current_user)

    try:
        order = (
            db.query(Order)
            .filter(
                Order.id == order_id,
                Order.customer_id == current_user.id,
            )
            .with_for_update()
            .first()
        )

        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        if order.status != "Placed":
            raise HTTPException(
                status_code=400,
                detail="An order can only be cancelled while its status is Placed",
            )

        old_status = order.status
        order.status = "Cancelled"

        if (
            order.payment_method == "Online"
            and order.payment_status == "Paid"
        ):
            # Mock refund: no payment gateway is involved.
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
        from datetime import datetime

        for usage in usages:
            usage.status = "Released"
            usage.released_at = datetime.utcnow()

        record_status_change(
            db, order, old_status, "Cancelled", current_user.id
        )

        db.commit()
        db.refresh(order)

        return OrderCancelResponse(
            message="Order cancelled successfully",
            order_id=order.id,
            order_number=order.order_number,
            status=order.status,
            payment_status=order.payment_status,
        )

    except Exception:
        db.rollback()
        raise


@router.post(
    "/{order_id}/reorder",
    response_model=ReorderResponse,
)
def reorder(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_customer(current_user)

    try:
        old_order = (
            db.query(Order)
            .options(joinedload(Order.items))
            .filter(
                Order.id == order_id,
                Order.customer_id == current_user.id,
            )
            .first()
        )

        if not old_order:
            raise HTTPException(status_code=404, detail="Order not found")

        cart = (
            db.query(Cart)
            .options(joinedload(Cart.items))
            .filter(Cart.customer_id == current_user.id)
            .with_for_update()
            .first()
        )

        if not cart:
            cart = Cart(
                customer_id=current_user.id,
                restaurant_id=None,
                discount_amount=0,
            )
            db.add(cart)
            db.flush()

        added_items = 0
        skipped_items = []

        for old_item in old_order.items:
            menu_item = (
                db.query(OrderItem.menu_item.property.mapper.class_)
                .filter(False)
                .first()
            )

            # Load the current menu item separately. The historical order
            # item remains unchanged.
            from app.models import MenuItem, Restaurant

            menu_item = (
                db.query(MenuItem)
                .filter(MenuItem.id == old_item.menu_item_id)
                .first()
            )

            if (
                not menu_item
                or menu_item.is_deleted
                or not menu_item.is_available
            ):
                skipped_items.append(old_item.item_name)
                continue

            restaurant = (
                db.query(Restaurant)
                .filter(Restaurant.id == menu_item.restaurant_id)
                .first()
            )

            if not restaurant or not restaurant.is_active:
                skipped_items.append(old_item.item_name)
                continue

            if cart.restaurant_id not in (None, menu_item.restaurant_id):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Your cart has items from another restaurant. "
                        "Clear the cart to continue"
                    ),
                )

            existing = next(
                (
                    item for item in cart.items
                    if item.menu_item_id == menu_item.id
                ),
                None,
            )

            if existing:
                new_quantity = existing.quantity + old_item.quantity
                if new_quantity > 10:
                    skipped_items.append(
                        f"{old_item.item_name} (quantity limit exceeded)"
                    )
                    continue
                existing.quantity = new_quantity
                existing.unit_price = menu_item.price
            else:
                if old_item.quantity > 10:
                    skipped_items.append(
                        f"{old_item.item_name} (quantity limit exceeded)"
                    )
                    continue

                new_item = CartItem(
                    cart_id=cart.id,
                    menu_item_id=menu_item.id,
                    quantity=old_item.quantity,
                    unit_price=menu_item.price,
                )
                db.add(new_item)
                cart.items.append(new_item)

            cart.restaurant_id = menu_item.restaurant_id
            added_items += 1

        # A historical coupon is never copied to a new cart.
        cart.applied_coupon_code = None
        cart.discount_amount = 0

        db.commit()

        return ReorderResponse(
            message="Reorder completed",
            order_id=old_order.id,
            added_items=added_items,
            skipped_items=skipped_items,
        )

    except Exception:
        db.rollback()
        raise
        if status:
            query = query.filter(Order.status == status)

    if restaurant_id is not None:
        query = query.filter(
        Order.restaurant_id == restaurant_id
    )

    if from_date and to_date and from_date > to_date:
        raise HTTPException(
        status_code=400,
        detail="from_date must be before or equal to to_date",
    )

    if from_date:
        query = query.filter(Order.placed_at >= from_date)

    if to_date:
        query = query.filter(Order.placed_at <= to_date)

    orders = (
        query.order_by(Order.placed_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return orders
