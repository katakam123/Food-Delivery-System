
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


def handle_integrity_error(exc: IntegrityError) -> HTTPException:
    message = str(exc.orig).lower()

    if "email" in message:
        detail = "Email address already exists"
    elif "order_number" in message:
        detail = "Order number already exists"
    elif "vehicle_number" in message:
        detail = "Vehicle number already exists"
    elif "coupon" in message or "code" in message:
        detail = "Coupon code already exists"
    else:
        detail = "A record with these values already exists"

    return HTTPException(status_code=409, detail=detail)
