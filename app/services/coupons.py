from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.cart import Cart
from app.models.coupon import Coupon
from app.models.coupon_usage import CouponUsage
from app.models.menu_item import MenuItem
from app.models.cart import CartItem


CENT = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)





def get_cart_item_total(db: Session, cart: Cart) -> Decimal:
    rows = (
        db.query(CartItem.unit_price, CartItem.quantity)
        .filter(CartItem.cart_id == cart.id)
        .all()
    )

    total = sum(
        (
            Decimal(price) * quantity
            for price, quantity in rows
        ),
        Decimal("0.00"),
    )

    return money(total)


def validate_coupon(
    db: Session,
    coupon: Coupon,
    cart: Cart,
    customer_id: int,
    *,
    check_usage: bool = True,
) -> Decimal:
    now = datetime.utcnow()

    if not coupon.is_active:
        raise HTTPException(400, "This coupon is inactive")

    if now < coupon.valid_from:
        raise HTTPException(400, "This coupon is not valid yet")

    if now > coupon.valid_to:
        raise HTTPException(400, "This coupon has expired")

    if not cart.items:
        raise HTTPException(400, "Your cart is empty")

    if cart.restaurant_id is None:
        raise HTTPException(400, "Your cart has no restaurant")

    if (
        coupon.restaurant_id is not None
        and coupon.restaurant_id != cart.restaurant_id
    ):
        raise HTTPException(
            400,
            "This coupon is not valid for your cart's restaurant",
        )

    item_total = get_cart_item_total(db, cart)

    if item_total < Decimal(coupon.min_order_value):
        amount = Decimal(coupon.min_order_value)
        raise HTTPException(
            400,
            f"Minimum order value is ₹{amount:.2f}",
        )

    if check_usage:
        if coupon.total_usage_limit is not None:
            used_total = (
                db.query(CouponUsage)
                .filter(CouponUsage.coupon_id == coupon.id)
                .filter(CouponUsage.status == "Used")
                .count()
            )

            if used_total >= coupon.total_usage_limit:
                raise HTTPException(
                    400,
                    "This coupon has reached its total usage limit",
                )

        user_uses = (
            db.query(CouponUsage)
            .filter(
                CouponUsage.coupon_id == coupon.id,
                CouponUsage.customer_id == customer_id,
                CouponUsage.status == "Used",
            )
            .count()
        )

        if user_uses >= coupon.per_user_limit:
            raise HTTPException(
                400,
                "You have reached this coupon's usage limit",
            )

    if coupon.first_order_only:
        # This becomes accurate once the Order model exists.
        from app.models.order import Order

        delivered_orders = (
            db.query(Order)
            .filter(
                Order.customer_id == customer_id,
                Order.status == "Delivered",
            )
            .count()
        )

        if delivered_orders > 0:
            raise HTTPException(
                400,
                "This coupon is only valid on your first order",
            )

    if coupon.discount_type == "Percentage":
        discount = item_total * Decimal(coupon.discount_value) / Decimal("100")

        if coupon.max_discount is not None:
            discount = min(discount, Decimal(coupon.max_discount))
    else:
        discount = Decimal(coupon.discount_value)

    return money(min(max(discount, Decimal("0.00")), item_total))