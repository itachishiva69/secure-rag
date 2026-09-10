from uuid import uuid4

from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services.jobs import (
    mark_document_ingestion_failed,
)


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def test_mark_document_ingestion_failed_transitions_processing_document(
    db_session,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.jobs.SessionLocal",
        lambda: db_session,
    )

    department = Department(
        name=unique_name("IngestionFailure")
    )

    db_session.add(department)
    db_session.flush()

    user = User(
        email=unique_email(
            "ingestion-failure-admin"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department.id,
    )

    db_session.add(user)
    db_session.flush()

    document = Document(
        filename=f"{uuid4().hex}.pdf",
        storage_path=f"test/{uuid4().hex}.pdf",
        uploaded_by=user.id,
        status=DocumentStatus.PROCESSING,
    )

    db_session.add(document)
    db_session.flush()

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=department.id,
        )
    )

    db_session.commit()

    document_id = document.id

    assert mark_document_ingestion_failed(
        document_id
    ) is True

    saved_document = db_session.get(
        Document,
        document_id,
    )

    assert saved_document is not None
    assert saved_document.status == (
        DocumentStatus.FAILED
    )
    assert saved_document.processing_started_at is None
