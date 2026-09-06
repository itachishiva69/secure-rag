from datetime import timedelta

from app.services import jobs


def test_reconciliation_job_calls_processing_and_deletion_services(
    monkeypatch,
):
    processing_calls: list[
        tuple[object, timedelta]
    ] = []

    deleting_calls: list[
        tuple[object, timedelta]
    ] = []

    def fake_reconcile_processing(
        *,
        db,
        stale_after,
    ):
        processing_calls.append(
            (
                db,
                stale_after,
            )
        )

        return [
            10,
            20,
        ]

    def fake_reconcile_deleting(
        *,
        db,
        stale_after,
    ):
        deleting_calls.append(
            (
                db,
                stale_after,
            )
        )

        return [
            30,
            40,
        ]

    monkeypatch.setattr(
        jobs,
        "reconcile_stale_processing_documents",
        fake_reconcile_processing,
    )

    monkeypatch.setattr(
        jobs,
        "reconcile_stale_deleting_documents",
        fake_reconcile_deleting,
    )

    class FakeSettings:
        reconciliation_stale_processing_minutes = 30
        reconciliation_stale_deleting_minutes = 45

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
        "get_settings",
        lambda: FakeSettings(),
    )

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        lambda: FakeSession(),
    )

    result = (
        jobs.reconcile_stale_documents_job()
    )

    assert result == {
        "processing": [
            10,
            20,
        ],
        "deleting": [
            30,
            40,
        ],
    }

    assert len(
        processing_calls
    ) == 1

    assert len(
        deleting_calls
    ) == 1

    processing_db, processing_stale_after = (
        processing_calls[0]
    )

    deleting_db, deleting_stale_after = (
        deleting_calls[0]
    )

    assert isinstance(
        processing_db,
        FakeSession,
    )

    assert isinstance(
        deleting_db,
        FakeSession,
    )

    assert processing_stale_after == (
        timedelta(
            minutes=30
        )
    )

    assert deleting_stale_after == (
        timedelta(
            minutes=45
        )
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


def test_cleanup_job_reraises_qdrant_failures(
    monkeypatch,
):
    class FakeDocument:
        id = 123
        storage_path = (
            "/tmp/cleanup-test.txt"
        )
        status = (
            jobs.DocumentStatus.DELETING
        )

    class FakeSession:
        def __init__(self):
            self.deleted = False
            self.committed = False

        def __enter__(self):
            return self

        def __exit__(
            self,
            exc_type,
            exc_value,
            traceback,
        ):
            return False

        def get(
            self,
            model,
            document_id,
        ):
            return FakeDocument()

        def delete(
            self,
            document,
        ):
            self.deleted = True

        def commit(self):
            self.committed = True

    fake_session = FakeSession()

    def fake_session_factory():
        return fake_session

    def failing_qdrant(
        document_id: int,
    ):
        raise RuntimeError(
            "simulated qdrant failure"
        )

    monkeypatch.setattr(
        jobs,
        "SessionLocal",
        fake_session_factory,
    )

    monkeypatch.setattr(
        jobs,
        "delete_document_vectors",
        failing_qdrant,
    )

    try:
        jobs.delete_document_job(
            document_id=123,
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "simulated qdrant failure"
        )
    else:
        raise AssertionError(
            "delete_document_job must "
            "re-raise Qdrant failures"
        )

    assert fake_session.deleted is False
    assert fake_session.committed is False