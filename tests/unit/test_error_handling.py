import uuid

from fastapi import (
    HTTPException,
    Request,
)
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(
    app,
    raise_server_exceptions=False,
)


def make_request_id() -> str:
    return str(uuid.uuid4())


def register_test_route(
    path: str,
    endpoint,
    *,
    method: str = "GET",
):
    app.router.add_api_route(
        path,
        endpoint,
        methods=[method],
    )


def remove_test_route(path: str):
    route = next(
        route
        for route in app.routes
        if getattr(
            route,
            "path",
            None,
        )
        == path
    )

    app.routes.remove(route)


def test_http_exception_returns_detail_and_request_id():
    request_id = make_request_id()

    async def failing_endpoint(
        request: Request,
    ):
        raise HTTPException(
            status_code=404,
            detail="Resource not found",
        )

    path = "/test-error-http"

    register_test_route(
        path,
        failing_endpoint,
    )

    try:
        response = client.get(
            path,
            headers={
                "X-Request-ID": request_id,
            },
        )

        assert response.status_code == 404

        body = response.json()

        assert body["detail"] == (
            "Resource not found"
        )

        assert body["request_id"] == (
            request_id
        )

        assert response.headers[
            "X-Request-ID"
        ] == request_id

    finally:
        remove_test_route(path)


def test_http_exception_preserves_headers():
    request_id = make_request_id()

    async def failing_endpoint(
        request: Request,
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={
                "Retry-After": "30",
            },
        )

    path = "/test-error-http-headers"

    register_test_route(
        path,
        failing_endpoint,
    )

    try:
        response = client.get(
            path,
            headers={
                "X-Request-ID": request_id,
            },
        )

        assert response.status_code == 429

        body = response.json()

        assert body["detail"] == (
            "Too many requests"
        )

        assert body["request_id"] == (
            request_id
        )

        assert response.headers[
            "Retry-After"
        ] == "30"

        assert response.headers[
            "X-Request-ID"
        ] == request_id

    finally:
        remove_test_route(path)


def test_validation_error_returns_422_with_request_id():
    request_id = make_request_id()

    async def validation_endpoint(
        request: Request,
    ):
        raise RequestValidationError(
            [
                {
                    "type": "missing",
                    "loc": (
                        "body",
                        "query",
                    ),
                    "msg": "Field required",
                    "input": None,
                }
            ]
        )

    path = "/test-error-validation"

    register_test_route(
        path,
        validation_endpoint,
        method="POST",
    )

    try:
        response = client.post(
            path,
            headers={
                "X-Request-ID": request_id,
            },
            json={},
        )

        assert response.status_code == 422

        body = response.json()

        assert body["request_id"] == (
            request_id
        )

        assert isinstance(
            body["detail"],
            list,
        )

        assert body["detail"][0]["type"] == (
            "missing"
        )

        assert response.headers[
            "X-Request-ID"
        ] == request_id

    finally:
        remove_test_route(path)


def test_unhandled_exception_hides_internal_details():
    request_id = make_request_id()

    async def failing_endpoint(
        request: Request,
    ):
        raise RuntimeError(
            "secret internal failure"
        )

    path = "/test-error-internal"

    register_test_route(
        path,
        failing_endpoint,
    )

    try:
        response = client.get(
            path,
            headers={
                "X-Request-ID": request_id,
            },
        )

        assert response.status_code == 500

        body = response.json()

        assert body["detail"] == (
            "Internal server error"
        )

        assert body["request_id"] == (
            request_id
        )

        assert (
            "secret internal failure"
            not in response.text
        )

        assert response.headers[
            "X-Request-ID"
        ] == request_id

    finally:
        remove_test_route(path)