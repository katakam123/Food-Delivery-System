
from datetime import datetime, time
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

# Use the restaurant's local timezone for peak-hour pricing.
LOCAL_TIMEZONE = ZoneInfo("Asia/Kolkata")
SURGE_MULTIPLIER = Decimal("1.5")


def is_peak_hour(now: datetime | None = None) -> bool:
    if now is None:
        now = datetime.now(LOCAL_TIMEZONE)
    elif now.tzinfo is None:
        # Naive timestamps are interpreted as local time here.
        now = now.replace(tzinfo=LOCAL_TIMEZONE)
    else:
        now = now.astimezone(LOCAL_TIMEZONE)

    current_time = now.time().replace(tzinfo=None)

    return (
        time(12, 0) <= current_time < time(14, 0)
        or time(19, 0) <= current_time < time(22, 0)
    )


def calculate_delivery_fee(
    distance_km: Decimal | float,
    now: datetime | None = None,
) -> Decimal:
    distance = Decimal(str(distance_km))

    if distance < 0:
        raise ValueError("Distance cannot be negative")

    # ₹20 for the first 3 km; ₹8 for each additional
    # started kilometre.
    extra_km = max(
        0,
        int((distance - Decimal("3")).to_integral_value(
            rounding="ROUND_CEILING"
        )),
    )
    base_fee = Decimal("20") + Decimal("8") * extra_km

    if is_peak_hour(now):
        base_fee *= SURGE_MULTIPLIER

    return base_fee.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
