from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, User
from app.models.enums import UserRole


def create_admin(db_session):
    admin = User(
        email="management-admin@example.com",
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=None,
    )

    db_session.add(admin)
    db_session.flush()

    return admin


def create_user(
    db_session,
    department_id=None,
):
    user = User(
        email="management-user@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def configure_app(
    db_session,
    user,
):
    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: user
    )


def test_non_admin_cannot_create_department(
    db_session,
):
    user = create_user(
        db_session
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/departments/",
            json={
                "name": "Finance"
            },
        )

        assert response.status_code == 403

        department = (
            db_session.query(Department)
            .filter(
                Department.name == "Finance"
            )
            .first()
        )

        assert department is None

    finally:
        app.dependency_overrides.clear()


def test_admin_can_create_department(
    db_session,
):
    admin = create_admin(
        db_session
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/departments/",
            json={
                "name": "Finance"
            },
        )

        assert response.status_code == 201

        body = response.json()

        assert body["name"] == "Finance"
        assert body["id"] > 0

    finally:
        app.dependency_overrides.clear()


def test_admin_cannot_create_duplicate_department(
    db_session,
):
    admin = create_admin(
        db_session
    )

    existing = Department(
        name="Finance"
    )

    db_session.add(existing)
    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/departments/",
            json={
                "name": "finance"
            },
        )

        assert response.status_code == 409

    finally:
        app.dependency_overrides.clear()


def test_admin_can_create_user(
    db_session,
):
    admin = create_admin(
        db_session
    )

    department = Department(
        name="Engineering"
    )

    db_session.add(department)
    db_session.flush()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/users/",
            json={
                "email": "new-user@example.com",
                "password": "strong-password",
                "role": "user",
                "department_id": department.id,
            },
        )

        assert response.status_code == 201

        body = response.json()

        assert body["email"] == (
            "new-user@example.com"
        )
        assert body["role"] == "user"
        assert body["department_id"] == (
            department.id
        )

        created_user = (
            db_session.query(User)
            .filter(
                User.email
                == "new-user@example.com"
            )
            .first()
        )

        assert created_user is not None
        assert created_user.password_hash != (
            "strong-password"
        )

    finally:
        app.dependency_overrides.clear()


def test_user_cannot_create_user(
    db_session,
):
    user = create_user(
        db_session
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/users/",
            json={
                "email": "another-user@example.com",
                "password": "strong-password",
                "role": "user",
            },
        )

        assert response.status_code == 403

    finally:
        app.dependency_overrides.clear()


def test_user_role_requires_department(
    db_session,
):
    admin = create_admin(
        db_session
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/users/",
            json={
                "email": "departmentless-user@example.com",
                "password": "strong-password",
                "role": "user",
            },
        )

        assert response.status_code == 400

    finally:
        app.dependency_overrides.clear()


def test_admin_can_list_users(
    db_session,
):
    admin = create_admin(
        db_session
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.get(
            "/users/"
        )

        assert response.status_code == 200

        body = response.json()

        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

        assert body["total"] >= 1

    finally:
        app.dependency_overrides.clear()


def test_admin_can_list_departments(
    db_session,
):
    admin = create_admin(
        db_session
    )

    department = Department(
        name="Engineering"
    )

    db_session.add(department)
    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.get(
            "/departments/"
        )

        assert response.status_code == 200

        body = response.json()

        assert len(body) == 1
        assert body[0]["name"] == "Engineering"

    finally:
        app.dependency_overrides.clear()