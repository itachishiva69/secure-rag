from uuid import uuid4

import pytest
from qdrant_client.models import FieldCondition, Filter, MatchValue

from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services import ingestion


def unique_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}@example.com"


def create_test_department(db_session, name: str):
    department = Department(name=name)
    db_session.add(department)
    db_session.flush()
    return department


def create_test_user(
    db_session,
    *,
    email: str,
    department_id: int,
):
    user = User(
        email=email,
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def create_test_document(
    db_session,
    *,
    user_id: int,
    department_ids: list[int],
    filename: str,
):
    document = Document(
        filename=filename,
        storage_path=f"test/{filename}",
        uploaded_by=user_id,
        status=DocumentStatus.UPLOADED,
    )

    db_session.add(document)
    db_session.flush()

    for department_id in department_ids:
        db_session.add(
            DocumentDepartment(
                document_id=document.id,
                department_id=department_id,
            )
        )

    db_session.flush()

    return document


def get_document_vectors(document_id: int):
    points, _ = qdrant_store.client.scroll(
        collection_name=qdrant_store.settings.qdrant_collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="document_id",
                    match=MatchValue(value=document_id),
                )
            ]
        ),
        limit=100,
        with_payload=True,
        with_vectors=False,
    )

    return points


def test_ingestion_preserves_department_ids(
    db_session,
    monkeypatch,
):
    engineering = create_test_department(
        db_session,
        unique_name("Engineering-Ingestion-Test"),
    )

    finance = create_test_department(
        db_session,
        unique_name("Finance-Ingestion-Test"),
    )

    admin = create_test_user(
        db_session,
        email=unique_email("ingestion-admin"),
        department_id=engineering.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_ids=[
            engineering.id,
            finance.id,
        ],
        filename="multi-department.txt",
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: "chunk one\n\nchunk two",
    )

    monkeypatch.setattr(
        ingestion,
        "normalize_text",
        lambda text: text,
    )

    monkeypatch.setattr(
        ingestion,
        "split_text",
        lambda _: [
            "chunk one",
            "chunk two",
        ],
    )

    try:
        indexed_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert indexed_count == 2

        db_session.refresh(document)

        assert document.status == DocumentStatus.INDEXED

        points = get_document_vectors(document.id)

        assert len(points) == 2

        expected_department_ids = sorted(
            [
                engineering.id,
                finance.id,
            ]
        )

        for point in points:
            payload = point.payload or {}

            assert payload["document_id"] == document.id
            assert sorted(
                payload["department_ids"]
            ) == expected_department_ids

    finally:
        qdrant_store.delete_document_vectors(
            document.id
        )


def test_reindexing_replaces_old_vectors(
    db_session,
    monkeypatch,
):
    engineering = create_test_department(
        db_session,
        unique_name("Engineering-Reindex-Test"),
    )

    admin = create_test_user(
        db_session,
        email=unique_email("reindex-admin"),
        department_id=engineering.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_ids=[engineering.id],
        filename="reindex-test.txt",
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: "initial document content",
    )

    monkeypatch.setattr(
        ingestion,
        "normalize_text",
        lambda text: text,
    )

    monkeypatch.setattr(
        ingestion,
        "split_text",
        lambda _: [
            "old chunk one",
            "old chunk two",
        ],
    )

    try:
        first_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert first_count == 2

        first_points = get_document_vectors(
            document.id
        )

        assert len(first_points) == 2

        monkeypatch.setattr(
            ingestion,
            "extract_text",
            lambda _: "updated document content",
        )

        monkeypatch.setattr(
            ingestion,
            "split_text",
            lambda _: [
                "new updated chunk",
            ],
        )

        second_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert second_count == 1

        second_points = get_document_vectors(
            document.id
        )

        assert len(second_points) == 1

        payload = second_points[0].payload or {}

        assert payload["text"] == "new updated chunk"
        assert payload["document_id"] == document.id
        assert payload["department_ids"] == [
            engineering.id
        ]

    finally:
        qdrant_store.delete_document_vectors(
            document.id
        )


def test_reindexing_uses_current_department_assignments(
    db_session,
    monkeypatch,
):
    engineering = create_test_department(
        db_session,
        unique_name("Engineering-Assignment-Test"),
    )

    finance = create_test_department(
        db_session,
        unique_name("Finance-Assignment-Test"),
    )

    admin = create_test_user(
        db_session,
        email=unique_email("assignment-admin"),
        department_id=engineering.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_ids=[engineering.id],
        filename="department-reassignment.txt",
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: "department assignment test",
    )

    monkeypatch.setattr(
        ingestion,
        "normalize_text",
        lambda text: text,
    )

    monkeypatch.setattr(
        ingestion,
        "split_text",
        lambda _: [
            "department assignment chunk",
        ],
    )

    try:
        first_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert first_count == 1

        first_points = get_document_vectors(
            document.id
        )

        assert len(first_points) == 1

        first_payload = (
            first_points[0].payload or {}
        )

        assert first_payload["department_ids"] == [
            engineering.id
        ]

        # Change the document's department assignment.
        db_session.query(
            DocumentDepartment
        ).filter(
            DocumentDepartment.document_id
            == document.id
        ).delete(
            synchronize_session=False
        )

        db_session.add(
            DocumentDepartment(
                document_id=document.id,
                department_id=finance.id,
            )
        )

        db_session.commit()

        # Re-ingest after changing the authorization mapping.
        second_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert second_count == 1

        second_points = get_document_vectors(
            document.id
        )

        assert len(second_points) == 1

        second_payload = (
            second_points[0].payload or {}
        )

        assert second_payload["document_id"] == document.id
        assert second_payload["department_ids"] == [
            finance.id
        ]

        assert (
            engineering.id
            not in second_payload["department_ids"]
        )

    finally:
        qdrant_store.delete_document_vectors(
            document.id
        )