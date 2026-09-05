from datetime import datetime, timedelta, timezone

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Document
from app.models.document_status import DocumentStatus
from app.services.queue import enqueue_ingestion_job


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
) -> Document | None:
    """
    Atomically claim one stale PROCESSING document.

    PostgreSQL row locking ensures that concurrent
    reconciliation workers cannot claim the same document.
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

    document.status = DocumentStatus.UPLOADED
    document.processing_started_at = None

    db.commit()

    return document


def reconcile_stale_processing_documents(
    db: Session,
    *,
    stale_after: timedelta,
) -> list[int]:
    """
    Recover documents whose ingestion workers appear
    to have stopped making progress.

    Each stale document is claimed using a PostgreSQL row
    lock before being transitioned to UPLOADED.

    The database transaction is committed before the
    ingestion job is enqueued.

    If enqueueing fails, the document is marked FAILED.
    """

    recovered_ids: list[int] = []

    while True:
        document = _claim_next_stale_processing_document(
            db,
            stale_after=stale_after,
        )

        if document is None:
            break

        document_id = document.id

        try:
            enqueue_ingestion_job(
                document_id
            )
        except Exception:
            failed_document = db.get(
                Document,
                document_id,
            )

            if failed_document is not None:
                failed_document.status = (
                    DocumentStatus.FAILED
                )
                failed_document.processing_started_at = None
                db.commit()

            raise

        recovered_ids.append(
            document_id
        )

    return recovered_ids