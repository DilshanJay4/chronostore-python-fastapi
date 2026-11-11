import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import decode_access_token
from app.domain.enums import UserRole
from app.schemas.users import (
    AddressCreate,
    UserRegisterRequest,
)
from app.services.auth import AuthService
from app.services.users import UserService

pytestmark = pytest.mark.db


def test_customer_registration_and_login(db_session: Session) -> None:
    settings = get_settings()
    auth_service = AuthService(db_session, settings)

    # Register
    reg_data = UserRegisterRequest(
        email="customer1@example.lk",
        password="SecurePassword123!",
        full_name="Kasun Perera",
        phone="+94771234567",
    )
    user = auth_service.register(reg_data)
    assert user.id is not None
    assert user.email == "customer1@example.lk"
    assert user.role == UserRole.CUSTOMER
    assert user.cart is not None

    # Cannot register duplicate email
    with pytest.raises(ConflictError):
        auth_service.register(reg_data)

    # Login
    tokens = auth_service.login("customer1@example.lk", "SecurePassword123!")
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"

    # Decode and verify claims
    claims = decode_access_token(tokens.access_token, settings)
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "customer"
    assert claims["iss"] == settings.jwt_issuer

    # Invalid password
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        auth_service.login("customer1@example.lk", "WrongPassword!")


def test_refresh_token_rotation_and_replay_protection(db_session: Session) -> None:
    settings = get_settings()
    auth_service = AuthService(db_session, settings)

    auth_service.register(
        UserRegisterRequest(
            email="refresh_test@example.lk",
            password="SecurePassword123!",
            full_name="Sunil Fernando",
        )
    )

    tokens1 = auth_service.login("refresh_test@example.lk", "SecurePassword123!")
    initial_refresh = tokens1.refresh_token

    # Rotate
    tokens2 = auth_service.refresh(initial_refresh)
    assert tokens2.refresh_token != initial_refresh
    assert tokens2.access_token

    # Replay attack: using the old (revoked) refresh token must fail and invalidate tokens
    with pytest.raises(AuthenticationError, match="Replay detected"):
        auth_service.refresh(initial_refresh)

    # After replay detection, even tokens2 should be invalidated
    with pytest.raises(AuthenticationError, match="Invalid refresh token"):
        auth_service.refresh(tokens2.refresh_token)


def test_user_addresses_and_default_flag(db_session: Session) -> None:
    settings = get_settings()
    auth_service = AuthService(db_session, settings)
    user_service = UserService(db_session, settings)

    user = auth_service.register(
        UserRegisterRequest(
            email="address_test@example.lk",
            password="SecurePassword123!",
            full_name="Nuwan Silva",
        )
    )

    # First address automatically becomes default
    addr1 = user_service.add_address(
        user.id,
        AddressCreate(
            label="Home",
            recipient_name="Nuwan Silva",
            phone="0712345678",
            street_line1="123 Galle Road",
            city="Colombo",
            postal_code="00300",
            province="Western",
            country_code="LK",
            is_default=False,
        ),
    )
    assert addr1.is_default is True

    # Second address explicitly marked default unsets addr1's default
    addr2 = user_service.add_address(
        user.id,
        AddressCreate(
            label="Work",
            recipient_name="Nuwan Silva (Office)",
            phone="0112345678",
            street_line1="45 Janadhipathi Mawatha",
            city="Colombo",
            postal_code="00100",
            province="Western",
            country_code="LK",
            is_default=True,
        ),
    )
    assert addr2.is_default is True

    addresses = user_service.get_addresses(user.id)
    assert len(addresses) == 2
    # Verify addr1 is no longer default in the database
    updated_addr1 = next(a for a in addresses if a.id == addr1.id)
    assert updated_addr1.is_default is False
