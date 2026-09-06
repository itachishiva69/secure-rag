import pytest
from pydantic import ValidationError
from app.core.config import Settings




def make_settings(**overrides):
    values = {
        "app_name": "Secure RAG",
        "app_env": "test",
        "debug": False,
        "database_url": "postgresql+psycopg://test:test@localhost:5433/test",
        "qdrant_url": "http://localhost:6333",
        "qdrant_collection": "documents",
        "jwt_secret": "test-secret-" + ("x" * 64),
        "redis_url": "redis://localhost:6379/0",
        "storage_path": "/tmp/secure-rag-test/documents",
        "llm_api_key": "test-key",
        "llm_model": "openai/gpt-oss-120b",
        "llm_base_url": "https://api.groq.com/openai/v1",
    }

    values.update(overrides)
    return Settings(**values)


def test_development_allows_local_services():
    settings = make_settings(
        app_env="development",
    )

    assert settings.app_env == "development"


def test_production_rejects_debug():
    with pytest.raises(ValueError, match="DEBUG"):
        make_settings(
            app_env="production",
            debug=True,
            database_url="postgresql+psycopg://user:pass@db.example:5432/app",
            qdrant_url="https://qdrant.example",
            redis_url="redis://redis.example:6379/0",
            storage_path="/app/storage/documents",
        )


def test_production_rejects_localhost_database():
    with pytest.raises(
        ValueError,
        match="DATABASE_URL must not use localhost",
    ):
        make_settings(
            app_env="production",
            database_url="postgresql+psycopg://user:pass@localhost:5432/app",
            qdrant_url="https://qdrant.example",
            redis_url="redis://redis.example:6379/0",
            storage_path="/app/storage/documents",
        )


def test_production_rejects_localhost_qdrant():
    with pytest.raises(
        ValueError,
        match="QDRANT_URL must not use localhost",
    ):
        make_settings(
            app_env="production",
            database_url="postgresql+psycopg://user:pass@db.example:5432/app",
            qdrant_url="http://localhost:6333",
            redis_url="redis://redis.example:6379/0",
            storage_path="/app/storage/documents",
        )


def test_production_rejects_localhost_redis():
    with pytest.raises(
        ValueError,
        match="REDIS_URL must not use localhost",
    ):
        make_settings(
            app_env="production",
            database_url="postgresql+psycopg://user:pass@db.example:5432/app",
            qdrant_url="https://qdrant.example",
            redis_url="redis://localhost:6379/0",
            storage_path="/app/storage/documents",
        )


def test_production_requires_absolute_storage_path():
    with pytest.raises(
        ValueError,
        match="STORAGE_PATH",
    ):
        make_settings(
            app_env="production",
            database_url="postgresql+psycopg://user:pass@db.example:5432/app",
            qdrant_url="https://qdrant.example",
            redis_url="redis://redis.example:6379/0",
            storage_path="storage/documents",
        )


def test_jwt_secret_must_be_long_enough():
    with pytest.raises(
        ValueError,
        match="JWT_SECRET",
    ):
        make_settings(
            app_env="production",
            jwt_secret="too-short",
            database_url="postgresql+psycopg://user:pass@db.example:5432/app",
            qdrant_url="https://qdrant.example",
            redis_url="redis://redis.example:6379/0",
            storage_path="/app/storage/documents",
        )


def test_jwt_secret_rejects_known_placeholder():
    with pytest.raises(
        ValueError,
        match="JWT_SECRET",
    ):
        make_settings(
            app_env="production",
            jwt_secret="change-this-in-production",
            database_url="postgresql+psycopg://user:pass@db.example:5432/app",
            qdrant_url="https://qdrant.example",
            redis_url="redis://redis.example:6379/0",
            storage_path="/app/storage/documents",
        )


