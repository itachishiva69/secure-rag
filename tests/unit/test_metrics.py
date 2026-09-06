from prometheus_client import REGISTRY

from app.core.metrics import (
    DOCUMENTS_TOTAL,
    HTTP_REQUESTS_TOTAL,
    METRICS_COLLECTIONS_TOTAL,
    record_http_request,
)


def test_record_http_request_updates_request_counter():
    metric = HTTP_REQUESTS_TOTAL.labels(
        method="GET",
        path="/health",
        status_code="200",
    )

    before = metric._value.get()

    record_http_request(
        method="GET",
        path="/health",
        status_code=200,
        duration_seconds=0.01,
    )

    after = metric._value.get()

    assert after == before + 1


def test_document_metric_has_status_label():
    DOCUMENTS_TOTAL.labels(
        status="indexed"
    ).set(3)

    assert (
        DOCUMENTS_TOTAL.labels(
            status="indexed"
        )._value.get()
        == 3
    )


def test_secure_rag_metrics_are_registered():
    metric_names = {
        sample.name
        for metric in REGISTRY.collect()
        for sample in metric.samples
    }

    assert (
        "secure_rag_http_requests_total"
        in metric_names
    )

    assert (
        "secure_rag_http_request_duration_seconds_count"
        in metric_names
    )

    assert (
        "secure_rag_documents_total"
        in metric_names
    )

    assert (
        "secure_rag_outbox_events_total"
        in metric_names
    )

    assert (
        "secure_rag_rq_queue_depth"
        in metric_names
    )

    assert (
        "secure_rag_metrics_collections_total"
        in metric_names
    )


def test_metrics_collection_status_labels_exist():
    for status in (
        "success",
        "failure",
    ):
        METRICS_COLLECTIONS_TOTAL.labels(
            status=status
        )