from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.main import app
from app.models.enums import UserRole


client = TestClient(app)


def test_query_rejects_client_supplied_department_ids():
    fake_user = SimpleNamespace(
        id=1,
        email="finance@example.com",
        role=UserRole.USER,
        department_id=2,
    )

    app.dependency_overrides[get_current_user] = (
        lambda: fake_user
    )

    try:
        with patch(
            "app.api.query.retrieve_documents"
        ) as mock_retrieve:

            response = client.post(
                "/query/",
                json={
                    "query": "How does engineering authentication work?",
                    "limit": 5,
                    "department_ids": [3],
                },
            )

        assert response.status_code == 422

        body = response.json()

        assert any(
            error["type"] == "extra_forbidden"
            and error["loc"] == [
                "body",
                "department_ids",
            ]
            for error in body["detail"]
        )

        mock_retrieve.assert_not_called()

    finally:
        app.dependency_overrides.clear()