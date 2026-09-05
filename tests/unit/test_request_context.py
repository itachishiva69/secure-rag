from uuid import UUID

from app.core.request_context import (
    generate_request_id,
    get_request_id,
    normalize_request_id,
    reset_request_id,
    set_request_id,
)


def test_generate_request_id_returns_uuid():
    request_id = generate_request_id()

    UUID(request_id)


def test_normalize_valid_request_id():
    request_id = (
        "550e8400-e29b-41d4-a716-446655440000"
    )

    normalized = normalize_request_id(
        request_id
    )

    assert normalized == request_id


def test_normalize_invalid_request_id_generates_new_id():
    normalized = normalize_request_id(
        "not-a-valid-uuid"
    )

    UUID(normalized)

    assert normalized != "not-a-valid-uuid"


def test_normalize_missing_request_id_generates_new_id():
    normalized = normalize_request_id(
        None
    )

    UUID(normalized)


def test_request_id_context_can_be_set_and_reset():
    assert get_request_id() is None

    token = set_request_id(
        "550e8400-e29b-41d4-a716-446655440000"
    )

    try:
        assert get_request_id() == (
            "550e8400-e29b-41d4-a716-446655440000"
        )
    finally:
        reset_request_id(token)

    assert get_request_id() is None