from functools import lru_cache

from redis import Redis
from rq import Queue, Retry

from app.core.config import get_settings


settings = get_settings()


INGESTION_RETRY_MAX = 3
INGESTION_RETRY_INTERVALS = [
    30,
    120,
    300,
]


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


def enqueue_ingestion_job(
    document_id: int,
):
    queue = get_ingestion_queue()

    return queue.enqueue(
        "app.services.jobs.ingest_document_job",
        document_id,
        retry=Retry(
            max=INGESTION_RETRY_MAX,
            interval=INGESTION_RETRY_INTERVALS,
        ),
    )