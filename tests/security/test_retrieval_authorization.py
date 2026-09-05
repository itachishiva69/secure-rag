from types import SimpleNamespace
from unittest.mock import patch

from app.models.enums import UserRole
from app.services.retrieval import retrieve_documents


def test_user_retrieval_is_filtered_by_department():
    user = SimpleNamespace(
        role=UserRole.USER,
        department_id=3,
    )

    with patch(
        "app.services.retrieval.search"
    ) as mock_search:

        mock_search.return_value = None

        retrieve_documents(
            query="How does authentication work?",
            current_user=user,
            limit=5,
        )

        mock_search.assert_called_once_with(
            query="How does authentication work?",
            allowed_department_ids=[3],
            limit=5,
        )


def test_user_without_department_gets_no_department_access():
    user = SimpleNamespace(
        role=UserRole.USER,
        department_id=None,
    )

    with patch(
        "app.services.retrieval.search"
    ) as mock_search:

        result = retrieve_documents(
            query="confidential information",
            current_user=user,
            limit=5,
        )

        assert result == []

        mock_search.assert_not_called()


def test_admin_retrieval_is_unrestricted():
    user = SimpleNamespace(
        role=UserRole.ADMIN,
        department_id=None,
    )

    with patch(
        "app.services.retrieval.search"
    ) as mock_search:

        mock_search.return_value = None

        retrieve_documents(
            query="company information",
            current_user=user,
            limit=5,
        )

        mock_search.assert_called_once_with(
            query="company information",
            allowed_department_ids=None,
            limit=5,
        )