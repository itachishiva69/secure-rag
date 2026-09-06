from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import (
    Department,
    Document,
    DocumentDepartment,
    OutboxEvent,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services import reconciliation


def unique_name(
    prefix: str,
) -> str:
    return (
        f"{prefix}-{uuid4().hex}"
    )


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
            "Reconciliation"
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
    user = User(
        email=unique_email(
            "reconciliation-admin"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
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
    user_id: int,
    department_id: int,
    status: DocumentStatus = DocumentStatus.PROCESSING,
    processing_started_at: datetime | None = None,
):
    document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=user_id,
        status=status,
        processing_started_at=(
            processing_started_at
            if processing_started_at is not None
            else (
                datetime.now(timezone.utc)
                - timedelta(hours=2)
            )
        ),
    )

    db_session.add(
        document
    )

    db_session.flush()

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=department_id,
        )
    )

    db_session.flush()

    return document


def test_find_stale_processing_documents(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    stale_document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    fresh_document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(minutes=5)
        ),
    )

    stale_ids = (
        reconciliation.find_stale_processing_document_ids(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert stale_document.id in stale_ids
    assert fresh_document.id not in stale_ids


def test_non_processing_documents_are_not_reconciled(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    indexed_document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        status=DocumentStatus.INDEXED,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    failed_document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        status=DocumentStatus.FAILED,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    stale_ids = (
        reconciliation.find_stale_processing_document_ids(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert indexed_document.id not in stale_ids
    assert failed_document.id not in stale_ids


def test_reconciliation_creates_ingestion_outbox_event(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    def fail_direct_enqueue(*args, **kwargs):
        raise AssertionError(
            "reconciliation must not "
            "enqueue directly to Redis/RQ"
        )

    monkeypatch.setattr(
        reconciliation,
        "enqueue_ingestion_job",
        fail_direct_enqueue,
        raising=False,
    )

    recovered_ids = (
        reconciliation.reconcile_stale_processing_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    db_session.refresh(
        document
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "ingest_document",
        )
        .all()
    )

    assert recovered_ids == [
        document.id
    ]

    assert document.status == (
        DocumentStatus.UPLOADED
    )

    assert (
        document.processing_started_at
        is None
    )

    assert len(events) == 1

    assert events[0].status == (
        "pending"
    )

    assert events[0].attempts == 0


def test_reconciliation_does_not_requeue_fresh_document(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(minutes=5)
        ),
    )

    recovered_ids = (
        reconciliation.reconcile_stale_processing_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    db_session.refresh(
        document
    )

    assert recovered_ids == []

    assert document.status == (
        DocumentStatus.PROCESSING
    )

    assert (
        document.processing_started_at
        is not None
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "ingest_document",
        )
        .all()
    )

    assert events == []


def test_reconciliation_rolls_back_when_outbox_creation_fails(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    # Commit the initial document state so the transaction
    # intentionally rolled back by reconciliation does not
    # also remove the test fixture data.
    db_session.commit()

    def failing_outbox_creation(
        db,
        *,
        document_id: int,
    ):
        raise RuntimeError(
            "simulated outbox failure"
        )

    monkeypatch.setattr(
        reconciliation,
        "create_ingestion_outbox_event",
        failing_outbox_creation,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated outbox failure",
    ):
        reconciliation.reconcile_stale_processing_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )

    db_session.refresh(
        document
    )

    assert document.status == (
        DocumentStatus.PROCESSING
    )

    assert (
        document.processing_started_at
        is not None
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "ingest_document",
        )
        .all()
    )

    assert events == []


def test_reconciliation_is_idempotent_after_first_claim(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        processing_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    first_recovery = (
        reconciliation.reconcile_stale_processing_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    second_recovery = (
        reconciliation.reconcile_stale_processing_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "ingest_document",
        )
        .all()
    )

    assert first_recovery == [
        document.id
    ]

    assert second_recovery == []

    assert len(events) == 1

    assert events[0].status == (
        "pending"
    )