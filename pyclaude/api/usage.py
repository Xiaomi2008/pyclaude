from __future__ import annotations

from typing import Any, Mapping

from pyclaude.core.runtime import Usage


def normalize_usage(payload: Mapping[str, Any] | None) -> Usage:
    source = payload or {}
    return Usage(
        input_tokens=_read_token_count(source, "input_tokens", "prompt_tokens"),
        output_tokens=_read_token_count(source, "output_tokens", "completion_tokens"),
        cache_read_tokens=_read_token_count(
            source,
            "cache_read_tokens",
            "cache_read_input_tokens",
        ),
        cache_write_tokens=_read_token_count(
            source,
            "cache_write_tokens",
            "cache_creation_input_tokens",
        ),
    )


def _read_token_count(payload: Mapping[str, Any], *names: str) -> int:
    value = 0
    for name in names:
        if name in payload:
            value = payload[name]
            break
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        label = names[0]
        raise ValueError(f"{label} must be a non-negative integer")
    return value
