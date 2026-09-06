import pytest

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
    )

    assert settings.app_env == "production"
    assert settings.debug is False