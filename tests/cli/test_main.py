from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from pyclaude.api.anthropic import AnthropicModelClient
from pyclaude.core.messages import Message
from pyclaude.core.runtime import QueryResult, SessionState, Usage
from pyclaude.state.config import ResolvedConfig


def now() -> datetime:
    return datetime.now(UTC)


def assistant_message(text: str) -> Message:
    return Message(role="assistant", content=text, timestamp=now())


def test_build_runtime_context_uses_resolved_config_and_anthropic_model_client() -> (
    None
):
    from pyclaude.state.runtime import build_runtime_context

    config = ResolvedConfig(
        api_key="test-key",
        model="claude-test",
        base_url="https://example.invalid/v1/messages",
        temperature=0.3,
        max_turns=5,
    )

    context = build_runtime_context(config=config, cwd=Path("/tmp/pyclaude"))

    assert context.cwd == Path("/tmp/pyclaude")
    assert context.config == {
        "api_key": "test-key",
        "model": "claude-test",
        "base_url": "https://example.invalid/v1/messages",
        "temperature": 0.3,
        "max_turns": 5,
    }
    assert isinstance(context.model_client, AnthropicModelClient)
    assert context.session_state == SessionState(
        session_id=context.session_state.session_id,
        conversation_id=context.session_state.conversation_id,
        turn_count=0,
    )


def test_build_runtime_context_creates_fresh_in_memory_session_per_context() -> None:
    from pyclaude.state.runtime import build_runtime_context

    config = ResolvedConfig(api_key="test-key", model="claude-test")

    first = build_runtime_context(config=config, cwd=Path("/tmp/one"))
    second = build_runtime_context(config=config, cwd=Path("/tmp/two"))

    assert first.session_state is not second.session_state
    assert first.session_state.session_id != second.session_state.session_id
    assert first.session_state.conversation_id != second.session_state.conversation_id
    assert first.session_state.turn_count == 0
    assert second.session_state.turn_count == 0


def test_main_accepts_prompt_and_invokes_query_engine_directly(
    monkeypatch, capsys
) -> None:
    import pyclaude.cli.main as main_module

    resolved = ResolvedConfig(api_key="test-key", model="claude-test")
    fake_context = object()
    events: list[tuple[str, object]] = []

    class FakeCommandRegistry:
        def maybe_match(self, prompt: str):
            events.append(("maybe_match", prompt))
            return None

    class FakeQueryEngine:
        def __init__(self, *, context, system_instructions=None) -> None:
            events.append(("init", context))

        async def submit(self, prompt: str, **kwargs):
            events.append(("submit", prompt))
            events.append(("submit_kwargs", kwargs))
            return QueryResult(
                messages=[assistant_message("done")],
                usage=Usage(input_tokens=1, output_tokens=1),
                stop_reason="completed",
                turns_completed=1,
            )

    monkeypatch.setattr(main_module, "QueryEngine", FakeQueryEngine)
    monkeypatch.setattr(main_module, "CommandRegistry", FakeCommandRegistry)
    monkeypatch.setattr(
        main_module, "build_runtime_context", lambda *, config, cwd: fake_context
    )
    monkeypatch.setattr(main_module, "resolve_config", lambda **_: resolved)

    exit_code = main_module.main(
        ["--prompt", "hello", "--api-key", "test-key", "--model", "claude-test"]
    )

    assert exit_code == 0
    assert events == [
        ("maybe_match", "hello"),
        ("init", fake_context),
        ("submit", "hello"),
        (
            "submit_kwargs",
            {"max_turns": None, "model": "claude-test", "temperature": None},
        ),
    ]
    assert capsys.readouterr().out.strip() == "done"


def test_main_uses_command_registry_as_real_seam_before_query_engine(
    monkeypatch, capsys
) -> None:
    import pyclaude.cli.main as main_module

    resolved = ResolvedConfig(api_key="test-key", model="claude-test")
    fake_context = object()
    events: list[tuple[str, object]] = []

    class FakeCommandRegistry:
        def maybe_match(self, prompt: str):
            events.append(("maybe_match", prompt))
            return None

    class FakeQueryEngine:
        def __init__(self, *, context, system_instructions=None) -> None:
            events.append(("init", context))

        async def submit(self, prompt: str, **kwargs):
            events.append(("submit", prompt))
            return QueryResult(
                messages=[assistant_message("done")],
                usage=Usage(input_tokens=1, output_tokens=1),
                stop_reason="completed",
                turns_completed=1,
            )

    monkeypatch.setattr(main_module, "QueryEngine", FakeQueryEngine)
    monkeypatch.setattr(main_module, "CommandRegistry", FakeCommandRegistry)
    monkeypatch.setattr(
        main_module, "build_runtime_context", lambda *, config, cwd: fake_context
    )
    monkeypatch.setattr(main_module, "resolve_config", lambda **_: resolved)

    exit_code = main_module.main(
        ["--prompt", "hello", "--api-key", "test-key", "--model", "claude-test"]
    )

    assert exit_code == 0
    assert events == [
        ("maybe_match", "hello"),
        ("init", fake_context),
        ("submit", "hello"),
    ]
    assert capsys.readouterr().out.strip() == "done"


def test_main_resolves_config_before_building_runtime_dependencies(
    monkeypatch, tmp_path, capsys
) -> None:
    import pyclaude.cli.main as main_module

    order: list[str] = []
    resolved = ResolvedConfig(api_key="resolved-key", model="resolved-model")

    def fake_resolve_config(**kwargs):
        order.append("resolve")
        assert kwargs["cli"] == {"api_key": "cli-key", "model": "cli-model"}
        return resolved

    def fake_build_runtime_context(*, config, cwd):
        order.append("build")
        assert config is resolved
        assert cwd == tmp_path
        return object()

    class FakeQueryEngine:
        def __init__(self, *, context, system_instructions=None) -> None:
            order.append("engine")

        async def submit(self, prompt: str, **kwargs):
            order.append("submit")
            return QueryResult(
                messages=[assistant_message("ok")],
                usage=Usage(input_tokens=1, output_tokens=1),
                stop_reason="completed",
                turns_completed=1,
            )

    monkeypatch.setattr(main_module, "resolve_config", fake_resolve_config)
    monkeypatch.setattr(
        main_module, "build_runtime_context", fake_build_runtime_context
    )
    monkeypatch.setattr(main_module, "QueryEngine", FakeQueryEngine)

    exit_code = main_module.main(
        [
            "--prompt",
            "hello",
            "--api-key",
            "cli-key",
            "--model",
            "cli-model",
            "--cwd",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert order == ["resolve", "build", "engine", "submit"]
    assert capsys.readouterr().out.strip() == "ok"


def test_main_surfaces_classified_live_transport_auth_error(
    monkeypatch, capsys
) -> None:
    import urllib.error

    import pyclaude.cli.main as main_module

    body = json.dumps(
        {
            "type": "error",
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout: float):
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=io.BytesIO(body),
        )

    monkeypatch.setattr("pyclaude.api.anthropic._urlopen", fake_urlopen)

    exit_code = main_module.main(
        ["--prompt", "hello", "--api-key", "test-key", "--model", "claude-test"]
    )

    assert exit_code == 1
    assert (
        capsys.readouterr().err.strip()
        == "Anthropic authentication failed (401): invalid x-api-key"
    )
