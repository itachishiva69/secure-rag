from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, Document, User
from app.models.document_status import DocumentStatus
from app.models.outbox_event import OutboxEvent
from app.models.enums import UserRole
from app.services import jobs


def unique_name(
    prefix: str,
) -> str:
    return f"{prefix}-{uuid4().hex}"


def unique_email(
    prefix: str,
) -> str:
    return (
        f"{prefix}-{uuid4().hex}"
        "@example.com"
    )


def create_department(
    db_session,
):
    department = Department(
        name=unique_name(
            "Deletion"
        )
    )

    db_session.add(
        department
    )

    db_session.flush()

    return department


def create_admin(
    db_session,
    department_id: int,
):
    admin = User(
        email=unique_email(
            "deletion-admin"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )

    db_session.add(
        admin
    )

    db_session.flush()

    return admin


def create_user(
    db_session,
    department_id: int,
):
    user = User(
        email=unique_email(
            "deletion-user"
        ),
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department_id,
    )

    db_session.add(
        user
    )

    db_session.flush()

    return user


def create_document(
    db_session,
    *,
    uploaded_by: int,
    department_id: int,
    status: DocumentStatus = DocumentStatus.INDEXED,
    storage_path: str = "storage/documents/delete-test.txt",
):
    document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=storage_path,
        uploaded_by=uploaded_by,
        status=status,
    )

    department = db_session.get(
        Department,
        department_id,
    )

    assert department is not None

    document.departments = [
        department
    ]

    db_session.add(
        document
    )

    db_session.flush()

    return document


def configure_app(
    db_session,
    user,
):
    app.dependency_overrides[
        get_db
    ] = lambda: db_session

    app.dependency_overrides[
        get_current_user
    ] = lambda: user


@pytest.fixture(
    autouse=True
)
def clear_overrides():
    app.dependency_overrides.clear()

    yield

    app.dependency_overrides.clear()


def bind_jobs_to_test_database(
    db_session,
    monkeypatch,
):
    test_session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
    )

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        test_session_factory,
    )


def test_non_admin_cannot_delete_document(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_user(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        uploaded_by=user.id,
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        user,
    )

    client = TestClient(
        app
    )

    response = client.delete(
        f"/documents/{document.id}"
    )

    assert response.status_code == 403

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None

    assert document_in_db.status == (
        DocumentStatus.INDEXED
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id
        )
        .all()
    )

    assert events == []


def test_delete_rejects_processing_document(
    db_session,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.PROCESSING,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    response = client.delete(
        f"/documents/{document.id}"
    )

    assert response.status_code == 409

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None

    assert document_in_db.status == (
        DocumentStatus.PROCESSING
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id
        )
        .all()
    )

    assert events == []


def test_delete_marks_document_deleting_and_creates_pending_event(
    db_session,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    response = client.delete(
        f"/documents/{document.id}"
    )

    assert response.status_code == 202

    response_data = response.json()

    assert response_data["id"] == (
        document.id
    )

    assert response_data["status"] == (
        "deleting"
    )

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None

    assert document_in_db.status == (
        DocumentStatus.DELETING
    )

    assert document_in_db.deletion_started_at is not None

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id
        )
        .all()
    )

    assert len(events) == 1

    event = events[0]

    assert event.event_type == (
        "delete_document"
    )

    assert event.status == (
        "pending"
    )

    assert event.document_id == (
        document.id
    )


