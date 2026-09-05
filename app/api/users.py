from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from app.services.admin_service import (
    create_user,
    list_users,
    update_user,
)
from app.services.audit import record_audit_event


router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


password_hasher = PasswordHash.recommended()


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_endpoint(
    data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        try:
            role = UserRole(
                data.role.lower().strip()
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user role",
            ) from exc

        password_hash = password_hasher.hash(
            data.password
        )

        user = create_user(
            db=db,
            email=str(data.email),
            password_hash=password_hash,
            role=role,
            department_id=data.department_id,
        )

        record_audit_event(
            db,
            user=current_user,
            action="user_create",
            resource_type="user",
            resource_id=user.id,
            department_id=user.department_id,
            success=True,
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user",
        ) from exc

    return user


@router.get(
    "/",
    response_model=UserListResponse,
)
def list_users_endpoint(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users, total = list_users(
        db=db,
        limit=limit,
        offset=offset,
    )

    record_audit_event(
        db,
        user=current_user,
        action="user_list",
        resource_type="user",
        resource_id=None,
        department_id=None,
        success=True,
    )

    db.commit()

    return UserListResponse(
        items=users,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
)
def update_user_endpoint(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        role = None

        if "role" in data.model_fields_set:
            if data.role is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Role cannot be null",
                )

            try:
                role = UserRole(
                    data.role.lower().strip()
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid user role",
                ) from exc

        user = update_user(
            db=db,
            user_id=user_id,
            email=(
                str(data.email)
                if data.email is not None
                else None
            ),
            role=role,
            department_id=data.department_id,
            email_provided=(
                "email" in data.model_fields_set
            ),
            role_provided=(
                "role" in data.model_fields_set
            ),
            department_provided=(
                "department_id"
                in data.model_fields_set
            ),
        )

        record_audit_event(
            db,
            user=current_user,
            action="user_update",
            resource_type="user",
            resource_id=user.id,
            department_id=user.department_id,
            success=True,
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user",
        ) from exc

    return user