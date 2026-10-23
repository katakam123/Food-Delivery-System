from sqlalchemy import case, func, literal_column
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user, require_roles
from app.models import (
    Order,
    Restaurant,
    MenuItem,
    DeliveryPartner,
    Coupon,
    CouponUsage,
)

# If your order-item model is exported from app.models,
# import it here. The report below assumes its name is OrderItem.
from app.models import OrderItem


router = APIRouter(prefix="/reports", tags=["Reports"])


def date_range_filter(query, column, start_date, end_date):
    """Apply an inclusive date range using a half-open datetime interval."""
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    if start_date:
        query = query.filter(column >= datetime.combine(start_date, time.min))

    if end_date:
        query = query.filter(
            column < datetime.combine(end_date + timedelta(days=1), time.min)
        )

    return query


def delivered_orders_query(db: Session):
    return db.query(Order).filter(Order.status == "Delivered")


# ---------------------------------------------------------
# 1. ADMIN DASHBOARD
# GET /reports/admin-dashboard
# ---------------------------------------------------------
@router.get("/admin-dashboard")
def admin_dashboard(
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    today = date.today()
    start = datetime.combine(today, time.min)
    end = start + timedelta(days=1)

    todays_orders = db.query(Order).filter(
        Order.placed_at >= start,
        Order.placed_at < end,
    )

    total_orders = todays_orders.count()

    delivered_orders = todays_orders.filter(
        Order.status == "Delivered"
    ).count()

    cancelled_orders = todays_orders.filter(
        Order.status == "Cancelled"
    ).count()

    rejected_orders = todays_orders.filter(
        Order.status == "Rejected"
    ).count()

    # Revenue and discounts are counted only for delivered orders.
    revenue, discounts = db.query(
        func.coalesce(func.sum(Order.grand_total), 0),
        func.coalesce(func.sum(Order.discount_amount), 0),
    ).filter(
        Order.placed_at >= start,
        Order.placed_at < end,
        Order.status == "Delivered",
    ).first()

    online_partners = db.query(DeliveryPartner).filter(
        DeliveryPartner.is_online.is_(True),
        DeliveryPartner.is_approved.is_(True),
    ).count()

    # Prefer pickup-to-delivery time when timestamps are available.
    duration_seconds = func.timestampdiff(
        func.SECOND,
        Order.picked_up_at,
        Order.delivered_at,
    )

    avg_seconds = db.query(
        func.avg(duration_seconds)
    ).filter(
        Order.placed_at >= start,
        Order.placed_at < end,
        Order.status == "Delivered",
        Order.picked_up_at.isnot(None),
        Order.delivered_at.isnot(None),
    ).scalar()

    return {
        "date": today.isoformat(),
        "total_orders": total_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "rejected_orders": rejected_orders,
        "total_revenue": float(revenue or 0),
        "total_discount_given": float(discounts or 0),
        "online_partners": online_partners,
        "average_delivery_time_minutes": (
            round(float(avg_seconds) / 60, 2)
            if avg_seconds is not None
            else 0
        ),
    }


# ---------------------------------------------------------
# 2. TOP 10 RESTAURANTS
# GET /reports/top-restaurants
# ---------------------------------------------------------
@router.get("/top-restaurants")
def top_restaurants(
    start_date: date = Query(...),
    end_date: date = Query(...),
    sort_by: str = Query(default="revenue", pattern="^(orders|revenue)$"),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Admin")),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)

    query = (
        db.query(
            Restaurant.id.label("restaurant_id"),
            Restaurant.name.label("restaurant_name"),
            func.count(Order.id).label("total_orders"),
            func.coalesce(
                func.sum(
                    func.case(
                        (Order.status == "Delivered", Order.grand_total),
                        else_=0,
                    )
                ),
                0,
            ).label("revenue"),
        )
        .outerjoin(
            Order,
            (Order.restaurant_id == Restaurant.id)
            & (Order.placed_at >= start)
            & (Order.placed_at < end),
        )
        .group_by(Restaurant.id, Restaurant.name)
    )

    sort_column = (
        "total_orders" if sort_by == "orders" else "revenue"
    )

    rows = query.order_by(
        func.coalesce(
            func.sum(Order.id) if sort_by == "orders"
            else func.sum(
                func.case(
                    (Order.status == "Delivered", Order.grand_total),
                    else_=0,
                )
            ),
            0,
        ).desc()
    ).limit(10).all()

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "sorted_by": sort_column,
        "restaurants": [
            {
                "restaurant_id": row.restaurant_id,
                "restaurant_name": row.restaurant_name,
                "total_orders": row.total_orders,
                "revenue": float(row.revenue or 0),
            }
            for row in rows
        ],
    }


# ---------------------------------------------------------
# 3. COUPON USAGE
# GET /reports/coupon-usage
# ---------------------------------------------------------
@router.get("/coupon-usage")
def coupon_usage_report(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.role not in ("Admin", "Restaurant Owner"):
        raise HTTPException(
            status_code=403,
            detail="Admin or Restaurant Owner role required",
        )

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)

    query = (
        db.query(
            Coupon.id.label("coupon_id"),
            Coupon.code.label("coupon_code"),
            Coupon.restaurant_id.label("restaurant_id"),
            func.count(CouponUsage.id).label("times_used"),
            func.coalesce(
                func.sum(CouponUsage.discount_amount), 0
            ).label("total_discount"),
            func.coalesce(
                func.sum(Order.grand_total), 0
            ).label("revenue"),
        )
        .join(CouponUsage, CouponUsage.coupon_id == Coupon.id)
        .join(Order, Order.id == CouponUsage.order_id)
        .filter(
            CouponUsage.status == "Used",
            Order.status == "Delivered",
            Order.placed_at >= start,
            Order.placed_at < end,
        )
    )

    # Owners can only view coupons belonging to their own restaurants.
    if current_user.role == "Restaurant Owner":
        query = query.join(
            Restaurant, Restaurant.id == Coupon.restaurant_id
        ).filter(Restaurant.owner_id == current_user.id)

    rows = query.group_by(
        Coupon.id, Coupon.code, Coupon.restaurant_id
    ).order_by(func.count(CouponUsage.id).desc()).all()

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "coupons": [
            {
                "coupon_id": row.coupon_id,
                "coupon_code": row.coupon_code,
                "restaurant_id": row.restaurant_id,
                "times_used": row.times_used,
                "total_discount_given": float(row.total_discount or 0),
                "revenue": float(row.revenue or 0),
            }
            for row in rows
        ],
    }


