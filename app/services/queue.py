from functools import lru_cache

from redis import Redis
from rq import Queue

from app.core.config import get_settings


settings = get_settings()


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=False,
    )


@lru_cache
def get_ingestion_queue() -> Queue:
    return Queue(
        "document-ingestion",
        connection=get_redis(),
    )