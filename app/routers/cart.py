
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.cart import Cart, CartItem
from app.models.menu_item import MenuItem
from app.schemas.cart import (
    CartItemAdd,
    CartItemUpdate,
    CartResponse,
)

router = APIRouter(prefix="/cart", tags=["Cart Management"])

MONEY = Decimal("0.01")
DIFFERENT_RESTAURANT_MESSAGE = (
    "Your cart has items from another restaurant. Clear the cart to continue"
)


def require_customer(user: User) -> None:
    if user.role != "Customer":
        raise HTTPException(
            status_code=403,
            detail="Only customers can manage a cart",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive",
        )


def get_or_create_cart(db: Session, customer_id: int) -> Cart:
    cart = (
        db.query(Cart)
        .filter(Cart.customer_id == customer_id)
        .first()
    )

    if cart is None:
        cart = Cart(customer_id=customer_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)

    return cart


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def build_cart_response(cart: Cart) -> dict:
    lines = []
    item_total = Decimal("0.00")

    for cart_item in cart.items:
        menu_item = cart_item.menu_item
        unit_price = Decimal(cart_item.unit_price)
        line_total = money(unit_price * cart_item.quantity)
        item_total += line_total

        lines.append(
            {
                "id": cart_item.id,
                "menu_item_id": cart_item.menu_item_id,
                "name": menu_item.name,
                "quantity": cart_item.quantity,
                "unit_price": money(unit_price),
                "line_total": line_total,
                "is_veg": menu_item.is_veg,
            }
        )

    item_total = money(item_total)

    discount = money(
        Decimal(cart.discount_amount or Decimal("0.00"))
    )
    # Never return a negative payable total.
    discount = min(max(discount, Decimal("0.00")), item_total)

    total_after_discount = money(item_total - discount)

    return {
        "id": cart.id,
        "customer_id": cart.customer_id,
        "restaurant_id": cart.restaurant_id,
        "items": lines,
        "item_total": item_total,
        "applied_coupon": cart.applied_coupon_code,
        "discount": discount,
        "total_after_discount": total_after_discount,
        "created_at": cart.created_at,
        "updated_at": cart.updated_at,
    }


def get_cart_item_for_customer(
    db: Session,
    cart: Cart,
    item_id: int,
) -> CartItem:
    item = (
        db.query(CartItem)
        .options(joinedload(CartItem.menu_item))
        .filter(
            CartItem.id == item_id,
            CartItem.cart_id == cart.id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Cart item not found",
        )

    return item


@router.get("", response_model=CartResponse)
def get_cart(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)
    cart = get_or_create_cart(db, user.id)

    cart = (
        db.query(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.menu_item)
        )
        .filter(Cart.id == cart.id)
        .first()
    )

    return build_cart_response(cart)


@router.post(
    "/items",
    response_model=CartResponse,
    status_code=status.HTTP_200_OK,
)
def add_cart_item(
    payload: CartItemAdd,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)
    cart = get_or_create_cart(db, user.id)

    menu_item = db.get(MenuItem, payload.menu_item_id)

    if menu_item is None or menu_item.is_deleted:
        raise HTTPException(
            status_code=404,
            detail="Menu item not found",
        )

    if not menu_item.is_available:
        raise HTTPException(
            status_code=409,
            detail="This menu item is unavailable",
        )

    if not menu_item.restaurant.is_active:
        raise HTTPException(
            status_code=409,
            detail="This restaurant is inactive",
        )

    if (
        cart.restaurant_id is not None
        and cart.restaurant_id != menu_item.restaurant_id
    ):
        raise HTTPException(
            status_code=409,
            detail=DIFFERENT_RESTAURANT_MESSAGE,
        )

    existing_item = (
        db.query(CartItem)
        .filter(
            CartItem.cart_id == cart.id,
            CartItem.menu_item_id == menu_item.id,
        )
        .first()
    )

    if existing_item is not None:
        new_quantity = existing_item.quantity + payload.quantity

        if new_quantity > 10:
            raise HTTPException(
                status_code=422,
                detail="Total quantity for an item cannot exceed 10",
            )

        existing_item.quantity = new_quantity
    else:
        cart_item = CartItem(
            cart_id=cart.id,
            menu_item_id=menu_item.id,
            quantity=payload.quantity,
            unit_price=menu_item.price,
        )
        db.add(cart_item)

    if cart.restaurant_id is None:
        cart.restaurant_id = menu_item.restaurant_id

    db.commit()

    cart = (
        db.query(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.menu_item)
        )
        .filter(Cart.id == cart.id)
        .first()
    )

    return build_cart_response(cart)


@router.put("/items/{item_id}", response_model=CartResponse)
def update_cart_item(
    item_id: int,
    payload: CartItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)
    cart = get_or_create_cart(db, user.id)

    item = get_cart_item_for_customer(db, cart, item_id)

    if item.menu_item.is_deleted or not item.menu_item.is_available:
        raise HTTPException(
            status_code=409,
            detail="This menu item is unavailable",
        )

    item.quantity = payload.quantity
    db.commit()

    cart = (
        db.query(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.menu_item)
        )
        .filter(Cart.id == cart.id)
        .first()
    )

    return build_cart_response(cart)


@router.delete("/items/{item_id}", response_model=CartResponse)
def delete_cart_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)
    cart = get_or_create_cart(db, user.id)

    item = get_cart_item_for_customer(db, cart, item_id)
    db.delete(item)
    db.flush()

    remaining_count = (
        db.query(CartItem)
        .filter(CartItem.cart_id == cart.id)
        .count()
    )

    if remaining_count == 0:
        cart.restaurant_id = None
        cart.applied_coupon_code = None
        cart.discount_amount = Decimal("0.00")

    db.commit()

    cart = (
        db.query(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.menu_item)
        )
        .filter(Cart.id == cart.id)
        .first()
    )

    return build_cart_response(cart)


@router.delete("")
def clear_cart(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_customer(user)
    cart = get_or_create_cart(db, user.id)

    db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).delete(synchronize_session=False)

    cart.restaurant_id = None
    cart.applied_coupon_code = None
    cart.discount_amount = Decimal("0.00")

    db.commit()

    return {"message": "Cart cleared successfully"}
