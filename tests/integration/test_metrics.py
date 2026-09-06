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
        "secure_rag_outbox_events_total"
        in response.text
    )

    assert (
        "secure_rag_rq_queue_depth"
        in response.text
    )