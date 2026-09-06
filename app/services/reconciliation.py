import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Document
from app.models.document_status import DocumentStatus
from app.services.outbox import (
    create_ingestion_outbox_event,
)


logger = logging.getLogger(__name__)


DEFAULT_STALE_PROCESSING_MINUTES = 30


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