# ---------------------------------------------------------
# 4. RESTAURANT SALES
# GET /reports/restaurant-sales
# ---------------------------------------------------------
@router.get("/restaurant-sales")
def restaurant_sales(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Restaurant Owner")),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    restaurant_ids = [
        row.id
        for row in db.query(Restaurant.id).filter(
            Restaurant.owner_id == current_user.id
        ).all()
    ]

    if not restaurant_ids:
        return {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily_sales": [],
            "total_orders": 0,
            "best_selling_items": [],
            "average_preparation_time_minutes": 0,
        }

    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)

    orders = db.query(Order).filter(
        Order.restaurant_id.in_(restaurant_ids),
        Order.placed_at >= start,
        Order.placed_at < end,
    )

    delivered = orders.filter(Order.status == "Delivered")

    total_orders = orders.count()

    daily_rows = (
        db.query(
            func.date(Order.placed_at).label("day"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.grand_total), 0).label("sales"),
        )
        .filter(
            Order.restaurant_id.in_(restaurant_ids),
            Order.placed_at >= start,
            Order.placed_at < end,
            Order.status == "Delivered",
        )
        .group_by(func.date(Order.placed_at))
        .order_by(func.date(Order.placed_at))
        .all()
    )

    # Assumes OrderItem has order_id, menu_item_id, quantity,
    # and MenuItem has name. Rename fields here if your models differ.
    best_selling_rows = (
        db.query(
            MenuItem.id.label("menu_item_id"),
            MenuItem.name.label("item_name"),
            func.sum(OrderItem.quantity).label("quantity_sold"),
        )
        .join(OrderItem, OrderItem.menu_item_id == MenuItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.restaurant_id.in_(restaurant_ids),
            Order.placed_at >= start,
            Order.placed_at < end,
            Order.status == "Delivered",
        )
        .group_by(MenuItem.id, MenuItem.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(10)
        .all()
    )

    # If estimated_preparation_minutes is stored on Order,
    # this reports its average for delivered orders.
    avg_prep = delivered.with_entities(
        func.avg(Order.estimated_preparation_minutes)
    ).scalar()

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_orders": total_orders,
        "daily_sales": [
            {
                "date": row.day.isoformat(),
                "total_orders": row.orders,
                "sales": float(row.sales or 0),
            }
            for row in daily_rows
        ],
        "best_selling_items": [
            {
                "menu_item_id": row.menu_item_id,
                "item_name": row.item_name,
                "quantity_sold": int(row.quantity_sold or 0),
            }
            for row in best_selling_rows
        ],
        "average_preparation_time_minutes": (
            round(float(avg_prep), 2) if avg_prep is not None else 0
        ),
    }


# ---------------------------------------------------------
# 5. DELIVERY PARTNER SUMMARY
# GET /reports/partner-summary
# ---------------------------------------------------------
@router.get("/partner-summary")
def partner_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles("Delivery Partner")),
):
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be on or before end_date",
        )

    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date + timedelta(days=1), time.min)

    orders = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status == "Delivered",
        Order.delivered_at >= start,
        Order.delivered_at < end,
    )

    rows = (
        db.query(
            func.date(Order.delivered_at).label("day"),
            func.count(Order.id).label("deliveries"),
            func.coalesce(func.sum(Order.distance_km), 0).label("distance"),
            func.coalesce(
                func.sum(25 + 6 * Order.distance_km + Order.tip_amount),
                0,
            ).label("earnings"),
        )
        .filter(
            Order.delivery_partner_id == current_user.id,
            Order.status == "Delivered",
            Order.delivered_at >= start,
            Order.delivered_at < end,
        )
        .group_by(func.date(Order.delivered_at))
        .order_by(func.date(Order.delivered_at))
        .all()
    )

    totals = orders.with_entities(
        func.count(Order.id),
        func.coalesce(func.sum(Order.distance_km), 0),
        func.coalesce(
            func.sum(25 + 6 * Order.distance_km + Order.tip_amount), 0
        ),
    ).first()

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_deliveries": int(totals[0] or 0),
        "total_distance_km": round(float(totals[1] or 0), 2),
        "total_earnings": round(float(totals[2] or 0), 2),
        "daily_summary": [
            {
                "date": row.day.isoformat(),
                "deliveries_completed": row.deliveries,
                "distance_km": round(float(row.distance or 0), 2),
                "earnings": round(float(row.earnings or 0), 2),
            }
            for row in rows
        ],
    }
