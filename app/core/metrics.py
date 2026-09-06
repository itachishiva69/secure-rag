import logging
from datetime import datetime, timedelta, timezone

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models import Document, OutboxEvent
from app.models.document_status import DocumentStatus
from app.services.queue import (
    get_ingestion_queue,
    get_maintenance_queue,
)


logger = logging.getLogger(
    "app.metrics"
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
    labelnames=("status",),
)

STALE_DOCUMENTS_TOTAL = Gauge(
    "secure_rag_stale_documents_total",
    "Current number of documents exceeding configured stale thresholds.",
    labelnames=("status",),
)

OUTBOX_EVENTS_TOTAL = Gauge(
    "secure_rag_outbox_events_total",
    "Current number of outbox events by status.",
    labelnames=("status",),
)

OUTBOX_EVENTS_READY = Gauge(
    "secure_rag_outbox_events_ready",
    "Current number of pending outbox events ready for dispatch.",
)

OUTBOX_PENDING_OLDEST_AGE_SECONDS = Gauge(
    "secure_rag_outbox_pending_oldest_age_seconds",
    "Age in seconds of the oldest pending outbox event.",
)

RQ_QUEUE_DEPTH = Gauge(
    "secure_rag_rq_queue_depth",
    "Current number of queued RQ jobs waiting for processing.",
    labelnames=("queue",),
)

METRICS_COLLECTIONS_TOTAL = Counter(
    "secure_rag_metrics_collections_total",
    "Total attempts to collect application state metrics.",
    labelnames=("status",),
)


def _initialize_labeled_metrics() -> None:
    for status in DocumentStatus:
        DOCUMENTS_TOTAL.labels(
            status=status.value,
        )

    for status in (
        "processing",
        "deleting",
    ):
        STALE_DOCUMENTS_TOTAL.labels(
            status=status,
        )

    for status in (
        "pending",
        "dispatched",
    ):
        OUTBOX_EVENTS_TOTAL.labels(
            status=status,
        )

    for queue_name in (
        "document-ingestion",
        "document-maintenance",
    ):
        RQ_QUEUE_DEPTH.labels(
            queue=queue_name,
        )

    for status in (
        "success",
        "failure",
    ):
        METRICS_COLLECTIONS_TOTAL.labels(
            status=status,
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
    started_at = datetime.now(
        timezone.utc
    )

    try:
        _collect_state_metrics()

    except Exception:
        METRICS_COLLECTIONS_TOTAL.labels(
            status="failure",
        ).inc()

        logger.exception(
            "metrics_state_collection_failed",
            extra={
                "duration_ms": round(
                    (
                        datetime.now(
                            timezone.utc
                        )
                        - started_at
                    ).total_seconds()
                    * 1000,
                    2,
                ),
            },
        )

        raise

    else:
        METRICS_COLLECTIONS_TOTAL.labels(
            status="success",
        ).inc()


def _collect_state_metrics() -> None:
    settings = get_settings()

    now = datetime.now(
        timezone.utc
    )

    processing_cutoff = (
        now
        - timedelta(
            minutes=(
                settings.reconciliation_stale_processing_minutes
            )
        )
    )

    deleting_cutoff = (
        now
        - timedelta(
            minutes=(
                settings.reconciliation_stale_deleting_minutes
            )
        )
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

        stale_processing_count = (
            db.query(
                Document.id
            )
            .filter(
                Document.status
                == DocumentStatus.PROCESSING,
                Document.processing_started_at.is_not(None),
                Document.processing_started_at
                < processing_cutoff,
            )
            .count()
        )

        STALE_DOCUMENTS_TOTAL.labels(
            status="processing",
        ).set(
            stale_processing_count
        )

        stale_deleting_count = (
            db.query(
                Document.id
            )
            .filter(
                Document.status
                == DocumentStatus.DELETING,
                Document.deletion_started_at.is_not(None),
                Document.deletion_started_at
                < deleting_cutoff,
            )
            .count()
        )

        STALE_DOCUMENTS_TOTAL.labels(
            status="deleting",
        ).set(
            stale_deleting_count
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

        oldest_pending = (
            db.query(
                func.min(
                    OutboxEvent.created_at
                )
            )
            .filter(
                OutboxEvent.status
                == "pending",
            )
            .scalar()
        )

        if oldest_pending is None:
            OUTBOX_PENDING_OLDEST_AGE_SECONDS.set(
                0
            )
        else:
            if oldest_pending.tzinfo is None:
                oldest_pending = (
                    oldest_pending.replace(
                        tzinfo=timezone.utc
                    )
                )

            age_seconds = max(
                0.0,
                (
                    now
                    - oldest_pending
                ).total_seconds(),
            )

            OUTBOX_PENDING_OLDEST_AGE_SECONDS.set(
                age_seconds
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