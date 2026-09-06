import asyncio
import json
import logging

from starlette.requests import Request

from app.core.logging import JsonFormatter
from app.main import (
    unhandled_exception_handler,
)


def make_request(
    *,
    path: str = "/internal-test",
):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
        }
    )


def test_unhandled_exception_returns_safe_response():
    request = make_request()

    request.state.request_id = (
        "test-request-id"
    )

    secret_error = RuntimeError(
        "database password must never leak"
    )

    response = asyncio.run(
        unhandled_exception_handler(
            request,
            secret_error,
        )
    )

    assert response.status_code == 500

    body = json.loads(
        response.body.decode("utf-8")
    )

    assert body == {
        "detail": "Internal server error",
        "request_id": "test-request-id",
    }

    assert (
        "database password"
        not in response.body.decode(
            "utf-8"
        )
    )

    assert response.headers[
        "X-Request-ID"
    ] == "test-request-id"


def test_json_formatter_includes_safe_fields():
    formatter = JsonFormatter()

    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="query_completed",
        args=(),
        exc_info=None,
    )

    record.request_id = (
        "test-request-id"
    )

    record.user_id = 42
    record.source_count = 3

    output = formatter.format(
        record
    )

    payload = json.loads(output)

    assert payload["logger"] == (
        "app.test"
    )

    assert payload["message"] == (
        "query_completed"
    )

    assert payload["request_id"] == (
        "test-request-id"
    )

    assert payload["user_id"] == 42

    assert payload["source_count"] == 3