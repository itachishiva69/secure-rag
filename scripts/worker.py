from rq import Worker

from app.services.queue import (
    get_ingestion_queue,
    get_maintenance_queue,
)


def main():
    ingestion_queue = (
        get_ingestion_queue()
    )

    maintenance_queue = (
        get_maintenance_queue()
    )

    worker = Worker(
        [
            ingestion_queue,
            maintenance_queue,
        ],
        connection=ingestion_queue.connection,
    )

    print(
        "Starting Secure RAG background worker..."
    )

    worker.work(
        with_scheduler=True
    )


if __name__ == "__main__":
    main()