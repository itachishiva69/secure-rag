from app.services import runtime


class FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class FakeConnection:
    def __init__(self, lock_state):
        self.lock_state = lock_state
        self.closed = False

    def execute(self, statement, params=None):
        sql = str(statement)

        if "pg_try_advisory_lock" in sql:
            acquired = not self.lock_state["held"]

            if acquired:
                self.lock_state["held"] = True

            return FakeResult(acquired)

        if "pg_advisory_unlock" in sql:
            self.lock_state["held"] = False
            return FakeResult(True)

        return FakeResult(1)

    def close(self):
        self.closed = True


class FakeEngine:
    def __init__(self):
        self.lock_state = {"held": False}
        self.connections = []

    def connect(self):
        connection = FakeConnection(
            self.lock_state
        )
        self.connections.append(connection)
        return connection


def test_inline_runtime_uses_single_outbox_leader(
    monkeypatch,
):
    fake_engine = FakeEngine()

    monkeypatch.setattr(
        runtime,
        "engine",
        fake_engine,
    )

    first_runtime = runtime.InlineRuntime(
        processing_enabled=True
    )
    second_runtime = runtime.InlineRuntime(
        processing_enabled=True
    )

    assert (
        first_runtime._acquire_outbox_leadership()
        is True
    )
    assert (
        second_runtime._acquire_outbox_leadership()
        is False
    )

    first_runtime._release_outbox_leadership()

    assert (
        second_runtime._acquire_outbox_leadership()
        is True
    )

    second_runtime._release_outbox_leadership()

    assert all(
        connection.closed
        for connection in fake_engine.connections
    )
