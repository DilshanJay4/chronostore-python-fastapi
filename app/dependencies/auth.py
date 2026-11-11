"""FastAPI dependencies for security and authentication."""

import uuid

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError, RateLimitedError
from app.core.security import decode_access_token
from app.db.session import get_db
from app.domain.enums import UserRole
from app.models.entities import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user_payload(
    token: str | None = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not token:
        raise AuthenticationError("Not authenticated.")
    return decode_access_token(token, settings)


def get_current_user(
    payload: dict = Depends(get_current_user_payload),
    session: Session = Depends(get_db),
) -> User:
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError, TypeError) as exc:
        raise AuthenticationError("Invalid token subject.") from exc

    user = session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive.")
    return user


def require_role(*roles: UserRole):
    def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError("Insufficient permissions to perform this action.")
        return user

    return role_checker


require_admin = require_role(UserRole.ADMIN)


def check_auth_rate_limit(request: Request) -> None:
    """Enforce rate limits on authentication endpoints based on client IP."""
    limiter = getattr(request.app.state, "auth_rate_limiter", None)
    if not limiter:
        return
    client_ip = request.client.host if request.client else "unknown"
    key = f"auth:{client_ip}"
    retry_after = limiter.hit(key)
    if retry_after is not None:
        raise RateLimitedError(retry_after_seconds=retry_after)
