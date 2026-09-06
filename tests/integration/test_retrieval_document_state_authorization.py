from types import SimpleNamespace

from app.models import Department, Document, DocumentDepartment, User
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services import retrieval


def create_user(
    db_session,
    *,
    email,
    department_id,
    role=UserRole.USER,
):
    user = User(
        email=email,
        password_hash="test-hash",
        role=role,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def create_document(
    db_session,
    *,
    user_id,
    department,
    status,
):
    document = Document(
        filename="security-state-test.txt",
        storage_path="test/security-state-test.txt",
        uploaded_by=user_id,
        status=status,
    )

    document.departments = [department]

    db_session.add(document)
    db_session.flush()

    return document


def make_point(
    *,
    document_id,
    department_ids,
):
    return SimpleNamespace(
        payload={
            "document_id": document_id,
            "filename": "security-state-test.txt",
            "chunk_index": 0,
            "department_ids": department_ids,
            "text": "Confidential security test",
        }
    )


def test_deleting_document_is_removed_before_reranking(
    db_session,
    monkeypatch,
):
    department = Department(
        name="Security-State-Deleting"
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        email="security-state-deleting@example.com",
        department_id=department.id,
    )

    document = create_document(
        db_session,
        user_id=user.id,
        department=department,
        status=DocumentStatus.DELETING,
    )

    search_result = SimpleNamespace(
        points=[
            make_point(
                document_id=document.id,
                department_ids=[department.id],
            )
        ]
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        lambda **kwargs: search_result,
    )

    class FailingReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            raise AssertionError(
                "DELETING document reached reranker"
            )

    results = retrieval.retrieve_documents(
        db=db_session,
        query="confidential",
        current_user=user,
        limit=5,
        reranker=FailingReranker(),
    )

    assert results.points == []


def test_missing_document_is_removed_before_llm(
    db_session,
    monkeypatch,
):
    department = Department(
        name="Security-State-Missing"
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        email="security-state-missing@example.com",
        department_id=department.id,
    )

    nonexistent_document_id = 999999

    search_result = SimpleNamespace(
        points=[
            make_point(
                document_id=nonexistent_document_id,
                department_ids=[department.id],
            )
        ]
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        lambda **kwargs: search_result,
    )

    class FailingReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            raise AssertionError(
                "Missing document reached reranker"
            )

    results = retrieval.retrieve_documents(
        db=db_session,
        query="confidential",
        current_user=user,
        limit=5,
        reranker=FailingReranker(),
    )

    assert results.points == []


def test_qdrant_payload_cannot_grant_department_access(
    db_session,
    monkeypatch,
):
    finance = Department(
        name="Security-State-Payload-Finance"
    )

    engineering = Department(
        name="Security-State-Payload-Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )
    db_session.flush()

    finance_user = create_user(
        db_session,
        email="security-state-payload-finance@example.com",
        department_id=finance.id,
    )

    engineering_document = create_document(
        db_session,
        user_id=finance_user.id,
        department=engineering,
        status=DocumentStatus.INDEXED,
    )

    # Simulate stale, corrupted, or forged vector metadata:
    # Qdrant claims the document belongs to Finance even though
    # PostgreSQL says it belongs to Engineering.
    forged_search_result = SimpleNamespace(
        points=[
            make_point(
                document_id=engineering_document.id,
                department_ids=[finance.id],
            )
        ]
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        lambda **kwargs: forged_search_result,
    )

    class FailingReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            raise AssertionError(
                "Forged Qdrant metadata granted access"
            )

    results = retrieval.retrieve_documents(
        db=db_session,
        query="confidential",
        current_user=finance_user,
        limit=5,
        reranker=FailingReranker(),
    )

    assert results.points == []


def test_multidepartment_document_is_accessible_to_authorized_department(
    db_session,
    monkeypatch,
):
    finance = Department(
        name="Security-State-Multi-Finance"
    )

    engineering = Department(
        name="Security-State-Multi-Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )
    db_session.flush()

    finance_user = create_user(
        db_session,
        email="security-state-multi-finance@example.com",
        department_id=finance.id,
    )

    document = Document(
        filename="security-state-multi.txt",
        storage_path="test/security-state-multi.txt",
        uploaded_by=finance_user.id,
        status=DocumentStatus.INDEXED,
    )

    db_session.add(document)
    db_session.flush()

    db_session.add_all(
        [
            DocumentDepartment(
                document_id=document.id,
                department_id=finance.id,
            ),
            DocumentDepartment(
                document_id=document.id,
                department_id=engineering.id,
            ),
        ]
    )
    db_session.flush()

    search_result = SimpleNamespace(
        points=[
            make_point(
                document_id=document.id,
                department_ids=[
                    finance.id,
                    engineering.id,
                ],
            )
        ]
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        lambda **kwargs: search_result,
    )

    captured = []

    class SpyReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            captured.extend(chunks)

            return [
                SimpleNamespace(
                    chunk=chunks[0],
                    score=1.0,
                )
            ]

    results = retrieval.retrieve_documents(
        db=db_session,
        query="confidential",
        current_user=finance_user,
        limit=5,
        reranker=SpyReranker(),
    )

    assert len(captured) == 1
    assert captured[0].document_id == document.id
    assert len(results.points) == 1


def test_authorized_department_document_reaches_reranker(
    db_session,
    monkeypatch,
):
    department = Department(
        name="Security-State-Authorized"
    )

    db_session.add(department)
    db_session.flush()

    user = create_user(
        db_session,
        email="security-state-authorized@example.com",
        department_id=department.id,
    )

    document = create_document(
        db_session,
        user_id=user.id,
        department=department,
        status=DocumentStatus.INDEXED,
    )

    search_result = SimpleNamespace(
        points=[
            make_point(
                document_id=document.id,
                department_ids=[department.id],
            )
        ]
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        lambda **kwargs: search_result,
    )

    captured = []

    class SpyReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            captured.extend(chunks)

            return [
                SimpleNamespace(
                    chunk=chunks[0],
                    score=1.0,
                )
            ]

    results = retrieval.retrieve_documents(
        db=db_session,
        query="confidential",
        current_user=user,
        limit=5,
        reranker=SpyReranker(),
    )

    assert len(captured) == 1
    assert captured[0].document_id == document.id
    assert len(results.points) == 1