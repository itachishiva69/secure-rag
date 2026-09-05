from rq import Worker

from app.services.queue import get_ingestion_queue


def main():
    queue = get_ingestion_queue()

    worker = Worker(
        [queue],
        connection=queue.connection,
    )

    print("Starting document ingestion worker...")

    worker.work()


if __name__ == "__main__":
    main()