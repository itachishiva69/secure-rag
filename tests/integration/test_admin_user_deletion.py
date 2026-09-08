from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import AuditLog, Department, Document, User
from app.models.enums import UserRole


def create_admin(db_session, *, email):
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
    role=UserRole.USER,
):
    user = User(
        email=email,
        password_hash="test-hash",
        role=role,
        department_id=department_id,
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_department(db_session, name):
    department = Department(name=name)
    db_session.add(department)
    db_session.flush()
    return department


def configure_app(db_session, user):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user] = lambda: user


def test_admin_can_delete_user_and_preserve_audit_history(db_session):
    admin = create_admin(db_session, email="delete-admin@example.com")
    department = create_department(db_session, "Delete-User-Department")
    target = create_user(
        db_session,
        email="delete-target@example.com",
        department_id=department.id,
    )

    old_audit = AuditLog(
        user_id=target.id,
        action="query",
        resource_type="query",
        resource_id=None,
        department_id=department.id,
        success=True,
    )
    db_session.add(old_audit)
    db_session.commit()

    target_id = target.id
    old_audit_id = old_audit.id
    configure_app(db_session, admin)

    try:
        client = TestClient(app)
        response = client.delete(f"/users/{target_id}")

        assert response.status_code == 204
        assert db_session.get(User, target_id) is None

        preserved = db_session.get(AuditLog, old_audit_id)
        assert preserved is not None
        assert preserved.user_id is None

        deletion_audit = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.user_id == admin.id,
                AuditLog.action == "user_delete",
                AuditLog.resource_id == target_id,
            )
            .one()
        )
        assert deletion_audit.success is True
    finally:
        app.dependency_overrides.clear()


def test_admin_cannot_delete_self(db_session):
    admin = create_admin(db_session, email="self-delete-admin@example.com")
    db_session.commit()
    configure_app(db_session, admin)

    try:
        client = TestClient(app)
        response = client.delete(f"/users/{admin.id}")

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "You cannot delete your own administrator account"
        )
        db_session.expire_all()
        assert db_session.get(User, admin.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_admin_can_delete_another_admin_when_one_admin_remains(db_session):
    actor = create_admin(
        db_session,
        email="actor-delete-admin@example.com",
    )
    target = create_admin(
        db_session,
        email="target-delete-admin@example.com",
    )
    db_session.commit()
    configure_app(db_session, actor)

    try:
        client = TestClient(app)
        response = client.delete(f"/users/{target.id}")

        assert response.status_code == 204
        assert db_session.get(User, target.id) is None
        assert db_session.get(User, actor.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_user_with_documents_cannot_be_deleted(db_session):
    admin = create_admin(
        db_session,
        email="document-owner-delete-admin@example.com",
    )
    department = create_department(
        db_session,
        "Document-Owner-Department",
    )
    target = create_user(
        db_session,
        email="document-owner@example.com",
        department_id=department.id,
    )

    document = Document(
        filename="owned-document.txt",
        storage_path="test/owned-document.txt",
        uploaded_by=target.id,
        status="indexed",
    )
    document.departments = [department]
    db_session.add(document)
    db_session.commit()

    configure_app(db_session, admin)

    try:
        client = TestClient(app)
        response = client.delete(f"/users/{target.id}")

        assert response.status_code == 409
        assert response.json()["detail"] == (
            "User cannot be deleted while documents are owned by "
            "this account. Delete or reassign those documents first."
        )

        db_session.expire_all()
        assert db_session.get(User, target.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_non_admin_cannot_delete_user(db_session):
    department = create_department(
        db_session,
        "Non-Admin-Delete-Department",
    )
    actor = create_user(
        db_session,
        email="non-admin-actor@example.com",
        department_id=department.id,
    )
    target = create_user(
        db_session,
        email="non-admin-target@example.com",
        department_id=department.id,
    )
    db_session.commit()

    configure_app(db_session, actor)

    try:
        client = TestClient(app)
        response = client.delete(f"/users/{target.id}")

        assert response.status_code == 403
        assert db_session.get(User, target.id) is not None
    finally:
        app.dependency_overrides.clear()


def test_delete_nonexistent_user_returns_404(db_session):
    admin = create_admin(
        db_session,
        email="missing-delete-admin@example.com",
    )
    db_session.commit()
    configure_app(db_session, admin)

    try:
        client = TestClient(app)
        response = client.delete("/users/999999999")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
