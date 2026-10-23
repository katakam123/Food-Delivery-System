from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.restaurant import Restaurant
from app.models.cart import Cart, CartItem
from app.models.coupon import Coupon
from app.models.coupon_usage import CouponUsage
from app.schemas.coupon import (
    CouponCreate,
    CouponUpdate,
    CouponResponse,
    AvailableCouponResponse,
    ApplyCouponRequest,
)
from app.services.coupons import validate_coupon

router = APIRouter(tags=["Coupons"])


def require_admin_or_owner(user: User) -> None:
    if user.role not in ("Admin", "Restaurant Owner"):
        raise HTTPException(
            status_code=403,
            detail="Only Admins and Restaurant Owners can manage coupons",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account is inactive",
        )

    if user.role == "Restaurant Owner" and not user.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Admin approval is required",
        )


def get_managed_coupon(
    coupon_id: int,
    db: Session,
    user: User,
) -> Coupon:
    coupon = db.get(Coupon, coupon_id)

    if coupon is None:
        raise HTTPException(404, "Coupon not found")

    if user.role == "Admin":
        return coupon

    if coupon.created_by != user.id:
        raise HTTPException(
            403,
            "You cannot manage this coupon",
        )

    if coupon.restaurant_id is None:
        raise HTTPException(
            403,
            "Restaurant Owners cannot manage platform-wide coupons",
        )

    restaurant = db.get(Restaurant, coupon.restaurant_id)

    if restaurant is None or restaurant.owner_id != user.id:
        raise HTTPException(
            403,
            "You can manage coupons only for your own restaurant",
        )

    return coupon


def get_customer_cart(db: Session, customer_id: int) -> Cart:
    cart = (
        db.query(Cart)
        .options(
            joinedload(Cart.items).joinedload(CartItem.menu_item)
        )
        .filter(Cart.customer_id == customer_id)
        .first()
    )

    if cart is None:
        raise HTTPException(400, "Your cart is empty")

    return cart


def get_coupon_by_code(db: Session, code: str) -> Coupon:
    coupon = (
        db.query(Coupon)
        .filter(Coupon.code == code.strip().upper())
        .first()
    )

    if coupon is None:
        raise HTTPException(400, "Invalid coupon code")

    return coupon


