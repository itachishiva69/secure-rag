import asyncio
import json
import logging

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.core.logging import JsonFormatter
from app.main import (
    http_exception_handler,
    request_validation_exception_handler,
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


def test_http_exception_preserves_safe_detail():
    request = make_request()

    request.state.request_id = (
        "test-request-id"
    )

    exception = HTTPException(
        status_code=403,
        detail="Admin privileges required",
    )

    response = asyncio.run(
        http_exception_handler(
            request,
            exception,
        )
    )

    assert response.status_code == 403

    body = json.loads(
        response.body.decode("utf-8")
    )

    assert body == {
        "detail": "Admin privileges required",
    }

    assert response.headers[
        "X-Request-ID"
    ] == "test-request-id"


def test_http_exception_preserves_headers():
    request = make_request()

    request.state.request_id = (
        "test-request-id"
    )

    exception = HTTPException(
        status_code=429,
        detail="Too many requests",
        headers={
            "Retry-After": "60",
        },
    )

    response = asyncio.run(
        http_exception_handler(
            request,
            exception,
        )
    )

    assert response.status_code == 429

    assert response.headers[
        "Retry-After"
    ] == "60"

    assert response.headers[
        "X-Request-ID"
    ] == "test-request-id"


def test_request_validation_preserves_fastapi_shape():
    request = make_request(
        path="/auth/login"
    )

    request.state.request_id = (
        "test-request-id"
    )

    validation_error = (
        RequestValidationError(
            [
                {
                    "type": "missing",
                    "loc": (
                        "body",
                        "password",
                    ),
                    "msg": "Field required",
                    "input": {},
                }
            ]
        )
    )

    response = asyncio.run(
        request_validation_exception_handler(
            request,
            validation_error,
        )
    )

    assert response.status_code == 422

    body = json.loads(
        response.body.decode("utf-8")
    )

    assert body == {
        "detail": [
            {
                "type": "missing",
                "loc": [
                    "body",
                    "password",
                ],
                "msg": "Field required",
                "input": {},
            }
        ],
    }

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