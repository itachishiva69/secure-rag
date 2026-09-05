from unittest.mock import Mock

from app.api import query as query_api
from app.services import jobs


def test_ingestion_job_logs_start_and_completion(
    monkeypatch,
):
    def fake_ingest_document(
        *,
        db,
        document_id,
    ):
        assert document_id == 42
        return 3

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

    fake_logger = Mock()

    monkeypatch.setattr(
        jobs,
        "ingest_document",
        fake_ingest_document,
    )

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        lambda: FakeSession(),
    )

    monkeypatch.setattr(
        jobs,
        "logger",
        fake_logger,
    )

    jobs.ingest_document_job(42)

    fake_logger.info.assert_any_call(
        "document_ingestion_job_started",
        extra={
            "document_id": 42,
        },
    )

    fake_logger.info.assert_any_call(
        "document_ingestion_job_completed",
        extra={
            "document_id": 42,
            "indexed_count": 3,
        },
    )

    fake_logger.exception.assert_not_called()


def test_ingestion_job_logs_failure(
    monkeypatch,
):
    def failing_ingest_document(
        *,
        db,
        document_id,
    ):
        raise RuntimeError(
            "simulated ingestion failure"
        )

    class FakeSession:
        def __enter__(self):
            return object()

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

    fake_logger = Mock()

    monkeypatch.setattr(
        jobs,
        "ingest_document",
        failing_ingest_document,
    )

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        lambda: FakeSession(),
    )

    monkeypatch.setattr(
        jobs,
        "logger",
        fake_logger,
    )

    try:
        jobs.ingest_document_job(42)
    except RuntimeError as exc:
        assert str(exc) == (
            "simulated ingestion failure"
        )

    fake_logger.exception.assert_called_once_with(
        "document_ingestion_job_failed",
        extra={
            "document_id": 42,
        },
    )

    fake_logger.info.assert_called_once_with(
        "document_ingestion_job_started",
        extra={
            "document_id": 42,
        },
    )


def test_query_log_does_not_include_query_text(
    monkeypatch,
):
    sensitive_query = (
        "this contains confidential information"
    )

    fake_logger = Mock()

    monkeypatch.setattr(
        query_api,
        "logger",
        fake_logger,
    )

    query_api.logger.info(
        "query_started",
        extra={
            "user_id": 1,
            "user_role": "user",
            "department_id": 2,
            "requested_limit": 5,
            "reranker_enabled": True,
        },
    )

    fake_logger.info.assert_called_once_with(
        "query_started",
        extra={
            "user_id": 1,
            "user_role": "user",
            "department_id": 2,
            "requested_limit": 5,
            "reranker_enabled": True,
        },
    )

    logged_calls = fake_logger.info.call_args_list

    assert sensitive_query not in (
        str(logged_calls)
    )