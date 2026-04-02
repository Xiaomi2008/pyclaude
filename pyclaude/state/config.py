from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


FIELD_NAMES = frozenset({"api_key", "model", "base_url", "temperature", "max_turns"})
INTEGER_PATTERN = re.compile(r"[+-]?\d+")
ENV_FIELD_NAMES = {
    "PYCLAUDE_API_KEY": "api_key",
    "PYCLAUDE_MODEL": "model",
    "PYCLAUDE_BASE_URL": "base_url",
    "PYCLAUDE_TEMPERATURE": "temperature",
    "PYCLAUDE_MAX_TURNS": "max_turns",
}


@dataclass(frozen=True)
class ResolvedConfig:
    api_key: str
    model: str
    base_url: str | None = None
    temperature: float | None = None
    max_turns: int | None = None


def load_config_file(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config file must contain a JSON object")
    return {key: value for key, value in raw.items() if key in FIELD_NAMES}


def resolve_config(
    *,
    cli: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    file_config: Mapping[str, Any] | None = None,
    defaults: Mapping[str, Any] | None = None,
) -> ResolvedConfig:
    merged: dict[str, Any] = {}

    for source in (defaults, file_config, _resolve_env(env), cli):
        merged.update(_normalize_source(source))

    missing = [name for name in ("api_key", "model") if not merged.get(name)]
    if missing:
        missing_names = ", ".join(missing)
        raise ValueError(f"missing required config values: {missing_names}")

    return ResolvedConfig(
        api_key=_coerce_required_str("api_key", merged["api_key"]),
        model=_coerce_required_str("model", merged["model"]),
        base_url=_coerce_optional_str("base_url", merged.get("base_url")),
        temperature=_coerce_optional_float("temperature", merged.get("temperature")),
        max_turns=_coerce_optional_int("max_turns", merged.get("max_turns")),
    )


def _resolve_env(env: Mapping[str, str] | None) -> dict[str, Any]:
    if env is None:
        return {}
    return {
        field_name: env_value
        for env_name, field_name in ENV_FIELD_NAMES.items()
        if (env_value := env.get(env_name)) is not None
    }


def _normalize_source(source: Mapping[str, Any] | None) -> dict[str, Any]:
    if source is None:
        return {}
    return {
        key: value
        for key, value in source.items()
        if key in FIELD_NAMES and value is not None
    }


def _coerce_required_str(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be a non-empty string")
    return normalized


def _coerce_optional_str(field_name: str, value: Any) -> str | None:
    if value is None:
        return None
    return _coerce_required_str(field_name, value)


def _coerce_optional_float(field_name: str, value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must be a finite number")
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not math.isfinite(normalized):
        raise ValueError(f"{field_name} must be a finite number")
    return normalized


def _coerce_optional_int(field_name: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized or INTEGER_PATTERN.fullmatch(normalized) is None:
            raise ValueError(f"{field_name} must be an integer")
        return int(normalized)
    raise ValueError(f"{field_name} must be an integer")
