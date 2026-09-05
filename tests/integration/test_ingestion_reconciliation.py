from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services import reconciliation


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


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


def test_reconciliation_requeues_stale_document(
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

    enqueued_ids: list[int] = []

    def fake_enqueue(
        document_id: int,
    ):
        enqueued_ids.append(
            document_id
        )

    monkeypatch.setattr(
        reconciliation,
        "enqueue_ingestion_job",
        fake_enqueue,
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

    assert recovered_ids == [
        document.id
    ]

    assert enqueued_ids == [
        document.id
    ]

    assert document.status == (
        DocumentStatus.UPLOADED
    )

    assert (
        document.processing_started_at
        is None
    )


def test_reconciliation_does_not_requeue_fresh_document(
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
            - timedelta(minutes=5)
        ),
    )

    enqueued_ids: list[int] = []

    def fake_enqueue(
        document_id: int,
    ):
        enqueued_ids.append(
            document_id
        )

    monkeypatch.setattr(
        reconciliation,
        "enqueue_ingestion_job",
        fake_enqueue,
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
    assert enqueued_ids == []

    assert document.status == (
        DocumentStatus.PROCESSING
    )

    assert (
        document.processing_started_at
        is not None
    )


def test_reconciliation_marks_document_failed_when_requeue_fails(
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

    def failing_enqueue(
        document_id: int,
    ):
        raise RuntimeError(
            "simulated enqueue failure"
        )

    monkeypatch.setattr(
        reconciliation,
        "enqueue_ingestion_job",
        failing_enqueue,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated enqueue failure",
    ):
        reconciliation.reconcile_stale_processing_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )

    db_session.refresh(
        document
    )

    assert document.status == (
        DocumentStatus.FAILED
    )

    assert (
        document.processing_started_at
        is None
    )


def test_reconciliation_is_idempotent_after_first_claim(
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

    enqueued_ids: list[int] = []

    def fake_enqueue(
        document_id: int,
    ):
        enqueued_ids.append(
            document_id
        )

    monkeypatch.setattr(
        reconciliation,
        "enqueue_ingestion_job",
        fake_enqueue,
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

    assert first_recovery == [
        document.id
    ]

    assert second_recovery == []

    assert enqueued_ids == [
        document.id
    ]