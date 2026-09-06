from dataclasses import dataclass
from functools import lru_cache

from redis import Redis

from app.core.config import get_settings
from app.services.queue import get_redis


_RATE_LIMIT_SCRIPT = """
local current = redis.call("INCR", KEYS[1])

if current == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end

return current
"""


class RateLimitError(Exception):
    """Raised when rate limiting cannot be evaluated."""


@dataclass(frozen=True)
class RateLimitExceeded(Exception):
    """Raised when a client exceeds its configured rate limit."""

    limit: int
    window_seconds: int


class RateLimiter:
    def __init__(
        self,
        redis: Redis,
        *,
        requests: int,
        window_seconds: int,
        key_prefix: str,
    ):
        if requests <= 0:
            raise ValueError(
                "requests must be greater than zero"
            )

        if window_seconds <= 0:
            raise ValueError(
                "window_seconds must be greater than zero"
            )

        self.redis = redis
        self.requests = requests
        self.window_seconds = window_seconds
        self.key_prefix = key_prefix

    def check(
        self,
        *,
        subject: str,
    ) -> None:
        key = f"{self.key_prefix}:{subject}"

        try:
            current = self.redis.eval(
                _RATE_LIMIT_SCRIPT,
                1,
                key,
                self.window_seconds,
            )
        except Exception as exc:
            raise RateLimitError(
                "Rate limiter could not be evaluated"
            ) from exc

        if int(current) > self.requests:
            raise RateLimitExceeded(
                limit=self.requests,
                window_seconds=self.window_seconds,
            )


@lru_cache
def get_query_rate_limiter() -> RateLimiter:
    settings = get_settings()

    return RateLimiter(
        redis=get_redis(),
        requests=settings.query_rate_limit_requests,
        window_seconds=(
            settings.query_rate_limit_window_seconds
        ),
        key_prefix="secure-rag:rate-limit:query",
    )


@lru_cache
def get_login_ip_rate_limiter() -> RateLimiter:
    settings = get_settings()

    return RateLimiter(
        redis=get_redis(),
        requests=settings.login_rate_limit_requests,
        window_seconds=(
            settings.login_rate_limit_window_seconds
        ),
        key_prefix="secure-rag:rate-limit:login-ip",
    )


@lru_cache
def get_login_email_rate_limiter() -> RateLimiter:
    settings = get_settings()

    return RateLimiter(
        redis=get_redis(),
        requests=settings.login_rate_limit_requests,
        window_seconds=(
            settings.login_rate_limit_window_seconds
        ),
        key_prefix="secure-rag:rate-limit:login-email",
    )