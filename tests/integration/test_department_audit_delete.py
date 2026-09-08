from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import AuditLog, Department, User
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


def test_unused_department_with_audit_history_can_be_deleted(
    db_session,
):
    admin = create_admin(
        db_session,
        email="audit-delete-admin@example.com",
    )

    department = create_department(
        db_session,
        "Audited Department",
    )

    audit_log = AuditLog(
        user_id=admin.id,
        action="department_update",
        resource_type="department",
        resource_id=department.id,
        department_id=department.id,
        success=True,
    )

    db_session.add(audit_log)
    db_session.commit()

    audit_log_id = audit_log.id
    department_id = department.id

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(app)

    try:
        response = client.delete(
            f"/departments/{department_id}"
        )

        assert response.status_code == 204

        db_session.expire_all()

        assert db_session.get(
            Department,
            department_id,
        ) is None

        preserved_audit_log = db_session.get(
            AuditLog,
            audit_log_id,
        )

        assert preserved_audit_log is not None
        assert (
            preserved_audit_log.department_id
            is None
        )

        assert (
            preserved_audit_log.resource_id
            == department_id
        )

    finally:
        app.dependency_overrides.clear()
