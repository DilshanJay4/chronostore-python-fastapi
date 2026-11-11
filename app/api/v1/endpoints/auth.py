"""Endpoints for authentication (registration, login, refresh, logout)."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.openapi import AUTH_RESPONSES, RATE_LIMIT_RESPONSE, VALIDATION_RESPONSE, responses
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.dependencies.auth import check_auth_rate_limit
from app.schemas.users import (
    LoginRequest,
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
    summary="Login to obtain access and refresh tokens (JSON or OAuth2 password form)",
    dependencies=[Depends(check_auth_rate_limit)],
    responses=responses(AUTH_RESPONSES, VALIDATION_RESPONSE, RATE_LIMIT_RESPONSE),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": LoginRequest.model_json_schema(),
                },
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "required": ["username", "password"],
                        "properties": {
                            "username": {"type": "string", "format": "email"},
                            "password": {"type": "string", "format": "password"},
                            "grant_type": {"type": "string", "default": "password"},
                            "scope": {"type": "string", "default": ""},
                        },
                    }
                },
            },
        }
    },
)
async def login(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            raw_json = await request.json()
            parsed = LoginRequest.model_validate(raw_json)
            email = str(parsed.email)
            password = parsed.password
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc
        except Exception as exc:
            raise RequestValidationError(
                [{"loc": ["body"], "msg": "Invalid JSON body", "type": "value_error.jsondecode"}]
            ) from exc
    else:
        form = await request.form()
        username = form.get("username") or form.get("email")
        password_val = form.get("password")
        errors = []
        if not username or not isinstance(username, str):
            errors.append(
                {"loc": ["body", "username"], "msg": "Field required", "type": "missing"}
            )
        if not password_val or not isinstance(password_val, str):
            errors.append(
                {"loc": ["body", "password"], "msg": "Field required", "type": "missing"}
            )
        if errors:
            raise RequestValidationError(errors)
        email = str(username)
        password = str(password_val)

    service = AuthService(session, settings)
    return service.login(email, password)


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
