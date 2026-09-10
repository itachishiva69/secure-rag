import logging
from datetime import datetime, timedelta, timezone

from rq.exceptions import DuplicateJobError
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Document, OutboxEvent
from app.models.document_status import DocumentStatus
from app.services.queue import (
    enqueue_cleanup_job,
    enqueue_ingestion_job,
)


logger = logging.getLogger(__name__)


INGEST_DOCUMENT_EVENT = (
    "ingest_document"
)

DELETE_DOCUMENT_EVENT = (
    "delete_document"
)

OUTBOX_PENDING = "pending"
OUTBOX_DISPATCHED = "dispatched"

DISPATCH_RETRY_SECONDS = 60


def _find_pending_event(
    db: Session,
    *,
    document_id: int,
    event_type: str,
) -> OutboxEvent | None:
    return (
        db.query(OutboxEvent)
        .filter(
            and_(
                OutboxEvent.document_id
                == document_id,
                OutboxEvent.event_type
                == event_type,
                OutboxEvent.status
                == OUTBOX_PENDING,
            )
        )
        .order_by(
            OutboxEvent.id
        )
        .first()
    )


def create_ingestion_outbox_event(
    db: Session,
    *,
    document_id: int,
) -> OutboxEvent:
    existing = _find_pending_event(
        db,
        document_id=document_id,
        event_type=INGEST_DOCUMENT_EVENT,
    )

    if existing is not None:
        return existing

    event = OutboxEvent(
        event_type=INGEST_DOCUMENT_EVENT,
        document_id=document_id,
        status=OUTBOX_PENDING,
        attempts=0,
    )

    db.add(event)
    db.flush()

    return event


def create_delete_outbox_event(
    db: Session,
    *,
    document_id: int,
) -> OutboxEvent:
    existing = _find_pending_event(
        db,
        document_id=document_id,
        event_type=DELETE_DOCUMENT_EVENT,
    )

    if existing is not None:
        return existing

    event = OutboxEvent(
        event_type=DELETE_DOCUMENT_EVENT,
        document_id=document_id,
        status=OUTBOX_PENDING,
        attempts=0,
    )

    db.add(event)
    db.flush()

    return event


def _claim_next_pending_event(
    db: Session,
) -> OutboxEvent | None:
    now = datetime.now(
        timezone.utc
    )

    event = (
        db.query(OutboxEvent)
        .filter(
            and_(
                OutboxEvent.status
                == OUTBOX_PENDING,
                OutboxEvent.available_at
                <= now,
            )
        )
        .order_by(
            OutboxEvent.id
        )
        .with_for_update(
            skip_locked=True
        )
        .first()
    )

    if event is None:
        return None

    event.attempts += 1

    db.commit()

    return event


def _mark_event_dispatched(
    db: Session,
    event: OutboxEvent,
) -> None:
    event.status = (
        OUTBOX_DISPATCHED
    )

    event.dispatched_at = (
        datetime.now(timezone.utc)
    )

    event.last_error = None

    db.commit()


def _mark_event_retryable(
    db: Session,
    event: OutboxEvent,
    exc: Exception,
) -> None:
    if event.event_type == INGEST_DOCUMENT_EVENT:
        document = db.get(
            Document,
            event.document_id,
        )

        # A process restart can leave ingestion stuck in
        # PROCESSING even though the durable outbox event still
        # needs delivery. Reset that orphaned state so the retry
        # can enter the normal UPLOADED -> PROCESSING transition.
        if (
            document is not None
            and document.status
            == DocumentStatus.PROCESSING
        ):
            document.status = (
                DocumentStatus.UPLOADED
            )
            document.processing_started_at = None

            logger.warning(
                "outbox_ingestion_state_recovered",
                extra={
                    "outbox_event_id": event.id,
                    "document_id": event.document_id,
                },
            )

    event.available_at = (
        datetime.now(timezone.utc)
        + timedelta(
            seconds=DISPATCH_RETRY_SECONDS
        )
    )

    event.last_error = str(
        exc
    )

    db.commit()


def _dispatch_event(
    event: OutboxEvent,
) -> None:
    if event.event_type == (
        INGEST_DOCUMENT_EVENT
    ):
        enqueue_ingestion_job(
            document_id=event.document_id,
            job_id=(
                f"document-ingestion-outbox-"
                f"{event.id}"
            ),
        )

        return

    if event.event_type == (
        DELETE_DOCUMENT_EVENT
    ):
        enqueue_cleanup_job(
            document_id=event.document_id,
            job_id=(
                f"document-cleanup-outbox-"
                f"{event.id}"
            ),
        )

        return

    raise ValueError(
        f"Unsupported outbox event type: "
        f"{event.event_type}"
    )


def dispatch_pending_outbox_events(
    db: Session,
) -> list[int]:
    dispatched_ids: list[int] = []

    while True:
        event = (
            _claim_next_pending_event(
                db
            )
        )

        if event is None:
            break

        try:
            _dispatch_event(
                event
            )

        except DuplicateJobError:
            # The database transaction may have failed after
            # Redis accepted the job. On the next dispatcher
            # pass RQ reports that the deterministic unique job
            # already exists. That means delivery already
            # succeeded and the outbox event can safely be
            # finalized.
            logger.info(
                "outbox_event_job_already_exists",
                extra={
                    "outbox_event_id": event.id,
                    "document_id": event.document_id,
                    "event_type": event.event_type,
                },
            )

            _mark_event_dispatched(
                db,
                event,
            )

            dispatched_ids.append(
                event.id
            )

        except Exception as exc:
            logger.exception(
                "outbox_event_dispatch_failed",
                extra={
                    "outbox_event_id": event.id,
                    "document_id": event.document_id,
                    "event_type": event.event_type,
                },
            )

            _mark_event_retryable(
                db,
                event,
                exc,
            )

        else:
            _mark_event_dispatched(
                db,
                event,
            )

            dispatched_ids.append(
                event.id
            )

    return dispatched_ids
