import pytest
from httpx import ASGITransport, AsyncClient

from app.api import documents as documents_api
from app.api.dependencies import (
    get_current_user,
    get_db,
)
from app.main import app
from app.models import (
    Department,
    Document,
    OutboxEvent,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services import outbox


def unique_name(
    prefix: str,
) -> str:
    from uuid import uuid4

    return f"{prefix}-{uuid4().hex}"


def unique_email(
    prefix: str,
) -> str:
    from uuid import uuid4

    return (
        f"{prefix}-{uuid4().hex}"
        "@example.com"
    )


def create_department(
    db_session,
):
    department = Department(
        name=unique_name(
            "UploadConsistency"
        )
    )

    db_session.add(
        department
    )

    db_session.flush()

    return department


def create_admin(
    db_session,
    department_id: int,
):
    admin = User(
        email=unique_email(
            "upload-consistency-admin"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )

    db_session.add(
        admin
    )

    db_session.flush()

    return admin


def configure_test_dependencies(
    db_session,
    admin,
):
    app.dependency_overrides[
        get_db
    ] = lambda: db_session

    app.dependency_overrides[
        get_current_user
    ] = lambda: admin


def clear_test_dependencies():
    app.dependency_overrides.pop(
        get_db,
        None,
    )

    app.dependency_overrides.pop(
        get_current_user,
        None,
    )


class NoOpRateLimiter:
    def check(
        self,
        subject: str,
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_document_and_outbox_commit_together(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_path = (
        tmp_path
        / "consistent-document.txt"
    )

    storage_path.write_bytes(
        b"valid upload content"
    )

    async def fake_save_uploaded_file(
        file,
    ):
        return str(storage_path)

    monkeypatch.setattr(
        documents_api,
        "save_uploaded_file",
        fake_save_uploaded_file,
    )

    monkeypatch.setattr(
        documents_api,
        "get_upload_rate_limiter",
        lambda: NoOpRateLimiter(),
    )

    configure_test_dependencies(
        db_session,
        admin,
    )

    try:
        transport = ASGITransport(
            app=app
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/documents/upload",
                files={
                    "file": (
                        "consistent-document.txt",
                        b"valid upload content",
                        "text/plain",
                    )
                },
                data={
                    "department_ids": str(
                        department.id
                    )
                },
            )

        assert response.status_code == 200

        document = (
            db_session.query(Document)
            .filter(
                Document.filename
                == "consistent-document.txt"
            )
            .order_by(
                Document.id.desc()
            )
            .first()
        )

        assert document is not None

        assert document.status == (
            DocumentStatus.UPLOADED
        )

        event = (
            db_session.query(OutboxEvent)
            .filter(
                OutboxEvent.document_id
                == document.id
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

    finally:
        clear_test_dependencies()


@pytest.mark.asyncio
async def test_storage_failure_does_not_create_database_records(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    async def failing_save_uploaded_file(
        file,
    ):
        raise RuntimeError(
            "simulated storage failure"
        )

    monkeypatch.setattr(
        documents_api,
        "save_uploaded_file",
        failing_save_uploaded_file,
    )

    monkeypatch.setattr(
        documents_api,
        "get_upload_rate_limiter",
        lambda: NoOpRateLimiter(),
    )

    configure_test_dependencies(
        db_session,
        admin,
    )

    filename = (
        "failed-storage.txt"
    )

    try:
        transport = ASGITransport(
            app=app,
            raise_app_exceptions=False,
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/documents/upload",
                files={
                    "file": (
                        filename,
                        b"content",
                        "text/plain",
                    )
                },
                data={
                    "department_ids": str(
                        department.id
                    )
                },
            )

        assert response.status_code == 500

        document = (
            db_session.query(Document)
            .filter(
                Document.filename
                == filename
            )
            .first()
        )

        assert document is None

    finally:
        clear_test_dependencies()


@pytest.mark.asyncio
async def test_upload_succeeds_without_redis_enqueue(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_path = (
        tmp_path
        / "queued-document.txt"
    )

    storage_path.write_bytes(
        b"valid upload content"
    )

    async def fake_save_uploaded_file(
        file,
    ):
        return str(storage_path)

    monkeypatch.setattr(
        documents_api,
        "save_uploaded_file",
        fake_save_uploaded_file,
    )

    # Disable only the rate limiter's Redis dependency.
    #
    # The upload endpoint itself must not contact Redis.
    # It records the ingestion request in PostgreSQL as
    # a durable outbox event instead.
    monkeypatch.setattr(
        documents_api,
        "get_upload_rate_limiter",
        lambda: NoOpRateLimiter(),
    )

    configure_test_dependencies(
        db_session,
        admin,
    )

    filename = (
        "queued-document.txt"
    )

    try:
        transport = ASGITransport(
            app=app
        )

        async with AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/documents/upload",
                files={
                    "file": (
                        filename,
                        b"valid upload content",
                        "text/plain",
                    )
                },
                data={
                    "department_ids": str(
                        department.id
                    )
                },
            )

        assert response.status_code == 200

        document = (
            db_session.query(Document)
            .filter(
                Document.filename
                == filename
            )
            .order_by(
                Document.id.desc()
            )
            .first()
        )

        assert document is not None

        assert document.status == (
            DocumentStatus.UPLOADED
        )

        event = (
            db_session.query(OutboxEvent)
            .filter(
                OutboxEvent.document_id
                == document.id
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

    finally:
        clear_test_dependencies()