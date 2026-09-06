from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_request_body_within_limit_is_allowed():
    response = client.post(
        "/auth/login",
        json={
            "email": "test@example.com",
            "password": "small-password",
        },
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code != 413


def test_request_with_oversized_content_length_is_rejected():
    response = client.post(
        "/auth/login",
        content=b"x",
        headers={
            "Host": "testserver",
            "Content-Length": str(
                31 * 1024 * 1024
            ),
        },
    )

    assert response.status_code == 413

    assert response.json() == {
        "detail": (
            "Request body is too large. "
            "The maximum allowed size is 30 MB."
        )
    }


def test_request_body_limit_returns_json_error():
    response = client.post(
        "/auth/login",
        content=b"x",
        headers={
            "Host": "testserver",
            "Content-Length": str(
                31 * 1024 * 1024
            ),
        },
    )

    assert response.headers[
        "content-type"
    ].startswith(
        "application/json"
    )


def test_request_body_limit_preserves_request_id():
    request_id = (
        "4f3b7e91-3f79-4bbf-9d27-5cc7cf41c1d7"
    )

    response = client.post(
        "/auth/login",
        content=b"x",
        headers={
            "Host": "testserver",
            "Content-Length": str(
                31 * 1024 * 1024
            ),
            "X-Request-ID": request_id,
        },
    )

    assert response.status_code == 413

    assert response.headers[
        "X-Request-ID"
    ] == request_id