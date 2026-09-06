import json
import logging

from app.core.logging import (
    JsonFormatter,
    RequestIdFilter,
)
from app.core.request_context import (
    get_request_id,
    reset_request_id,
    set_request_id,
)


def make_log_record(
    *,
    message: str = "test_event",
    level: int = logging.INFO,
):
    return logging.LogRecord(
        name="app.test",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


def test_formatter_returns_valid_json():
    formatter = JsonFormatter()

    output = formatter.format(
        make_log_record()
    )

    payload = json.loads(output)

    assert isinstance(payload, dict)


def test_formatter_includes_core_fields():
    formatter = JsonFormatter()

    output = formatter.format(
        make_log_record(
            message="structured_event"
        )
    )

    payload = json.loads(output)

    assert payload["logger"] == "app.test"
    assert payload["message"] == (
        "structured_event"
    )


def test_formatter_preserves_safe_extra_fields():
    formatter = JsonFormatter()

    record = make_log_record()

    record.user_id = 42
    record.document_id = 123
    record.status_code = 200
    record.duration_ms = 12.5

    output = formatter.format(record)

    payload = json.loads(output)

    assert payload["user_id"] == 42
    assert payload["document_id"] == 123
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5


def test_request_id_filter_copies_context_request_id():
    request_id_filter = RequestIdFilter()

    assert get_request_id() is None

    token = set_request_id(
        "structured-test-request-id"
    )

    try:
        record = make_log_record(
            message="request_event"
        )

        assert request_id_filter.filter(record)

        assert record.request_id == (
            "structured-test-request-id"
        )

    finally:
        reset_request_id(token)


def test_formatter_serializes_filtered_request_id():
    formatter = JsonFormatter()
    request_id_filter = RequestIdFilter()

    token = set_request_id(
        "structured-test-request-id"
    )

    try:
        record = make_log_record(
            message="request_event"
        )

        assert request_id_filter.filter(record)

        output = formatter.format(record)

        payload = json.loads(output)

        assert payload["request_id"] == (
            "structured-test-request-id"
        )

    finally:
        reset_request_id(token)


def test_formatter_preserves_explicit_request_id():
    formatter = JsonFormatter()

    record = make_log_record()

    record.request_id = (
        "explicit-request-id"
    )

    output = formatter.format(record)

    payload = json.loads(output)

    assert payload["request_id"] == (
        "explicit-request-id"
    )


def test_formatter_does_not_fail_with_missing_optional_fields():
    formatter = JsonFormatter()

    output = formatter.format(
        make_log_record(
            message="minimal_event"
        )
    )

    payload = json.loads(output)

    assert payload["logger"] == "app.test"
    assert payload["message"] == (
        "minimal_event"
    )