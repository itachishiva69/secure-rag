from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_security_headers_are_present():
    response = client.get(
        "/health",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 200

    assert response.headers[
        "X-Content-Type-Options"
    ] == "nosniff"

    assert response.headers[
        "X-Frame-Options"
    ] == "DENY"

    assert response.headers[
        "Referrer-Policy"
    ] == "no-referrer"

    assert response.headers[
        "Permissions-Policy"
    ] == (
        "camera=(), "
        "microphone=(), "
        "geolocation=()"
    )


def test_trusted_host_allows_configured_test_host():
    response = client.get(
        "/health",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 200


def test_trusted_host_rejects_unknown_host():
    response = client.get(
        "/health",
        headers={
            "Host": "attacker.example",
        },
    )

    assert response.status_code == 400


def test_cors_allows_configured_origin():
    response = client.get(
        "/health",
        headers={
            "Host": "testserver",
            "Origin": "http://localhost:3000",
        },
    )

    assert response.status_code == 200
    assert response.headers[
        "access-control-allow-origin"
    ] == "http://localhost:3000"


def test_cors_rejects_unconfigured_origin():
    response = client.get(
        "/health",
        headers={
            "Host": "testserver",
            "Origin": "https://attacker.example",
        },
    )

    assert response.status_code == 200
    assert (
        "access-control-allow-origin"
        not in response.headers
    )


def test_cors_preflight_allows_configured_origin():
    response = client.options(
        "/query/",
        headers={
            "Host": "testserver",
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization,content-type"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers[
        "access-control-allow-origin"
    ] == "http://localhost:3000"

    assert "POST" in response.headers[
        "access-control-allow-methods"
    ]

    allow_headers = response.headers[
        "access-control-allow-headers"
    ].lower()

    assert "authorization" in allow_headers
    assert "content-type" in allow_headers