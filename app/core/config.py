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

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()