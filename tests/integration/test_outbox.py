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
from app.services import outbox


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
            "Outbox"
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
            "outbox-admin"
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
):
    document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=user_id,
        status=DocumentStatus.UPLOADED,
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


def test_create_ingestion_outbox_event(
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
        user_id=admin.id,
        department_id=department.id,
    )

    event = (
        outbox.create_ingestion_outbox_event(
            db_session,
            document_id=document.id,
        )
    )

    db_session.commit()

    saved_event = db_session.get(
        OutboxEvent,
        event.id,
    )

    assert saved_event is not None
    assert saved_event.document_id == (
        document.id
    )
    assert saved_event.event_type == (
        outbox.INGEST_DOCUMENT_EVENT
    )
    assert saved_event.status == (
        outbox.OUTBOX_PENDING
    )
    assert saved_event.attempts == 0


def test_dispatch_marks_event_dispatched(
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
        user_id=admin.id,
        department_id=department.id,
    )

    event = (
        outbox.create_ingestion_outbox_event(
            db_session,
            document_id=document.id,
        )
    )

    db_session.commit()

    calls: list[tuple[int, str]] = []

    def fake_enqueue(
        document_id: int,
        *,
        job_id: str | None = None,
    ):
        calls.append(
            (
                document_id,
                job_id,
            )
        )

    monkeypatch.setattr(
        outbox,
        "enqueue_ingestion_job",
        fake_enqueue,
    )

    dispatched_ids = (
        outbox.dispatch_pending_outbox_events(
            db_session
        )
    )

    db_session.refresh(
        event
    )

    assert dispatched_ids == [
        event.id
    ]

    assert calls == [
        (
            document.id,
            f"document-ingestion-outbox-{event.id}",
        )
    ]

    assert event.status == (
        outbox.OUTBOX_DISPATCHED
    )

    assert event.dispatched_at is not None
    assert event.last_error is None
    assert event.attempts == 1


def test_dispatch_failure_keeps_event_pending(
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
        user_id=admin.id,
        department_id=department.id,
    )

    event = (
        outbox.create_ingestion_outbox_event(
            db_session,
            document_id=document.id,
        )
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

    db_session.refresh(
        event
    )

    assert dispatched_ids == []

    assert event.status == (
        outbox.OUTBOX_PENDING
    )

    assert event.attempts == 1

    assert event.last_error == (
        "simulated Redis failure"
    )

    assert (
        event.available_at
        > datetime.now(timezone.utc)
    )


def test_dispatch_ignores_future_events(
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
        user_id=admin.id,
        department_id=department.id,
    )

    event = (
        outbox.create_ingestion_outbox_event(
            db_session,
            document_id=document.id,
        )
    )

    event.available_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=10)
    )

    db_session.commit()

    calls: list[int] = []

    def fake_enqueue(
        document_id: int,
        *,
        job_id: str | None = None,
    ):
        calls.append(
            document_id
        )

    monkeypatch.setattr(
        outbox,
        "enqueue_ingestion_job",
        fake_enqueue,
    )

    dispatched_ids = (
        outbox.dispatch_pending_outbox_events(
            db_session
        )
    )

    assert dispatched_ids == []
    assert calls == []


def test_dispatch_continues_after_one_failure(
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

    first_document = create_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
    )

    second_document = create_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
    )

    first_event = (
        outbox.create_ingestion_outbox_event(
            db_session,
            document_id=first_document.id,
        )
    )

    second_event = (
        outbox.create_ingestion_outbox_event(
            db_session,
            document_id=second_document.id,
        )
    )

    db_session.commit()

    calls: list[int] = []

    def enqueue_with_first_failure(
        document_id: int,
        *,
        job_id: str | None = None,
    ):
        if document_id == first_document.id:
            raise RuntimeError(
                "first event failed"
            )

        calls.append(
            document_id
        )

    monkeypatch.setattr(
        outbox,
        "enqueue_ingestion_job",
        enqueue_with_first_failure,
    )

    dispatched_ids = (
        outbox.dispatch_pending_outbox_events(
            db_session
        )
    )

    db_session.refresh(
        first_event
    )

    db_session.refresh(
        second_event
    )

    assert dispatched_ids == [
        second_event.id
    ]

    assert first_event.status == (
        outbox.OUTBOX_PENDING
    )

    assert second_event.status == (
        outbox.OUTBOX_DISPATCHED
    )

    assert calls == [
        second_document.id
    ]