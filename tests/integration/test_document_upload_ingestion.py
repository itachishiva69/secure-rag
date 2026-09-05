from pathlib import Path

from fastapi.testclient import TestClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)
from sqlalchemy import select

from app.api import documents as documents_api
from app.api.dependencies import (
    get_current_user,
    get_db,
)
from app.main import app
from app.models import (
    Department,
    Document,
    DocumentDepartment,
    OutboxEvent,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services import file_storage
from app.services import jobs
from app.services import outbox


class SessionContext:
    def __init__(
        self,
        db_session,
    ):
        self.db_session = db_session

    def __enter__(self):
        return self.db_session

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ):
        return False


class NoOpRateLimiter:
    def check(
        self,
        subject: str,
    ) -> None:
        return None


def get_document_vectors(
    document_id: int,
):
    points, _ = qdrant_store.client.scroll(
        collection_name=(
            qdrant_store.settings.qdrant_collection
        ),
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(
                        value=document_id
                    ),
                )
            ]
        ),
        limit=100,
        with_payload=True,
        with_vectors=False,
    )

    return points


def create_admin(
    db_session,
    department_id: int,
):
    admin = User(
        email=(
            "upload-integration-admin@example.com"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )

    db_session.add(admin)
    db_session.flush()

    return admin


def create_user(
    db_session,
    *,
    email: str,
    department_id: int,
):
    user = User(
        email=email,
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def test_admin_uploads_document_and_worker_indexes_it(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = Department(
        name="Upload-Ingestion-Engineering"
    )

    db_session.add(department)
    db_session.flush()

    admin = create_admin(
        db_session,
        department.id,
    )

    test_storage_path = (
        tmp_path / "documents"
    )

    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(test_storage_path),
    )

    monkeypatch.setattr(
        documents_api,
        "get_upload_rate_limiter",
        lambda: NoOpRateLimiter(),
    )

    app.dependency_overrides[
        get_db
    ] = lambda: db_session

    app.dependency_overrides[
        get_current_user
    ] = lambda: admin

    client = TestClient(
        app
    )

    document_id = None

    try:
        document_content = (
            "This is a confidential engineering document. "
            "It contains information that should only be "
            "available to the Engineering department."
        )

        response = client.post(
            "/documents/upload",
            files={
                "file": (
                    "engineering-confidential.txt",
                    document_content.encode(
                        "utf-8"
                    ),
                    "text/plain",
                )
            },
            data={
                "department_ids": str(
                    department.id
                ),
            },
        )

        assert response.status_code == 200

        body = response.json()

        document_id = body["id"]

        assert body["filename"] == (
            "engineering-confidential.txt"
        )

        assert body["uploaded_by"] == (
            admin.id
        )

        assert body["department_ids"] == [
            department.id
        ]

        assert body["status"] == "uploaded"

        storage_path = Path(
            body["storage_path"]
        )

        assert storage_path.exists()
        assert storage_path.is_file()

        assert storage_path.read_text(
            encoding="utf-8"
        ) == document_content

        # Upload no longer talks directly to RQ.
        # It creates a durable PostgreSQL outbox event.
        event = (
            db_session.query(
                OutboxEvent
            )
            .filter(
                OutboxEvent.document_id
                == document_id
            )
            .order_by(
                OutboxEvent.id.desc()
            )
            .first()
        )

        assert event is not None

        assert event.event_type == (
            outbox.INGEST_DOCUMENT_EVENT
        )

        assert event.status == (
            outbox.OUTBOX_PENDING
        )

        enqueued_jobs: list[
            tuple[int, str | None]
        ] = []

        def fake_enqueue_ingestion_job(
            document_id: int,
            *,
            job_id: str | None = None,
        ):
            enqueued_jobs.append(
                (
                    document_id,
                    job_id,
                )
            )

        monkeypatch.setattr(
            outbox,
            "enqueue_ingestion_job",
            fake_enqueue_ingestion_job,
        )

        dispatched_ids = (
            outbox.dispatch_pending_outbox_events(
                db_session
            )
        )

        db_session.refresh(
            event
        )

        assert dispatched_ids == [
            event.id
        ]

        assert enqueued_jobs == [
            (
                document_id,
                (
                    f"document-ingestion-outbox-"
                    f"{event.id}"
                ),
            )
        ]

        assert event.status == (
            outbox.OUTBOX_DISPATCHED
        )

        # Execute the real background ingestion
        # job with a worker-style database session.
        monkeypatch.setattr(
            jobs,
            "SessionLocal",
            lambda: SessionContext(
                db_session
            ),
        )

        jobs.ingest_document_job(
            document_id
        )

        db_session.expire_all()

        document = db_session.get(
            Document,
            document_id,
        )

        assert document is not None

        assert document.status == (
            DocumentStatus.INDEXED
        )

        points = get_document_vectors(
            document_id
        )

        assert len(points) >= 1

        for point in points:
            payload = (
                point.payload
                or {}
            )

            assert payload[
                "document_id"
            ] == document_id

            assert payload[
                "filename"
            ] == (
                "engineering-confidential.txt"
            )

            assert payload[
                "department_ids"
            ] == [
                department.id
            ]

            assert payload[
                "text"
            ]

    finally:
        if document_id is not None:
            qdrant_store.delete_document_vectors(
                document_id
            )

        app.dependency_overrides.clear()


def test_non_admin_cannot_upload_document(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = Department(
        name="Upload-NonAdmin-Engineering"
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        email=(
            "upload-nonadmin@example.com"
        ),
        department_id=department.id,
    )

    test_storage_path = (
        tmp_path / "documents"
    )

    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(test_storage_path),
    )

    monkeypatch.setattr(
        documents_api,
        "get_upload_rate_limiter",
        lambda: NoOpRateLimiter(),
    )

    app.dependency_overrides[
        get_db
    ] = lambda: db_session

    app.dependency_overrides[
        get_current_user
    ] = lambda: user

    client = TestClient(
        app
    )

    try:
        response = client.post(
            "/documents/upload",
            files={
                "file": (
                    "unauthorized.txt",
                    b"Unauthorized document",
                    "text/plain",
                )
            },
            data={
                "department_ids": str(
                    department.id
                ),
            },
        )

        assert response.status_code == 403

        assert response.json() == {
            "detail": (
                "Admin privileges required"
            )
        }

        # No document should have been created.
        documents = db_session.scalars(
            select(Document)
        ).all()

        assert documents == []

        # No outbox event should have been created.
        events = db_session.scalars(
            select(OutboxEvent)
        ).all()

        assert events == []

        # No file should have been stored.
        if test_storage_path.exists():
            stored_files = list(
                test_storage_path.rglob("*")
            )
            assert stored_files == []

    finally:
        app.dependency_overrides.clear()