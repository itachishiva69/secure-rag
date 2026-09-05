from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.security import hash_password
from app.db.database import get_db
from app.main import app
from app.models import (
    Department,
    Document,
    DocumentDepartment,
    User,
)
from app.models.enums import UserRole
from app.services import retrieval


def use_test_database(db_session):
    app.dependency_overrides[get_db] = lambda: db_session


def create_test_user(
    db_session,
    *,
    email,
    department_id,
):
    user = User(
        email=email,
        password_hash=hash_password("test-password"),
        role=UserRole.USER,
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

    db_session.add(
        DocumentDepartment(
            document_id=document.id,
            department_id=department_id,
        )
    )

    db_session.flush()

    return document


def make_fake_search(expected_department_id):
    def fake_search(
        *,
        query,
        allowed_department_ids=None,
        limit=5,
    ):
        if allowed_department_ids != [
            expected_department_id
        ]:
            return SimpleNamespace(
                points=[]
            )

        point = SimpleNamespace(
            payload={
                "document_id": 100,
                "filename": "engineering-secret.txt",
                "chunk_index": 0,
                "department_ids": [
                    expected_department_id
                ],
                "text": (
                    "Engineering confidential "
                    "information"
                ),
            }
        )

        return SimpleNamespace(
            points=[point]
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

    create_test_document(
        db_session,
        uploaded_by=finance_user.id,
        department_id=engineering.id,
        filename="engineering-secret.txt",
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        make_fake_search(
            engineering.id
        ),
    )

    app.dependency_overrides.clear()

    use_test_database(db_session)

    app.dependency_overrides[get_current_user] = (
        lambda: finance_user
    )

    client = TestClient(app)

    response = client.post(
        "/query/",
        json={
            "query": "engineering confidential information",
            "limit": 5,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["results"] == []


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

    create_test_document(
        db_session,
        uploaded_by=engineering_user.id,
        department_id=engineering.id,
        filename="engineering-secret.txt",
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        make_fake_search(
            engineering.id
        ),
    )

    app.dependency_overrides.clear()

    use_test_database(db_session)

    app.dependency_overrides[get_current_user] = (
        lambda: engineering_user
    )

    client = TestClient(app)

    response = client.post(
        "/query/",
        json={
            "query": "engineering confidential information",
            "limit": 5,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body["results"]) == 1

    result = body["results"][0]

    assert result["filename"] == (
        "engineering-secret.txt"
    )

    assert result["department_ids"] == [
        engineering.id
    ]

    assert result["text"] == (
        "Engineering confidential information"
    )


def test_query_request_cannot_override_department_filter(
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
        email="rag-filter-bypass@example.com",
        department_id=finance.id,
    )

    monkeypatch.setattr(
        retrieval,
        "search",
        make_fake_search(
            engineering.id
        ),
    )

    app.dependency_overrides.clear()

    use_test_database(db_session)

    app.dependency_overrides[get_current_user] = (
        lambda: finance_user
    )

    client = TestClient(app)

    response = client.post(
        "/query/",
        json={
            "query": "engineering confidential information",
            "limit": 5,
            "department_ids": [
                engineering.id
            ],
        },
    )

    assert response.status_code == 422