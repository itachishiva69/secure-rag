from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_api
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
from app.services.rate_limit import (
    RateLimitError,
    RateLimitExceeded,
)


def use_test_database(db_session):
    app.dependency_overrides[get_db] = (
        lambda: db_session
    )


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


def disable_login_rate_limiting(monkeypatch):
    limiter = FakeRateLimiter()

    monkeypatch.setattr(
        auth_api,
        "get_login_ip_rate_limiter",
        lambda: limiter,
    )

    monkeypatch.setattr(
        auth_api,
        "get_login_email_rate_limiter",
        lambda: limiter,
    )

    return limiter


class FakeRateLimiter:
    def __init__(self):
        self.calls = []

    def check(self, *, subject):
        self.calls.append(subject)


class FailingRateLimiter:
    def check(self, *, subject):
        raise RateLimitError(
            "simulated redis failure"
        )


class ExceededRateLimiter:
    def __init__(self):
        self.calls = []

    def check(self, *, subject):
        self.calls.append(subject)

        raise RateLimitExceeded(
            limit=5,
            window_seconds=60,
        )


@pytest.fixture(autouse=True)
def isolate_login_rate_limiting(monkeypatch):
    limiter = FakeRateLimiter()

    monkeypatch.setattr(
        auth_api,
        "get_login_ip_rate_limiter",
        lambda: limiter,
    )

    monkeypatch.setattr(
        auth_api,
        "get_login_email_rate_limiter",
        lambda: limiter,
    )


def test_valid_login_returns_jwt(
    db_session,
):
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
    assert isinstance(
        body["access_token"],
        str,
    )
    assert body["access_token"]


def test_invalid_password_returns_401(
    db_session,
):
    department = Department(
        name="Engineering"
    )

    db_session.add(department)
    db_session.flush()

    create_test_user(
        db_session,
        email=(
            "jwt-invalid-password@example.com"
        ),
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

    body = response.json()

    assert body["detail"] == (
        "Invalid email or password"
    )
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == (
        body["request_id"]
    )


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
            "Authorization": (
                "Bearer not-a-real-jwt"
            ),
        },
    )

    assert response.status_code == 401


def test_expired_token_returns_401(
    db_session,
):
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
            "Authorization": (
                f"Bearer {expired_token}"
            ),
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

    response = login(
        client,
        "jwt-finance@example.com",
        "finance-password",
    )

    assert response.status_code == 200

    token = response.json()["access_token"]

    response = client.get(
        f"/documents/{document.id}",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
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


def test_engineering_jwt_can_access_engineering_document(
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

    response = login(
        client,
        "jwt-engineering@example.com",
        "engineering-password",
    )

    assert response.status_code == 200

    token = response.json()["access_token"]

    response = client.get(
        f"/documents/{document.id}",
        headers={
            "Authorization": (
                f"Bearer {token}"
            ),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == document.id
    assert body["filename"] == (
        "engineering-secret.txt"
    )


def test_login_rate_limit_allows_valid_login(
    db_session,
    monkeypatch,
):
    department = Department(
        name="Login Rate Limit Success"
    )

    db_session.add(department)
    db_session.flush()

    create_test_user(
        db_session,
        email="login-rate-success@example.com",
        password="correct-password",
        department_id=department.id,
    )

    fake_limiter = FakeRateLimiter()

    monkeypatch.setattr(
        auth_api,
        "get_login_ip_rate_limiter",
        lambda: fake_limiter,
    )

    monkeypatch.setattr(
        auth_api,
        "get_login_email_rate_limiter",
        lambda: fake_limiter,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    response = login(
        client,
        "login-rate-success@example.com",
        "correct-password",
    )

    assert response.status_code == 200

    assert len(fake_limiter.calls) == 2


def test_login_rate_limit_returns_429(
    db_session,
    monkeypatch,
):
    department = Department(
        name="Login Rate Limit Exceeded"
    )

    db_session.add(department)
    db_session.flush()

    create_test_user(
        db_session,
        email="login-rate-exceeded@example.com",
        password="correct-password",
        department_id=department.id,
    )

    limiter = ExceededRateLimiter()

    monkeypatch.setattr(
        auth_api,
        "get_login_ip_rate_limiter",
        lambda: limiter,
    )

    monkeypatch.setattr(
        auth_api,
        "get_login_email_rate_limiter",
        lambda: limiter,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    response = login(
        client,
        "login-rate-exceeded@example.com",
        "wrong-password",
    )

    assert response.status_code == 429

    body = response.json()

    assert body["detail"] == (
        "Too many login attempts. "
        "Please try again later."
    )
    assert body["request_id"]

    assert response.headers["X-Request-ID"] == (
        body["request_id"]
    )

    assert response.headers["Retry-After"] == (
        "60"
    )


def test_login_rate_limit_failure_returns_503(
    db_session,
    monkeypatch,
):
    failing_limiter = FailingRateLimiter()

    monkeypatch.setattr(
        auth_api,
        "get_login_ip_rate_limiter",
        lambda: failing_limiter,
    )

    monkeypatch.setattr(
        auth_api,
        "get_login_email_rate_limiter",
        lambda: failing_limiter,
    )

    app.dependency_overrides.clear()
    use_test_database(db_session)

    client = TestClient(app)

    response = login(
        client,
        "does-not-matter@example.com",
        "wrong-password",
    )

    assert response.status_code == 503

    body = response.json()

    assert body["detail"] == (
        "The request protection service "
        "is temporarily unavailable."
    )
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == (
        body["request_id"]
    )