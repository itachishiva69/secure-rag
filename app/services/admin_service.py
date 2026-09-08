from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Department, Document, User
from app.models.enums import UserRole


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
            func.lower(Department.name)
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
    db.flush()

    return department


def update_department(
    db: Session,
    *,
    department_id: int,
    name: str,
) -> Department:
    department = (
        db.query(Department)
        .filter(
            Department.id == department_id
        )
        .with_for_update()
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    normalized_name = name.strip()

    if not normalized_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department name cannot be empty",
        )

    existing_department = (
        db.query(Department)
        .filter(
            func.lower(Department.name)
            == normalized_name.lower(),
            Department.id != department_id,
        )
        .first()
    )

    if existing_department is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Department already exists",
        )

    department.name = normalized_name

    db.flush()

    return department


def delete_department(
    db: Session,
    *,
    department_id: int,
) -> None:
    department = (
        db.query(Department)
        .filter(
            Department.id == department_id
        )
        .with_for_update()
        .first()
    )

    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found",
        )

    user_count = (
        db.query(
            func.count(User.id)
        )
        .filter(
            User.department_id
            == department_id
        )
        .scalar()
        or 0
    )

    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Department cannot be deleted "
                "while users are assigned to it"
            ),
        )

    document_count = (
        db.query(
            func.count(
                func.distinct(Document.id)
            )
        )
        .join(Document.departments)
        .filter(
            Department.id == department_id
        )
        .scalar()
        or 0
    )

    if document_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Department cannot be deleted "
                "while documents are assigned to it"
            ),
        )

    db.delete(department)
    db.flush()


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
    db.flush()

    return user


def update_user(
    db: Session,
    *,
    user_id: int,
    email: str | None,
    role: UserRole | None,
    department_id: int | None,
    email_provided: bool,
    role_provided: bool,
    department_provided: bool,
) -> User:
    user = (
        db.query(User)
        .filter(
            User.id == user_id
        )
        .with_for_update()
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    new_email = user.email

    if email_provided:
        if email is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email cannot be null",
            )

        new_email = email.strip().lower()

        existing_user = (
            db.query(User)
            .filter(
                func.lower(User.email)
                == new_email,
                User.id != user_id,
            )
            .first()
        )

        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User email already exists",
            )

    if role_provided:
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role cannot be null",
            )

        new_role = role
    else:
        new_role = user.role

    if department_provided:
        new_department_id = department_id
    else:
        new_department_id = user.department_id

    if new_department_id is not None:
        department = db.get(
            Department,
            new_department_id,
        )

        if department is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Department not found",
            )

    if (
        new_role == UserRole.USER
        and new_department_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "A department is required for "
                "user accounts"
            ),
        )

    if (
        user.role == UserRole.ADMIN
        and new_role != UserRole.ADMIN
    ):
        remaining_admins = (
            db.query(
                func.count(User.id)
            )
            .filter(
                User.role == UserRole.ADMIN,
                User.id != user_id,
            )
            .scalar()
            or 0
        )

        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "The last administrator "
                    "cannot be demoted"
                ),
            )

    user.email = new_email
    user.role = new_role
    user.department_id = new_department_id

    db.flush()

    return user



def delete_user(
    db: Session,
    *,
    user_id: int,
    current_user_id: int,
) -> None:
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.id == current_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot delete your own administrator account",
        )

    if user.role == UserRole.ADMIN:
        remaining_admins = (
            db.query(func.count(User.id))
            .filter(
                User.role == UserRole.ADMIN,
                User.id != user_id,
            )
            .scalar()
            or 0
        )

        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last administrator cannot be deleted",
            )

    document_count = (
        db.query(func.count(Document.id))
        .filter(Document.uploaded_by == user_id)
        .scalar()
        or 0
    )

    if document_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "User cannot be deleted while documents are owned by "
                "this account. Delete or reassign those documents first."
            ),
        )

    db.delete(user)
    db.flush()


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
