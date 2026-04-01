from __future__ import annotations

import json

import pytest

from pyclaude.state.config import (
    ResolvedConfig,
    load_config_file,
    resolve_config,
)


def test_cli_overrides_env_file_and_defaults() -> None:
    resolved = resolve_config(
        cli={"model": "cli-model", "temperature": 0.7},
        env={
            "PYCLAUDE_MODEL": "env-model",
            "PYCLAUDE_API_KEY": "env-key",
            "PYCLAUDE_TEMPERATURE": "0.2",
            "PYCLAUDE_MAX_TURNS": "9",
        },
        file_config={
            "model": "file-model",
            "api_key": "file-key",
            "temperature": 0.1,
            "max_turns": 4,
            "base_url": "https://file.example",
        },
        defaults={
            "model": "default-model",
            "base_url": "https://default.example",
            "max_turns": 2,
        },
    )

    assert resolved == ResolvedConfig(
        api_key="env-key",
        model="cli-model",
        base_url="https://file.example",
        temperature=0.7,
        max_turns=9,
    )


def test_env_overrides_file_and_defaults_when_cli_missing() -> None:
    resolved = resolve_config(
        cli={},
        env={
            "PYCLAUDE_API_KEY": "env-key",
            "PYCLAUDE_BASE_URL": "https://env.example",
        },
        file_config={
            "api_key": "file-key",
            "model": "file-model",
            "base_url": "https://file.example",
        },
        defaults={"model": "default-model", "temperature": 0.3, "max_turns": 5},
    )

    assert resolved == ResolvedConfig(
        api_key="env-key",
        model="file-model",
        base_url="https://env.example",
        temperature=0.3,
        max_turns=5,
    )


def test_missing_required_values_raises_error() -> None:
    with pytest.raises(ValueError, match="api_key, model"):
        resolve_config(cli={}, env={}, file_config={}, defaults={})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("api_key", "   ", "api_key"),
        ("model", "\t", "model"),
        ("base_url", False, "base_url"),
        ("temperature", "nan", "temperature"),
    ],
)
def test_invalid_config_values_raise_error(
    field: str,
    value: object,
    message: str,
) -> None:
    config = {"api_key": "test-key", "model": "test-model", field: value}

    with pytest.raises(ValueError, match=message):
        resolve_config(cli=config, env={}, file_config={}, defaults={})


@pytest.mark.parametrize("value", [3.7, True, "3.7", "true"])
def test_max_turns_must_be_a_whole_integer_count(value: object) -> None:
    with pytest.raises(ValueError, match="max_turns"):
        resolve_config(
            cli={"api_key": "test-key", "model": "test-model", "max_turns": value},
            env={},
            file_config={},
            defaults={},
        )


def test_load_config_file_reads_json_object(tmp_path) -> None:
    config_path = tmp_path / "pyclaude.json"
    config_path.write_text(
        json.dumps(
            {
                "api_key": "file-key",
                "model": "file-model",
                "temperature": 0.4,
            }
        ),
        encoding="utf-8",
    )

    assert load_config_file(config_path) == {
        "api_key": "file-key",
        "model": "file-model",
        "temperature": 0.4,
    }
