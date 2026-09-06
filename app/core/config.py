from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import model_validator
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
    max_request_body_size_mb: int = 30
    storage_path: str = "storage/documents"

    redis_url: str = "redis://localhost:6379/0"

    llm_api_key: str | None = None
    llm_model: str = "openai/gpt-oss-120b"
    llm_base_url: str = (
        "https://api.groq.com/openai/v1"
    )
    llm_timeout_seconds: float = 30.0

    reranker_model: str = (
        "cross-encoder/ms-marco-MiniLM-L6-v2"
    )
    reranker_candidate_limit: int = 10

    query_rate_limit_requests: int = 30
    query_rate_limit_window_seconds: int = 60

    login_rate_limit_requests: int = 5
    login_rate_limit_window_seconds: int = 60

    upload_rate_limit_requests: int = 10
    upload_rate_limit_window_seconds: int = 60

    context_max_chars: int = 12000

    reconciliation_interval_seconds: int = 300
    reconciliation_stale_processing_minutes: int = 30
    reconciliation_stale_deleting_minutes: int = 30

    cors_allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    trusted_hosts: list[str] = [
        "localhost",
        "127.0.0.1",
        "testserver",
        "test",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_configuration(self):
        allowed_envs = {
            "development",
            "test",
            "staging",
            "production",
        }
        if self.login_rate_limit_requests <= 0:
            raise ValueError(
        "LOGIN_RATE_LIMIT_REQUESTS "
        "must be positive"
            )

        if self.login_rate_limit_window_seconds <= 0:
            raise ValueError(
                "LOGIN_RATE_LIMIT_WINDOW_SECONDS "
                "must be positive"
            )
        if self.app_env not in allowed_envs:
            raise ValueError(
                "APP_ENV must be one of: "
                "development, test, staging, production"
            )

        if self.access_token_expire_minutes <= 0:
            raise ValueError(
                "ACCESS_TOKEN_EXPIRE_MINUTES "
                "must be positive"
            )

        if self.max_upload_size_mb <= 0:
            raise ValueError(
                "MAX_UPLOAD_SIZE_MB must be positive"
            )

        if self.max_request_body_size_mb <= 0:
            raise ValueError(
                "MAX_REQUEST_BODY_SIZE_MB "
                "must be positive"
            )

        if (
            self.max_request_body_size_mb
            < self.max_upload_size_mb
        ):
            raise ValueError(
                "MAX_REQUEST_BODY_SIZE_MB must be "
                "greater than or equal to "
                "MAX_UPLOAD_SIZE_MB"
            )

        if self.llm_timeout_seconds <= 0:
            raise ValueError(
                "LLM_TIMEOUT_SECONDS must be positive"
            )

        if self.reranker_candidate_limit <= 0:
            raise ValueError(
                "RERANKER_CANDIDATE_LIMIT "
                "must be positive"
            )

        if self.query_rate_limit_requests <= 0:
            raise ValueError(
                "QUERY_RATE_LIMIT_REQUESTS "
                "must be positive"
            )

        if self.query_rate_limit_window_seconds <= 0:
            raise ValueError(
                "QUERY_RATE_LIMIT_WINDOW_SECONDS "
                "must be positive"
            )

        if self.upload_rate_limit_requests <= 0:
            raise ValueError(
                "UPLOAD_RATE_LIMIT_REQUESTS "
                "must be positive"
            )

        if self.upload_rate_limit_window_seconds <= 0:
            raise ValueError(
                "UPLOAD_RATE_LIMIT_WINDOW_SECONDS "
                "must be positive"
            )

        if self.context_max_chars <= 0:
            raise ValueError(
                "CONTEXT_MAX_CHARS must be positive"
            )

        if self.reconciliation_interval_seconds <= 0:
            raise ValueError(
                "RECONCILIATION_INTERVAL_SECONDS "
                "must be positive"
            )

        if (
            self.reconciliation_stale_processing_minutes
            <= 0
        ):
            raise ValueError(
                "RECONCILIATION_STALE_PROCESSING_MINUTES "
                "must be positive"
            )

        if (
            self.reconciliation_stale_deleting_minutes
            <= 0
        ):
            raise ValueError(
                "RECONCILIATION_STALE_DELETING_MINUTES "
                "must be positive"
            )

        self._validate_cors_configuration()
        self._validate_trusted_hosts()

        if self.app_env == "production":
            self._validate_production()

        return self

    def _validate_cors_configuration(self) -> None:
        if not self.cors_allowed_origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must contain "
                "at least one origin"
            )

        for origin in self.cors_allowed_origins:
            parsed = urlparse(origin)

            if parsed.scheme not in {
                "http",
                "https",
            }:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must contain "
                    "only http or https origins"
                )

            if not parsed.netloc:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS contains "
                    "an invalid origin"
                )

            if (
                parsed.path not in {"", "/"}
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must contain "
                    "origins without paths or query strings"
                )

    def _validate_trusted_hosts(self) -> None:
        if not self.trusted_hosts:
            raise ValueError(
                "TRUSTED_HOSTS must contain "
                "at least one host"
            )

        for host in self.trusted_hosts:
            if not host.strip():
                raise ValueError(
                    "TRUSTED_HOSTS cannot contain "
                    "empty hosts"
                )

    def _validate_production(self) -> None:
        if self.debug:
            raise ValueError(
                "DEBUG must be false when APP_ENV=production"
            )

        if len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must contain at least "
                "32 characters"
            )

        if self.jwt_secret in {
            "change-this-in-production",
            "change-this-in-production-secret",
            "your-secret-key",
        }:
            raise ValueError(
                "JWT_SECRET must not use a known placeholder"
            )

        self._validate_non_local_service(
            self.database_url,
            "DATABASE_URL",
        )

        self._validate_non_local_service(
            self.qdrant_url,
            "QDRANT_URL",
        )

        self._validate_non_local_service(
            self.redis_url,
            "REDIS_URL",
        )

        if not Path(self.storage_path).is_absolute():
            raise ValueError(
                "STORAGE_PATH must be absolute when "
                "APP_ENV=production"
            )

        default_origins = {
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        }

        if set(self.cors_allowed_origins) == default_origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must be explicitly "
                "configured when APP_ENV=production"
            )

        default_hosts = {
            "localhost",
            "127.0.0.1",
            "testserver",
            "test",
        }

        if set(self.trusted_hosts) == default_hosts:
            raise ValueError(
                "TRUSTED_HOSTS must be explicitly "
                "configured when APP_ENV=production"
            )

        if "*" in self.trusted_hosts:
            raise ValueError(
                "TRUSTED_HOSTS must not contain '*' "
                "when APP_ENV=production"
            )

        if "*" in self.cors_allowed_origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not contain '*' "
                "when APP_ENV=production"
            )

    @staticmethod
    def _validate_non_local_service(
        url: str,
        field_name: str,
    ) -> None:
        parsed = urlparse(url)

        hostname = parsed.hostname

        if hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError(
                f"{field_name} must not use localhost "
                "when APP_ENV=production"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()