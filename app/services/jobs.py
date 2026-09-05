import logging
from datetime import timedelta
from pathlib import Path

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models import Document
from app.models.document_status import DocumentStatus
from app.services.ingestion import ingest_document
from app.services.outbox import (
    dispatch_pending_outbox_events,
)
from app.services.reconciliation import (
    reconcile_stale_processing_documents,
)


logger = logging.getLogger(__name__)

settings = get_settings()


def ingest_document_job(
    document_id: int,
) -> None:
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

    Qdrant cleanup happens during the delete request.
    This job removes the stored file and then deletes the
    PostgreSQL document row.

    Every operation is idempotent:
    deleting a missing file is safe, and deleting an already
    removed database row is treated as successful completion.
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
                    "document_cleanup_job_already_complete",
                    extra={
                        "document_id": document_id,
                    },
                )
                return

            if document.status != (
                DocumentStatus.DELETING
            ):
                logger.warning(
                    "document_cleanup_job_invalid_status",
                    extra={
                        "document_id": document_id,
                        "status": (
                            document.status.value
                        ),
                    },
                )
                return

            storage_path = (
                document.storage_path
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


def reconcile_stale_documents_job() -> None:
    stale_after_minutes = (
        settings.reconciliation_stale_processing_minutes
    )

    stale_after = timedelta(
        minutes=stale_after_minutes
    )

    logger.info(
        "document_reconciliation_job_started",
        extra={
            "stale_after_minutes": (
                stale_after_minutes
            ),
        },
    )

    try:
        with SessionLocal() as db:
            recovered_ids = (
                reconcile_stale_processing_documents(
                    db=db,
                    stale_after=stale_after,
                )
            )

        logger.info(
            "document_reconciliation_job_completed",
            extra={
                "recovered_count": len(
                    recovered_ids
                ),
                "recovered_document_ids": (
                    recovered_ids
                ),
            },
        )

    except Exception:
        logger.exception(
            "document_reconciliation_job_failed"
        )

        raise


def dispatch_pending_outbox_job() -> None:
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

    except Exception:
        logger.exception(
            "outbox_dispatch_job_failed"
        )

        raise