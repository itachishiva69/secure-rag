import logging.config


LOG_FORMAT = (
    "%(asctime)s %(levelname)s "
    "%(name)s %(message)s"
)


def configure_logging() -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": LOG_FORMAT,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
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