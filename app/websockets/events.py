
from sqlalchemy.orm import Session

from app.models import (
    DeliveryOffer,
    DeliveryPartner,
    Order,
    Restaurant,
)
from app.websockets.manager import manager
from app.websockets.tracking import build_tracking_payload


async def publish_order_update(db: Session, order_id: int):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return

    payload = build_tracking_payload(db, order)
    await manager.send_order(order.id, payload)


async def publish_new_order(db: Session, order_id: int):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return

    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == order.restaurant_id)
        .first()
    )
    if not restaurant:
        return

    await manager.send_restaurant(
        restaurant.owner_id,
        {
            "event": "new_order",
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "item_total": str(order.item_total),
            "grand_total": str(order.grand_total),
            "placed_at": order.placed_at.isoformat(),
        },
    )


async def publish_delivery_offer(db: Session, offer_id: int):
    offer = (
        db.query(DeliveryOffer)
        .filter(DeliveryOffer.id == offer_id)
        .first()
    )
    if not offer or offer.status != "Pending":
        return

    partner = (
        db.query(DeliveryPartner)
        .filter(DeliveryPartner.id == offer.partner_id)
        .first()
    )
    order = db.query(Order).filter(Order.id == offer.order_id).first()

    if not partner or not order:
        return

    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == order.restaurant_id)
        .first()
    )

    if not restaurant:
        return

    from app.models import Address
    from app.utils.geo import haversine_distance_km

    address = (
        db.query(Address)
        .filter(Address.id == order.address_id)
        .first()
    )

    pickup_distance = None
    if (
        partner.current_latitude is not None
        and partner.current_longitude is not None
        and restaurant.latitude is not None
        and restaurant.longitude is not None
    ):
        pickup_distance = haversine_distance_km(
            float(partner.current_latitude),
            float(partner.current_longitude),
            float(restaurant.latitude),
            float(restaurant.longitude),
        )

    delivery_distance = None
    if address and restaurant.latitude is not None and restaurant.longitude is not None:
        delivery_distance = haversine_distance_km(
            float(restaurant.latitude),
            float(restaurant.longitude),
            float(address.latitude),
            float(address.longitude),
        )

    remaining_seconds = max(
        0,
        int((offer.expires_at - offer.offered_at).total_seconds()),
    )

    expected_earnings = (
        25 + 6 * float(order.distance_km) + float(order.tip_amount or 0)
    )

    await manager.send_partner(
        partner.user_id,
        {
            "event": "delivery_offer",
            "offer_id": offer.id,
            "order_id": order.id,
            "restaurant_name": restaurant.name,
            "pickup_distance_km": pickup_distance,
            "delivery_distance_km": delivery_distance,
            "expected_earnings": round(expected_earnings, 2),
            "seconds_left": remaining_seconds,
            "expires_at": offer.expires_at.isoformat(),
        },
    )