def test_delete_nonexistent_document_returns_404(
    db_session,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    response = client.delete(
        "/documents/999999"
    )

    assert response.status_code == 404

    events = (
        db_session.query(OutboxEvent)
        .all()
    )

    assert events == []


def test_get_hides_deleting_document(
    db_session,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.DELETING,
    )

    db_session.commit()

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    response = client.get(
        f"/documents/{document.id}"
    )

    assert response.status_code == 404


def test_cleanup_job_deletes_qdrant_then_file_then_database_row(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_file = (
        tmp_path
        / "document.txt"
    )

    storage_file.write_text(
        "cleanup test",
        encoding="utf-8",
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.DELETING,
        storage_path=str(
            storage_file
        ),
    )

    document.deletion_started_at = (
        datetime.now(timezone.utc)
    )

    document_id = document.id

    db_session.commit()

    bind_jobs_to_test_database(
        db_session,
        monkeypatch,
    )

    call_order: list[str] = []

    def fake_delete_vectors(
        document_id: int,
    ):
        assert document_id == (
            document_id_expected
        )

        call_order.append(
            "qdrant"
        )

    document_id_expected = document_id

    monkeypatch.setattr(
        jobs,
        "delete_document_vectors",
        fake_delete_vectors,
    )

    original_unlink = Path.unlink

    def tracking_unlink(
        self,
        missing_ok=False,
    ):
        call_order.append(
            "file"
        )

        return original_unlink(
            self,
            missing_ok=missing_ok,
        )

    monkeypatch.setattr(
        Path,
        "unlink",
        tracking_unlink,
    )

    jobs.delete_document_job(
        document_id
    )

    assert call_order == [
        "qdrant",
        "file",
    ]

    assert not storage_file.exists()

    deleted_document = (
        db_session.get(
            Document,
            document_id,
        )
    )

    assert deleted_document is None


def test_cleanup_job_is_idempotent_when_file_is_missing(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_file = (
        tmp_path
        / "already-missing.txt"
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.DELETING,
        storage_path=str(
            storage_file
        ),
    )

    document.deletion_started_at = (
        datetime.now(timezone.utc)
    )

    document_id = document.id

    db_session.commit()

    bind_jobs_to_test_database(
        db_session,
        monkeypatch,
    )

    qdrant_calls: list[int] = []

    def fake_delete_vectors(
        deleted_document_id: int,
    ):
        qdrant_calls.append(
            deleted_document_id
        )

    monkeypatch.setattr(
        jobs,
        "delete_document_vectors",
        fake_delete_vectors,
    )

    jobs.delete_document_job(
        document_id
    )

    assert qdrant_calls == [
        document_id
    ]

    assert not storage_file.exists()

    deleted_document = (
        db_session.get(
            Document,
            document_id,
        )
    )

    assert deleted_document is None


def test_cleanup_job_qdrant_failure_keeps_document_deleting(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_file = (
        tmp_path
        / "qdrant-failure.txt"
    )

    storage_file.write_text(
        "must survive qdrant failure",
        encoding="utf-8",
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.DELETING,
        storage_path=str(
            storage_file
        ),
    )

    document_id = document.id

    document.deletion_started_at = (
        datetime.now(timezone.utc)
    )

    db_session.commit()

    bind_jobs_to_test_database(
        db_session,
        monkeypatch,
    )

    def failing_delete_vectors(
        document_id: int,
    ):
        raise RuntimeError(
            "simulated qdrant failure"
        )

    monkeypatch.setattr(
        jobs,
        "delete_document_vectors",
        failing_delete_vectors,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated qdrant failure",
    ):
        jobs.delete_document_job(
            document_id
        )

    document_in_db = (
        db_session.get(
            Document,
            document_id,
        )
    )

    assert document_in_db is not None

    assert document_in_db.status == (
        DocumentStatus.DELETING
    )

    assert (
        document_in_db.deletion_started_at
        is not None
    )

    assert storage_file.exists()


def test_cleanup_job_ignores_non_deleting_document(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_file = (
        tmp_path
        / "indexed.txt"
    )

    storage_file.write_text(
        "should remain",
        encoding="utf-8",
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.INDEXED,
        storage_path=str(
            storage_file
        ),
    )

    document_id = document.id

    db_session.commit()

    bind_jobs_to_test_database(
        db_session,
        monkeypatch,
    )

    qdrant_calls: list[int] = []

    def fake_delete_vectors(
        deleted_document_id: int,
    ):
        qdrant_calls.append(
            deleted_document_id
        )

    monkeypatch.setattr(
        jobs,
        "delete_document_vectors",
        fake_delete_vectors,
    )

    jobs.delete_document_job(
        document_id
    )

    assert qdrant_calls == []

    assert storage_file.exists()

    document_in_db = (
        db_session.get(
            Document,
            document_id,
        )
    )

    assert document_in_db is not None

    assert document_in_db.status == (
        DocumentStatus.INDEXED
    )


def test_cleanup_job_is_idempotent_when_document_is_missing(
    db_session,
    monkeypatch,
):
    bind_jobs_to_test_database(
        db_session,
        monkeypatch,
    )

    db_session.commit()

    jobs.delete_document_job(
        999999
    )