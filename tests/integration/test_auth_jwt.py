from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.database import get_db
from app.main import app
from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.enums import UserRole


def use_test_database(db_session):
    app.dependency_overrides[get_db] = lambda: db_session


def create_test_user(
    db_session,
    *,
    email,
    password,
    department_id,
):
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole.USER,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def create_test_document(
    db_session,
    *,
    uploaded_by,
    department_id,
):
    document = Document(
        filename="engineering-secret.txt",
        storage_path="test/engineering-secret.txt",
        uploaded_by=uploaded_by,
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


def login(client, email, password):
    return client.post(
        "/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )


def test_valid_login_returns_jwt(db_session):
    department = Department(
        name="Engineering"
    )

    db_session.add(department)
    db_session.flush()

    create_test_user(
        db_session,
        email="jwt-login@example.com",
        password="correct-password",
        department_id=department.id,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    response = login(
        client,
        "jwt-login@example.com",
        "correct-password",
    )

    assert response.status_code == 200

    body = response.json()

    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["access_token"]


def test_invalid_password_returns_401(db_session):
    department = Department(
        name="Engineering"
    )

    db_session.add(department)
    db_session.flush()

    create_test_user(
        db_session,
        email="jwt-invalid-password@example.com",
        password="correct-password",
        department_id=department.id,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    response = login(
        client,
        "jwt-invalid-password@example.com",
        "wrong-password",
    )

    assert response.status_code == 401

    assert response.json() == {
        "detail": "Invalid email or password"
    }


def test_missing_token_returns_401():
    app.dependency_overrides.clear()

    client = TestClient(app)

    response = client.get(
        "/auth/me"
    )

    assert response.status_code == 401


def test_malformed_token_returns_401():
    app.dependency_overrides.clear()

    client = TestClient(app)

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer not-a-real-jwt",
        },
    )

    assert response.status_code == 401


def test_expired_token_returns_401(db_session):
    department = Department(
        name="Engineering"
    )

    db_session.add(department)
    db_session.flush()

    user = create_test_user(
        db_session,
        email="jwt-expired@example.com",
        password="correct-password",
        department_id=department.id,
    )

    settings = get_settings()

    expired_at = (
        datetime.now(timezone.utc)
        - timedelta(minutes=1)
    )

    expired_token = jwt.encode(
        {
            "sub": str(user.id),
            "exp": expired_at,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {expired_token}",
        },
    )

    assert response.status_code == 401


def test_finance_jwt_cannot_access_engineering_document(
    db_session,
):
    finance = Department(
        name="Finance"
    )

    engineering = Department(
        name="Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )

    db_session.flush()

    finance_user = create_test_user(
        db_session,
        email="jwt-finance@example.com",
        password="finance-password",
        department_id=finance.id,
    )

    document = create_test_document(
        db_session,
        uploaded_by=finance_user.id,
        department_id=engineering.id,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    login_response = login(
        client,
        "jwt-finance@example.com",
        "finance-password",
    )

    assert login_response.status_code == 200

    token = login_response.json()[
        "access_token"
    ]

    response = client.get(
        f"/documents/{document.id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": "Document not found"
    }


def test_engineering_jwt_can_access_engineering_document(
    db_session,
):
    engineering = Department(
        name="Engineering"
    )

    db_session.add(engineering)
    db_session.flush()

    engineering_user = create_test_user(
        db_session,
        email="jwt-engineering@example.com",
        password="engineering-password",
        department_id=engineering.id,
    )

    document = create_test_document(
        db_session,
        uploaded_by=engineering_user.id,
        department_id=engineering.id,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    login_response = login(
        client,
        "jwt-engineering@example.com",
        "engineering-password",
    )

    assert login_response.status_code == 200

    token = login_response.json()[
        "access_token"
    ]

    response = client.get(
        f"/documents/{document.id}",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == document.id
    assert body["filename"] == "engineering-secret.txt"
    assert body["department_ids"] == [
        engineering.id
    ]