@router.post(
    "/coupons",
    response_model=CouponResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_coupon(
    payload: CouponCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin_or_owner(user)

    if user.role == "Admin" and payload.restaurant_id is not None:
        raise HTTPException(
            400,
            "Admin-created coupons must be platform-wide",
        )

    if user.role == "Restaurant Owner":
        if payload.restaurant_id is None:
            raise HTTPException(
                400,
                "Restaurant Owners must select their own restaurant",
            )

        restaurant = db.get(Restaurant, payload.restaurant_id)

        if restaurant is None or restaurant.owner_id != user.id:
            raise HTTPException(
                403,
                "You can create coupons only for your own restaurant",
            )

    if payload.valid_to <= datetime.utcnow():
        raise HTTPException(
            400,
            "Coupon valid_to must be in the future",
        )

    coupon = Coupon(
        **payload.model_dump(),
        created_by=user.id,
        is_active=True,
    )

    db.add(coupon)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409,
            "A coupon with this code already exists",
        )

    db.refresh(coupon)
    return coupon


@router.get("/coupons", response_model=list[CouponResponse])
def list_coupons(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin_or_owner(user)

    query = db.query(Coupon)

    if user.role == "Restaurant Owner":
        restaurant_ids = [
            row.id
            for row in db.query(Restaurant.id)
            .filter(Restaurant.owner_id == user.id)
            .all()
        ]

        query = query.filter(
            Coupon.restaurant_id.in_(restaurant_ids)
        )

    return query.order_by(Coupon.created_at.desc()).all()


@router.put(
    "/coupons/{coupon_id}",
    response_model=CouponResponse,
)
def update_coupon(
    coupon_id: int,
    payload: CouponUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin_or_owner(user)
    coupon = get_managed_coupon(coupon_id, db, user)

    updates = payload.model_dump(exclude_unset=True)

    for field, value in updates.items():
        if value is None and field in {
            "discount_type",
            "discount_value",
            "min_order_value",
            "valid_from",
            "valid_to",
            "per_user_limit",
            "first_order_only",
        }:
            raise HTTPException(
                422,
                f"{field} cannot be null",
            )

        setattr(coupon, field, value)

    if coupon.valid_to <= coupon.valid_from:
        raise HTTPException(
            400,
            "valid_to must be later than valid_from",
        )

    if coupon.valid_to <= datetime.utcnow():
        raise HTTPException(
            400,
            "Coupon valid_to must be in the future",
        )

    if coupon.discount_type == "Percentage":
        if coupon.discount_value > 100:
            raise HTTPException(
                400,
                "Percentage discount cannot exceed 100",
            )
    elif coupon.max_discount is not None:
        raise HTTPException(
            400,
            "max_discount is only applicable to Percentage coupons",
        )

    db.commit()
    db.refresh(coupon)
    return coupon


@router.put(
    "/coupons/{coupon_id}/deactivate",
    response_model=CouponResponse,
)
def deactivate_coupon(
    coupon_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_admin_or_owner(user)
    coupon = get_managed_coupon(coupon_id, db, user)

    coupon.is_active = False
    db.commit()
    db.refresh(coupon)

    return coupon


@router.get(
    "/coupons/available",
    response_model=list[AvailableCouponResponse],
)
def available_coupons(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "Customer" or not user.is_active:
        raise HTTPException(
            403,
            "An active Customer account is required",
        )

    cart = get_customer_cart(db, user.id)

    if not cart.items or cart.restaurant_id is None:
        return []

    now = datetime.utcnow()

    query = db.query(Coupon).filter(
        Coupon.is_active.is_(True),
        Coupon.valid_from <= now,
        Coupon.valid_to >= now,
    )

    # Include platform-wide coupons and coupons for this cart's restaurant.
    query = query.filter(
        (Coupon.restaurant_id.is_(None))
        | (Coupon.restaurant_id == cart.restaurant_id)
    )

    results = []

    for coupon in query.all():
        try:
            discount = validate_coupon(
                db,
                coupon,
                cart,
                user.id,
            )
        except HTTPException:
            # Exclude coupons the customer cannot currently use.
            continue

        data = CouponResponse.model_validate(coupon).model_dump()
        data["discount_you_get"] = discount
        results.append(data)

    results.sort(
        key=lambda row: row["discount_you_get"],
        reverse=True,
    )

    return results


@router.post("/cart/apply-coupon")
def apply_coupon(
    payload: ApplyCouponRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "Customer" or not user.is_active:
        raise HTTPException(
            403,
            "An active Customer account is required",
        )

    cart = get_customer_cart(db, user.id)
    coupon = get_coupon_by_code(db, payload.code)

    discount = validate_coupon(
        db,
        coupon,
        cart,
        user.id,
    )

    cart.applied_coupon_code = coupon.code
    cart.discount_amount = discount

    db.commit()

    return {
        "message": "Coupon applied successfully",
        "coupon_code": coupon.code,
        "item_total": sum(
            (
                Decimal(item.unit_price) * item.quantity
                for item in cart.items
            ),
            Decimal("0.00"),
        ),
        "discount": discount,
    }


@router.delete("/cart/coupon")
def remove_coupon(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.role != "Customer" or not user.is_active:
        raise HTTPException(
            403,
            "An active Customer account is required",
        )

    cart = (
        db.query(Cart)
        .filter(Cart.customer_id == user.id)
        .first()
    )

    if cart is None:
        raise HTTPException(404, "Cart not found")

    cart.applied_coupon_code = None
    cart.discount_amount = Decimal("0.00")

    db.commit()

    return {"message": "Coupon removed successfully"}
    restaurant_id: int | None = Query(default=None, gt=0),
    is_active: bool | None = Query(default=None),
    discount_type: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),