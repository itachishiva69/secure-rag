import logging
from uuid import UUID

from fastapi.testclient import TestClient

from app.main import app


def test_response_contains_generated_request_id():
    client = TestClient(app)

    response = client.get(
        "/health"
    )

    assert response.status_code == 200

    request_id = response.headers.get(
        "X-Request-ID"
    )

    assert request_id is not None

    UUID(request_id)

    assert response.json() == {
        "status": "ok",
        "environment": "development",
    }


def test_valid_request_id_is_preserved():
    client = TestClient(app)

    request_id = (
        "550e8400-e29b-41d4-a716-446655440000"
    )

    response = client.get(
        "/health",
        headers={
            "X-Request-ID": request_id,
        },
    )

    assert response.status_code == 200

    assert response.headers[
        "X-Request-ID"
    ] == request_id


def test_invalid_request_id_is_replaced():
    client = TestClient(app)

    response = client.get(
        "/health",
        headers={
            "X-Request-ID": "invalid-request-id",
        },
    )

    assert response.status_code == 200

    request_id = response.headers.get(
        "X-Request-ID"
    )

    assert request_id is not None

    UUID(request_id)

    assert request_id != (
        "invalid-request-id"
    )


def test_logging_filter_adds_request_id():
    from app.core.logging import (
        RequestIdFilter,
    )
    from app.core.request_context import (
        reset_request_id,
        set_request_id,
    )

    request_id = (
        "550e8400-e29b-41d4-a716-446655440000"
    )

    token = set_request_id(
        request_id
    )

    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="test",
            args=(),
            exc_info=None,
        )

        log_filter = RequestIdFilter()

        assert log_filter.filter(
            record
        ) is True

        assert record.request_id == request_id

    finally:
        reset_request_id(token)