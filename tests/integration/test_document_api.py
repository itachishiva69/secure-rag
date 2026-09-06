from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.enums import UserRole


def create_test_data(db_session):
    finance = Department(name="Finance")
    engineering = Department(name="Engineering")

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )
    db_session.flush()

    finance_user = User(
        email="finance-api@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=finance.id,
    )

    engineering_user = User(
        email="engineering-api@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=engineering.id,
    )

    db_session.add_all(
        [
            finance_user,
            engineering_user,
        ]
    )
    db_session.flush()

    document = Document(
        filename="engineering-secret.txt",
        storage_path="test/engineering-secret.txt",
        uploaded_by=engineering_user.id,
        status="indexed",
    )

    db_session.add(document)
    db_session.flush()

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=engineering.id,
        )
    )

    db_session.flush()

    return (
        finance_user,
        engineering_user,
        document,
    )


def test_finance_user_cannot_get_engineering_document(
    db_session,
):
    (
        finance_user,
        _,
        document,
    ) = create_test_data(db_session)

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: finance_user
    )

    client = TestClient(app)

    try:
        response = client.get(
            f"/documents/{document.id}"
        )

        assert response.status_code == 404

        body = response.json()

        assert body["detail"] == (
            "Document not found"
        )
        assert body["request_id"]
        assert response.headers["X-Request-ID"] == (
            body["request_id"]
        )

    finally:
        app.dependency_overrides.clear()


def test_engineering_user_can_get_engineering_document(
    db_session,
):
    (
        _,
        engineering_user,
        document,
    ) = create_test_data(db_session)

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: engineering_user
    )

    client = TestClient(app)

    try:
        response = client.get(
            f"/documents/{document.id}"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == document.id
        assert body["filename"] == (
            "engineering-secret.txt"
        )
        assert body["department_ids"] == [
            engineering_user.department_id
        ]

    finally:
        app.dependency_overrides.clear()