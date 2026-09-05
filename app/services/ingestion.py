import logging

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
    document = db.get(Document, document_id)

    if document is None:
        logger.error(
            "document_ingestion_document_not_found",
            extra={
                "document_id": document_id,
            },
        )

        raise ValueError(
            f"Document {document_id} not found"
        )

    logger.info(
        "document_ingestion_started",
        extra={
            "document_id": document.id,
            "uploaded_by": document.uploaded_by,
            "filename": document.filename,
        },
    )

    document.status = DocumentStatus.PROCESSING
    db.commit()

    try:
        delete_document_vectors(
            document.id
        )

        logger.info(
            "document_ingestion_previous_vectors_removed",
            extra={
                "document_id": document.id,
            },
        )

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

        logger.info(
            "document_ingestion_chunks_created",
            extra={
                "document_id": document.id,
                "chunk_count": len(chunks),
                "department_count": len(
                    department_ids
                ),
            },
        )

        ensure_collection()

        indexed_count = index_chunks(
            document_id=document.id,
            filename=document.filename,
            chunks=chunks,
            department_ids=department_ids,
        )

        if indexed_count != len(chunks):
            raise RuntimeError(
                "Indexed chunk count does not match "
                "the generated chunk count"
            )

        document.status = DocumentStatus.INDEXED
        db.commit()

        logger.info(
            "document_ingestion_completed",
            extra={
                "document_id": document.id,
                "indexed_count": indexed_count,
                "department_count": len(
                    department_ids
                ),
            },
        )

        return indexed_count

    except Exception:
        try:
            delete_document_vectors(
                document.id
            )
        finally:
            document.status = DocumentStatus.FAILED
            db.commit()

        logger.exception(
            "document_ingestion_failed",
            extra={
                "document_id": document.id,
            },
        )

        raise