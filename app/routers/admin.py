from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_roles
from app.database import get_db
from app.models.user import User
from app.schemas.auth import ApprovalResponse

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.put(
    "/users/{user_id}/approve",
    response_model=ApprovalResponse,
)
def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles("Admin")),
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    if user.role not in ("Restaurant Owner", "Delivery Partner"):
        raise HTTPException(
            status_code=400,
            detail="Only Restaurant Owners and Delivery Partners require approval",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=400,
            detail="Inactive users cannot be approved",
        )

    user.is_approved = True
    db.commit()
    db.refresh(user)

    return ApprovalResponse(
        message=f"{user.role} approved successfully",
        user=user,
    )