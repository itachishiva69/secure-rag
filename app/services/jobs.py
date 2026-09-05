import logging

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.services.ingestion import ingest_document
from app.services.reconciliation import (
    reconcile_stale_processing_documents,
)

logger = logging.getLogger(__name__)

settings = get_settings()


def ingest_document_job(
    document_id: int,
) -> None:
    """
    Background job for document ingestion.

    A new database session is created for each job because
    workers must not reuse FastAPI request-scoped sessions.

    Exceptions intentionally propagate so RQ can mark the
    job as failed and apply the configured retry policy.
    """

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


def reconcile_stale_documents_job() -> None:
    """
    Periodic maintenance job that finds ingestion attempts
    stuck in PROCESSING and requeues them.

    Exceptions propagate so the maintenance job is visible
    as failed to RQ.
    """

    stale_after_minutes = (
        settings.reconciliation_stale_processing_minutes
    )

    from datetime import timedelta

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