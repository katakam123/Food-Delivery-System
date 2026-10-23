
import math
import secrets
import uuid

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Address,
    Cart,
    CartItem,
    Coupon,
    CouponUsage,
    MenuItem,
    Order,
    OrderItem,
    OrderStatusHistory,
    Restaurant,
)
from app.services.coupons import validate_coupon
from app.utils.geo import haversine_distance_km


CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(
        CENT, rounding=ROUND_HALF_UP
    )


def calculate_delivery_fee(distance_km: float) -> Decimal:
    if distance_km <= 3:
        return Decimal("20.00")

    extra_km = math.ceil(distance_km - 3)
    return Decimal("20.00") + Decimal("8.00") * extra_km


def get_customer_cart(db: Session, customer_id: int) -> Cart:
    cart = (
        db.query(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.menu_item)
        )
        .filter(Cart.customer_id == customer_id)
        .with_for_update()
        .first()
    )

    if not cart:
        raise HTTPException(status_code=400, detail="Your cart is empty")

    if not cart.items:
        raise HTTPException(status_code=400, detail="Your cart is empty")

    return cart


def record_status_change(
    db: Session,
    order: Order,
    old_status: str | None,
    new_status: str,
    changed_by: int | None,
) -> None:
    db.add(
        OrderStatusHistory(
            order_id=order.id,
            old_status=old_status,
            new_status=new_status,
            changed_by=changed_by,
            changed_at=datetime.utcnow(),
        )
    )


