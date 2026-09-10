import logging
import threading
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from sqlalchemy import text

from app.core.config import get_settings
from app.db.database import SessionLocal, engine
from app.models import OutboxEvent
from app.services.jobs import (
    delete_document_job,
    ingest_document_job,
    reconcile_stale_documents_job,
)
from app.services.outbox import (
    DELETE_DOCUMENT_EVENT,
    INGEST_DOCUMENT_EVENT,
    OUTBOX_PENDING,
    _claim_next_pending_event,
    _mark_event_dispatched,
    _mark_event_retryable,
)
from app.services.queue import get_redis


logger = logging.getLogger(__name__)

settings = get_settings()

INLINE_POLL_SECONDS = 2.0
HEALTH_CHECK_INTERVAL_SECONDS = 30.0
INLINE_MAX_JOB_ATTEMPTS = 3


class RuntimeState:
    def __init__(self):
        self._lock = threading.Lock()
        self._ready = False
        self._failed_dependencies: list[str] = []
        self._last_check_at: datetime | None = None

    def set_ready(
        self,
        *,
        failed_dependencies: list[str],
    ) -> None:
        with self._lock:
            self._failed_dependencies = list(
                failed_dependencies
            )
            self._ready = not failed_dependencies
            self._last_check_at = datetime.now(
                timezone.utc
            )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "ready": self._ready,
                "failed_dependencies": list(
                    self._failed_dependencies
                ),
                "last_check_at": self._last_check_at,
            }

    def refresh_dependencies(self) -> None:
        checks = {
            "database": _check_database,
            "redis": _check_redis,
            "qdrant": _check_qdrant,
        }

        failed: list[str] = []

        for name, check in checks.items():
            try:
                check()
            except Exception:
                failed.append(name)

                logger.exception(
                    "runtime_dependency_check_failed",
                    extra={
                        "dependency": name,
                    },
                )

        previous = self.snapshot()

        self.set_ready(
            failed_dependencies=failed
        )

        current_ready = not failed

        if previous["ready"] != current_ready:
            logger.info(
                "runtime_readiness_changed",
                extra={
                    "ready": current_ready,
                    "failed_dependencies": failed,
                },
            )


runtime_state = RuntimeState()


