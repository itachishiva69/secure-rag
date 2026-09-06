import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, not_
from sqlalchemy.orm import Session

from app.models import Document, OutboxEvent
from app.models.document_status import DocumentStatus
from app.services.outbox import (
    DELETE_DOCUMENT_EVENT,
    OUTBOX_PENDING,
    create_delete_outbox_event,
    create_ingestion_outbox_event,
)


logger = logging.getLogger(__name__)


DEFAULT_STALE_PROCESSING_MINUTES = 30
DEFAULT_STALE_DELETING_MINUTES = 30


def find_stale_processing_document_ids(
    db: Session,
    *,
    stale_after: timedelta,
) -> list[int]:
    """
    Return IDs of documents that appear to have been stuck
    in PROCESSING beyond the supplied threshold.

    This function is read-only and does not claim documents.
    """

    cutoff = (
        datetime.now(timezone.utc)
        - stale_after
    )

    documents = (
        db.query(Document.id)
        .filter(
            and_(
                Document.status
                == DocumentStatus.PROCESSING,
                Document.processing_started_at.is_not(None),
                Document.processing_started_at
                < cutoff,
            )
        )
        .order_by(Document.id)
        .all()
    )

    return [
        document_id
        for document_id, in documents
    ]


def _claim_next_stale_processing_document(
    db: Session,
    *,
    stale_after: timedelta,
) -> int | None:
    """
    Atomically recover one stale PROCESSING document.

    PostgreSQL row locking ensures concurrent reconciliation
    workers cannot claim the same document.

    The document state transition and ingestion outbox event
    are committed in the same database transaction.

    This is the critical consistency boundary:

        PROCESSING -> UPLOADED
        + ingestion outbox event
        -----------------------
        one PostgreSQL transaction

    Redis/RQ is intentionally not contacted here.
    """

    cutoff = (
        datetime.now(timezone.utc)
        - stale_after
    )

    document = (
        db.query(Document)
        .filter(
            and_(
                Document.status
                == DocumentStatus.PROCESSING,
                Document.processing_started_at.is_not(None),
                Document.processing_started_at
                < cutoff,
            )
        )
        .order_by(Document.id)
        .with_for_update(
            skip_locked=True
        )
        .first()
    )

    if document is None:
        return None

    document_id = document.id

    document.status = (
        DocumentStatus.UPLOADED
    )

    document.processing_started_at = None

    create_ingestion_outbox_event(
        db,
        document_id=document_id,
    )

    db.commit()

    return document_id


def reconcile_stale_processing_documents(
    db: Session,
    *,
    stale_after: timedelta,
) -> list[int]:
    """
    Recover documents whose ingestion workers appear
    to have stopped making progress.

    Each stale document is claimed using a PostgreSQL row
    lock.

    Recovery and creation of the ingestion outbox event
    happen inside the same PostgreSQL transaction.

    The outbox dispatcher is responsible for eventually
    delivering the resulting ingestion event to Redis/RQ.

    If the database transaction fails, the transaction is
    rolled back and the document remains PROCESSING.
    """

    recovered_ids: list[int] = []

    while True:
        try:
            document_id = (
                _claim_next_stale_processing_document(
                    db,
                    stale_after=stale_after,
                )
            )

        except Exception:
            db.rollback()

            logger.exception(
                "document_reconciliation_transaction_failed"
            )

            raise

        if document_id is None:
            break

        recovered_ids.append(
            document_id
        )

        logger.info(
            "document_reconciliation_recovered",
            extra={
                "document_id": document_id,
            },
        )

    return recovered_ids


def _has_pending_delete_outbox_event(
    db: Session,
    *,
    document_id: int,
):
    """
    Return True when the document already has a pending
    cleanup outbox event.

    A pending event means the outbox dispatcher still has
    ownership of delivering the cleanup job, so creating or
    claiming another recovery event is unnecessary.
    """

    return (
        db.query(OutboxEvent.id)
        .filter(
            and_(
                OutboxEvent.document_id
                == document_id,
                OutboxEvent.event_type
                == DELETE_DOCUMENT_EVENT,
                OutboxEvent.status
                == OUTBOX_PENDING,
            )
        )
        .first()
        is not None
    )


