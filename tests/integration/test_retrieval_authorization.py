from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.main import app
from app.models import Department, Document, User
from app.models.enums import UserRole
from app.services import retrieval


def create_test_user(
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


def create_test_document(
    db_session,
    *,
    uploaded_by,
    department_id,
    filename,
):
    document = Document(
        filename=filename,
        storage_path=f"test/{filename}",
        uploaded_by=uploaded_by,
        status="indexed",
    )

    db_session.add(document)
    db_session.flush()

    department = db_session.get(
        Department,
        department_id,
    )

    document.departments.append(department)

    db_session.flush()

    return document


def make_fake_search(
    *,
    document_id,
    department_id,
):
    def fake_search(
        *,
        query,
        allowed_department_ids,
        limit,
    ):
        if department_id not in (
            allowed_department_ids or []
        ):
            return SimpleNamespace(
                points=[]
            )

        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "document_id": document_id,
                        "filename": (
                            "engineering-secret.txt"
                        ),
                        "chunk_index": 0,
                        "department_ids": [
                            department_id
                        ],
                        "text": (
                            "Engineering confidential "
                            "information."
                        ),
                    }
                )
            ]
        )

    return fake_search


def test_finance_user_cannot_retrieve_engineering_chunks(
    db_session,
    monkeypatch,
):
    finance = Department(
        name="Finance"
    )

    engineering = Department(
        name="Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )

    db_session.flush()

    finance_user = create_test_user(
        db_session,
        email="rag-finance@example.com",
        department_id=finance.id,
    )

    engineering_document = create_test_document(
        db_session,
        uploaded_by=finance_user.id,
        department_id=engineering.id,
        filename="engineering-secret.txt",
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        make_fake_search(
            document_id=engineering_document.id,
            department_id=engineering.id,
        ),
    )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "LLM must not receive unauthorized "
                "retrieval results"
            )

    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FakeProvider(),
    )

    app.dependency_overrides.clear()

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
                    "engineering confidential "
                    "information"
                ),
                "limit": 5,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["sources"] == []

        assert body["answer"] == (
            "I couldn't find any relevant "
            "information in the documents "
            "you are authorized to access."
        )

    finally:
        app.dependency_overrides.clear()


def test_engineering_user_can_retrieve_own_department_chunks(
    db_session,
    monkeypatch,
):
    engineering = Department(
        name="Engineering"
    )

    db_session.add(engineering)
    db_session.flush()

    engineering_user = create_test_user(
        db_session,
        email="rag-engineering@example.com",
        department_id=engineering.id,
    )

    engineering_document = create_test_document(
        db_session,
        uploaded_by=engineering_user.id,
        department_id=engineering.id,
        filename="engineering-secret.txt",
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        make_fake_search(
            document_id=engineering_document.id,
            department_id=engineering.id,
        ),
    )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            assert (
                "Engineering confidential "
                "information."
                in context.text
            )

            return (
                "Engineering confidential "
                "information was found."
            )

    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FakeProvider(),
    )

    app.dependency_overrides.clear()

    app.dependency_overrides[get_db] = (
        lambda: db_session
    )

    app.dependency_overrides[get_current_user] = (
        lambda: engineering_user
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": (
                    "engineering confidential "
                    "information"
                ),
                "limit": 5,
            },
        )

        assert response.status_code == 200

        body = response.json()

        assert body["answer"] == (
            "Engineering confidential "
            "information was found."
        )

        assert body["sources"] == [
            {
                "document_id": (
                    engineering_document.id
                ),
                "filename": (
                    "engineering-secret.txt"
                ),
                "chunk_index": 0,
            }
        ]

    finally:
        app.dependency_overrides.clear()