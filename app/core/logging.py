import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.request_context import get_request_id


STANDARD_LOG_RECORD_FIELDS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
}


def is_valid_request_id(
    value: str | None,
) -> bool:
    """
    Return True only when the supplied value is a valid UUID.
    """

    if not value:
        return False

    try:
        UUID(value)
    except (
        ValueError,
        TypeError,
        AttributeError,
    ):
        return False

    return True


class RequestIdFilter(logging.Filter):
    """
    Add the current request ID to application log records.

    The request ID comes from the shared request context used
    by the HTTP middleware.
    """

    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        record.request_id = (
            get_request_id()
        )

        return True


class JsonFormatter(logging.Formatter):
    """
    Serialize application logs as one JSON object per line.

    Request payloads, authorization headers, tokens, and query
    text are never automatically included.
    """

    def format(
        self,
        record: logging.LogRecord,
    ) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created,
                tz=timezone.utc,
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(
            record,
            "request_id",
            None,
        )

        if request_id is not None:
            payload["request_id"] = str(
                request_id
            )

        for key, value in record.__dict__.items():
            if key in STANDARD_LOG_RECORD_FIELDS:
                continue

            if key.startswith("_"):
                continue

            if key in {
                "message",
                "asctime",
                "request_id",
            }:
                continue

            payload[key] = self._safe_value(
                value
            )

        if record.exc_info:
            payload["exception"] = (
                self.formatException(
                    record.exc_info
                )
            )

        return json.dumps(
            payload,
            default=str,
            ensure_ascii=False,
        )

    @staticmethod
    def _safe_value(
        value: Any,
    ) -> Any:
        if value is None:
            return None

        if isinstance(
            value,
            (
                str,
                int,
                float,
                bool,
            ),
        ):
            return value

        if isinstance(
            value,
            (list, tuple),
        ):
            return [
                JsonFormatter._safe_value(
                    item
                )
                for item in value
            ]

        if isinstance(value, dict):
            return {
                str(key): (
                    JsonFormatter._safe_value(
                        item
                    )
                )
                for key, item in value.items()
            }

        return str(value)


def configure_logging(
    *,
    debug: bool,
) -> None:
    """
    Configure application logging once.
    """

    app_logger = logging.getLogger(
        "app"
    )

    level = (
        logging.DEBUG
        if debug
        else logging.INFO
    )

    app_logger.setLevel(level)
    app_logger.propagate = False

    if app_logger.handlers:
        return

    handler = logging.StreamHandler(
        sys.stderr
    )

    handler.setLevel(level)

    handler.addFilter(
        RequestIdFilter()
    )

    handler.setFormatter(
        JsonFormatter()
    )

    app_logger.addHandler(
        handler
    )