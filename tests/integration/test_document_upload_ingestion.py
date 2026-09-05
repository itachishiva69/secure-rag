from pathlib import Path

from fastapi.testclient import TestClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from app.api import documents as documents_api
from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import (
    Department,
    User,
)
from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services import file_storage
from app.services import jobs


class FakeQueue:
    def __init__(self):
        self.jobs = []

    def enqueue(self, function, *args, **kwargs):
        self.jobs.append(
            {
                "function": function,
                "args": args,
                "kwargs": kwargs,
            }
        )


class SessionContext:
    def __init__(self, db_session):
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


def get_document_vectors(document_id: int):
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
        email="upload-integration-admin@example.com",
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

    test_storage_path = tmp_path / "documents"

    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(test_storage_path),
    )

    fake_queue = FakeQueue()

    # The upload endpoint imported get_ingestion_queue
    # directly, so patch the reference used by the route.
    monkeypatch.setattr(
        documents_api,
        "get_ingestion_queue",
        lambda: fake_queue,
    )

    # The worker imported SessionLocal directly,
    # so patch the reference used by the worker.
    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        lambda: SessionContext(db_session),
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: admin
    )

    client = TestClient(app)

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
                    document_content.encode("utf-8"),
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

        assert body["uploaded_by"] == admin.id

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

        # The upload endpoint must enqueue exactly
        # one ingestion job.
        assert len(fake_queue.jobs) == 1

        queued_job = fake_queue.jobs[0]

        assert queued_job["function"] == (
            jobs.ingest_document_job
        )

        assert queued_job["args"] == (
            document_id,
        )

        # Execute the real background job.
        queued_job["function"](
            *queued_job["args"],
            **queued_job["kwargs"],
        )

        db_session.expire_all()

        from app.models import Document

        document = db_session.get(
            Document,
            document_id,
        )

        assert document is not None

        assert document.status.value == "indexed"

        points = get_document_vectors(
            document_id
        )

        assert len(points) >= 1

        for point in points:
            payload = point.payload or {}

            assert payload["document_id"] == (
                document_id
            )

            assert payload["filename"] == (
                "engineering-confidential.txt"
            )

            assert payload["department_ids"] == [
                department.id
            ]

            assert payload["text"]

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
        email="upload-nonadmin@example.com",
        department_id=department.id,
    )

    test_storage_path = tmp_path / "documents"

    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(test_storage_path),
    )

    fake_queue = FakeQueue()

    # Patch the reference actually used by
    # app.api.documents.
    monkeypatch.setattr(
        documents_api,
        "get_ingestion_queue",
        lambda: fake_queue,
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: user
    )

    client = TestClient(app)

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
            "detail": "Admin privileges required"
        }

        # No background job should have been queued.
        assert fake_queue.jobs == []

        # No document should have been created.
        from sqlalchemy import select

        from app.models import Document

        documents = db_session.scalars(
            select(Document)
        ).all()

        assert documents == []

    finally:
        app.dependency_overrides.clear()
