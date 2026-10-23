
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import DeliveryOffer, DeliveryPartner, Order, Restaurant
from app.websockets.auth import (
    authenticate_websocket,
    close_unauthorized,
)
from app.websockets.manager import manager
from app.websockets.tracking import build_tracking_payload

router = APIRouter()


def is_order_participant(db: Session, order: Order, user) -> bool:
    if user.role == "Admin":
        return True

    if order.customer_id == user.id:
        return True

    if order.delivery_partner_id == user.id:
        return True

    if user.role == "Restaurant Owner":
        return (
            db.query(Restaurant.id)
            .filter(
                Restaurant.id == order.restaurant_id,
                Restaurant.owner_id == user.id,
            )
            .first()
            is not None
        )

    return False


@router.websocket("/ws/orders/{order_id}")
async def order_tracking(websocket: WebSocket, order_id: int):
    db = SessionLocal()
    user = authenticate_websocket(websocket, db)

    if not user:
        await close_unauthorized(websocket)
        db.close()
        return

    order = db.query(Order).filter(Order.id == order_id).first()

    if not order or not is_order_participant(db, order, user):
        await close_unauthorized(websocket)
        db.close()
        return

    await manager.connect_order(order_id, user.id, websocket)

    try:
        await websocket.send_json(build_tracking_payload(db, order))

        # Keep the connection alive. Actual updates are pushed by the
        # status and location endpoints through the manager.
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect_order(order_id, user.id, websocket)
        db.close()


@router.websocket("/ws/restaurant")
async def restaurant_alerts(websocket: WebSocket):
    db = SessionLocal()
    user = authenticate_websocket(websocket, db)

    if (
        not user
        or user.role != "Restaurant Owner"
        or not user.is_active
        or not user.is_approved
    ):
        await close_unauthorized(websocket)
        db.close()
        return

    await manager.connect_restaurant(user.id, websocket)

    try:
        await websocket.send_json({
            "event": "connected",
            "message": "Restaurant alerts connected",
        })
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect_restaurant(user.id, websocket)
        db.close()


@router.websocket("/ws/partner")
async def partner_alerts(websocket: WebSocket):
    db = SessionLocal()
    user = authenticate_websocket(websocket, db)

    partner = None
    if user and user.role == "Delivery Partner" and user.is_active:
        partner = (
            db.query(DeliveryPartner)
            .filter(
                DeliveryPartner.user_id == user.id,
                DeliveryPartner.is_approved.is_(True),
            )
            .first()
        )

    if not user or not user.is_approved or not partner:
        await close_unauthorized(websocket)
        db.close()
        return

    await manager.connect_partner(user.id, websocket)

    try:
        await websocket.send_json({
            "event": "connected",
            "message": "Delivery partner alerts connected",
        })
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await manager.disconnect_partner(user.id, websocket)
        db.close()
