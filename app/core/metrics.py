from datetime import datetime, timezone

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func

from app.db.database import SessionLocal
from app.models import Document, OutboxEvent
from app.models.document_status import DocumentStatus
from app.services.queue import (
    get_ingestion_queue,
    get_maintenance_queue,
)


HTTP_REQUESTS_TOTAL = Counter(
    "secure_rag_http_requests_total",
    "Total HTTP requests processed by the API.",
    labelnames=(
        "method",
        "path",
        "status_code",
    ),
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "secure_rag_http_request_duration_seconds",
    "HTTP request processing duration in seconds.",
    labelnames=(
        "method",
        "path",
    ),
)

DOCUMENTS_TOTAL = Gauge(
    "secure_rag_documents_total",
    "Current number of documents by lifecycle status.",
    labelnames=(
        "status",
    ),
)

OUTBOX_EVENTS_TOTAL = Gauge(
    "secure_rag_outbox_events_total",
    "Current number of outbox events by status.",
    labelnames=(
        "status",
    ),
)

OUTBOX_EVENTS_READY = Gauge(
    "secure_rag_outbox_events_ready",
    "Current number of pending outbox events ready for dispatch.",
)

RQ_QUEUE_DEPTH = Gauge(
    "secure_rag_rq_queue_depth",
    "Current number of queued RQ jobs waiting for processing.",
    labelnames=(
        "queue",
    ),
)


def _initialize_labeled_metrics() -> None:
    for status in DocumentStatus:
        DOCUMENTS_TOTAL.labels(
            status=status.value,
        )

    for status in (
        "pending",
        "dispatched",
    ):
        OUTBOX_EVENTS_TOTAL.labels(
            status=status,
        )

    RQ_QUEUE_DEPTH.labels(
        queue="document-ingestion",
    )

    RQ_QUEUE_DEPTH.labels(
        queue="document-maintenance",
    )


_initialize_labeled_metrics()


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS_TOTAL.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).inc()

    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method,
        path=path,
    ).observe(
        duration_seconds
    )


def collect_state_metrics() -> None:
    now = datetime.now(
        timezone.utc
    )

    with SessionLocal() as db:
        document_counts = dict(
            db.query(
                Document.status,
                func.count(Document.id),
            )
            .group_by(
                Document.status
            )
            .all()
        )

        for status in DocumentStatus:
            DOCUMENTS_TOTAL.labels(
                status=status.value,
            ).set(
                document_counts.get(
                    status,
                    0,
                )
            )

        outbox_counts = dict(
            db.query(
                OutboxEvent.status,
                func.count(OutboxEvent.id),
            )
            .group_by(
                OutboxEvent.status
            )
            .all()
        )

        for status in (
            "pending",
            "dispatched",
        ):
            OUTBOX_EVENTS_TOTAL.labels(
                status=status,
            ).set(
                outbox_counts.get(
                    status,
                    0,
                )
            )

        ready_count = (
            db.query(
                OutboxEvent.id
            )
            .filter(
                OutboxEvent.status
                == "pending",
                OutboxEvent.available_at
                <= now,
            )
            .count()
        )

        OUTBOX_EVENTS_READY.set(
            ready_count
        )

    ingestion_queue = (
        get_ingestion_queue()
    )

    maintenance_queue = (
        get_maintenance_queue()
    )

    RQ_QUEUE_DEPTH.labels(
        queue=ingestion_queue.name,
    ).set(
        ingestion_queue.count
    )

    RQ_QUEUE_DEPTH.labels(
        queue=maintenance_queue.name,
    ).set(
        maintenance_queue.count
    )


def render_metrics() -> tuple[
    bytes,
    str,
]:
    collect_state_metrics()

    return (
        generate_latest(),
        CONTENT_TYPE_LATEST,
    )