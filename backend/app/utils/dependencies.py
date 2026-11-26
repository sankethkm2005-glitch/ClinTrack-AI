"""FastAPI dependencies for session extraction, CSRF validation, and role authorization."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.utils.security import verify_session_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Extract authenticated user from HTTP-only session cookie."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. No session cookie provided.",
        )
    
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again.",
        )
    
    # CSRF check for state-mutating HTTP methods
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_header or csrf_header != payload.get("csrf"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token validation failed.",
            )

    user = db.query(User).filter(User.id == payload.get("sub"), User.is_active == True).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account is deactivated.",
        )
    return user


def require_role(allowed_roles: list[str]):
    """Enforce role authorization."""
    def _role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: role '{user.role}' is not authorized for this resource.",
            )
        return user
    return _role_checker


require_patient = require_role(["patient"])
require_doctor = require_role(["doctor"])


def require_verified_doctor(user: User = Depends(require_doctor)) -> User:
    """Ensure doctor account has been verified by an administrator."""
    if not user.doctor_profile or user.doctor_profile.verification_status != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor account verification required. Your account is currently pending or not verified.",
        )
    return user

