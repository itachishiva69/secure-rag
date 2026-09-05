import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import OutboxEvent
from app.services.queue import enqueue_ingestion_job


logger = logging.getLogger(__name__)


INGEST_DOCUMENT_EVENT = "ingest_document"

OUTBOX_PENDING = "pending"
OUTBOX_DISPATCHED = "dispatched"

DISPATCH_RETRY_SECONDS = 60


def create_ingestion_outbox_event(
    db: Session,
    *,
    document_id: int,
) -> OutboxEvent:
    existing_event = (
        db.query(OutboxEvent)
        .filter(
            and_(
                OutboxEvent.document_id
                == document_id,
                OutboxEvent.event_type
                == INGEST_DOCUMENT_EVENT,
                OutboxEvent.status
                == OUTBOX_PENDING,
            )
        )
        .order_by(
            OutboxEvent.id.desc()
        )
        .first()
    )

    if existing_event is not None:
        return existing_event

    event = OutboxEvent(
        event_type=INGEST_DOCUMENT_EVENT,
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


def dispatch_pending_outbox_events(
    db: Session,
) -> list[int]:
    """
    Publish pending outbox events to RQ.

    PostgreSQL remains the durable source of truth.
    RQ is the execution transport.

    Events are claimed with SKIP LOCKED so concurrent
    dispatchers do not process the same event at once.
    """

    dispatched_ids: list[int] = []

    while True:
        event = _claim_next_pending_event(
            db
        )

        if event is None:
            break

        try:
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

            else:
                raise ValueError(
                    f"Unsupported outbox event type: "
                    f"{event.event_type}"
                )

            event.status = (
                OUTBOX_DISPATCHED
            )
            event.dispatched_at = (
                datetime.now(timezone.utc)
            )
            event.last_error = None

            db.commit()

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

    return dispatched_ids