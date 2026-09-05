import pytest
from fastapi import HTTPException

from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.enums import UserRole
from app.services.document_service import (
    get_document_for_user,
)


def create_department(db_session, name):
    department = Department(name=name)

    db_session.add(department)
    db_session.flush()

    return department


def create_user(
    db_session,
    email,
    department_id,
):
    user = User(
        email=email,
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def create_document(
    db_session,
    user_id,
    department_id,
):
    document = Document(
        filename="engineering-secret.txt",
        storage_path="test/engineering-secret.txt",
        uploaded_by=user_id,
        status="indexed",
    )

    db_session.add(document)
    db_session.flush()

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=department_id,
        )
    )

    db_session.flush()

    return document


def test_user_can_access_document_in_own_department(
    db_session,
):
    engineering = create_department(
        db_session,
        "Engineering",
    )

    user = create_user(
        db_session,
        "engineering-test@example.com",
        engineering.id,
    )

    document = create_document(
        db_session,
        user.id,
        engineering.id,
    )

    result = get_document_for_user(
        db=db_session,
        document_id=document.id,
        current_user=user,
    )

    assert result.id == document.id


def test_user_cannot_access_document_in_other_department(
    db_session,
):
    finance = create_department(
        db_session,
        "Finance",
    )

    engineering = create_department(
        db_session,
        "Engineering",
    )

    finance_user = create_user(
        db_session,
        "finance-test@example.com",
        finance.id,
    )

    document = create_document(
        db_session,
        finance_user.id,
        engineering.id,
    )

    with pytest.raises(HTTPException) as exc_info:
        get_document_for_user(
            db=db_session,
            document_id=document.id,
            current_user=finance_user,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Document not found"