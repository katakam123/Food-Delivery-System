from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


PublicRole = Literal[
    "Customer",
    "Restaurant Owner",
    "Delivery Partner",
]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: PublicRole = "Customer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: str
    is_active: bool
    is_approved: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApprovalResponse(BaseModel):
    message: str
    user: UserResponse