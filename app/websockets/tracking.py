
import math

from sqlalchemy.orm import Session

from app.models import Address, DeliveryPartner, Order, Restaurant, User
from app.utils.geo import haversine_distance_km


def build_tracking_payload(db: Session, order: Order) -> dict:
    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.id == order.restaurant_id)
        .first()
    )

    address = (
        db.query(Address)
        .filter(Address.id == order.address_id)
        .first()
    )

    partner_data = None
    remaining_distance = None
    eta_minutes = None

    if order.delivery_partner_id is not None:
        partner = (
            db.query(DeliveryPartner)
            .filter(
                DeliveryPartner.user_id == order.delivery_partner_id
            )
            .first()
        )

        user = (
            db.query(User)
            .filter(User.id == order.delivery_partner_id)
            .first()
        )

        if partner:
            partner_data = {
                "name": user.email if user else "Delivery Partner",
                "vehicle_type": partner.vehicle_type,
                "vehicle_number": partner.vehicle_number,
                "latitude": (
                    float(partner.current_latitude)
                    if partner.current_latitude is not None
                    else None
                ),
                "longitude": (
                    float(partner.current_longitude)
                    if partner.current_longitude is not None
                    else None
                ),
                "last_location_at": (
                    partner.last_location_at.isoformat()
                    if partner.last_location_at
                    else None
                ),
            }

            if (
                partner.current_latitude is not None
                and partner.current_longitude is not None
                and address is not None
            ):
                remaining_distance = haversine_distance_km(
                    float(partner.current_latitude),
                    float(partner.current_longitude),
                    float(address.latitude),
                    float(address.longitude),
                )
                # Nominal travel-time estimate, not live road routing.
                eta_minutes = math.ceil(
                    (remaining_distance / 20.0) * 60
                )

    return {
        "event": "order_tracking",
        "order_id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "restaurant": restaurant.name if restaurant else None,
        "partner": partner_data,
        "distance_remaining_km": remaining_distance,
        "estimated_arrival_minutes": eta_minutes,
        "updated_at": order.delivered_at.isoformat()
        if order.delivered_at
        else None,
    }
