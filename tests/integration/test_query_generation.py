from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, Document, User
from app.models.enums import UserRole
from app.rag.reranker import get_reranker


def create_test_data(db_session):
    finance = Department(
        name="Generation-Finance"
    )

    engineering = Department(
        name="Generation-Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )

    db_session.flush()

    finance_user = User(
        email="generation-finance@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=finance.id,
    )

    engineering_user = User(
        email="generation-engineering@example.com",
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


def test_query_sends_only_authorized_context_to_llm(
    db_session,
    monkeypatch,
):
    (
        finance_user,
        _,
        finance_document,
        engineering_document,
    ) = create_test_data(db_session)

    captured = {}

    fake_reranker = object()

    def fake_retrieve_documents(
        *,
        query,
        current_user,
        limit,
        reranker,
    ):
        captured["query"] = query
        captured["current_user"] = current_user
        captured["limit"] = limit
        captured["reranker"] = reranker

        assert current_user.id == finance_user.id
        assert reranker is fake_reranker

        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "document_id": finance_document.id,
                        "filename": "finance-policy.txt",
                        "chunk_index": 0,
                        "department_ids": [
                            finance_user.department_id
                        ],
                        "text": (
                            "Finance department "
                            "budget policy."
                        ),
                    }
                )
            ]
        )

    class FakeProvider:
        def __init__(self):
            self.query = None
            self.context = None

        def generate(
            self,
            *,
            query,
            context,
        ):
            self.query = query
            self.context = context

            return (
                "The finance department "
                "has a budget policy."
            )

    fake_provider = FakeProvider()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )

    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: fake_provider,
    )

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: finance_user
    )

    app.dependency_overrides[get_reranker] = (
        lambda: fake_reranker
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "What is the finance budget policy?",
                "limit": 5,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["query"] == (
            "What is the finance budget policy?"
        )

        assert body["answer"] == (
            "The finance department has a budget policy."
        )

        assert body["sources"] == [
            {
                "document_id": finance_document.id,
                "filename": "finance-policy.txt",
                "chunk_index": 0,
            }
        ]

        assert captured["query"] == (
            "What is the finance budget policy?"
        )

        assert captured["current_user"] is finance_user

        assert captured["limit"] == 5

        assert captured["reranker"] is fake_reranker

        assert fake_provider.query == (
            "What is the finance budget policy?"
        )

        assert (
            "Finance department budget policy."
            in fake_provider.context.text
        )

        assert (
            "engineering-secret.txt"
            not in fake_provider.context.text
        )

        assert (
            "Engineering"
            not in fake_provider.context.text
        )

        assert str(engineering_document.id) not in (
            fake_provider.context.text
        )

    finally:
        app.dependency_overrides.clear()