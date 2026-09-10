import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document
from app.models.document_status import DocumentStatus
from app.rag.qdrant_store import (
    delete_document_vectors,
    ensure_collection,
    index_chunks,
)
from app.services.chunking import split_text
from app.services.document_extractor import (
    extract_text,
    normalize_text,
)


logger = logging.getLogger(__name__)


def _is_stale_processing_document(
    document: Document,
) -> bool:
    processing_started_at = (
        document.processing_started_at
    )

    if processing_started_at is None:
        return True

    settings = get_settings()

    stale_after = timedelta(
        minutes=(
            settings.reconciliation_stale_processing_minutes
        )
    )

    cutoff = (
        datetime.now(timezone.utc)
        - stale_after
    )

    return processing_started_at < cutoff


def ingest_document(
    db: Session,
    document_id: int,
) -> int:
    document = (
        db.query(Document)
        .filter(
            Document.id
            == document_id
        )
        .with_for_update()
        .first()
    )

    if document is None:
        raise ValueError(
            f"Document {document_id} not found"
        )

    if document.status == (
        DocumentStatus.DELETING
    ):
        # A deletion request won the race.
        # Treat the ingestion request as successfully
        # cancelled rather than indexing a deleted document.
        return 0

    if document.status == (
        DocumentStatus.PROCESSING
    ):
        if _is_stale_processing_document(
            document
        ):
            logger.warning(
                "document_ingestion_stale_state_recovered",
                extra={
                    "document_id": document_id,
                    "processing_started_at": (
                        document.processing_started_at
                    ),
                },
            )

            document.status = (
                DocumentStatus.UPLOADED
            )

            document.processing_started_at = None

            db.flush()

        else:
            logger.info(
                "document_ingestion_already_in_progress",
                extra={
                    "document_id": document_id,
                    "processing_started_at": (
                        document.processing_started_at
                    ),
                },
            )

            # Another worker currently owns ingestion.
            # Do not fight it or reset its state.
            return 0

    document.status = (
        DocumentStatus.PROCESSING
    )

    document.processing_started_at = (
        datetime.now(timezone.utc)
    )

    db.commit()

    try:
        logger.info(
            "document_storage_check_before_extract",
            extra={
                "document_id": document_id,
                "storage_reference": (
                    document.storage_path
                ),
            },
        )

        text = extract_text(
            document.storage_path
        )

        text = normalize_text(
            text
        )

        if not text:
            raise ValueError(
                "Document contains no extractable text"
            )

        chunks = split_text(
            text
        )

        if not chunks:
            raise ValueError(
                "Document produced no chunks"
            )

        department_ids = [
            department.id
            for department
            in document.departments
        ]

        if not department_ids:
            raise ValueError(
                "Document has no department assignments"
            )

        ensure_collection()

        delete_document_vectors(
            document.id
        )

        indexed_count = index_chunks(
            document_id=document.id,
            filename=document.filename,
            chunks=chunks,
            department_ids=department_ids,
        )

        document.status = (
            DocumentStatus.INDEXED
        )

        document.processing_started_at = (
            None
        )

        db.commit()

        return indexed_count

    except Exception:
        try:
            delete_document_vectors(
                document.id
            )
        except Exception:
            pass

        document.status = (
            DocumentStatus.FAILED
        )

        document.processing_started_at = (
            None
        )

        db.commit()

        raise
