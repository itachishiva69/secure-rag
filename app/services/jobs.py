import logging
from datetime import timedelta
from pathlib import Path

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models import Document
from app.models.document_status import DocumentStatus
from app.rag.qdrant_store import delete_document_vectors
from app.services.ingestion import ingest_document
from app.services.outbox import dispatch_pending_outbox_events
from app.services.reconciliation import (
    reconcile_stale_deleting_documents,
    reconcile_stale_processing_documents,
)

logger = logging.getLogger(__name__)


def ingest_document_job(
    document_id: int,
) -> int:
    logger.info(
        "document_ingestion_job_started",
        extra={
            "document_id": document_id,
        },
    )

    try:
        with SessionLocal() as db:
            indexed_count = ingest_document(
                db=db,
                document_id=document_id,
            )

        logger.info(
            "document_ingestion_job_completed",
            extra={
                "document_id": document_id,
                "indexed_count": indexed_count,
            },
        )

        return indexed_count

    except Exception:
        logger.exception(
            "document_ingestion_job_failed",
            extra={
                "document_id": document_id,
            },
        )

        raise


def delete_document_job(
    document_id: int,
) -> None:
    """
    Complete a previously requested document deletion.

    PostgreSQL must already contain the document in DELETING state
    before this worker starts.

    Cleanup order:

        1. Delete Qdrant vectors.
        2. Delete the stored file.
        3. Delete the PostgreSQL document row.

    The worker is idempotent:
    - a missing document means deletion already completed;
    - a missing storage file is safe because missing_ok=True;
    - a non-DELETING document is ignored.
    """
    logger.info(
        "document_cleanup_job_started",
        extra={
            "document_id": document_id,
        },
    )

    try:
        with SessionLocal() as db:
            document = db.get(
                Document,
                document_id,
            )

            if document is None:
                logger.info(
                    "document_cleanup_already_complete",
                    extra={
                        "document_id": document_id,
                    },
                )
                return

            if document.status != DocumentStatus.DELETING:
                logger.warning(
                    "document_cleanup_invalid_state",
                    extra={
                        "document_id": document_id,
                        "status": document.status.value,
                    },
                )
                return

            storage_path = document.storage_path

            # External cleanup happens before the database row is
            # removed. If Qdrant fails, the PostgreSQL row remains
            # in DELETING state and the RQ retry can safely try again.
            delete_document_vectors(
                document_id
            )

            Path(
                storage_path
            ).unlink(
                missing_ok=True
            )

            db.delete(
                document
            )

            db.commit()

        logger.info(
            "document_cleanup_job_completed",
            extra={
                "document_id": document_id,
            },
        )

    except Exception:
        logger.exception(
            "document_cleanup_job_failed",
            extra={
                "document_id": document_id,
            },
        )

        raise


def reconcile_stale_documents_job() -> dict[str, list[int]]:
    """
    Recover stale ingestion and deletion operations.

    Reconciliation only changes PostgreSQL state and creates
    outbox events. It does not directly enqueue Redis/RQ jobs.
    """
    settings = get_settings()

    recovered_processing_ids: list[int] = []
    recovered_deleting_ids: list[int] = []

    processing_stale_after = timedelta(
        minutes=(
            settings.reconciliation_stale_processing_minutes
        )
    )

    deleting_stale_after = timedelta(
        minutes=(
            settings.reconciliation_stale_deleting_minutes
        )
    )

    logger.info(
        "document_reconciliation_job_started",
        extra={
            "processing_stale_after_minutes": (
                settings.reconciliation_stale_processing_minutes
            ),
            "deleting_stale_after_minutes": (
                settings.reconciliation_stale_deleting_minutes
            ),
        },
    )

    try:
        with SessionLocal() as db:
            recovered_processing_ids = (
                reconcile_stale_processing_documents(
                    db=db,
                    stale_after=processing_stale_after,
                )
            )

            recovered_deleting_ids = (
                reconcile_stale_deleting_documents(
                    db=db,
                    stale_after=deleting_stale_after,
                )
            )

    except Exception:
        logger.exception(
            "document_reconciliation_job_failed"
        )

        raise

    logger.info(
        "document_reconciliation_job_completed",
        extra={
            "recovered_processing_ids": (
                recovered_processing_ids
            ),
            "recovered_deleting_ids": (
                recovered_deleting_ids
            ),
        },
    )

    return {
        "processing": recovered_processing_ids,
        "deleting": recovered_deleting_ids,
    }


def dispatch_pending_outbox_job() -> list[int]:
    """
    Dispatch durable PostgreSQL outbox events to RQ.
    """
    logger.info(
        "outbox_dispatch_job_started"
    )

    try:
        with SessionLocal() as db:
            dispatched_ids = (
                dispatch_pending_outbox_events(
                    db=db
                )
            )

        logger.info(
            "outbox_dispatch_job_completed",
            extra={
                "dispatched_count": len(
                    dispatched_ids
                ),
                "dispatched_outbox_event_ids": (
                    dispatched_ids
                ),
            },
        )

        return dispatched_ids

    except Exception:
        logger.exception(
            "outbox_dispatch_job_failed"
        )

        raise