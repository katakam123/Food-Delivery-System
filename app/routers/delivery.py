
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models import (
    DeliveryOffer,
    DeliveryPartner,
    Order,
    OrderStatusHistory,
    Restaurant,
    User,
)
from app.schemas.delivery import (
    AvailabilityUpdate,
    DeliverRequest,
    DeliveryOfferResponse,
    DeliveryResult,
    EarningsItem,
    EarningsSummary,
    LocationUpdate,
)
from app.services.delivery_assignment import (
    offer_next_partner,
    partner_has_active_delivery,
    utcnow,
)
from app.services.orders import record_status_change
from app.websockets.events import publish_order_update

router = APIRouter(tags=["Delivery Partner"])


def require_partner(db: Session, user):
    if user.role != "Delivery Partner" or not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="An active delivery partner account is required",
        )

    partner = (
        db.query(DeliveryPartner)
        .filter(DeliveryPartner.user_id == user.id)
        .with_for_update()
        .first()
    )
    if not partner or not partner.is_approved or not user.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Delivery partner approval is required",
        )

    return partner


@router.put("/partners/me/availability")
def update_availability(
    payload: AvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    partner = require_partner(db, current_user)

    if payload.is_online:
        if (
            partner.current_latitude is None
            or partner.current_longitude is None
        ):
            raise HTTPException(
                status_code=400,
                detail="Update your location before going online",
            )

    partner.is_online = payload.is_online
    db.commit()

    return {"message": "Availability updated", "is_online": partner.is_online}


@router.put("/partners/me/location")
def update_location(
    payload: LocationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    partner = require_partner(db, current_user)

    partner.current_latitude = payload.latitude
    partner.current_longitude = payload.longitude
    partner.last_location_at = utcnow()

    db.commit()
    active_order_ids = [
    order_id
    for (order_id,) in db.query(Order.id)
    .filter(
        Order.delivery_partner_id == current_user.id,
        Order.status.in_([
            "Picked Up",
            "Out for Delivery",
        ]),
    )
    .all()
]
    for order_id in active_order_ids:
        publish_order_update(db, order_id)
    return {
        "message": "Location updated",
        "latitude": partner.current_latitude,
        "longitude": partner.current_longitude,
    }


@router.get(
    "/partners/me/offers",
    response_model=list[DeliveryOfferResponse],
)
def my_offers(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    partner = require_partner(db, current_user)
    now = utcnow()

    # Mark expired offers before returning the remaining pending offers.
    expired = (
        db.query(DeliveryOffer)
        .filter(
            DeliveryOffer.partner_id == partner.id,
            DeliveryOffer.status == "Pending",
            DeliveryOffer.expires_at <= now,
        )
        .all()
    )
    expired_order_ids = {offer.order_id for offer in expired}

    for offer in expired:
        offer.status = "Expired"

    db.commit()

    for order_id in expired_order_ids:
        offer_next_partner(db, order_id)

    return (
        db.query(DeliveryOffer)
        .filter(
            DeliveryOffer.partner_id == partner.id,
            DeliveryOffer.status == "Pending",
            DeliveryOffer.expires_at > utcnow(),
        )
        .order_by(DeliveryOffer.offered_at.desc())
        .all()
    )


def get_partner_offer(db: Session, offer_id: int, partner_id: int):
    offer = (
        db.query(DeliveryOffer)
        .filter(
            DeliveryOffer.id == offer_id,
            DeliveryOffer.partner_id == partner_id,
        )
        .with_for_update()
        .first()
    )

    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    return offer


@router.put("/offers/{offer_id}/accept")
def accept_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    partner = require_partner(db, current_user)

    try:
        offer = get_partner_offer(db, offer_id, partner.id)
        order = (
            db.query(Order)
            .filter(Order.id == offer.order_id)
            .with_for_update()
            .first()
        )

        if offer.status != "Pending" or offer.expires_at <= utcnow():
            if offer.status == "Pending":
                offer.status = "Expired"
            db.commit()
            if order:
                offer_next_partner(db, order.id)
            raise HTTPException(
                status_code=400,
                detail="This offer has expired or is no longer available",
            )

        if not order or order.status != "Accepted":
            raise HTTPException(
                status_code=400,
                detail="Order is not awaiting delivery assignment",
            )

        if order.delivery_partner_id is not None:
            raise HTTPException(
                status_code=409,
                detail="Another partner has already been assigned",
            )

        if partner_has_active_delivery(db, current_user.id):
            raise HTTPException(
                status_code=409,
                detail="You already have an active delivery",
            )

        offer.status = "Accepted"
        order.delivery_partner_id = current_user.id

        # All other pending offers for this order become unavailable.
        other_offers = (
            db.query(DeliveryOffer)
            .filter(
                DeliveryOffer.order_id == order.id,
                DeliveryOffer.id != offer.id,
                DeliveryOffer.status == "Pending",
            )
            .with_for_update()
            .all()
        )
        for other in other_offers:
            other.status = "Expired"

        db.commit()

        return {
            "message": "Delivery offer accepted",
            "order_id": order.id,
            "partner_id": current_user.id,
        }

    except Exception:
        db.rollback()
        raise


@router.put("/offers/{offer_id}/decline")
def decline_offer(
    offer_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    partner = require_partner(db, current_user)

    try:
        offer = get_partner_offer(db, offer_id, partner.id)

        if offer.status != "Pending":
            raise HTTPException(
                status_code=400, detail="Offer is no longer pending"
            )

        offer.status = "Declined"
        order_id = offer.order_id
        db.commit()

        next_offer = offer_next_partner(db, order_id)

        return {
            "message": "Offer declined",
            "next_partner_offered": next_offer is not None,
        }

    except Exception:
        db.rollback()
        raise


def get_assigned_order(
    db: Session, order_id: int, partner_user_id: int
):
    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.delivery_partner_id == partner_user_id,
        )
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Assigned order not found",
        )

    return order


@router.put(
    "/orders/{order_id}/pickup",
    response_model=DeliveryResult,
)
def pickup_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_partner(db, current_user)

    try:
        order = get_assigned_order(db, order_id, current_user.id)

        if order.status != "Ready for Pickup":
            raise HTTPException(
                status_code=400,
                detail="Order must be Ready for Pickup before pickup",
            )

        old_status = order.status
        order.status = "Picked Up"
        order.picked_up_at = utcnow()

        record_status_change(
            db, order, old_status, "Picked Up", current_user.id
        )
        db.commit()

        return DeliveryResult(
            message="Order picked up",
            order_id=order.id,
            status=order.status,
            payment_status=order.payment_status,
        )

    except Exception:
        db.rollback()
        raise


@router.put(
    "/orders/{order_id}/out-for-delivery",
    response_model=DeliveryResult,
)
def mark_out_for_delivery(
    order_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_partner(db, current_user)

    try:
        order = get_assigned_order(db, order_id, current_user.id)

        if order.status != "Picked Up":
            raise HTTPException(
                status_code=400,
                detail="Order must be Picked Up first",
            )

        old_status = order.status
        order.status = "Out for Delivery"
        order.out_for_delivery_at = utcnow()

        record_status_change(
            db, order, old_status, order.status, current_user.id
        )
        db.commit()

        return DeliveryResult(
            message="Order is out for delivery",
            order_id=order.id,
            status=order.status,
            payment_status=order.payment_status,
        )

    except Exception:
        db.rollback()
        raise


@router.put(
    "/orders/{order_id}/deliver",
    response_model=DeliveryResult,
)
def deliver_order(
    order_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_partner(db, current_user)

    otp = payload.get("otp")
    if not isinstance(otp, str) or len(otp) != 4 or not otp.isdigit():
        raise HTTPException(
            status_code=400,
            detail="A valid 4-digit OTP is required",
        )

    try:
        order = get_assigned_order(db, order_id, current_user.id)

        if order.status != "Out for Delivery":
            raise HTTPException(
                status_code=400,
                detail="Order must be Out for Delivery before delivery",
            )

        if order.delivery_locked:
            raise HTTPException(
                status_code=423,
                detail="Delivery is locked. Contact Admin",
            )

        if otp != order.delivery_otp:
            order.otp_failed_attempts += 1

            if order.otp_failed_attempts >= 3:
                order.delivery_locked = True

            db.commit()

            if order.delivery_locked:
                # TODO: send a persistent Admin notification here.
                raise HTTPException(
                    status_code=423,
                    detail="Three incorrect OTP attempts. Delivery is locked",
                )

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Incorrect OTP. "
                    f"{3 - order.otp_failed_attempts} attempt(s) remaining"
                ),
            )

        old_status = order.status
        order.status = "Delivered"
        order.delivered_at = utcnow()

        if order.payment_method == "COD":
            order.payment_status = "Paid"

        record_status_change(
            db, order, old_status, "Delivered", current_user.id
        )
        db.commit()

        return DeliveryResult(
            message="Order delivered successfully",
            order_id=order.id,
            status=order.status,
            payment_status=order.payment_status,
        )

    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/partners/me/earnings", response_model=EarningsSummary)
def my_earnings(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    require_partner(db, current_user)

    today = date.today()
    start = start_date or today
    end = end_date or today

    if start > end:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end + timedelta(days=1), time.min)

    orders = (
        db.query(Order)
        .filter(
            Order.delivery_partner_id == current_user.id,
            Order.status == "Delivered",
            Order.delivered_at >= start_dt,
            Order.delivered_at < end_dt,
        )
        .order_by(Order.delivered_at.desc())
        .all()
    )

    items = []
    total = Decimal("0.00")

    for order in orders:
        base = Decimal("25.00")
        distance_pay = Decimal("6.00") * Decimal(str(order.distance_km))
        tip = Decimal(str(order.tip_amount or 0))
        earnings = base + distance_pay + tip
        total += earnings

        items.append(
            EarningsItem(
                order_id=order.id,
                order_number=order.order_number,
                delivered_at=order.delivered_at,
                distance_km=order.distance_km,
                base_amount=base,
                distance_amount=distance_pay,
                tip_amount=tip,
                total_earnings=earnings,
            )
        )

    return EarningsSummary(
        start_date=start_dt,
        end_date=end_dt - timedelta(seconds=1),
        deliveries=len(items),
        total_earnings=total.quantize(Decimal("0.01")),
        items=items,
    )
payload: DeliverRequest