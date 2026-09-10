from datetime import datetime, timezone
from uuid import uuid4

from app.models import (
    Department,
    Document,
    DocumentDepartment,
    OutboxEvent,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services import outbox


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def create_department(db_session):
    department = Department(
        name=unique_name("OutboxRecovery")
    )
    db_session.add(department)
    db_session.flush()
    return department


def create_admin(db_session, department_id: int):
    user = User(
        email=unique_email("outbox-recovery-admin"),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )
    db_session.add(user)
    db_session.flush()
    return user


def create_document(
    db_session,
    *,
    user_id: int,
    department_id: int,
):
    document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=user_id,
        status=DocumentStatus.UPLOADED,
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


def test_dispatch_failure_recovers_orphaned_processing_document(
    db_session,
    monkeypatch,
):
    department = create_department(db_session)
    admin = create_admin(
        db_session,
        department.id,
    )
    document = create_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
    )

    document.status = DocumentStatus.PROCESSING
    document.processing_started_at = (
        datetime.now(timezone.utc)
    )

    event = outbox.create_ingestion_outbox_event(
        db_session,
        document_id=document.id,
    )

    db_session.commit()

    def failing_enqueue(
        document_id: int,
        *,
        job_id: str | None = None,
    ):
        raise RuntimeError(
            "simulated Redis failure"
        )

    monkeypatch.setattr(
        outbox,
        "enqueue_ingestion_job",
        failing_enqueue,
    )

    dispatched_ids = (
        outbox.dispatch_pending_outbox_events(
            db_session
        )
    )

    db_session.refresh(document)
    db_session.refresh(event)

    assert dispatched_ids == []

    assert document.status == (
        DocumentStatus.UPLOADED
    )
    assert document.processing_started_at is None

    assert event.status == (
        outbox.OUTBOX_PENDING
    )
    assert event.attempts == 1
    assert event.last_error == (
        "simulated Redis failure"
    )
    assert event.available_at > (
        datetime.now(timezone.utc)
    )
