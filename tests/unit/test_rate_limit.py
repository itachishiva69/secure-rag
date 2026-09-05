from unittest.mock import Mock

import pytest

from app.services.rate_limit import (
    RateLimitError,
    RateLimitExceeded,
    RateLimiter,
)


def create_limiter(
    redis,
    *,
    requests=5,
    window_seconds=60,
):
    return RateLimiter(
        redis=redis,
        requests=requests,
        window_seconds=window_seconds,
        key_prefix="test",
    )


def test_rate_limiter_allows_request_under_limit():
    redis = Mock()
    redis.eval.return_value = 3

    limiter = create_limiter(redis)

    limiter.check(
        subject="user-1"
    )

    redis.eval.assert_called_once()

    args = redis.eval.call_args.args

    assert args[1] == 1
    assert args[2] == "test:user-1"
    assert args[3] == 60


def test_rate_limiter_rejects_request_over_limit():
    redis = Mock()
    redis.eval.return_value = 6

    limiter = create_limiter(
        redis,
        requests=5,
    )

    with pytest.raises(
        RateLimitExceeded
    ) as exc_info:
        limiter.check(
            subject="user-1"
        )

    assert exc_info.value.limit == 5
    assert exc_info.value.window_seconds == 60


def test_rate_limiter_uses_independent_subject_keys():
    redis = Mock()
    redis.eval.return_value = 1

    limiter = create_limiter(redis)

    limiter.check(
        subject="user-1"
    )

    limiter.check(
        subject="user-2"
    )

    calls = redis.eval.call_args_list

    assert calls[0].args[2] == (
        "test:user-1"
    )

    assert calls[1].args[2] == (
        "test:user-2"
    )


def test_rate_limiter_wraps_redis_failure():
    redis = Mock()

    redis.eval.side_effect = RuntimeError(
        "redis unavailable"
    )

    limiter = create_limiter(redis)

    with pytest.raises(
        RateLimitError,
        match="Rate limiter could not be evaluated",
    ):
        limiter.check(
            subject="user-1"
        )


def test_rate_limiter_rejects_invalid_request_limit():
    with pytest.raises(
        ValueError,
        match="requests must be greater than zero",
    ):
        create_limiter(
            Mock(),
            requests=0,
        )


def test_rate_limiter_rejects_invalid_window():
    with pytest.raises(
        ValueError,
        match="window_seconds must be greater than zero",
    ):
        create_limiter(
            Mock(),
            window_seconds=0,
        )