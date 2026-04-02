from __future__ import annotations

import pytest

from pyclaude.api.usage import normalize_usage
from pyclaude.core.runtime import Usage


def test_normalize_usage_accepts_canonical_usage_shape() -> None:
    assert normalize_usage({"input_tokens": 11, "output_tokens": 7}) == Usage(
        input_tokens=11,
        output_tokens=7,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )


def test_normalize_usage_maps_provider_aliases_to_canonical_usage() -> None:
    payload = {
        "prompt_tokens": 13,
        "completion_tokens": 5,
        "cache_read_input_tokens": 2,
        "cache_creation_input_tokens": 3,
    }

    assert normalize_usage(payload) == Usage(
        input_tokens=13,
        output_tokens=5,
        cache_read_tokens=2,
        cache_write_tokens=3,
    )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"input_tokens": -1, "output_tokens": 1}, "input_tokens"),
        ({"input_tokens": 1, "output_tokens": "two"}, "output_tokens"),
    ],
)
def test_normalize_usage_rejects_invalid_token_counts(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_usage(payload)
