from rq.cron import CronScheduler

from app.core.config import get_settings
from app.services.queue import (
    MAINTENANCE_QUEUE_NAME,
    get_redis,
)


settings = get_settings()


def main():
    redis_connection = get_redis()

    scheduler = CronScheduler(
        connection=redis_connection,
        logging_level="INFO",
    )

    scheduler.register(
        "app.services.jobs.reconcile_stale_documents_job",
        queue_name=MAINTENANCE_QUEUE_NAME,
        interval=(
            settings.reconciliation_interval_seconds
        ),
        job_timeout=(
            settings.reconciliation_interval_seconds
            * 2
        ),
    )

    print(
        "Starting Secure RAG reconciliation scheduler..."
    )

    scheduler.start()


if __name__ == "__main__":
    main()