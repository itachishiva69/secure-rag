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


def create_test_department(db_session):
    department = Department(
        name=unique_name("Reliability-Department")
    )

    db_session.add(department)
    db_session.flush()

    return department


def create_test_user(
    db_session,
    department_id: int,
):
    user = User(
        email=unique_email("reliability-admin"),
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
    department_id: int,
):
    document = Document(
        filename="reliability-test.txt",
        storage_path="test/reliability-test.txt",
        uploaded_by=user_id,
        status=DocumentStatus.UPLOADED,
    )

    db_session.add(document)
    db_session.flush()

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=department_id,
        )
    )

    db_session.flush()

    return document


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


def cleanup_document(
    document_id: int,
):
    qdrant_store.delete_document_vectors(
        document_id
    )


def test_failed_ingestion_removes_existing_vectors(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session
    )

    user = create_test_user(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: "initial content",
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
            "initial chunk one",
            "initial chunk two",
        ],
    )

    try:
        first_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert first_count == 2

        assert len(
            get_document_vectors(
                document.id
            )
        ) == 2

        def failing_extract(_):
            raise RuntimeError(
                "simulated extraction failure"
            )

        monkeypatch.setattr(
            ingestion,
            "extract_text",
            failing_extract,
        )

        with pytest.raises(
            RuntimeError,
            match="simulated extraction failure",
        ):
            ingestion.ingest_document(
                db_session,
                document.id,
            )

        db_session.refresh(document)

        assert document.status == (
            DocumentStatus.FAILED
        )

        assert (
            get_document_vectors(
                document.id
            )
            == []
        )

    finally:
        cleanup_document(
            document.id
        )


def test_partial_indexing_is_cleaned_up_after_failure(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session
    )

    user = create_test_user(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: "document content",
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
            "chunk three",
        ],
    )

    original_index_chunks = (
        ingestion.index_chunks
    )

    def failing_index_chunks(
        *,
        document_id,
        filename,
        chunks,
        department_ids,
    ):
        original_index_chunks(
            document_id=document_id,
            filename=filename,
            chunks=chunks[:1],
            department_ids=department_ids,
        )

        raise RuntimeError(
            "simulated indexing failure"
        )

    monkeypatch.setattr(
        ingestion,
        "index_chunks",
        failing_index_chunks,
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="simulated indexing failure",
        ):
            ingestion.ingest_document(
                db_session,
                document.id,
            )

        db_session.refresh(document)

        assert document.status == (
            DocumentStatus.FAILED
        )

        assert (
            get_document_vectors(
                document.id
            )
            == []
        )

    finally:
        cleanup_document(
            document.id
        )


def test_retry_after_failure_produces_clean_index(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session
    )

    user = create_test_user(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=user.id,
        department_id=department.id,
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: "retryable content",
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
            "retry chunk one",
            "retry chunk two",
        ],
    )

    original_index_chunks = (
        ingestion.index_chunks
    )

    call_count = 0

    def fail_once_then_succeed(
        *,
        document_id,
        filename,
        chunks,
        department_ids,
    ):
        nonlocal call_count

        call_count += 1

        if call_count == 1:
            original_index_chunks(
                document_id=document_id,
                filename=filename,
                chunks=chunks[:1],
                department_ids=department_ids,
            )

            raise RuntimeError(
                "simulated transient failure"
            )

        return original_index_chunks(
            document_id=document_id,
            filename=filename,
            chunks=chunks,
            department_ids=department_ids,
        )

    monkeypatch.setattr(
        ingestion,
        "index_chunks",
        fail_once_then_succeed,
    )

    try:
        with pytest.raises(
            RuntimeError,
            match="simulated transient failure",
        ):
            ingestion.ingest_document(
                db_session,
                document.id,
            )

        db_session.refresh(document)

        assert document.status == (
            DocumentStatus.FAILED
        )

        assert (
            get_document_vectors(
                document.id
            )
            == []
        )

        indexed_count = ingestion.ingest_document(
            db_session,
            document.id,
        )

        assert indexed_count == 2

        db_session.refresh(document)

        assert document.status == (
            DocumentStatus.INDEXED
        )

        points = get_document_vectors(
            document.id
        )

        assert len(points) == 2

        chunk_indexes = sorted(
            point.payload["chunk_index"]
            for point in points
        )

        assert chunk_indexes == [0, 1]

        texts = sorted(
            point.payload["text"]
            for point in points
        )

        assert texts == [
            "retry chunk one",
            "retry chunk two",
        ]

    finally:
        cleanup_document(
            document.id
        )