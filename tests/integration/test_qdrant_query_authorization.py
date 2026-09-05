from app.models import Department, Document, User
from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services.retrieval import retrieve_documents


def create_test_data(db_session):
    finance = Department(
        name="Qdrant-Finance"
    )

    engineering = Department(
        name="Qdrant-Engineering"
    )

    db_session.add_all(
        [
            finance,
            engineering,
        ]
    )

    db_session.flush()

    finance_user = User(
        email="qdrant-finance@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=finance.id,
    )

    engineering_user = User(
        email="qdrant-engineering@example.com",
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
        filename="qdrant-finance.txt",
        storage_path="test/qdrant-finance.txt",
        uploaded_by=finance_user.id,
        status="indexed",
    )

    engineering_document = Document(
        filename="qdrant-engineering.txt",
        storage_path="test/qdrant-engineering.txt",
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


def test_real_qdrant_filter_blocks_other_department(
    db_session,
):
    (
        finance_user,
        engineering_user,
        finance_document,
        engineering_document,
    ) = create_test_data(db_session)

    indexed_document_ids = []

    try:
        qdrant_store.ensure_collection()

        finance_chunks = [
            "Finance department budget and accounting policy."
        ]

        engineering_chunks = [
            "Engineering department infrastructure and deployment policy."
        ]

        finance_count = qdrant_store.index_chunks(
            document_id=finance_document.id,
            filename=finance_document.filename,
            chunks=finance_chunks,
            department_ids=[
                finance_user.department_id
            ],
        )

        engineering_count = qdrant_store.index_chunks(
            document_id=engineering_document.id,
            filename=engineering_document.filename,
            chunks=engineering_chunks,
            department_ids=[
                engineering_user.department_id
            ],
        )

        assert finance_count == 1
        assert engineering_count == 1

        indexed_document_ids.extend(
            [
                finance_document.id,
                engineering_document.id,
            ]
        )

        results = retrieve_documents(
            query="department policy",
            current_user=finance_user,
            limit=10,
        )

        assert results is not None

        points = results.points

        assert len(points) >= 1

        returned_document_ids = {
            point.payload["document_id"]
            for point in points
        }

        returned_department_ids = {
            department_id
            for point in points
            for department_id in point.payload[
                "department_ids"
            ]
        }

        # Finance user must receive at least one
        # Finance result.
        assert finance_document.id in (
            returned_document_ids
        )

        # Engineering document must never be returned.
        assert engineering_document.id not in (
            returned_document_ids
        )

        # Engineering department must never appear
        # in the returned payloads.
        assert engineering_user.department_id not in (
            returned_department_ids
        )

        # Every returned vector must belong to the
        # Finance department.
        for point in points:
            payload = point.payload or {}

            assert payload["document_id"] == (
                finance_document.id
            )

            assert payload["department_ids"] == [
                finance_user.department_id
            ]

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )


def test_user_without_department_cannot_retrieve_from_qdrant(
    db_session,
):
    user = User(
        email="qdrant-no-department@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=None,
    )

    db_session.add(user)
    db_session.flush()

    results = retrieve_documents(
        query="department policy",
        current_user=user,
        limit=10,
    )

    # A user without a department receives an empty
    # result directly from the authorization layer.
    assert results == []


def test_admin_can_retrieve_across_departments(
    db_session,
):
    (
        finance_user,
        engineering_user,
        finance_document,
        engineering_document,
    ) = create_test_data(db_session)

    admin = User(
        email="qdrant-admin@example.com",
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=None,
    )

    db_session.add(admin)
    db_session.flush()

    indexed_document_ids = []

    try:
        qdrant_store.ensure_collection()

        qdrant_store.index_chunks(
            document_id=finance_document.id,
            filename=finance_document.filename,
            chunks=[
                "Finance department budget policy."
            ],
            department_ids=[
                finance_user.department_id
            ],
        )

        qdrant_store.index_chunks(
            document_id=engineering_document.id,
            filename=engineering_document.filename,
            chunks=[
                "Engineering department deployment policy."
            ],
            department_ids=[
                engineering_user.department_id
            ],
        )

        indexed_document_ids.extend(
            [
                finance_document.id,
                engineering_document.id,
            ]
        )

        results = retrieve_documents(
            query="department policy",
            current_user=admin,
            limit=10,
        )

        assert results is not None

        points = results.points

        returned_document_ids = {
            point.payload["document_id"]
            for point in points
        }

        # Admin retrieval is intentionally unrestricted
        # under the current authorization model.
        assert finance_document.id in (
            returned_document_ids
        )

        assert engineering_document.id in (
            returned_document_ids
        )

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )