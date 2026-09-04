from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from jwt.exceptions import PyJWTError

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models import User
from app.models.enums import UserRole


bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        bearer_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        user_id = decode_access_token(token)
    except (PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    return current_user