class InlineRuntime:
    def __init__(
        self,
        *,
        processing_enabled: bool,
    ):
        self.processing_enabled = (
            processing_enabled
        )

        self._stop_event = threading.Event()

        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        logger.info(
            "inline_runtime_starting",
            extra={
                "processing_enabled": (
                    self.processing_enabled
                ),
            },
        )

        # Perform one synchronous dependency check before
        # FastAPI declares the application ready.
        runtime_state.refresh_dependencies()

        health_thread = threading.Thread(
            target=self._health_loop,
            name="secure-rag-runtime-health",
            daemon=True,
        )

        self._threads.append(
            health_thread
        )

        health_thread.start()

        if not self.processing_enabled:
            logger.info(
                "inline_processing_disabled"
            )
            return

        outbox_thread = threading.Thread(
            target=self._outbox_loop,
            name="secure-rag-inline-outbox",
            daemon=True,
        )

        maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            name="secure-rag-inline-maintenance",
            daemon=True,
        )

        self._threads.extend(
            [
                outbox_thread,
                maintenance_thread,
            ]
        )

        outbox_thread.start()
        maintenance_thread.start()

        logger.info(
            "inline_processing_started",
            extra={
                "poll_seconds": INLINE_POLL_SECONDS,
                "maintenance_interval_seconds": (
                    settings.reconciliation_interval_seconds
                ),
            },
        )

    def stop(self) -> None:
        logger.info(
            "inline_runtime_stopping"
        )

        self._stop_event.set()

        for thread in self._threads:
            thread.join(timeout=5)

        self._threads.clear()

        logger.info(
            "inline_runtime_stopped"
        )

    def _health_loop(self) -> None:
        while not self._stop_event.wait(
            HEALTH_CHECK_INTERVAL_SECONDS
        ):
            try:
                runtime_state.refresh_dependencies()
            except Exception:
                logger.exception(
                    "runtime_health_loop_failed"
                )

    def _outbox_loop(self) -> None:
        while not self._stop_event.is_set():
            did_work = False

            try:
                while True:
                    processed = (
                        self._process_one_outbox_event()
                    )

                    if not processed:
                        break

                    did_work = True

            except Exception:
                logger.exception(
                    "inline_outbox_loop_failed"
                )

            if not did_work:
                self._stop_event.wait(
                    INLINE_POLL_SECONDS
                )

    def _maintenance_loop(self) -> None:
        # Run once on startup so old stale work can be
        # recovered immediately.
        self._run_maintenance()

        while not self._stop_event.wait(
            settings.reconciliation_interval_seconds
        ):
            self._run_maintenance()

    @staticmethod
    def _run_maintenance() -> None:
        try:
            result = reconcile_stale_documents_job()

            if (
                result["processing"]
                or result["deleting"]
            ):
                logger.info(
                    "inline_maintenance_recovered_documents",
                    extra=result,
                )

        except Exception:
            logger.exception(
                "inline_maintenance_failed"
            )

    @staticmethod
    def _process_one_outbox_event() -> bool:
        with SessionLocal() as db:
            event = _claim_next_pending_event(db)

            if event is None:
                return False

            event_id = event.id
            document_id = event.document_id
            event_type = event.event_type
            attempts = event.attempts

        logger.info(
            "inline_outbox_event_started",
            extra={
                "outbox_event_id": event_id,
                "document_id": document_id,
                "event_type": event_type,
                "attempts": attempts,
            },
        )

        try:
            if event_type == INGEST_DOCUMENT_EVENT:
                ingest_document_job(
                    document_id
                )

            elif event_type == DELETE_DOCUMENT_EVENT:
                delete_document_job(
                    document_id
                )

            else:
                raise ValueError(
                    f"Unsupported outbox event type: "
                    f"{event_type}"
                )

        except Exception as exc:
            logger.exception(
                "inline_outbox_event_failed",
                extra={
                    "outbox_event_id": event_id,
                    "document_id": document_id,
                    "event_type": event_type,
                    "attempts": attempts,
                },
            )

            with SessionLocal() as db:
                current_event = db.get(
                    OutboxEvent,
                    event_id,
                )

                if current_event is not None:
                    if attempts >= INLINE_MAX_JOB_ATTEMPTS:
                        # Match the existing RQ retry boundary:
                        # leave the document FAILED/DELETING for
                        # reconciliation and finalize the event
                        # so a permanently broken job does not
                        # retry forever.
                        _mark_event_dispatched(
                            db,
                            current_event,
                        )

                        logger.error(
                            "inline_outbox_event_retry_exhausted",
                            extra={
                                "outbox_event_id": event_id,
                                "document_id": document_id,
                                "event_type": event_type,
                                "attempts": attempts,
                            },
                        )

                    else:
                        _mark_event_retryable(
                            db,
                            current_event,
                            exc,
                        )

            return True

        else:
            # Deletion can remove the document, which cascades
            # the outbox row. Re-fetch the event instead of
            # keeping the original ORM object alive.
            with SessionLocal() as db:
                current_event = db.get(
                    OutboxEvent,
                    event_id,
                )

                if current_event is not None:
                    _mark_event_dispatched(
                        db,
                        current_event,
                    )

            logger.info(
                "inline_outbox_event_completed",
                extra={
                    "outbox_event_id": event_id,
                    "document_id": document_id,
                    "event_type": event_type,
                    "attempts": attempts,
                },
            )

            return True


def _check_database() -> None:
    with engine.connect() as connection:
        connection.execute(
            text("SELECT 1")
        )


def _check_redis() -> None:
    get_redis().ping()


def _check_qdrant() -> None:
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    try:
        client.get_collections()
    finally:
        client.close()


_runtime: InlineRuntime | None = None


def start_runtime() -> InlineRuntime:
    global _runtime

    if _runtime is not None:
        return _runtime

    runtime = InlineRuntime(
        processing_enabled=(
            settings.inline_background_processing_enabled
        ),
    )

    runtime.start()

    _runtime = runtime

    return runtime


def stop_runtime() -> None:
    global _runtime

    if _runtime is None:
        return

    _runtime.stop()
    _runtime = None


def get_runtime_state() -> RuntimeState:
    return runtime_state
