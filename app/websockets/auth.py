
import jwt
from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User


def authenticate_websocket(
    websocket: WebSocket,
    db: Session,
) -> User | None:
    token = websocket.query_params.get("token")

    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        if payload.get("type") != "access":
            return None

        subject = payload.get("sub")
        if subject is None:
            return None

        user_id = int(subject)

    except (jwt.PyJWTError, ValueError, TypeError):
        return None

    user = db.query(User).filter(User.id == user_id).first()

    if not user or not user.is_active:
        return None

    return user


async def close_unauthorized(websocket: WebSocket):
    # Close before accepting: clients receive a policy-violation close.
    await websocket.close(code=1008, reason="Invalid or unauthorized token")
