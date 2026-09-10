from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.models import Department, Document, User
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.services.retrieval import retrieve_documents


def test_user_retrieval_is_filtered_by_department(
    db_session,
):
    user = SimpleNamespace(
        role=UserRole.USER,
        department_id=3,
    )

    with patch(
        "app.services.retrieval.search"
    ) as mock_search:
        mock_search.return_value = None

        retrieve_documents(
            db=db_session,
            query="How does authentication work?",
            current_user=user,
            limit=5,
        )

        mock_search.assert_called_once_with(
            query="How does authentication work?",
            allowed_department_ids=[3],
            limit=5,
        )


def test_user_without_department_gets_no_department_access(
    db_session,
):
    user = SimpleNamespace(
        role=UserRole.USER,
        department_id=None,
    )

    with patch(
        "app.services.retrieval.search"
    ) as mock_search:
        result = retrieve_documents(
            db=db_session,
            query="confidential information",
            current_user=user,
            limit=5,
        )

        assert result == []

        mock_search.assert_not_called()


def test_admin_retrieval_is_unrestricted(
    db_session,
):
    user = SimpleNamespace(
        role=UserRole.ADMIN,
        department_id=None,
    )

    with patch(
        "app.services.retrieval.search"
    ) as mock_search:
        mock_search.return_value = None

        retrieve_documents(
            db=db_session,
            query="company information",
            current_user=user,
            limit=5,
        )

        mock_search.assert_called_once_with(
            query="company information",
            allowed_department_ids=None,
            limit=5,
        )


def _create_department_and_user(
    db_session,
    department_name: str,
    email_prefix: str,
) -> tuple[Department, User]:
    department = Department(
        name=department_name,
    )
    db_session.add(department)
    db_session.flush()

    user = User(
        email=f"{email_prefix}-{uuid4().hex}@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department.id,
    )
    db_session.add(user)
    db_session.flush()

    return department, user


def _create_indexed_document(
    db_session,
    *,
    department: Department,
    filename: str,
    uploaded_by: int,
    status: DocumentStatus = DocumentStatus.INDEXED,
) -> Document:
    document = Document(
        filename=filename,
        storage_path=f"/tmp/{uuid4().hex}.txt",
        uploaded_by=uploaded_by,
        status=status,
    )
    document.departments = [department]

    db_session.add(document)
    db_session.flush()

    return document


def _point(
    *,
    document_id: int,
    filename: str,
    department_ids: list[int],
):
    return SimpleNamespace(
        payload={
            "document_id": document_id,
            "filename": filename,
            "chunk_index": 0,
            "department_ids": department_ids,
            "text": f"content for {filename}",
        }
    )


def test_user_cannot_retrieve_document_from_another_department(
    db_session,
):
    engineering, engineering_user = (
        _create_department_and_user(
            db_session,
            f"Auth-Engineering-{uuid4().hex}",
            "engineering-user",
        )
    )
    test_department, uploader = (
        _create_department_and_user(
            db_session,
            f"Auth-Test-{uuid4().hex}",
            "test-uploader",
        )
    )

    engineering_document = _create_indexed_document(
        db_session,
        department=engineering,
        filename="engineering-policy.txt",
        uploaded_by=engineering_user.id,
    )
    test_document = _create_indexed_document(
        db_session,
        department=test_department,
        filename="test-policy.txt",
        uploaded_by=uploader.id,
    )

    results = SimpleNamespace(
        points=[
            _point(
                document_id=engineering_document.id,
                filename=engineering_document.filename,
                department_ids=[engineering.id],
            ),
            _point(
                document_id=test_document.id,
                filename=test_document.filename,
                department_ids=[test_department.id],
            ),
        ]
    )

    with patch(
        "app.services.retrieval.search",
        return_value=results,
    ):
        filtered_results = retrieve_documents(
            db=db_session,
            query="department policy",
            current_user=engineering_user,
            limit=5,
        )

    assert [
        point.payload["document_id"]
        for point in filtered_results.points
    ] == [engineering_document.id]


def test_user_cannot_retrieve_document_with_spoofed_department_payload(
    db_session,
):
    engineering, engineering_user = (
        _create_department_and_user(
            db_session,
            f"Spoof-Engineering-{uuid4().hex}",
            "spoof-engineering-user",
        )
    )
    test_department, uploader = (
        _create_department_and_user(
            db_session,
            f"Spoof-Test-{uuid4().hex}",
            "spoof-test-uploader",
        )
    )

    test_document = _create_indexed_document(
        db_session,
        department=test_department,
        filename="spoofed-payload.txt",
        uploaded_by=uploader.id,
    )

    results = SimpleNamespace(
        points=[
            _point(
                document_id=test_document.id,
                filename=test_document.filename,
                department_ids=[engineering.id],
            )
        ]
    )

    with patch(
        "app.services.retrieval.search",
        return_value=results,
    ):
        filtered_results = retrieve_documents(
            db=db_session,
            query="confidential engineering content",
            current_user=engineering_user,
            limit=5,
        )

    assert filtered_results.points == []


def test_deleting_document_is_not_retrievable(
    db_session,
):
    engineering, engineering_user = (
        _create_department_and_user(
            db_session,
            f"Deleting-Engineering-{uuid4().hex}",
            "deleting-engineering-user",
        )
    )

    deleting_document = _create_indexed_document(
        db_session,
        department=engineering,
        filename="deleting-document.txt",
        uploaded_by=engineering_user.id,
        status=DocumentStatus.DELETING,
    )

    results = SimpleNamespace(
        points=[
            _point(
                document_id=deleting_document.id,
                filename=deleting_document.filename,
                department_ids=[engineering.id],
            )
        ]
    )

    with patch(
        "app.services.retrieval.search",
        return_value=results,
    ):
        filtered_results = retrieve_documents(
            db=db_session,
            query="deleting document",
            current_user=engineering_user,
            limit=5,
        )

    assert filtered_results.points == []


def test_admin_can_retrieve_documents_across_departments(
    db_session,
):
    engineering, engineering_user = (
        _create_department_and_user(
            db_session,
            f"Admin-Engineering-{uuid4().hex}",
            "admin-test-engineering-user",
        )
    )
    test_department, test_user = (
        _create_department_and_user(
            db_session,
            f"Admin-Test-{uuid4().hex}",
            "admin-test-test-user",
        )
    )

    engineering_document = _create_indexed_document(
        db_session,
        department=engineering,
        filename="admin-engineering.txt",
        uploaded_by=engineering_user.id,
    )
    test_document = _create_indexed_document(
        db_session,
        department=test_department,
        filename="admin-test.txt",
        uploaded_by=test_user.id,
    )

    admin = User(
        email=f"retrieval-admin-{uuid4().hex}@example.com",
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=None,
    )
    db_session.add(admin)
    db_session.flush()

    results = SimpleNamespace(
        points=[
            _point(
                document_id=engineering_document.id,
                filename=engineering_document.filename,
                department_ids=[engineering.id],
            ),
            _point(
                document_id=test_document.id,
                filename=test_document.filename,
                department_ids=[test_department.id],
            ),
        ]
    )

    with patch(
        "app.services.retrieval.search",
        return_value=results,
    ):
        filtered_results = retrieve_documents(
            db=db_session,
            query="company-wide policy",
            current_user=admin,
            limit=5,
        )

    assert {
        point.payload["document_id"]
        for point in filtered_results.points
    } == {
        engineering_document.id,
        test_document.id,
    }
