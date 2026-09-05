from datetime import datetime, timezone

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


def ingest_document(
    db: Session,
    document_id: int,
) -> int:
    document = db.get(
        Document,
        document_id,
    )

    if document is None:
        raise ValueError(
            f"Document {document_id} not found"
        )

    document.status = DocumentStatus.PROCESSING
    document.processing_started_at = datetime.now(
        timezone.utc
    )
    db.commit()

    try:
        text = extract_text(
            document.storage_path
        )

        text = normalize_text(text)

        if not text:
            raise ValueError(
                "Document contains no extractable text"
            )

        chunks = split_text(text)

        if not chunks:
            raise ValueError(
                "Document produced no chunks"
            )

        department_ids = [
            department.id
            for department in document.departments
        ]

        if not department_ids:
            raise ValueError(
                "Document has no department assignments"
            )

        ensure_collection()

        # Remove any previous index before creating the
        # new version. This prevents stale chunks from
        # surviving a successful re-index.
        delete_document_vectors(
            document.id
        )

        indexed_count = index_chunks(
            document_id=document.id,
            filename=document.filename,
            chunks=chunks,
            department_ids=department_ids,
        )

        document.status = DocumentStatus.INDEXED
        document.processing_started_at = None

        db.commit()

        return indexed_count

    except Exception:
        # A failure after partial Qdrant writes must not
        # leave an incomplete or stale index behind.
        try:
            delete_document_vectors(
                document.id
            )
        except Exception:
            # The original ingestion error is more useful
            # to the caller than a cleanup error. The document
            # will still be marked FAILED below.
            pass

        document.status = DocumentStatus.FAILED
        document.processing_started_at = None

        db.commit()

        raise