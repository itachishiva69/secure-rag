from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import AuditLog, Department, Document, User
from app.models.enums import UserRole


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def create_user(
    db_session,
    *,
    role: UserRole,
    department_id: int | None,
):
    user = User(
        email=unique_email("audit-test"),
        password_hash="test-hash",
        role=role,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def test_record_audit_event_persists_expected_fields(
    db_session,
):
    from app.services.audit import record_audit_event

    department = Department(
        name=unique_name("Audit-Department")
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        role=UserRole.USER,
        department_id=department.id,
    )

    audit_log = record_audit_event(
        db_session,
        user=user,
        action="query",
        resource_type="query",
        department_id=department.id,
    )

    db_session.commit()

    stored = db_session.get(
        AuditLog,
        audit_log.id,
    )

    assert stored is not None
    assert stored.user_id == user.id
    assert stored.action == "query"
    assert stored.resource_type == "query"
    assert stored.resource_id is None
    assert stored.department_id == department.id
    assert stored.success is True
    assert stored.created_at is not None


def test_query_creates_audit_record_without_query_text(
    db_session,
    monkeypatch,
):
    department = Department(
        name=unique_name("Audit-Query-Department")
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        role=UserRole.USER,
        department_id=department.id,
    )

    class FakeReranker:
        pass

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        lambda **kwargs: type(
            "SearchResult",
            (),
            {
                "points": [],
            },
        )(),
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: user
    )

    from app.api.query import get_query_reranker

    app.dependency_overrides[get_query_reranker] = (
        lambda: FakeReranker()
    )

    client = TestClient(app)

    sensitive_query = (
        "super-secret confidential project information"
    )

    try:
        response = client.post(
            "/query/",
            json={
                "query": sensitive_query,
                "limit": 5,
            },
        )

        assert response.status_code == 200

        audit_logs = db_session.scalars(
            select(AuditLog)
            .where(
                AuditLog.user_id == user.id
            )
            .where(
                AuditLog.action == "query"
            )
        ).all()

        assert len(audit_logs) == 1

        audit_log = audit_logs[0]

        assert audit_log.resource_type == "query"

        assert sensitive_query not in (
            str(audit_log.__dict__)
        )

    finally:
        app.dependency_overrides.clear()


def test_document_access_creates_success_audit_record(
    db_session,
    monkeypatch,
):
    department = Department(
        name=unique_name("Audit-Document-Department")
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        role=UserRole.USER,
        department_id=department.id,
    )

    document = Document(
        filename="audit-document.txt",
        storage_path="test/audit-document.txt",
        uploaded_by=user.id,
        status="indexed",
    )

    document.departments.append(
        department
    )

    db_session.add(document)
    db_session.flush()

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: user
    )

    client = TestClient(app)

    try:
        response = client.get(
            f"/documents/{document.id}"
        )

        assert response.status_code == 200

        audit_logs = db_session.scalars(
            select(AuditLog)
            .where(
                AuditLog.user_id == user.id
            )
            .where(
                AuditLog.action
                == "document_access"
            )
        ).all()

        assert len(audit_logs) == 1

        audit_log = audit_logs[0]

        assert audit_log.resource_type == (
            "document"
        )

        assert audit_log.resource_id == (
            document.id
        )

        assert audit_log.department_id == (
            department.id
        )

        assert audit_log.success is True

    finally:
        app.dependency_overrides.clear()


def test_unauthorized_document_access_creates_failed_audit_record(
    db_session,
):
    finance = Department(
        name=unique_name("Audit-Finance")
    )

    engineering = Department(
        name=unique_name("Audit-Engineering")
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )
    db_session.flush()

    finance_user = create_user(
        db_session,
        role=UserRole.USER,
        department_id=finance.id,
    )

    engineering_admin = create_user(
        db_session,
        role=UserRole.ADMIN,
        department_id=engineering.id,
    )

    document = Document(
        filename="restricted.txt",
        storage_path="test/restricted.txt",
        uploaded_by=engineering_admin.id,
        status="indexed",
    )

    document.departments.append(
        engineering
    )

    db_session.add(document)
    db_session.flush()

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

        audit_logs = db_session.scalars(
            select(AuditLog)
            .where(
                AuditLog.user_id
                == finance_user.id
            )
            .where(
                AuditLog.action
                == "document_access"
            )
        ).all()

        assert len(audit_logs) == 1

        audit_log = audit_logs[0]

        assert audit_log.resource_id == (
            document.id
        )

        assert audit_log.department_id == (
            finance.id
        )

        assert audit_log.success is False

    finally:
        app.dependency_overrides.clear()