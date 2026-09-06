import logging

from app.core.logging import (
    JsonFormatter,
    configure_logging,
)


def test_worker_and_scheduler_loggers_are_under_app_namespace():
    worker_logger = logging.getLogger(
        "app.worker"
    )

    scheduler_logger = logging.getLogger(
        "app.scheduler"
    )

    assert worker_logger.name.startswith(
        "app."
    )

    assert scheduler_logger.name.startswith(
        "app."
    )


def test_json_formatter_serializes_operational_fields():
    record = logging.LogRecord(
        name="app.worker",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="worker_started",
        args=(),
        exc_info=None,
    )

    record.request_id = None
    record.queues = [
        "document-ingestion",
        "document-maintenance",
    ]

    formatted = JsonFormatter().format(
        record
    )

    assert '"message": "worker_started"' in (
        formatted
    )

    assert '"queues": ["document-ingestion", "document-maintenance"]' in (
        formatted
    )


def test_configure_logging_attaches_json_handler():
    logger = logging.getLogger(
        "app"
    )

    configure_logging(
        debug=False
    )

    assert logger.handlers

    assert any(
        handler.formatter.__class__.__name__
        == "JsonFormatter"
        for handler in logger.handlers
    )