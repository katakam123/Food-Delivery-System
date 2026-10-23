
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.utils.pricing import (
    calculate_delivery_fee,
    is_peak_hour,
)

IST = ZoneInfo("Asia/Kolkata")


def test_normal_delivery_fee():
    now = datetime(2026, 10, 23, 15, 0, tzinfo=IST)
    assert calculate_delivery_fee(5, now) == Decimal("36.00")


def test_lunch_surge():
    now = datetime(2026, 10, 23, 12, 30, tzinfo=IST)
    assert is_peak_hour(now)
    assert calculate_delivery_fee(5, now) == Decimal("54.00")


def test_dinner_surge():
    now = datetime(2026, 10, 23, 20, 0, tzinfo=IST)
    assert is_peak_hour(now)
    assert calculate_delivery_fee(5, now) == Decimal("54.00")


def test_peak_hour_boundaries():
    assert not is_peak_hour(
        datetime(2026, 10, 23, 14, 0, tzinfo=IST)
    )
    assert not is_peak_hour(
        datetime(2026, 10, 23, 22, 0, tzinfo=IST)
    )


def test_negative_distance_is_rejected():
    try:
        calculate_delivery_fee(-1)
        assert False, "Expected ValueError"
    except ValueError:
        pass
