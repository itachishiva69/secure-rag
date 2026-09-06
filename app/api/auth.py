import hashlib

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    verify_password,
)
from app.db.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.rate_limit import (
    RateLimitError,
    RateLimitExceeded,
    RateLimiter,
    get_login_email_rate_limiter,
    get_login_ip_rate_limiter,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


def _normalize_login_email(
    email: str,
) -> str:
    return email.strip().lower()


def _email_rate_limit_subject(
    email: str,
) -> str:
    normalized = _normalize_login_email(
        email
    )

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def _get_client_ip(
    request: Request,
) -> str:
    if request.client is None:
        return "unknown"

    return request.client.host


def _enforce_login_rate_limits(
    *,
    request: Request,
    email: str,
) -> None:
    ip_rate_limiter = (
        get_login_ip_rate_limiter()
    )

    email_rate_limiter = (
        get_login_email_rate_limiter()
    )

    try:
        ip_rate_limiter.check(
            subject=_get_client_ip(request)
        )

        email_rate_limiter.check(
            subject=_email_rate_limit_subject(
                email
            )
        )

    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many login attempts. "
                "Please try again later."
            ),
            headers={
                "Retry-After": str(
                    exc.window_seconds
                ),
            },
        ) from exc

    except RateLimitError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The request protection service "
                "is temporarily unavailable."
            ),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    request: LoginRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    _enforce_login_rate_limits(
        request=http_request,
        email=request.email,
    )

    normalized_email = (
        _normalize_login_email(
            request.email
        )
    )

    result = db.execute(
        select(User).where(
            User.email == normalized_email
        )
    )

    user = result.scalar_one_or_none()

    if user is None or not verify_password(
        request.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_401_UNAUTHORIZED
            ),
            detail="Invalid email or password",
        )

    token = create_access_token(user.id)

    return TokenResponse(
        access_token=token,
    )


@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(
        get_current_user
    ),
):
    return current_user