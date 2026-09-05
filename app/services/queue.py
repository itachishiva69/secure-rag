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


INGESTION_QUEUE_NAME = "document-ingestion"
MAINTENANCE_QUEUE_NAME = "document-maintenance"


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        decode_responses=False,
    )


@lru_cache
def get_ingestion_queue() -> Queue:
    return Queue(
        INGESTION_QUEUE_NAME,
        connection=get_redis(),
    )


@lru_cache
def get_maintenance_queue() -> Queue:
    return Queue(
        MAINTENANCE_QUEUE_NAME,
        connection=get_redis(),
    )


def enqueue_ingestion_job(
    document_id: int,
    *,
    job_id: str | None = None,
):
    queue = get_ingestion_queue()

    enqueue_options = {
        "retry": Retry(
            max=INGESTION_RETRY_MAX,
            interval=INGESTION_RETRY_INTERVALS,
        ),
    }

    if job_id is not None:
        enqueue_options["job_id"] = job_id
        enqueue_options["unique"] = True

    return queue.enqueue(
        "app.services.jobs.ingest_document_job",
        document_id,
        **enqueue_options,
    )