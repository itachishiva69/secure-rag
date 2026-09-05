from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Department, User
from app.models.enums import UserRole
from app.schemas.department import DepartmentCreate


def create_department(
    db: Session,
    *,
    name: str,
) -> Department:
    normalized_name = name.strip()

    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department name cannot be empty",
        )

    existing_department = (
        db.query(Department)
        .filter(
            func.lower(
                Department.name
            )
            == normalized_name.lower()
        )
        .first()
    )

    if existing_department is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department already exists",
        )

    department = Department(
        name=normalized_name
    )

    db.add(department)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department already exists",
        ) from exc

    return department


def create_user(
    db: Session,
    *,
    email: str,
    password_hash: str,
    role: UserRole,
    department_id: int | None,
) -> User:
    normalized_email = email.strip().lower()

    existing_user = (
        db.query(User)
        .filter(
            func.lower(User.email)
            == normalized_email
        )
        .first()
    )

    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User email already exists",
        )

    if role == UserRole.USER:
        if department_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A department is required for "
                    "user accounts"
                ),
            )

    if department_id is not None:
        department = db.get(
            Department,
            department_id,
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department not found",
            )

    user = User(
        email=normalized_email,
        password_hash=password_hash,
        role=role,
        department_id=department_id,
    )

    db.add(user)

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User email already exists",
        ) from exc

    return user


def list_users(
    db: Session,
    *,
    limit: int,
    offset: int,
) -> tuple[list[User], int]:
    total = (
        db.query(
            func.count(User.id)
        )
        .scalar()
        or 0
    )

    users = (
        db.query(User)
        .order_by(
            User.created_at.desc(),
            User.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return users, total