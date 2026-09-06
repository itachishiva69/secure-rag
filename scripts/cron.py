import logging

from redis import Redis
from rq.cron import CronScheduler

from app.core.config import get_settings
from app.services.jobs import (
    dispatch_pending_outbox_job,
    reconcile_stale_documents_job,
)
from app.services.queue import MAINTENANCE_QUEUE_NAME


logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()

    redis = Redis.from_url(
        settings.redis_url,
        decode_responses=False,
    )

    interval = (
        settings.reconciliation_interval_seconds
    )

    if interval <= 0:
        raise ValueError(
            "RECONCILIATION_INTERVAL_SECONDS must be greater than zero"
        )

    scheduler = CronScheduler(
        connection=redis,
        name="secure-rag-maintenance-scheduler",
    )

    scheduler.register(
        reconcile_stale_documents_job,
        MAINTENANCE_QUEUE_NAME,
        interval=interval,
        name="secure-rag-document-reconciliation",
    )

    scheduler.register(
        dispatch_pending_outbox_job,
        MAINTENANCE_QUEUE_NAME,
        interval=interval,
        name="secure-rag-outbox-dispatch",
    )

    logger.info(
        "secure_rag_scheduler_started",
        extra={
            "queue": MAINTENANCE_QUEUE_NAME,
            "interval_seconds": interval,
        },
    )

    scheduler.start()


if __name__ == "__main__":
    main()