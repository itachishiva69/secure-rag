import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

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
        raise ValueError(
            f"Document {document_id} is already processing"
        )

    document.status = (
        DocumentStatus.PROCESSING
    )

    document.processing_started_at = (
        datetime.now(timezone.utc)
    )

    db.commit()

    try:
        storage_path = Path(
            document.storage_path
        )

        logger.info(
            "document_storage_check_before_extract",
            extra={
                "document_id": document_id,
                "path": str(storage_path),
                "exists": storage_path.exists(),
                "is_file": storage_path.is_file(),
                "size": (
                    storage_path.stat().st_size
                    if storage_path.exists()
                    else None
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