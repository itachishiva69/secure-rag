import logging

from app.db.database import SessionLocal
from app.services.ingestion import ingest_document


logger = logging.getLogger(__name__)


def ingest_document_job(
    document_id: int,
) -> None:
    """
    Background job for document ingestion.

    A new database session is created for each job because
    workers must not reuse FastAPI request-scoped sessions.

    Exceptions intentionally propagate so the queue can
    record the job as failed and apply its retry policy.
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