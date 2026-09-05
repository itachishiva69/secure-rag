from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, Document, User
from app.models.enums import UserRole


def create_admin(
    db_session,
    *,
    email,
):
    admin = User(
        email=email,
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=None,
    )

    db_session.add(admin)
    db_session.flush()

    return admin


def create_user(
    db_session,
    *,
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


def create_department(
    db_session,
    name,
):
    department = Department(
        name=name
    )

    db_session.add(department)
    db_session.flush()

    return department


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


def test_admin_can_rename_department(
    db_session,
):
    admin = create_admin(
        db_session,
        email="update-admin@example.com",
    )

    department = create_department(
        db_session,
        "Engineering",
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/departments/{department.id}",
            json={
                "name": "Platform Engineering"
            },
        )

        assert response.status_code == 200
        assert response.json()["name"] == (
            "Platform Engineering"
        )

        db_session.expire_all()

        refreshed = db_session.get(
            Department,
            department.id,
        )

        assert refreshed is not None
        assert refreshed.name == (
            "Platform Engineering"
        )

    finally:
        app.dependency_overrides.clear()


def test_duplicate_department_rename_returns_409(
    db_session,
):
    admin = create_admin(
        db_session,
        email="rename-admin@example.com",
    )

    engineering = create_department(
        db_session,
        "Engineering",
    )

    create_department(
        db_session,
        "Finance",
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/departments/{engineering.id}",
            json={
                "name": "finance"
            },
        )

        assert response.status_code == 409

        db_session.expire_all()

        refreshed = db_session.get(
            Department,
            engineering.id,
        )

        assert refreshed is not None
        assert refreshed.name == "Engineering"

    finally:
        app.dependency_overrides.clear()


def test_department_cannot_be_deleted_with_users(
    db_session,
):
    admin = create_admin(
        db_session,
        email="department-delete-admin@example.com",
    )

    department = create_department(
        db_session,
        "Engineering",
    )

    create_user(
        db_session,
        email="department-user@example.com",
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.delete(
            f"/departments/{department.id}"
        )

        assert response.status_code == 409

        department_in_db = db_session.get(
            Department,
            department.id,
        )

        assert department_in_db is not None

    finally:
        app.dependency_overrides.clear()


def test_department_cannot_be_deleted_with_documents(
    db_session,
):
    admin = create_admin(
        db_session,
        email="document-delete-admin@example.com",
    )

    department = create_department(
        db_session,
        "Engineering",
    )

    document = Document(
        filename="dependent.txt",
        storage_path="test/dependent.txt",
        uploaded_by=admin.id,
        status="indexed",
    )

    document.departments = [
        department
    ]

    db_session.add(document)
    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.delete(
            f"/departments/{department.id}"
        )

        assert response.status_code == 409

        department_in_db = db_session.get(
            Department,
            department.id,
        )

        assert department_in_db is not None

    finally:
        app.dependency_overrides.clear()


def test_unused_department_can_be_deleted(
    db_session,
):
    admin = create_admin(
        db_session,
        email="unused-delete-admin@example.com",
    )

    department = create_department(
        db_session,
        "Unused",
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.delete(
            f"/departments/{department.id}"
        )

        assert response.status_code == 204

        assert db_session.get(
            Department,
            department.id,
        ) is None

    finally:
        app.dependency_overrides.clear()


def test_admin_can_change_user_department(
    db_session,
):
    admin = create_admin(
        db_session,
        email="change-dept-admin@example.com",
    )

    engineering = create_department(
        db_session,
        "Engineering",
    )

    finance = create_department(
        db_session,
        "Finance",
    )

    user = create_user(
        db_session,
        email="change-dept-user@example.com",
        department_id=engineering.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/users/{user.id}",
            json={
                "department_id": finance.id
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["department_id"] == finance.id

        db_session.expire_all()

        refreshed = db_session.get(
            User,
            user.id,
        )

        assert refreshed is not None
        assert refreshed.department_id == finance.id

    finally:
        app.dependency_overrides.clear()


def test_user_cannot_be_changed_to_no_department(
    db_session,
):
    admin = create_admin(
        db_session,
        email="null-dept-admin@example.com",
    )

    department = create_department(
        db_session,
        "Engineering",
    )

    user = create_user(
        db_session,
        email="null-dept-user@example.com",
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/users/{user.id}",
            json={
                "department_id": None
            },
        )

        assert response.status_code == 400

        db_session.expire_all()

        refreshed = db_session.get(
            User,
            user.id,
        )

        assert refreshed is not None
        assert refreshed.department_id == (
            department.id
        )

    finally:
        app.dependency_overrides.clear()


def test_admin_can_promote_user(
    db_session,
):
    admin = create_admin(
        db_session,
        email="promote-admin@example.com",
    )

    department = create_department(
        db_session,
        "Engineering",
    )

    user = create_user(
        db_session,
        email="promote-user@example.com",
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/users/{user.id}",
            json={
                "role": "admin"
            },
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    finally:
        app.dependency_overrides.clear()


def test_last_admin_cannot_be_demoted(
    db_session,
):
    admin = create_admin(
        db_session,
        email="last-admin@example.com",
    )

    department = create_department(
        db_session,
        "Engineering",
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/users/{admin.id}",
            json={
                "role": "user",
                "department_id": department.id,
            },
        )

        assert response.status_code == 409

        db_session.expire_all()

        refreshed = db_session.get(
            User,
            admin.id,
        )

        assert refreshed is not None
        assert refreshed.role == (
            UserRole.ADMIN
        )

    finally:
        app.dependency_overrides.clear()


def test_non_admin_cannot_update_user(
    db_session,
):
    department = create_department(
        db_session,
        "Engineering",
    )

    user = create_user(
        db_session,
        email="regular-user@example.com",
        department_id=department.id,
    )

    target = create_user(
        db_session,
        email="target-user@example.com",
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.patch(
            f"/users/{target.id}",
            json={
                "role": "admin"
            },
        )

        assert response.status_code == 403

    finally:
        app.dependency_overrides.clear()