from app.services import jobs
from scripts import cron


def test_scheduler_registers_callable_jobs(
    monkeypatch,
):
    registered_jobs = []

    class FakeRedis:
        @classmethod
        def from_url(
            cls,
            url,
            *,
            decode_responses,
        ):
            return cls()

    class FakeScheduler:
        def __init__(
            self,
            *,
            connection,
            name,
        ):
            self.connection = connection
            self.name = name

        def register(
            self,
            func,
            queue_name,
            *,
            interval,
            name,
        ):
            registered_jobs.append(
                {
                    "func": func,
                    "queue_name": queue_name,
                    "interval": interval,
                    "name": name,
                }
            )

        def start(self):
            return None

    class FakeSettings:
        redis_url = (
            "redis://localhost:6379/0"
        )

        reconciliation_interval_seconds = 300

    monkeypatch.setattr(
        cron,
        "Redis",
        FakeRedis,
    )

    monkeypatch.setattr(
        cron,
        "CronScheduler",
        FakeScheduler,
    )

    monkeypatch.setattr(
        cron,
        "get_settings",
        lambda: FakeSettings(),
    )

    cron.main()

    assert len(
        registered_jobs
    ) == 2

    assert registered_jobs[0][
        "func"
    ] is jobs.reconcile_stale_documents_job

    assert registered_jobs[1][
        "func"
    ] is jobs.dispatch_pending_outbox_job

    assert registered_jobs[0][
        "queue_name"
    ] == cron.MAINTENANCE_QUEUE_NAME

    assert registered_jobs[1][
        "queue_name"
    ] == cron.MAINTENANCE_QUEUE_NAME

    assert registered_jobs[0][
        "interval"
    ] == 300

    assert registered_jobs[1][
        "interval"
    ] == 300

    assert registered_jobs[0][
        "name"
    ] == (
        "secure-rag-document-reconciliation"
    )

    assert registered_jobs[1][
        "name"
    ] == (
        "secure-rag-outbox-dispatch"
    )


def test_scheduler_rejects_non_positive_interval(
    monkeypatch,
):
    class FakeSettings:
        redis_url = (
            "redis://localhost:6379/0"
        )

        reconciliation_interval_seconds = 0

    monkeypatch.setattr(
        cron,
        "get_settings",
        lambda: FakeSettings(),
    )

    try:
        cron.main()
    except ValueError as exc:
        assert str(exc) == (
            "RECONCILIATION_INTERVAL_SECONDS "
            "must be greater than zero"
        )
    else:
        raise AssertionError(
            "cron.main() must reject "
            "a non-positive interval"
        )