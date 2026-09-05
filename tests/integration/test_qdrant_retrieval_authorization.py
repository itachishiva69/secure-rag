from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services.authorization import get_allowed_department_ids


def create_test_user(
    *,
    department_id,
):
    return type(
        "TestUser",
        (),
        {
            "id": 1,
            "role": UserRole.USER,
            "department_id": department_id,
        },
    )()


def index_test_chunk(
    *,
    document_id,
    filename,
    department_ids,
    text,
):
    qdrant_store.index_chunks(
        document_id=document_id,
        filename=filename,
        department_ids=department_ids,
        chunks=[text],
    )


def test_finance_filter_cannot_retrieve_engineering_vector():
    finance_department_id = 9101
    engineering_department_id = 9102
    document_id = 91001

    index_test_chunk(
        document_id=document_id,
        filename="engineering-qdrant-security-test.txt",
        department_ids=[engineering_department_id],
        text="Engineering confidential Qdrant security test",
    )

    finance_user = create_test_user(
        department_id=finance_department_id,
    )

    allowed_department_ids = get_allowed_department_ids(
        finance_user
    )

    try:
        results = qdrant_store.search(
            query="Engineering confidential Qdrant security test",
            allowed_department_ids=allowed_department_ids,
            limit=5,
        )

        assert results.points == []

    finally:
        qdrant_store.delete_document_vectors(
            document_id
        )


def test_engineering_filter_can_retrieve_engineering_vector():
    engineering_department_id = 9103
    document_id = 91002

    index_test_chunk(
        document_id=document_id,
        filename="engineering-qdrant-security-test.txt",
        department_ids=[engineering_department_id],
        text="Engineering confidential Qdrant security test",
    )

    engineering_user = create_test_user(
        department_id=engineering_department_id,
    )

    allowed_department_ids = get_allowed_department_ids(
        engineering_user
    )

    try:
        results = qdrant_store.search(
            query="Engineering confidential Qdrant security test",
            allowed_department_ids=allowed_department_ids,
            limit=5,
        )

        assert len(results.points) == 1

        payload = results.points[0].payload

        assert payload["document_id"] == document_id
        assert payload["filename"] == (
            "engineering-qdrant-security-test.txt"
        )
        assert payload["department_ids"] == [
            engineering_department_id
        ]
        assert payload["text"] == (
            "Engineering confidential Qdrant security test"
        )

    finally:
        qdrant_store.delete_document_vectors(
            document_id
        )


def test_empty_department_authorization_returns_no_results():
    document_id = 91003
    engineering_department_id = 9104

    index_test_chunk(
        document_id=document_id,
        filename="engineering-qdrant-security-test.txt",
        department_ids=[engineering_department_id],
        text="Engineering confidential Qdrant security test",
    )

    user_without_department = create_test_user(
        department_id=None,
    )

    allowed_department_ids = get_allowed_department_ids(
        user_without_department
    )

    try:
        assert allowed_department_ids == []

        results = qdrant_store.search(
            query="Engineering confidential Qdrant security test",
            allowed_department_ids=allowed_department_ids,
            limit=5,
        )

        assert results == []

    finally:
        qdrant_store.delete_document_vectors(
            document_id
        )