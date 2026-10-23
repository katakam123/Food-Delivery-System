
import logging
import os
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    Coupon,
    CouponUsage,
    DeliveryOffer,
    DeliveryPartner,
    Order,
    User,
)
from app.services.delivery_assignment import offer_next_partner
from app.services.orders import record_status_change
from app.websockets.events import (
    publish_delivery_offer,
    publish_order_update,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

# Configure this with the ID of a dedicated System user in your database.
SYSTEM_USER_ID = int(os.getenv("SYSTEM_USER_ID", "0"))

ACTIVE_DELIVERY_STATUSES = [
    "Accepted",
    "Preparing",
    "Ready for Pickup",
    "Picked Up",
    "Out for Delivery",
]


def get_system_user_id(db: Session) -> int:
    """Return the dedicated System user's ID for audit history."""
    if SYSTEM_USER_ID <= 0:
        raise RuntimeError(
            "Set SYSTEM_USER_ID in .env to the ID of a dedicated System user."
        )

    system_user = (
        db.query(User)
        .filter(User.id == SYSTEM_USER_ID)
        .first()
    )

    if system_user is None:
        raise RuntimeError(
            f"System user ID {SYSTEM_USER_ID} does not exist."
        )

    return system_user.id


async def auto_reject_unanswered_orders():
    """Reject Placed orders that have waited at least five minutes."""
    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        system_id = get_system_user_id(db)

        orders = (
            db.query(Order)
            .filter(
                Order.status == "Placed",
                Order.placed_at <= cutoff,
            )
            .with_for_update()
            .all()
        )

        changed_order_ids = []

        for order in orders:
            old_status = order.status
            order.status = "Rejected"
            order.rejection_reason = "Restaurant did not respond"

            if (
                order.payment_method == "Online"
                and order.payment_status == "Paid"
            ):
                # This is a local status update, not a real payment gateway refund.
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

            for usage in usages:
                usage.status = "Released"
                usage.released_at = datetime.utcnow()

            record_status_change(
                db,
                order,
                old_status,
                "Rejected",
                system_id,
            )
            changed_order_ids.append(order.id)

        db.commit()

        # Publish after commit so connected customers see the saved status.
        for order_id in changed_order_ids:
            try:
                await publish_order_update(db, order_id)
            except Exception:
                logger.exception(
                    "Could not broadcast auto-rejection for order %s",
                    order_id,
                )

        if changed_order_ids:
            logger.info(
                "Automatically rejected %s unanswered orders",
                len(changed_order_ids),
            )

    except Exception:
        db.rollback()
        logger.exception("Auto-reject job failed")
    finally:
        db.close()


async def expire_delivery_offers():
    """Expire overdue offers and offer eligible orders to the next partner."""
    db = SessionLocal()

    try:
        now = datetime.utcnow()

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

        db.commit()

        for order_id in order_ids:
            try:
                next_offer = offer_next_partner(db, order_id)

                if next_offer is not None:
                    await publish_delivery_offer(db, next_offer.id)
            except Exception:
                db.rollback()
                logger.exception(
                    "Could not reassign delivery offer for order %s",
                    order_id,
                )

    except Exception:
        db.rollback()
        logger.exception("Offer-expiry job failed")
    finally:
        db.close()


async def retry_unassigned_orders():
    """
    Retry assignment for Accepted orders without a partner.
    Admin notification must be connected to the project's notification system.
    """
    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=15)

        orders = (
            db.query(Order)
            .filter(
                Order.status == "Accepted",
                Order.delivery_partner_id.is_(None),
                Order.placed_at <= cutoff,
            )
            .all()
        )

        for order in orders:
            try:
                offer = offer_next_partner(db, order.id)

                if offer is not None:
                    await publish_delivery_offer(db, offer.id)
                else:
                    logger.warning(
                        "Order %s remains unassigned after 15 minutes; "
                        "an Admin alert is required.",
                        order.id,
                    )
            except Exception:
                db.rollback()
                logger.exception(
                    "Assignment retry failed for order %s",
                    order.id,
                )

    except Exception:
        db.rollback()
        logger.exception("Unassigned-order job failed")
    finally:
        db.close()


async def mark_inactive_partners_offline():
    """Set partners Offline if their last location update is over 10 minutes old."""
    db = SessionLocal()

    try:
        cutoff = datetime.utcnow() - timedelta(minutes=10)

        partners = (
            db.query(DeliveryPartner)
            .filter(
                DeliveryPartner.is_online.is_(True),
                (
                    (DeliveryPartner.last_location_at.is_(None))
                    | (DeliveryPartner.last_location_at < cutoff)
                ),
            )
            .all()
        )

        for partner in partners:
            partner.is_online = False

        db.commit()

        if partners:
            logger.info(
                "Set %s inactive delivery partners Offline",
                len(partners),
            )

    except Exception:
        db.rollback()
        logger.exception("Inactive-partner job failed")
    finally:
        db.close()


async def deactivate_expired_coupons():
    """Deactivate coupons whose valid_to date has passed."""
    db = SessionLocal()

    try:
        now = datetime.utcnow()

        expired_coupons = (
            db.query(Coupon)
            .filter(
                Coupon.is_active.is_(True),
                Coupon.valid_to < now,
            )
            .all()
        )

        for coupon in expired_coupons:
            coupon.is_active = False

        db.commit()

        if expired_coupons:
            logger.info(
                "Deactivated %s expired coupons",
                len(expired_coupons),
            )

    except Exception:
        db.rollback()
        logger.exception("Coupon-expiry job failed")
    finally:
        db.close()


def start_scheduler():
    """Register jobs once and start them with the application."""
    if scheduler.running:
        return

    scheduler.add_job(
        auto_reject_unanswered_orders,
        trigger="interval",
        minutes=1,
        id="auto_reject_orders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        expire_delivery_offers,
        trigger="interval",
        seconds=10,
        id="expire_delivery_offers",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        retry_unassigned_orders,
        trigger="interval",
        minutes=1,
        id="retry_unassigned_orders",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        mark_inactive_partners_offline,
        trigger="interval",
        minutes=5,
        id="inactive_partners_offline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        deactivate_expired_coupons,
        trigger="cron",
        hour=0,
        minute=5,
        id="deactivate_expired_coupons",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    logger.info("Food delivery scheduled jobs started")


def stop_scheduler():
    """Stop the scheduler during application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Food delivery scheduled jobs stopped")
