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
            "DeletionReconciliation"
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
            "deletion-reconciliation-admin"
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


def create_deleting_document(
    db_session,
    *,
    user_id: int,
    department_id: int,
    deletion_started_at: datetime | None = None,
):
    document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=user_id,
        status=DocumentStatus.DELETING,
        deletion_started_at=(
            deletion_started_at
            if deletion_started_at is not None
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


def create_outbox_event(
    db_session,
    *,
    document_id: int,
    event_type: str,
    status: str = "pending",
):
    event = OutboxEvent(
        event_type=event_type,
        document_id=document_id,
        status=status,
        attempts=0,
    )

    db_session.add(
        event
    )

    db_session.flush()

    return event


def test_find_stale_deleting_documents(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    stale_document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        deletion_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    fresh_document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        deletion_started_at=(
            datetime.now(timezone.utc)
            - timedelta(minutes=5)
        ),
    )

    stale_ids = (
        reconciliation.find_stale_deleting_document_ids(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert stale_document.id in stale_ids
    assert fresh_document.id not in stale_ids


def test_non_deleting_documents_are_not_reconciled(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    indexed_document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=user.id,
        status=DocumentStatus.INDEXED,
        deletion_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    processing_document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=user.id,
        status=DocumentStatus.PROCESSING,
        deletion_started_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
    )

    db_session.add_all(
        [
            indexed_document,
            processing_document,
        ]
    )

    db_session.flush()

    stale_ids = (
        reconciliation.find_stale_deleting_document_ids(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert indexed_document.id not in stale_ids
    assert processing_document.id not in stale_ids


def test_stale_deleting_document_creates_cleanup_outbox_event(
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

    document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    def fail_direct_enqueue(*args, **kwargs):
        raise AssertionError(
            "reconciliation must not enqueue directly "
            "to Redis/RQ"
        )

    monkeypatch.setattr(
        reconciliation,
        "enqueue_cleanup_job",
        fail_direct_enqueue,
        raising=False,
    )

    recovered_ids = (
        reconciliation.reconcile_stale_deleting_documents(
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
            == "delete_document",
        )
        .all()
    )

    assert recovered_ids == [
        document.id
    ]

    assert document.status == (
        DocumentStatus.DELETING
    )

    assert len(events) == 1

    assert events[0].status == (
        "pending"
    )

    assert events[0].attempts == 0


def test_pending_cleanup_event_prevents_repeated_recovery(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    create_outbox_event(
        db_session,
        document_id=document.id,
        event_type="delete_document",
        status="pending",
    )

    stale_ids = (
        reconciliation.find_stale_deleting_document_ids(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert document.id not in stale_ids

    recovered_ids = (
        reconciliation.reconcile_stale_deleting_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert recovered_ids == []

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "delete_document",
        )
        .all()
    )

    assert len(events) == 1


def test_dispatched_cleanup_event_can_be_recovered_again(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    create_outbox_event(
        db_session,
        document_id=document.id,
        event_type="delete_document",
        status="dispatched",
    )

    recovered_ids = (
        reconciliation.reconcile_stale_deleting_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    assert recovered_ids == [
        document.id
    ]

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "delete_document",
        )
        .order_by(OutboxEvent.id)
        .all()
    )

    assert len(events) == 2
    assert events[0].status == "dispatched"
    assert events[1].status == "pending"


def test_reconciliation_rolls_back_when_delete_outbox_creation_fails(
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

    document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    db_session.commit()

    def failing_outbox_creation(
        db,
        *,
        document_id: int,
    ):
        raise RuntimeError(
            "simulated delete outbox failure"
        )

    monkeypatch.setattr(
        reconciliation,
        "create_delete_outbox_event",
        failing_outbox_creation,
    )

    with pytest.raises(
        RuntimeError,
        match="simulated delete outbox failure",
    ):
        reconciliation.reconcile_stale_deleting_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )

    db_session.refresh(
        document
    )

    assert document.status == (
        DocumentStatus.DELETING
    )

    assert (
        document.deletion_started_at
        is not None
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "delete_document",
        )
        .all()
    )

    assert events == []


def test_reconciliation_does_not_recover_fresh_deleting_document(
    db_session,
):
    department = create_department(
        db_session
    )

    user = create_admin(
        db_session,
        department.id,
    )

    document = create_deleting_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
        deletion_started_at=(
            datetime.now(timezone.utc)
            - timedelta(minutes=5)
        ),
    )

    recovered_ids = (
        reconciliation.reconcile_stale_deleting_documents(
            db_session,
            stale_after=timedelta(minutes=30),
        )
    )

    db_session.refresh(
        document
    )

    assert recovered_ids == []

    assert document.status == (
        DocumentStatus.DELETING
    )

    events = (
        db_session.query(OutboxEvent)
        .filter(
            OutboxEvent.document_id
            == document.id,
            OutboxEvent.event_type
            == "delete_document",
        )
        .all()
    )

    assert events == []