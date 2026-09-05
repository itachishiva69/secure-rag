from fastapi.testclient import TestClient
from qdrant_client.models import ScoredPoint

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, Document, User
from app.models.enums import UserRole
from app.services.llm_provider import LLMProviderError


def create_test_data(db_session):
    finance = Department(
        name="Query-Finance"
    )

    engineering = Department(
        name="Query-Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )

    db_session.flush()

    finance_user = User(
        email="query-finance@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=finance.id,
    )

    engineering_user = User(
        email="query-engineering@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=engineering.id,
    )

    db_session.add_all(
        [
            finance_user,
            engineering_user,
        ]
    )

    db_session.flush()

    finance_document = Document(
        filename="finance-policy.txt",
        storage_path="test/finance-policy.txt",
        uploaded_by=finance_user.id,
        status="indexed",
    )

    engineering_document = Document(
        filename="engineering-secret.txt",
        storage_path="test/engineering-secret.txt",
        uploaded_by=engineering_user.id,
        status="indexed",
    )

    db_session.add_all(
        [
            finance_document,
            engineering_document,
        ]
    )

    db_session.flush()

    return (
        finance_user,
        engineering_user,
        finance_document,
        engineering_document,
    )


def test_finance_user_retrieval_only_returns_finance_chunks(
    db_session,
    monkeypatch,
):
    (
        finance_user,
        engineering_user,
        finance_document,
        _,
    ) = create_test_data(db_session)

    captured = {}

    def fake_search(
        *,
        query,
        allowed_department_ids,
        limit,
    ):
        captured["query"] = query
        captured["allowed_department_ids"] = (
            allowed_department_ids
        )
        captured["limit"] = limit

        return type(
            "SearchResult",
            (),
            {
                "points": [
                    ScoredPoint(
                        id="finance-point",
                        version=1,
                        score=0.95,
                        payload={
                            "document_id": (
                                finance_document.id
                            ),
                            "filename": (
                                "finance-policy.txt"
                            ),
                            "chunk_index": 0,
                            "department_ids": [
                                finance_user.department_id
                            ],
                            "text": (
                                "Finance department "
                                "policy information."
                            ),
                        },
                    )
                ]
            },
        )()

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            captured["llm_query"] = query
            captured["llm_context"] = context

            return (
                "The finance department policy "
                "contains finance information."
            )

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

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": (
                    "What is the company finance policy?"
                ),
                "limit": 5,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["query"] == (
            "What is the company finance policy?"
        )

        assert body["answer"] == (
            "The finance department policy "
            "contains finance information."
        )

        assert body["sources"] == [
            {
                "document_id": finance_document.id,
                "filename": "finance-policy.txt",
                "chunk_index": 0,
            }
        ]

        # Authorization must reach retrieval.
        assert captured["allowed_department_ids"] == [
            finance_user.department_id
        ]

        assert engineering_user.department_id not in (
            captured["allowed_department_ids"]
        )

        # The LLM receives the authorized context.
        assert captured["llm_query"] == (
            "What is the company finance policy?"
        )

        assert (
            "Finance department policy information."
            in captured["llm_context"].text
        )

        # The other department must never reach
        # the LLM context.
        assert (
            "engineering-secret.txt"
            not in captured["llm_context"].text
        )

        assert (
            "Engineering"
            not in captured["llm_context"].text
        )

    finally:
        app.dependency_overrides.clear()


def test_user_with_no_department_gets_no_results(
    db_session,
    monkeypatch,
):
    user = User(
        email="query-no-department@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=None,
    )

    db_session.add(user)
    db_session.flush()

    captured = {}

    def fake_search(
        *,
        query,
        allowed_department_ids,
        limit,
    ):
        captured["query"] = query
        captured["allowed_department_ids"] = (
            allowed_department_ids
        )
        captured["limit"] = limit

        return type(
            "SearchResult",
            (),
            {
                "points": []
            },
        )()

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "LLM must not be called when "
                "there is no authorized context"
            )

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
        lambda: user
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": (
                    "What documents do I have access to?"
                ),
                "limit": 5,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["query"] == (
            "What documents do I have access to?"
        )

        assert body["answer"] == (
            "I couldn't find any relevant "
            "information in the documents "
            "you are authorized to access."
        )

        assert body["sources"] == []

        assert captured["allowed_department_ids"] == []

        assert captured["query"] == (
            "What documents do I have access to?"
        )

        assert captured["limit"] == 5

    finally:
        app.dependency_overrides.clear()


def test_llm_provider_failure_returns_502(
    db_session,
    monkeypatch,
):
    (
        finance_user,
        _,
        finance_document,
        _,
    ) = create_test_data(db_session)

    def fake_search(
        *,
        query,
        allowed_department_ids,
        limit,
    ):
        assert allowed_department_ids == [
            finance_user.department_id
        ]

        return type(
            "SearchResult",
            (),
            {
                "points": [
                    ScoredPoint(
                        id="finance-point",
                        version=1,
                        score=0.95,
                        payload={
                            "document_id": (
                                finance_document.id
                            ),
                            "filename": (
                                "finance-policy.txt"
                            ),
                            "chunk_index": 0,
                            "department_ids": [
                                finance_user.department_id
                            ],
                            "text": (
                                "Finance department "
                                "policy information."
                            ),
                        },
                    )
                ]
            },
        )()

    class FailingProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise LLMProviderError(
                "simulated provider failure"
            )

    monkeypatch.setattr(
        "app.services.retrieval.search",
        fake_search,
    )

    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FailingProvider(),
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: finance_user
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": (
                    "What is the company finance policy?"
                ),
                "limit": 5,
            },
        )

        assert response.status_code == 502

        body = response.json()

        assert body["detail"] == (
            "The language model provider is "
            "temporarily unavailable."
        )

        # The internal provider error must never
        # be exposed to the API client.
        assert "simulated provider failure" not in (
            response.text
        )

    finally:
        app.dependency_overrides.clear()