def find_stale_deleting_document_ids(
    db: Session,
    *,
    stale_after: timedelta,
) -> list[int]:
    """
    Return IDs of documents that appear to have been stuck
    in DELETING beyond the supplied threshold.

    Documents that already have a pending cleanup outbox
    event are excluded because the outbox dispatcher already
    has work queued for them.
    """

    cutoff = (
        datetime.now(timezone.utc)
        - stale_after
    )

    pending_delete_exists = (
        db.query(OutboxEvent.id)
        .filter(
            and_(
                OutboxEvent.document_id
                == Document.id,
                OutboxEvent.event_type
                == DELETE_DOCUMENT_EVENT,
                OutboxEvent.status
                == OUTBOX_PENDING,
            )
        )
        .exists()
    )

    documents = (
        db.query(Document.id)
        .filter(
            and_(
                Document.status
                == DocumentStatus.DELETING,
                Document.deletion_started_at.is_not(None),
                Document.deletion_started_at
                < cutoff,
                not_(pending_delete_exists),
            )
        )
        .order_by(Document.id)
        .all()
    )

    return [
        document_id
        for document_id, in documents
    ]


def _claim_next_stale_deleting_document(
    db: Session,
    *,
    stale_after: timedelta,
) -> int | None:
    """
    Atomically recover one stale DELETING document.

    The document remains DELETING.

    A cleanup outbox event is created in the same PostgreSQL
    transaction so the outbox dispatcher can eventually
    deliver cleanup work to Redis/RQ.

    Redis/RQ is intentionally not contacted here.

    A document with an existing pending cleanup event is
    skipped. This prevents repeated recovery of the same
    document during a single reconciliation run.

    If an earlier cleanup event was already dispatched but
    its worker was lost, the document remains stale and no
    pending event exists, allowing reconciliation to create
    a new cleanup event.
    """

    cutoff = (
        datetime.now(timezone.utc)
        - stale_after
    )

    pending_delete_exists = (
        db.query(OutboxEvent.id)
        .filter(
            and_(
                OutboxEvent.document_id
                == Document.id,
                OutboxEvent.event_type
                == DELETE_DOCUMENT_EVENT,
                OutboxEvent.status
                == OUTBOX_PENDING,
            )
        )
        .exists()
    )

    document = (
        db.query(Document)
        .filter(
            and_(
                Document.status
                == DocumentStatus.DELETING,
                Document.deletion_started_at.is_not(None),
                Document.deletion_started_at
                < cutoff,
                not_(pending_delete_exists),
            )
        )
        .order_by(Document.id)
        .with_for_update(
            skip_locked=True
        )
        .first()
    )

    if document is None:
        return None

    document_id = document.id

    create_delete_outbox_event(
        db,
        document_id=document_id,
    )

    db.commit()

    return document_id


def reconcile_stale_deleting_documents(
    db: Session,
    *,
    stale_after: timedelta,
) -> list[int]:
    """
    Recover documents whose deletion workers appear
    to have stopped making progress.

    The document remains in DELETING state.

    Recovery and creation of the cleanup outbox event
    happen inside the same PostgreSQL transaction.

    The outbox dispatcher is responsible for eventually
    delivering the cleanup event to Redis/RQ.

    If the database transaction fails, the transaction is
    rolled back and the document remains DELETING.
    """

    recovered_ids: list[int] = []

    while True:
        try:
            document_id = (
                _claim_next_stale_deleting_document(
                    db,
                    stale_after=stale_after,
                )
            )

        except Exception:
            db.rollback()

            logger.exception(
                "document_deletion_reconciliation_transaction_failed"
            )

            raise

        if document_id is None:
            break

        recovered_ids.append(
            document_id
        )

        logger.info(
            "document_deletion_reconciliation_recovered",
            extra={
                "document_id": document_id,
            },
        )

    return recovered_ids