from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

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


def create_test_department(
    db_session,
    name: str,
):
    department = Department(
        name=name,
    )

    db_session.add(department)
    db_session.flush()

    return department


def create_test_admin(
    db_session,
    department_id: int,
):
    user = User(
        email=unique_email(
            "ingestion-reliability-admin"
        ),
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

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=department_id,
        )
    )

    db_session.flush()

    return document


def test_qdrant_failure_marks_document_failed(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session,
        unique_name(
            "Ingestion-Qdrant-Failure"
        ),
    )

    admin = create_test_admin(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
        filename=(
            f"qdrant-failure-"
            f"{uuid4().hex}.txt"
        ),
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: (
            "This document contains valid "
            "content for ingestion."
        ),
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
            "This document contains valid "
            "content for ingestion."
        ],
    )

    monkeypatch.setattr(
        ingestion,
        "ensure_collection",
        lambda: None,
    )

    delete_called = False

    def fake_delete_document_vectors(
        document_id: int,
    ):
        nonlocal delete_called

        assert document_id == document.id

        delete_called = True

    monkeypatch.setattr(
        ingestion,
        "delete_document_vectors",
        fake_delete_document_vectors,
    )

    def fake_index_chunks(
        *,
        document_id: int,
        filename: str,
        chunks: list[str],
        department_ids: list[int],
    ):
        assert document_id == document.id
        assert filename == document.filename
        assert chunks == [
            "This document contains valid "
            "content for ingestion."
        ]
        assert department_ids == [
            department.id
        ]

        raise RuntimeError(
            "simulated qdrant indexing failure"
        )

    monkeypatch.setattr(
        ingestion,
        "index_chunks",
        fake_index_chunks,
    )

    with pytest.raises(RuntimeError) as exc_info:
        ingestion.ingest_document(
            db=db_session,
            document_id=document.id,
        )

    assert (
        str(exc_info.value)
        == "simulated qdrant indexing failure"
    )

    assert delete_called is True

    db_session.expire_all()

    refreshed_document = db_session.get(
        Document,
        document.id,
    )

    assert refreshed_document is not None

    assert (
        refreshed_document.status
        == DocumentStatus.FAILED
    )

    assert (
        refreshed_document.status
        != DocumentStatus.INDEXED
    )


def test_qdrant_failure_cleans_up_partial_vectors(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session,
        unique_name(
            "Ingestion-Partial-Vectors"
        ),
    )

    admin = create_test_admin(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
        filename=(
            f"partial-vectors-"
            f"{uuid4().hex}.txt"
        ),
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: (
            "Document used to test "
            "partial Qdrant cleanup."
        ),
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
            "Document used to test "
            "partial Qdrant cleanup."
        ],
    )

    monkeypatch.setattr(
        ingestion,
        "ensure_collection",
        lambda: None,
    )

    cleanup_called = False

    def fake_delete_document_vectors(
        document_id: int,
    ):
        nonlocal cleanup_called

        assert document_id == document.id

        cleanup_called = True

    monkeypatch.setattr(
        ingestion,
        "delete_document_vectors",
        fake_delete_document_vectors,
    )

    def fake_index_chunks(
        *,
        document_id: int,
        filename: str,
        chunks: list[str],
        department_ids: list[int],
    ):
        assert document_id == document.id

        # Simulate a Qdrant operation that created
        # partial state and then failed.
        raise RuntimeError(
            "simulated partial Qdrant failure"
        )

    monkeypatch.setattr(
        ingestion,
        "index_chunks",
        fake_index_chunks,
    )

    with pytest.raises(RuntimeError):
        ingestion.ingest_document(
            db=db_session,
            document_id=document.id,
        )

    assert cleanup_called is True

    db_session.expire_all()

    refreshed_document = db_session.get(
        Document,
        document.id,
    )

    assert refreshed_document is not None

    assert (
        refreshed_document.status
        == DocumentStatus.FAILED
    )


def test_final_db_commit_failure_does_not_persist_indexed_status(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session,
        unique_name(
            "Ingestion-Commit-Failure"
        ),
    )

    admin = create_test_admin(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
        filename=(
            f"final-commit-failure-"
            f"{uuid4().hex}.txt"
        ),
    )

    document_id = document.id

    # The initial transaction must succeed so that
    # PROCESSING is persisted before ingestion starts.
    original_commit = db_session.commit

    commit_calls = 0

    def failing_final_commit():
        nonlocal commit_calls

        commit_calls += 1

        # First commit persists PROCESSING.
        if commit_calls == 1:
            original_commit()
            return

        # The second commit is the commit that would
        # persist INDEXED.
        raise SQLAlchemyError(
            "simulated final database commit failure"
        )

    monkeypatch.setattr(
        db_session,
        "commit",
        failing_final_commit,
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: (
            "Document used to verify "
            "final database commit failure."
        ),
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
            "Document used to verify "
            "final database commit failure."
        ],
    )

    monkeypatch.setattr(
        ingestion,
        "ensure_collection",
        lambda: None,
    )

    monkeypatch.setattr(
        ingestion,
        "delete_document_vectors",
        lambda document_id: None,
    )

    monkeypatch.setattr(
        ingestion,
        "index_chunks",
        lambda **kwargs: 1,
    )

    with pytest.raises(SQLAlchemyError) as exc_info:
        ingestion.ingest_document(
            db=db_session,
            document_id=document_id,
        )

    assert (
        str(exc_info.value)
        == "simulated final database commit failure"
    )

    # The failed commit must not cause the database
    # to permanently record INDEXED.
    db_session.rollback()
    db_session.expire_all()

    refreshed_document = db_session.get(
        Document,
        document_id,
    )

    assert refreshed_document is not None

    assert (
        refreshed_document.status
        == DocumentStatus.PROCESSING
    )

    assert (
        refreshed_document.status
        != DocumentStatus.INDEXED
    )


def test_successful_ingestion_persists_indexed_status(
    db_session,
    monkeypatch,
):
    department = create_test_department(
        db_session,
        unique_name(
            "Ingestion-Success"
        ),
    )

    admin = create_test_admin(
        db_session,
        department.id,
    )

    document = create_test_document(
        db_session,
        user_id=admin.id,
        department_id=department.id,
        filename=(
            f"successful-ingestion-"
            f"{uuid4().hex}.txt"
        ),
    )

    monkeypatch.setattr(
        ingestion,
        "extract_text",
        lambda _: (
            "Successful ingestion test "
            "document."
        ),
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
            "Successful ingestion test "
            "document."
        ],
    )

    monkeypatch.setattr(
        ingestion,
        "ensure_collection",
        lambda: None,
    )

    monkeypatch.setattr(
        ingestion,
        "delete_document_vectors",
        lambda document_id: None,
    )

    monkeypatch.setattr(
        ingestion,
        "index_chunks",
        lambda **kwargs: 1,
    )

    indexed_count = ingestion.ingest_document(
        db=db_session,
        document_id=document.id,
    )

    assert indexed_count == 1

    db_session.expire_all()

    refreshed_document = db_session.get(
        Document,
        document.id,
    )

    assert refreshed_document is not None

    assert (
        refreshed_document.status
        == DocumentStatus.INDEXED
    )