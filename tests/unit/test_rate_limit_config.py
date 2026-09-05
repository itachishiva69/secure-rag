from app.core.config import Settings


def test_query_rate_limit_defaults():
    settings = Settings(
        database_url="postgresql://test",
        qdrant_url="http://localhost:6333",
        jwt_secret="test-secret",
    )

    assert settings.query_rate_limit_requests == 30

    assert (
        settings.query_rate_limit_window_seconds
        == 60
    )


def test_query_rate_limit_can_be_overridden():
    settings = Settings(
        database_url="postgresql://test",
        qdrant_url="http://localhost:6333",
        jwt_secret="test-secret",
        query_rate_limit_requests=100,
        query_rate_limit_window_seconds=300,
    )

    assert settings.query_rate_limit_requests == 100

    assert (
        settings.query_rate_limit_window_seconds
        == 300
    )