from __future__ import annotations

import pytest

from pyclaude.api.errors import APIResponseError, APITransportError, is_retryable_error
from pyclaude.api.retries import RetryPolicy, next_retry_delay, should_retry


def test_retryable_error_classification_distinguishes_transport_and_status_errors() -> (
    None
):
    assert is_retryable_error(APITransportError("connection dropped")) is True
    assert is_retryable_error(APIResponseError("rate limited", status_code=429)) is True
    assert is_retryable_error(APIResponseError("bad request", status_code=400)) is False


def test_should_retry_stops_after_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3)
    error = APITransportError("temporary timeout")

    assert should_retry(error, attempt=1, policy=policy) is True
    assert should_retry(error, attempt=2, policy=policy) is True
    assert should_retry(error, attempt=3, policy=policy) is False


def test_should_retry_rejects_non_retryable_errors_even_before_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=4)

    assert (
        should_retry(
            APIResponseError("invalid request", status_code=422),
            attempt=1,
            policy=policy,
        )
        is False
    )


def test_next_retry_delay_uses_capped_exponential_backoff() -> None:
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=0.25, max_delay_seconds=1.0)

    assert next_retry_delay(attempt=1, policy=policy) == 0.25
    assert next_retry_delay(attempt=2, policy=policy) == 0.5
    assert next_retry_delay(attempt=3, policy=policy) == 1.0
    assert next_retry_delay(attempt=4, policy=policy) == 1.0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_attempts": 0}, "max_attempts"),
        ({"base_delay_seconds": -0.1}, "base_delay_seconds"),
        ({"max_delay_seconds": -0.1}, "max_delay_seconds"),
        ({"base_delay_seconds": 1.0, "max_delay_seconds": 0.5}, "max_delay_seconds"),
    ],
)
def test_retry_policy_rejects_invalid_values(
    kwargs: dict[str, float | int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        RetryPolicy(**kwargs)


def test_retry_helpers_reject_non_positive_attempts() -> None:
    policy = RetryPolicy()
    error = APITransportError("temporary timeout")

    with pytest.raises(ValueError, match="attempt"):
        should_retry(error, attempt=0, policy=policy)

    with pytest.raises(ValueError, match="attempt"):
        next_retry_delay(attempt=0, policy=policy)