def test_valid_production_configuration():
    settings = make_settings(
        app_env="production",
        debug=False,
        jwt_secret="production-test-secret-" + ("x" * 64),
        database_url="postgresql+psycopg://user:pass@db.example:5432/app",
        qdrant_url="https://qdrant.example",
        redis_url="redis://redis.example:6379/0",
        storage_path="/app/storage/documents",
        cors_allowed_origins=[
            "https://rag.example.com",
        ],
        trusted_hosts=[
            "rag.example.com",
        ],
    )

    assert settings.app_env == "production"
    assert settings.debug is False

def test_cors_origins_cannot_be_empty(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "[]",
    )

    with pytest.raises(
        ValidationError,
        match="CORS_ALLOWED_ORIGINS",
    ):
        Settings()


def test_cors_origin_must_be_http_or_https(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["javascript://attacker.example"]',
    )

    with pytest.raises(
        ValidationError,
        match="CORS_ALLOWED_ORIGINS",
    ):
        Settings()


def test_trusted_hosts_cannot_be_empty(monkeypatch):
    monkeypatch.setenv(
        "TRUSTED_HOSTS",
        "[]",
    )

    with pytest.raises(
        ValidationError,
        match="TRUSTED_HOSTS",
    ):
        Settings()


def test_production_cannot_use_wildcard_trusted_host(
    monkeypatch,
):
    monkeypatch.setenv(
        "APP_ENV",
        "production",
    )
    monkeypatch.setenv(
        "DEBUG",
        "false",
    )
    monkeypatch.setenv(
        "JWT_SECRET",
        "a" * 64,
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@postgres.example.com/db",
    )
    monkeypatch.setenv(
        "QDRANT_URL",
        "http://qdrant.example.com",
    )
    monkeypatch.setenv(
        "REDIS_URL",
        "redis://redis.example.com/0",
    )
    monkeypatch.setenv(
        "STORAGE_PATH",
        "/srv/secure-rag/storage",
    )
    monkeypatch.setenv(
        "TRUSTED_HOSTS",
        '["*"]',
    )
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["https://rag.example.com"]',
    )

    with pytest.raises(
        ValidationError,
        match="TRUSTED_HOSTS",
    ):
        Settings()


def test_production_cannot_use_wildcard_cors(
    monkeypatch,
):
    monkeypatch.setenv(
        "APP_ENV",
        "production",
    )
    monkeypatch.setenv(
        "DEBUG",
        "false",
    )
    monkeypatch.setenv(
        "JWT_SECRET",
        "a" * 64,
    )
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:pass@postgres.example.com/db",
    )
    monkeypatch.setenv(
        "QDRANT_URL",
        "http://qdrant.example.com",
    )
    monkeypatch.setenv(
        "REDIS_URL",
        "redis://redis.example.com/0",
    )
    monkeypatch.setenv(
        "STORAGE_PATH",
        "/srv/secure-rag/storage",
    )
    monkeypatch.setenv(
        "TRUSTED_HOSTS",
        '["rag.example.com"]',
    )
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        '["*"]',
    )

    with pytest.raises(
        ValidationError,
        match="CORS_ALLOWED_ORIGINS",
    ):
        Settings()

def test_request_body_size_default_is_at_least_upload_size():
    settings = make_settings()

    assert (
        settings.max_request_body_size_mb
        >= settings.max_upload_size_mb
    )


def test_request_body_size_must_be_positive():
    with pytest.raises(
        ValidationError,
        match="MAX_REQUEST_BODY_SIZE_MB",
    ):
        make_settings(
            max_request_body_size_mb=0,
        )


def test_request_body_size_cannot_be_smaller_than_upload_size():
    with pytest.raises(
        ValidationError,
        match=(
            "MAX_REQUEST_BODY_SIZE_MB must be "
            "greater than or equal to MAX_UPLOAD_SIZE_MB"
        ),
    ):
        make_settings(
            max_upload_size_mb=25,
            max_request_body_size_mb=24,
        )