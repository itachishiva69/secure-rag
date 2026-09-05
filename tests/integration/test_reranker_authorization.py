from unittest.mock import Mock

from app.models import Department, Document, User
from app.models.enums import UserRole
from app.rag.reranker import RerankedChunk
from app.rag import qdrant_store
from app.schemas.query import RetrievedChunk
from app.services.retrieval import retrieve_documents


def test_reranker_receives_only_authorized_candidates(
    db_session,
    monkeypatch,
):
    finance = Department(
        name="Reranker-Finance"
    )

    engineering = Department(
        name="Reranker-Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )
    db_session.flush()

    user = User(
        email="reranker-finance@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=finance.id,
    )

    db_session.add(user)
    db_session.flush()

    finance_document = Document(
        filename="finance.txt",
        storage_path="evaluation/finance.txt",
        uploaded_by=user.id,
        status="indexed",
    )

    engineering_document = Document(
        filename="engineering.txt",
        storage_path="evaluation/engineering.txt",
        uploaded_by=user.id,
        status="indexed",
    )

    finance_document.departments.append(finance)
    engineering_document.departments.append(
        engineering
    )

    db_session.add_all(
        [
            finance_document,
            engineering_document,
        ]
    )
    db_session.flush()

    finance_chunk = RetrievedChunk(
        document_id=finance_document.id,
        filename="finance.txt",
        chunk_index=0,
        department_ids=[finance.id],
        text="Finance department budget information.",
    )

    engineering_chunk = RetrievedChunk(
        document_id=engineering_document.id,
        filename="engineering.txt",
        chunk_index=0,
        department_ids=[engineering.id],
        text=(
            "Engineering department authentication "
            "information."
        ),
    )

    authorized_point = Mock()
    authorized_point.payload = (
        finance_chunk.model_dump()
    )

    unauthorized_point = Mock()
    unauthorized_point.payload = (
        engineering_chunk.model_dump()
    )

    search_result = Mock()
    search_result.points = [
        authorized_point,
        unauthorized_point,
    ]

    captured_chunks = []

    def fake_search(
        *,
        query,
        allowed_department_ids,
        limit,
    ):
        assert allowed_department_ids == [
            finance.id
        ]

        return search_result

    class SpyReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            captured_chunks.extend(chunks)

            return [
                RerankedChunk(
                    chunk=chunks[0],
                    score=1.0,
                )
            ]

    monkeypatch.setattr(
        qdrant_store,
        "search",
        fake_search,
    )

    monkeypatch.setattr(
        "app.services.retrieval.search",
        fake_search,
    )

    results = retrieve_documents(
        query="department information",
        current_user=user,
        limit=5,
        reranker=SpyReranker(),
    )

    assert len(captured_chunks) == 1

    assert captured_chunks[0].document_id == (
        finance_document.id
    )

    assert captured_chunks[0].filename == (
        "finance.txt"
    )

    captured_document_ids = {
        chunk.document_id
        for chunk in captured_chunks
    }

    assert captured_document_ids == {
        finance_document.id
    }

    assert all(
        chunk.document_id
        != engineering_document.id
        for chunk in captured_chunks
    )

    assert results.points == [
        authorized_point
    ]