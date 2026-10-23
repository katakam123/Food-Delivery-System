
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import (
    DeliveryOffer,
    DeliveryPartner,
    Order,
    Restaurant,
    User,
)
from app.utils.geo import haversine_distance_km


MAX_ASSIGNMENT_DISTANCE_KM = 5.0
OFFER_SECONDS = 30


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def partner_has_active_delivery(db: Session, partner_user_id: int) -> bool:
    active_statuses = [
        "Accepted",
        "Preparing",
        "Ready for Pickup",
        "Picked Up",
        "Out for Delivery",
    ]

    return (
        db.query(Order.id)
        .filter(
            Order.delivery_partner_id == partner_user_id,
            Order.status.in_(active_statuses),
        )
        .first()
        is not None
    )


def offer_next_partner(db: Session, order_id: int) -> DeliveryOffer | None:
    order = (
        db.query(Order)
        .filter(Order.id == order_id)
        .with_for_update()
        .first()
    )
    if not order or order.status in (
        "Rejected", "Cancelled", "Delivered"
    ):
        return None

    if order.delivery_partner_id is not None:
        return None

    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == order.restaurant_id)
        .first()
    )
    if not restaurant or restaurant.latitude is None or restaurant.longitude is None:
        return None

    previously_offered = {
        partner_id
        for (partner_id,) in db.query(DeliveryOffer.partner_id)
        .filter(DeliveryOffer.order_id == order_id)
        .all()
    }

    candidates = (
        db.query(DeliveryPartner, User)
        .join(User, User.id == DeliveryPartner.user_id)
        .filter(
            DeliveryPartner.is_approved.is_(True),
            DeliveryPartner.is_online.is_(True),
            User.is_active.is_(True),
            User.is_approved.is_(True),
            DeliveryPartner.current_latitude.is_not(None),
            DeliveryPartner.current_longitude.is_not(None),
        )
        .all()
    )

    eligible = []
    for partner, user in candidates:
        if partner.user_id in previously_offered:
            continue

        if partner_has_active_delivery(db, partner.user_id):
            continue

        distance = haversine_distance_km(
            float(restaurant.latitude),
            float(restaurant.longitude),
            float(partner.current_latitude),
            float(partner.current_longitude),
        )

        if distance <= MAX_ASSIGNMENT_DISTANCE_KM:
            eligible.append((distance, partner))

    eligible.sort(key=lambda item: item[0])

    if not eligible:
        return None

    _, partner = eligible[0]
    now = utcnow()

    offer = DeliveryOffer(
        order_id=order.id,
        partner_id=partner.id,
        status="Pending",
        offered_at=now,
        expires_at=now + timedelta(seconds=OFFER_SECONDS),
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)

    return offer


def expire_pending_offers(db: Session) -> list[int]:
    now = utcnow()

    expired = (
        db.query(DeliveryOffer)
        .filter(
            DeliveryOffer.status == "Pending",
            DeliveryOffer.expires_at <= now,
        )
        .with_for_update()
        .all()
    )

    order_ids = set()
    for offer in expired:
        offer.status = "Expired"
        order_ids.add(offer.order_id)

    if expired:
        db.commit()

    return list(order_ids)
