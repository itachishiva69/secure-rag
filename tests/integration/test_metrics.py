from fastapi.testclient import (
    TestClient,
)

from app.main import app


client = TestClient(app)


def test_metrics_endpoint_returns_prometheus_data():
    response = client.get(
        "/metrics",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 200

    assert (
        "secure_rag_http_requests_total"
        in response.text
    )

    assert (
        "secure_rag_http_request_duration_seconds"
        in response.text
    )

    assert (
        "secure_rag_documents_total"
        in response.text
    )

    assert (
        "secure_rag_stale_documents_total"
        in response.text
    )

    assert (
        "secure_rag_outbox_events_total"
        in response.text
    )

    assert (
        "secure_rag_outbox_events_ready"
        in response.text
    )

    assert (
        "secure_rag_outbox_pending_oldest_age_seconds"
        in response.text
    )

    assert (
        "secure_rag_rq_queue_depth"
        in response.text
    )

    assert (
        "secure_rag_metrics_collections_total"
        in response.text
    )


def test_metrics_endpoint_does_not_expose_request_id():
    request_id = (
        "12345678-1234-1234-1234-123456789012"
    )

    response = client.get(
        "/metrics",
        headers={
            "Host": "testserver",
            "X-Request-ID": request_id,
        },
    )

    assert response.status_code == 200

    assert request_id not in response.text


def test_metrics_collection_status_is_exposed():
    response = client.get(
        "/metrics",
        headers={
            "Host": "testserver",
        },
    )

    assert response.status_code == 200

    assert (
        'secure_rag_metrics_collections_total{status="success"}'
        in response.text
    )