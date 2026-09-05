from unittest.mock import Mock

from app.services import queue


def test_enqueue_ingestion_job_configures_retries(
    monkeypatch,
):
    fake_queue = Mock()

    monkeypatch.setattr(
        queue,
        "get_ingestion_queue",
        lambda: fake_queue,
    )

    job = queue.enqueue_ingestion_job(
        document_id=123,
    )

    assert job is fake_queue.enqueue.return_value

    fake_queue.enqueue.assert_called_once()

    args, kwargs = (
        fake_queue.enqueue.call_args
    )

    assert args == (
        "app.services.jobs.ingest_document_job",
        123,
    )

    retry = kwargs["retry"]

    assert retry.max == (
        queue.INGESTION_RETRY_MAX
    )

    assert retry.intervals == (
        queue.INGESTION_RETRY_INTERVALS
    )


def test_retry_configuration_is_bounded():
    assert queue.INGESTION_RETRY_MAX == 3

    assert queue.INGESTION_RETRY_INTERVALS == [
        30,
        120,
        300,
    ]