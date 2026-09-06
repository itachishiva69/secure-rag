from fastapi.testclient import TestClient

import app.main as main


client = TestClient(app=main.app)


def test_health_is_liveness_only():
    response = client.get(
        "/health",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ok",
        "environment": main.settings.app_env,
    }


def test_readiness_returns_200_when_dependencies_are_healthy(
    monkeypatch,
):
    calls = []

    def fake_database():
        calls.append("database")

    def fake_redis():
        calls.append("redis")

    def fake_qdrant():
        calls.append("qdrant")

    monkeypatch.setattr(
        main,
        "check_database",
        fake_database,
    )

    monkeypatch.setattr(
        main,
        "check_redis",
        fake_redis,
    )

    monkeypatch.setattr(
        main,
        "check_qdrant",
        fake_qdrant,
    )

    response = client.get(
        "/ready",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 200

    assert response.json() == {
        "status": "ready",
    }

    assert calls == [
        "database",
        "redis",
        "qdrant",
    ]


def test_readiness_returns_503_when_database_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "check_database",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "database failure"
                )
            )
        ),
    )

    monkeypatch.setattr(
        main,
        "check_redis",
        lambda: None,
    )

    monkeypatch.setattr(
        main,
        "check_qdrant",
        lambda: None,
    )

    response = client.get(
        "/ready",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 503

    assert response.json() == {
        "status": "not_ready",
        "failed_dependencies": [
            "database",
        ],
    }


def test_readiness_returns_503_when_redis_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "check_database",
        lambda: None,
    )

    monkeypatch.setattr(
        main,
        "check_redis",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "redis failure"
                )
            )
        ),
    )

    monkeypatch.setattr(
        main,
        "check_qdrant",
        lambda: None,
    )

    response = client.get(
        "/ready",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 503

    assert response.json() == {
        "status": "not_ready",
        "failed_dependencies": [
            "redis",
        ],
    }


def test_readiness_returns_503_when_qdrant_fails(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "check_database",
        lambda: None,
    )

    monkeypatch.setattr(
        main,
        "check_redis",
        lambda: None,
    )

    monkeypatch.setattr(
        main,
        "check_qdrant",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "qdrant failure"
                )
            )
        ),
    )

    response = client.get(
        "/ready",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 503

    assert response.json() == {
        "status": "not_ready",
        "failed_dependencies": [
            "qdrant",
        ],
    }


def test_readiness_reports_multiple_failed_dependencies(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "check_database",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "database failure"
                )
            )
        ),
    )

    monkeypatch.setattr(
        main,
        "check_redis",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "redis failure"
                )
            )
        ),
    )

    monkeypatch.setattr(
        main,
        "check_qdrant",
        lambda: None,
    )

    response = client.get(
        "/ready",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 503

    assert response.json() == {
        "status": "not_ready",
        "failed_dependencies": [
            "database",
            "redis",
        ],
    }


def test_qdrant_health_hides_internal_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "check_qdrant",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError(
                    "internal qdrant connection details"
                )
            )
        ),
    )

    response = client.get(
        "/health/qdrant",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 503

    assert response.json() == {
        "status": "unavailable",
    }

    assert (
        "internal qdrant connection details"
        not in response.text
    )