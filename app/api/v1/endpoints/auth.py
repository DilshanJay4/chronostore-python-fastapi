"""Endpoints for authentication (registration, login, refresh, logout)."""

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.openapi import AUTH_RESPONSES, RATE_LIMIT_RESPONSE, VALIDATION_RESPONSE, responses
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import check_auth_rate_limit
from app.schemas.users import (
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer account",
    dependencies=[Depends(check_auth_rate_limit)],
    responses=responses(VALIDATION_RESPONSE, RATE_LIMIT_RESPONSE),
)
def register(
    data: UserRegisterRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    service = AuthService(session, settings)
    user = service.register(data)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login to obtain access and refresh tokens (OAuth2 password form)",
    dependencies=[Depends(check_auth_rate_limit)],
    responses=responses(AUTH_RESPONSES, RATE_LIMIT_RESPONSE),
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    service = AuthService(session, settings)
    return service.login(form_data.username, form_data.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new access token",
    dependencies=[Depends(check_auth_rate_limit)],
    responses=responses(AUTH_RESPONSES, RATE_LIMIT_RESPONSE),
)
def refresh(
    data: RefreshTokenRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    service = AuthService(session, settings)
    return service.refresh(data.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
def logout(
    data: LogoutRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> None:
    service = AuthService(session, settings)
    service.logout(data.refresh_token)

