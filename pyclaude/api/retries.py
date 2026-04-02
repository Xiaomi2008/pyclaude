from __future__ import annotations

from dataclasses import dataclass

from pyclaude.api.errors import is_retryable_error


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be non-negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                "max_delay_seconds must be greater than or equal to base_delay_seconds"
            )


def should_retry(error: BaseException, *, attempt: int, policy: RetryPolicy) -> bool:
    _validate_attempt(attempt)
    return attempt < policy.max_attempts and is_retryable_error(error)


def next_retry_delay(*, attempt: int, policy: RetryPolicy) -> float:
    _validate_attempt(attempt)
    delay = policy.base_delay_seconds * (2 ** max(attempt - 1, 0))
    return min(delay, policy.max_delay_seconds)


def _validate_attempt(attempt: int) -> None:
    if attempt <= 0:
        raise ValueError("attempt must be greater than zero")
