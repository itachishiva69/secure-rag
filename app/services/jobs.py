from app.db.database import SessionLocal
from app.services.ingestion import ingest_document


def ingest_document_job(document_id: int) -> None:
    """
    Background job for document ingestion.

    A new database session is created for each job because
    workers must not reuse FastAPI request-scoped sessions.
    """

    with SessionLocal() as db:
        ingest_document(
            db=db,
            document_id=document_id,
        )