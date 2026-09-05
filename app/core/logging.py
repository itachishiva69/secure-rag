import logging
import logging.config

from app.core.request_context import get_request_id


LOG_FORMAT = (
    "%(asctime)s %(levelname)s "
    "[request_id=%(request_id)s] "
    "%(name)s %(message)s"
)


class RequestIdFilter(logging.Filter):
    def filter(
        self,
        record: logging.LogRecord,
    ) -> bool:
        record.request_id = (
            get_request_id() or "-"
        )

        return True


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {
                    "()": (
                        "app.core.logging.RequestIdFilter"
                    ),
                },
            },
            "formatters": {
                "default": {
                    "format": LOG_FORMAT,
                },
            },
            "handlers": {
                "console": {
                    "class": (
                        "logging.StreamHandler"
                    ),
                    "formatter": "default",
                    "filters": ["request_id"],
                    "stream": (
                        "ext://sys.stdout"
                    ),
                },
            },
            "loggers": {
                "app": {
                    "level": "INFO",
                    "propagate": True,
                },
            },
            "root": {
                "level": "WARNING",
                "handlers": ["console"],
            },
        }
    )