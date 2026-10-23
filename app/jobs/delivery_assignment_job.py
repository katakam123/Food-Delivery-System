
from datetime import timedelta

from app.database import SessionLocal
from app.models import Order
from app.services.delivery_assignment import (
    expire_pending_offers,
    offer_next_partner,
    utcnow,
)


def retry_delivery_assignments():
    db = SessionLocal()

    try:
        expired_order_ids = expire_pending_offers(db)

        # Include orders that never received an offer because no partner
        # was eligible at the time of the restaurant's acceptance.
        cutoff = utcnow() - timedelta(minutes=15)

        unassigned_orders = (
            db.query(Order)
            .filter(
                Order.status == "Accepted",
                Order.delivery_partner_id.is_(None),
            )
            .all()
        )

        for order in unassigned_orders:
            # Retry orders with expired offers and orders still awaiting
            # their first offer.
            if (
                order.id in expired_order_ids
                or order.placed_at <= cutoff
            ):
                offer_next_partner(db, order.id)

            # TODO: send a persistent Admin notification if assignment
            # has been unsuccessful for 15 minutes after acceptance.

    finally:
        db.close()
