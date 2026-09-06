from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

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
    return (
        f"{prefix}-{uuid4().hex}"
    )


def unique_email(
    prefix: str,
) -> str:
    return (
        f"{prefix}-{uuid4().hex}"
        "@example.com"
    )


def create_department(
    db_session,
    name: str | None = None,
):
    department = Department(
        name=(
            name
            or unique_name(
                "Lifecycle"
            )
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
    user = User(
        email=unique_email(
            "lifecycle-admin"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )

    db_session.add(
        user
    )

    db_session.flush()

    return user


def create_user(
    db_session,
    department_id: int,
):
    user = User(
        email=unique_email(
            "lifecycle-user"
        ),
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department_id,
    )

    db_session.add(
        user
    )

    db_session.flush()

    return user


def create_document(
    db_session,
    *,
    uploaded_by: int,
    department_ids: list[int],
    status: DocumentStatus = DocumentStatus.INDEXED,
):
    document = Document(
        filename=f"{uuid4().hex}.txt",
        storage_path=f"test/{uuid4().hex}.txt",
        uploaded_by=uploaded_by,
        status=status,
    )

    db_session.add(
        document
    )

    db_session.flush()

    departments = (
        db_session.query(Department)
        .filter(
            Department.id.in_(
                department_ids
            )
        )
        .all()
    )

    document.departments = departments

    db_session.flush()

    return document


def configure_app(
    db_session,
    user,
):
    app.dependency_overrides[
        get_db
    ] = lambda: db_session

    app.dependency_overrides[
        get_current_user
    ] = lambda: user


def test_admin_can_list_documents(
    db_session,
):
    department = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_ids=[
            department.id
        ],
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    try:
        response = client.get(
            "/documents"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 1
        assert body["limit"] == 20
        assert body["offset"] == 0

        assert (
            body["items"][0]["id"]
            == document.id
        )

    finally:
        app.dependency_overrides.clear()


def test_user_lists_only_own_department_documents(
    db_session,
):
    finance = create_department(
        db_session,
        "Lifecycle-Finance",
    )

    engineering = create_department(
        db_session,
        "Lifecycle-Engineering",
    )

    finance_user = create_user(
        db_session,
        finance.id,
    )

    finance_document = create_document(
        db_session,
        uploaded_by=finance_user.id,
        department_ids=[
            finance.id
        ],
    )

    create_document(
        db_session,
        uploaded_by=finance_user.id,
        department_ids=[
            engineering.id
        ],
    )

    configure_app(
        db_session,
        finance_user,
    )

    client = TestClient(
        app
    )

    try:
        response = client.get(
            "/documents"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 1
        assert len(
            body["items"]
        ) == 1

        assert (
            body["items"][0]["id"]
            == finance_document.id
        )

    finally:
        app.dependency_overrides.clear()


def test_non_admin_cannot_update_document_departments(
    db_session,
):
    engineering = create_department(
        db_session
    )

    finance = create_department(
        db_session
    )

    user = create_user(
        db_session,
        engineering.id,
    )

    document = create_document(
        db_session,
        uploaded_by=user.id,
        department_ids=[
            engineering.id
        ],
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(
        app
    )

    try:
        response = client.patch(
            f"/documents/{document.id}/departments",
            json={
                "department_ids": [
                    finance.id
                ]
            },
        )

        assert response.status_code == 403

    finally:
        app.dependency_overrides.clear()


def test_admin_updates_departments_and_creates_reindex_event(
    db_session,
):
    engineering = create_department(
        db_session
    )

    finance = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        engineering.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_ids=[
            engineering.id
        ],
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    try:
        response = client.patch(
            f"/documents/{document.id}/departments",
            json={
                "department_ids": [
                    finance.id
                ]
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["department_ids"] == [
            finance.id
        ]

        db_session.expire_all()

        refreshed_document = (
            db_session.get(
                Document,
                document.id,
            )
        )

        assert refreshed_document is not None

        assert [
            department.id
            for department
            in refreshed_document.departments
        ] == [
            finance.id
        ]

        event = (
            db_session.query(
                OutboxEvent
            )
            .filter(
                OutboxEvent.document_id
                == document.id,
                OutboxEvent.event_type
                == outbox.INGEST_DOCUMENT_EVENT,
                OutboxEvent.status
                == outbox.OUTBOX_PENDING,
            )
            .first()
        )

        assert event is not None

        assert refreshed_document.status == (
            DocumentStatus.UPLOADED
        )

    finally:
        app.dependency_overrides.clear()


def test_admin_can_schedule_reindex(
    db_session,
):
    engineering = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        engineering.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_ids=[
            engineering.id
        ],
        status=DocumentStatus.INDEXED,
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    try:
        response = client.post(
            f"/documents/{document.id}/reindex"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["status"] == "uploaded"

        db_session.expire_all()

        refreshed_document = (
            db_session.get(
                Document,
                document.id,
            )
        )

        assert refreshed_document is not None

        assert refreshed_document.status == (
            DocumentStatus.UPLOADED
        )

        event = (
            db_session.query(
                OutboxEvent
            )
            .filter(
                OutboxEvent.document_id
                == document.id,
                OutboxEvent.event_type
                == outbox.INGEST_DOCUMENT_EVENT,
                OutboxEvent.status
                == outbox.OUTBOX_PENDING,
            )
            .first()
        )

        assert event is not None

    finally:
        app.dependency_overrides.clear()


def test_reindex_rejects_document_already_processing(
    db_session,
):
    engineering = create_department(
        db_session
    )

    admin = create_admin(
        db_session,
        engineering.id,
    )

    document = create_document(
        db_session,
        uploaded_by=admin.id,
        department_ids=[
            engineering.id
        ],
        status=DocumentStatus.PROCESSING,
    )

    configure_app(
        db_session,
        admin,
    )

    client = TestClient(
        app
    )

    try:
        response = client.post(
            f"/documents/{document.id}/reindex"
        )

        assert response.status_code == 409

        body = response.json()

        assert body["detail"] == (
            "Document ingestion is already in progress"
        )
        assert body["request_id"]
        assert response.headers["X-Request-ID"] == (
            body["request_id"]
        )

    finally:
        app.dependency_overrides.clear()