from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, Document, User
from app.models.document_status import DocumentStatus
from app.models.outbox_event import OutboxEvent
from app.services import document_service, jobs


def create_department(db_session):
    department = Department(
        name="Engineering",
    )
    db_session.add(department)
    db_session.flush()

    return department


def create_admin(
    db_session,
    department_id,
):
    admin = User(
        email="admin-delete@example.com",
        password_hash="hashed-password",
        role="admin",
        department_id=department_id,
    )
    db_session.add(admin)
    db_session.flush()

    return admin


def create_user(
    db_session,
    department_id,
):
    user = User(
        email="user-delete@example.com",
        password_hash="hashed-password",
        role="user",
        department_id=department_id,
    )
    db_session.add(user)
    db_session.flush()

    return user


def create_document(
    db_session,
    *,
    uploaded_by,
    department_id,
    status=DocumentStatus.INDEXED,
    storage_path="storage/documents/delete-test.txt",
):
    document = Document(
        filename="delete-test.txt",
        storage_path=storage_path,
        uploaded_by=uploaded_by,
        status=status,
    )

    department = db_session.get(
        Department,
        department_id,
    )

    document.departments = [department]

    db_session.add(document)
    db_session.flush()

    return document


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


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()

    yield

    app.dependency_overrides.clear()


def test_non_admin_cannot_delete_document(
    db_session,
    monkeypatch,
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

    delete_called = False

    def fail_if_delete_called(
        document_id: int,
    ):
        nonlocal delete_called

        delete_called = True

    monkeypatch.setattr(
        document_service,
        "delete_document_vectors",
        fail_if_delete_called,
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
    assert delete_called is False

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None
    assert document_in_db.status == DocumentStatus.INDEXED

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id == document.id
        )
        .all()
    )

    assert events == []


def test_delete_rejects_processing_document(
    db_session,
    monkeypatch,
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

    delete_called = False

    def fail_if_delete_called(
        document_id: int,
    ):
        nonlocal delete_called

        delete_called = True

    monkeypatch.setattr(
        document_service,
        "delete_document_vectors",
        fail_if_delete_called,
    )

    # The DELETE endpoint rolls back its transaction
    # for the expected 409 response. The document must
    # therefore already be committed before the request.
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
    assert delete_called is False

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None
    assert document_in_db.status == DocumentStatus.PROCESSING

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id == document.id
        )
        .all()
    )

    assert events == []


def test_delete_marks_document_deleting_and_creates_pending_event(
    db_session,
    monkeypatch,
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

    deleted_document_ids = []

    def fake_delete_document_vectors(
        document_id: int,
    ):
        deleted_document_ids.append(
            document_id
        )

    monkeypatch.setattr(
        document_service,
        "delete_document_vectors",
        fake_delete_document_vectors,
    )

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

    assert deleted_document_ids == [
        document.id
    ]

    response_data = response.json()

    assert response_data["id"] == document.id
    assert response_data["status"] == "deleting"

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None
    assert document_in_db.status == DocumentStatus.DELETING

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id == document.id
        )
        .all()
    )

    assert len(events) == 1

    event = events[0]

    assert event.event_type == "delete_document"
    assert event.status == "pending"
    assert event.document_id == document.id


def test_delete_qdrant_failure_does_not_mark_document_deleting(
    db_session,
    monkeypatch,
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

    def failing_delete(
        document_id: int,
    ):
        raise RuntimeError(
            "simulated qdrant failure"
        )

    monkeypatch.setattr(
        document_service,
        "delete_document_vectors",
        failing_delete,
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

    assert response.status_code == 503

    document_in_db = db_session.get(
        Document,
        document.id,
    )

    assert document_in_db is not None
    assert document_in_db.status == DocumentStatus.INDEXED

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id == document.id
        )
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


def test_cleanup_job_removes_file_and_database_record(
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

    storage_path = (
        tmp_path
        / "cleanup.txt"
    )

    storage_path.write_text(
        "document to delete",
        encoding="utf-8",
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_id=department.id,
        status=DocumentStatus.DELETING,
        storage_path=str(storage_path),
    )

    document_id = document.id

    db_session.commit()

    # jobs.py imports SessionLocal when the module is
    # imported. That factory points at the application's
    # normal DB, while integration tests use secure_rag_test.
    #
    # Bind a fresh session factory to the same test connection
    # so the real cleanup job logic runs against the test DB.
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

    jobs.delete_document_job(
        document_id
    )

    assert not storage_path.exists()

    deleted_document = db_session.get(
        Document,
        document_id,
    )

    assert deleted_document is None


def test_cleanup_job_is_idempotent_when_document_is_missing(
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

    missing_document_id = 999999

    db_session.commit()

    jobs.delete_document_job(
        missing_document_id
    )
