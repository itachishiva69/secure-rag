from datetime import timedelta

from app.services import jobs


def test_reconciliation_job_calls_service(
    monkeypatch,
):
    calls: list[tuple[object, timedelta]] = []

    def fake_reconcile(
        *,
        db,
        stale_after,
    ):
        calls.append(
            (
                db,
                stale_after,
            )
        )

        return [10, 20]

    monkeypatch.setattr(
        jobs,
        "reconcile_stale_processing_documents",
        fake_reconcile,
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        lambda: FakeSession(),
    )

    jobs.reconcile_stale_documents_job()

    assert len(calls) == 1

    _, stale_after = calls[0]

    assert stale_after == (
        timedelta(minutes=30)
    )


def test_ingestion_job_reraises_failures(
    monkeypatch,
):
    def failing_ingestion(
        *,
        db,
        document_id,
    ):
        raise RuntimeError(
            "simulated ingestion failure"
        )

    monkeypatch.setattr(
        jobs,
        "ingest_document",
        failing_ingestion,
    )

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        lambda: FakeSession(),
    )

    try:
        jobs.ingest_document_job(
            document_id=123,
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "simulated ingestion failure"
        )
    else:
        raise AssertionError(
            "ingest_document_job must "
            "re-raise ingestion failures"
        )