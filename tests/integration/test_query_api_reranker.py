from types import SimpleNamespace

from fastapi.testclient import TestClient
from qdrant_client.models import ScoredPoint

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models.enums import UserRole
from app.rag.reranker import RerankedChunk, get_reranker

from tests.integration.test_query_api import (
    create_test_data,
)


def test_query_uses_reranked_order_for_context_and_sources(
    db_session,
    monkeypatch,
):
    (
        finance_user,
        _,
        finance_document,
        _,
    ) = create_test_data(db_session)

    chunks = [
        {
            "document_id": finance_document.id,
            "filename": "finance-policy.txt",
            "chunk_index": 0,
            "department_ids": [
                finance_user.department_id
            ],
            "text": "Original ranking chunk A.",
        },
        {
            "document_id": finance_document.id,
            "filename": "finance-policy.txt",
            "chunk_index": 1,
            "department_ids": [
                finance_user.department_id
            ],
            "text": "Original ranking chunk B.",
        },
        {
            "document_id": finance_document.id,
            "filename": "finance-policy.txt",
            "chunk_index": 2,
            "department_ids": [
                finance_user.department_id
            ],
            "text": "Original ranking chunk C.",
        },
    ]

    captured = {
        "search_limit": None,
        "reranker_query": None,
        "reranker_chunks": None,
        "reranker_limit": None,
        "llm_context": None,
    }

    def fake_search(
        *,
        query,
        allowed_department_ids,
        limit,
    ):
        assert allowed_department_ids == [
            finance_user.department_id
        ]

        captured["search_limit"] = limit

        return SimpleNamespace(
            points=[
                ScoredPoint(
                    id="finance-0",
                    version=1,
                    score=0.90,
                    payload=chunks[0],
                ),
                ScoredPoint(
                    id="finance-1",
                    version=1,
                    score=0.80,
                    payload=chunks[1],
                ),
                ScoredPoint(
                    id="finance-2",
                    version=1,
                    score=0.70,
                    payload=chunks[2],
                ),
            ]
        )

    class SpyReranker:
        def rerank(
            self,
            *,
            query,
            chunks,
            limit,
        ):
            captured["reranker_query"] = query
            captured["reranker_chunks"] = chunks
            captured["reranker_limit"] = limit

            # Simulate the reranker changing the original
            # Qdrant order from A, B, C to C, A.
            return [
                RerankedChunk(
                    chunk=chunks[2],
                    score=2.0,
                ),
                RerankedChunk(
                    chunk=chunks[0],
                    score=1.0,
                ),
            ]

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            captured["llm_context"] = context

            return "Answer based on reranked context."

    spy_reranker = SpyReranker()

    monkeypatch.setattr(
        "app.services.retrieval.search",
        fake_search,
    )

    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FakeProvider(),
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: finance_user
    )

    app.dependency_overrides[get_reranker] = (
        lambda: spy_reranker
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "What is the finance policy?",
                "limit": 2,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["answer"] == (
            "Answer based on reranked context."
        )

        # Qdrant provides the larger candidate set.
        assert captured["search_limit"] == 10

        # The reranker receives the same authorized
        # candidates returned by retrieval.
        assert captured["reranker_query"] == (
            "What is the finance policy?"
        )

        assert [
            chunk.chunk_index
            for chunk in captured["reranker_chunks"]
        ] == [0, 1, 2]

        # The endpoint asks retrieval for the requested
        # final result count.
        assert captured["reranker_limit"] == 2

        # The LLM receives the reranked order:
        # chunk 2 first, then chunk 0.
        context_text = captured["llm_context"].text

        assert (
            context_text.index(
                "Original ranking chunk C."
            )
            < context_text.index(
                "Original ranking chunk A."
            )
        )

        assert "Original ranking chunk B." not in (
            context_text
        )

        # API sources must preserve that same reranked order.
        assert body["sources"] == [
            {
                "document_id": finance_document.id,
                "filename": "finance-policy.txt",
                "chunk_index": 2,
            },
            {
                "document_id": finance_document.id,
                "filename": "finance-policy.txt",
                "chunk_index": 0,
            },
        ]

    finally:
        app.dependency_overrides.clear()