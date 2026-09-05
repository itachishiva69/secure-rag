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
    document = db.get(Document, document_id)

    if document is None:
        raise ValueError(
            f"Document {document_id} not found"
        )

    document.status = DocumentStatus.PROCESSING
    db.commit()

    try:
        # Remove any previous vectors before processing.
        #
        # This is important when:
        # - the document is being re-indexed;
        # - a previous attempt partially indexed vectors;
        # - the previous version of the document is still
        #   present in Qdrant.
        delete_document_vectors(
            document.id
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

        return indexed_count

    except Exception:
        # Never leave vectors from a failed ingestion attempt.
        try:
            delete_document_vectors(
                document.id
            )
        finally:
            document.status = DocumentStatus.FAILED
            db.commit()

        raise