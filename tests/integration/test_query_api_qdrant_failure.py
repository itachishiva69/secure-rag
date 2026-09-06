from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.query import get_query_reranker
from app.db.database import get_db
from app.main import app
from app.models import Department, User
from app.models.enums import UserRole
from app.rag.qdrant_store import QdrantStoreError


def create_test_user(db_session):
    department = Department(
        name="Qdrant-Failure-Test"
    )

    db_session.add(department)
    db_session.flush()

    user = User(
        email="qdrant-failure@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department.id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def test_qdrant_failure_returns_503_and_does_not_call_llm(
    db_session,
    monkeypatch,
):
    user = create_test_user(
        db_session
    )

    llm_called = False

    def fake_retrieve_documents(
        *,
        db,
        query,
        current_user,
        limit,
        reranker,
    ):
        assert db is db_session
        assert current_user is user
        assert query == "What is the company policy?"
        assert limit == 5
        assert reranker is None

        raise QdrantStoreError(
            "Qdrant search failed"
        )

    class FailingLLMProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            nonlocal llm_called
            llm_called = True

            raise AssertionError(
                "LLM must not be called after "
                "Qdrant retrieval failure"
            )

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )

    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FailingLLMProvider(),
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: user
    )

    app.dependency_overrides[get_query_reranker] = (
        lambda: None
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "What is the company policy?",
                "limit": 5,
            },
        )

        assert response.status_code == 503

        body = response.json()

        assert body["detail"] == (
            "The document retrieval service "
            "is temporarily unavailable."
        )

        assert "Qdrant search failed" not in (
            body["detail"]
        )

        assert llm_called is False

    finally:
        app.dependency_overrides.clear()