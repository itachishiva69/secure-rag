from contextvars import ContextVar
from uuid import UUID, uuid4


_request_id: ContextVar[str | None] = ContextVar(
    "request_id",
    default=None,
)


def generate_request_id() -> str:
    return str(uuid4())


def normalize_request_id(
    value: str | None,
) -> str:
    if value:
        try:
            return str(UUID(value))
        except (ValueError, AttributeError):
            pass

    return generate_request_id()


def set_request_id(
    request_id: str,
):
    return _request_id.set(request_id)


def reset_request_id(token) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()