def get_customer_order(
    db: Session, order_id: int, customer_id: int
) -> Order:
    order = (
        db.query(Order)
        .options(
            joinedload(Order.items),
            joinedload(Order.status_history),
        )
        .filter(
            Order.id == order_id,
            Order.customer_id == customer_id,
        )
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


def place_order(
    db: Session,
    customer_id: int,
    address_id: int,
    payment_method: str,
    tip_amount: Decimal,
) -> Order:
    try:
        # Lock the customer's cart while processing this order.
        cart = get_customer_cart(db, customer_id)

        restaurant = (
            db.query(Restaurant)
            .filter(Restaurant.id == cart.restaurant_id)
            .with_for_update()
            .first()
        )
        if not restaurant or not restaurant.is_active:
            raise HTTPException(
                status_code=400, detail="Restaurant is unavailable"
            )

        if not restaurant.is_open:
            raise HTTPException(
                status_code=400, detail="Restaurant is currently closed"
            )

        address = (
            db.query(Address)
            .filter(
                Address.id == address_id,
                Address.customer_id == customer_id,
            )
            .with_for_update()
            .first()
        )
        if not address:
            raise HTTPException(
                status_code=400,
                detail="Delivery address not found for this customer",
            )

        distance = haversine_distance_km(
            float(address.latitude),
            float(address.longitude),
            float(restaurant.latitude),
            float(restaurant.longitude),
        )

        if distance > float(restaurant.delivery_radius_km):
            raise HTTPException(
                status_code=400,
                detail="Delivery address is outside the restaurant's delivery radius",
            )

        item_total = Decimal("0.00")
        packaging_total = Decimal("0.00")
        order_lines = []

        # Validate availability and take a price snapshot at placement time.
        for cart_item in cart.items:
            menu_item = (
                db.query(MenuItem)
                .filter(MenuItem.id == cart_item.menu_item_id)
                .with_for_update()
                .first()
            )

            if (
                not menu_item
                or menu_item.is_deleted
                or not menu_item.is_available
                or menu_item.restaurant_id != restaurant.id
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Menu item {cart_item.menu_item_id} is unavailable. "
                        "Remove it from your cart and try again."
                    ),
                )

            if not 1 <= cart_item.quantity <= 10:
                raise HTTPException(
                    status_code=400,
                    detail="Each item quantity must be between 1 and 10",
                )

            unit_price = money(menu_item.price)
            packaging_charge = money(
                menu_item.packaging_charge or Decimal("0.00")
            )
            line_total = money(unit_price * cart_item.quantity)

            item_total += line_total
            packaging_total += packaging_charge * cart_item.quantity

            order_lines.append(
                {
                    "menu_item_id": menu_item.id,
                    "item_name": menu_item.name,
                    "quantity": cart_item.quantity,
                    "unit_price": unit_price,
                    "packaging_charge": packaging_charge,
                    "line_total": line_total,
                }
            )

        item_total = money(item_total)
        packaging_total = money(packaging_total)
        tip_amount = money(tip_amount)

        if item_total < money(restaurant.min_order_value):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Minimum order value is "
                    f"₹{money(restaurant.min_order_value)}"
                ),
            )

        # Refresh cart prices before validating the coupon because coupon
        # validation calculates the total from CartItem.unit_price.
        for cart_item, line in zip(cart.items, order_lines):
            cart_item.unit_price = line["unit_price"]

        db.flush()

        coupon_code = None
        discount_amount = Decimal("0.00")
        coupon = None

        if cart.applied_coupon_code:
            coupon = (
                db.query(Coupon)
                .filter(
                    Coupon.code == cart.applied_coupon_code.upper()
                )
                .with_for_update()
                .first()
            )

            if not coupon:
                raise HTTPException(
                    status_code=400,
                    detail="The applied coupon no longer exists",
                )

            # Revalidate at order placement; limits and validity may have
            # changed since the coupon was applied to the cart.
            discount_amount = money(
                validate_coupon(
                    db=db,
                    coupon=coupon,
                    cart=cart,
                    customer_id=customer_id,
                    check_usage=True,
                )
            )
            coupon_code = coupon.code

        discount_amount = min(discount_amount, item_total)
        taxable_total = money(item_total - discount_amount)
        delivery_fee = calculate_delivery_fee(distance)
        platform_fee = Decimal("5.00")
        gst_amount = money(taxable_total * Decimal("0.05"))

        grand_total = money(
            taxable_total
            + packaging_total
            + delivery_fee
            + platform_fee
            + gst_amount
            + tip_amount
        )

        order = Order(
            order_number=f"TEMP-{uuid.uuid4().hex}",
            customer_id=customer_id,
            restaurant_id=restaurant.id,
            address_id=address.id,
            item_total=item_total,
            coupon_code=coupon_code,
            discount_amount=discount_amount,
            packaging_charges=packaging_total,
            delivery_fee=delivery_fee,
            platform_fee=platform_fee,
            gst_amount=gst_amount,
            tip_amount=tip_amount,
            grand_total=grand_total,
            payment_method=payment_method,
            payment_status=(
                "Paid" if payment_method == "Online" else "Pending"
            ),
            status="Placed",
            distance_km=money(distance),
            delivery_otp=f"{secrets.randbelow(10000):04d}",
            placed_at=datetime.utcnow(),
        )
        db.add(order)
        db.flush()

        order.order_number = (
            f"ORD-{datetime.utcnow():%Y%m%d}-{order.id:04d}"
        )

        for line in order_lines:
            db.add(
                OrderItem(
                    order_id=order.id,
                    menu_item_id=line["menu_item_id"],
                    item_name=line["item_name"],
                    quantity=line["quantity"],
                    unit_price=line["unit_price"],
                    packaging_charge=line["packaging_charge"],
                    line_total=line["line_total"],
                )
            )

        record_status_change(
            db, order, None, "Placed", customer_id
        )

        if coupon:
            # Usage counts begin only when an order is placed.
            db.add(
                CouponUsage(
                    coupon_id=coupon.id,
                    customer_id=customer_id,
                    order_id=order.id,
                    discount_amount=discount_amount,
                    status="Used",
                    used_at=datetime.utcnow(),
                )
            )

        # Clear the cart inside the same transaction.
        for cart_item in list(cart.items):
            db.delete(cart_item)

        cart.restaurant_id = None
        cart.applied_coupon_code = None
        cart.discount_amount = Decimal("0.00")

        db.commit()

        return get_customer_order(db, order.id, customer_id)

    except Exception:
        db.rollback()
        raise
