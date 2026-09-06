import logging

from rq import Worker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.queue import (
    get_ingestion_queue,
    get_maintenance_queue,
)


logger = logging.getLogger(
    "app.worker"
)


def main() -> None:
    settings = get_settings()

    configure_logging(
        debug=settings.debug
    )

    ingestion_queue = (
        get_ingestion_queue()
    )

    maintenance_queue = (
        get_maintenance_queue()
    )

    logger.info(
        "worker_started",
        extra={
            "queues": [
                ingestion_queue.name,
                maintenance_queue.name,
            ],
        },
    )

    worker = Worker(
        [
            ingestion_queue,
            maintenance_queue,
        ],
        connection=ingestion_queue.connection,
    )

    try:
        worker.work(
            with_scheduler=True
        )
    except Exception:
        logger.exception(
            "worker_failed"
        )
        raise


if __name__ == "__main__":
    main()