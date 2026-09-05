from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Secure RAG"
    app_env: str = "development"
    debug: bool = True

    database_url: str

    qdrant_url: str
    qdrant_collection: str = "documents"

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    max_upload_size_mb: int = 25
    storage_path: str = "storage/documents"

    redis_url: str = "redis://localhost:6379/0"

    llm_api_key: str | None = None
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str = (
        "https://api.groq.com/openai/v1"
    )
    llm_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()