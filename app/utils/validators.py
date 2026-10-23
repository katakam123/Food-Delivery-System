
import re

from pydantic import AfterValidator
from typing import Annotated


def validate_phone(value: str) -> str:
    if not re.fullmatch(r"[0-9]{10}", value):
        raise ValueError("Phone number must contain exactly 10 digits")
    return value


def validate_pincode(value: str) -> str:
    if not re.fullmatch(r"[0-9]{6}", value):
        raise ValueError("Pincode must contain exactly 6 digits")
    return value


def validate_vehicle_number(value: str) -> str:
    value = value.strip().upper()
    if not value:
        raise ValueError("Vehicle number cannot be empty")
    return value


PhoneNumber = Annotated[str, AfterValidator(validate_phone)]
Pincode = Annotated[str, AfterValidator(validate_pincode)]
VehicleNumber = Annotated[str, AfterValidator(validate_vehicle_number)]
