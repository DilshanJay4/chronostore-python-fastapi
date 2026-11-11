"""Authentication business service: register, login, refresh rotation, logout."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, hash_token, verify_password
from app.domain.enums import UserRole
from app.models.entities import Cart, RefreshToken, User
from app.schemas.users import TokenResponse, UserRegisterRequest


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def register(self, data: UserRegisterRequest, role: UserRole = UserRole.CUSTOMER) -> User:
        existing = self.session.execute(
            select(User).where(User.email == data.email.lower())
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("A user with this email address already exists.")

        user = User(
            email=data.email.lower(),
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            phone=data.phone,
            role=role,
            is_active=True,
        )
        self.session.add(user)
        self.session.flush()

        # Create cart for new customer
        cart = Cart(user_id=user.id)
        self.session.add(cart)
        self.session.commit()
        self.session.refresh(user)
        return user

    def login(self, email: str, password: str) -> TokenResponse:
        user = self.session.execute(
            select(User).where(User.email == email.lower())
        ).scalar_one_or_none()
        if not user or not verify_password(password, user.password_hash):
            # Generic message to avoid email enumeration
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationError("Account is inactive.")

        return self._issue_tokens(user)

    def refresh(self, raw_refresh_token: str) -> TokenResponse:
        token_hash = hash_token(raw_refresh_token)
        stored_token = self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()

        if not stored_token:
            raise AuthenticationError("Invalid refresh token.")

        now = datetime.now(UTC)

        # Replay attack protection: if a revoked token is used, revoke all tokens for this user
        if stored_token.revoked_at is not None:
            self.session.execute(
                delete(RefreshToken).where(RefreshToken.user_id == stored_token.user_id)
            )
            self.session.commit()
            raise AuthenticationError("Refresh token was previously revoked. Replay detected.")

        if stored_token.expires_at <= now:
            raise AuthenticationError("Refresh token has expired.")

        user = self.session.execute(
            select(User).where(User.id == stored_token.user_id)
        ).scalar_one_or_none()
        if not user or not user.is_active:
            raise AuthenticationError("User is no longer active.")

        # Rotate token
        tokens = self._issue_tokens(user)
        stored_token.revoked_at = now
        stored_token.replaced_by_hash = hash_token(tokens.refresh_token)
        self.session.commit()
        return tokens

    def logout(self, raw_refresh_token: str) -> None:
        token_hash = hash_token(raw_refresh_token)
        stored_token = self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        ).scalar_one_or_none()
        if stored_token and stored_token.revoked_at is None:
            stored_token.revoked_at = datetime.now(UTC)
            self.session.commit()

    def _issue_tokens(self, user: User) -> TokenResponse:
        access_token = create_access_token(user.id, user.role.value, self.settings)
        raw_refresh = secrets.token_urlsafe(48)
        refresh_hash = hash_token(raw_refresh)
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.refresh_token_expire_days)

        token_record = RefreshToken(
            user_id=user.id,
            token_hash=refresh_hash,
            expires_at=expires_at,
        )
        self.session.add(token_record)
        self.session.commit()

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",  # noqa: S106
            expires_in=self.settings.access_token_expire_minutes * 60,
            refresh_token=raw_refresh,
        )
