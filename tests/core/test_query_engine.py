from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pyclaude.core.messages import Message
from pyclaude.core.runtime import QueryResult, RuntimeContext, SessionState, Usage
from pyclaude.tools.registry import ToolRegistry


def now() -> datetime:
    return datetime.now(UTC)


class DummyModelClient:
    async def stream(self, request):
        if False:
            yield request


class DummyToolOrchestrator:
    async def run(self, calls, context):
        return []


def make_context() -> RuntimeContext:
    return RuntimeContext(
        cwd=Path.cwd(),
        config={},
        session_state=SessionState(
            session_id="session", conversation_id="conversation"
        ),
        tool_registry=ToolRegistry(),
        tool_orchestrator=DummyToolOrchestrator(),
        model_client=DummyModelClient(),
    )


def assistant_message(text: str) -> Message:
    return Message(role="assistant", content=text, timestamp=now())


def test_submit_normalizes_string_prompt_and_prepends_system_message(
    monkeypatch,
) -> None:
    from pyclaude.core.query_engine import QueryEngine

    captured = {}

    async def fake_run_query_loop(*, context, request):
        captured["context"] = context
        captured["request"] = request
        return QueryResult(
            messages=[*request.messages, assistant_message("done")],
            usage=Usage(input_tokens=1, output_tokens=1),
            stop_reason="completed",
            turns_completed=1,
        )

    monkeypatch.setattr(
        "pyclaude.core.query_engine.query_loop.run_query_loop", fake_run_query_loop
    )

    engine = QueryEngine(context=make_context(), system_instructions="Be terse")

    result = asyncio.run(engine.submit("hello"))

    request = captured["request"]
    assert captured["context"] is engine.context
    assert [message.role for message in request.messages] == ["system", "user"]
    assert [message.content for message in request.messages] == ["Be terse", "hello"]
    assert result.messages[-1].role == "assistant"
    assert [message.role for message in engine.messages] == [
        "system",
        "user",
        "assistant",
    ]


def test_submit_preserves_conversation_history_within_engine_instance(
    monkeypatch,
) -> None:
    from pyclaude.core.query_engine import QueryEngine

    requests = []

    async def fake_run_query_loop(*, context, request):
        requests.append(request)
        return QueryResult(
            messages=[*request.messages, assistant_message(f"reply {len(requests)}")],
            usage=Usage(input_tokens=1, output_tokens=1),
            stop_reason="completed",
            turns_completed=1,
        )

    monkeypatch.setattr(
        "pyclaude.core.query_engine.query_loop.run_query_loop", fake_run_query_loop
    )

    engine = QueryEngine(context=make_context(), system_instructions="Be terse")

    asyncio.run(engine.submit("first"))
    asyncio.run(
        engine.submit([Message(role="user", content="second", timestamp=now())])
    )

    assert [message.content for message in requests[0].messages] == [
        "Be terse",
        "first",
    ]
    assert [message.content for message in requests[1].messages] == [
        "Be terse",
        "first",
        "reply 1",
        "second",
    ]
    assert [message.content for message in engine.messages] == [
        "Be terse",
        "first",
        "reply 1",
        "second",
        "reply 2",
    ]


def test_system_instructions_message_is_normalized_to_system_role(monkeypatch) -> None:
    from pyclaude.core.query_engine import QueryEngine

    captured = {}

    async def fake_run_query_loop(*, context, request):
        captured["request"] = request
        return QueryResult(
            messages=[*request.messages, assistant_message("done")],
            usage=Usage(input_tokens=1, output_tokens=1),
            stop_reason="completed",
            turns_completed=1,
        )

    monkeypatch.setattr(
        "pyclaude.core.query_engine.query_loop.run_query_loop", fake_run_query_loop
    )

    engine = QueryEngine(
        context=make_context(),
        system_instructions=Message(role="user", content="Be terse", timestamp=now()),
    )

    asyncio.run(engine.submit("hello"))

    request = captured["request"]
    assert [message.role for message in request.messages] == ["system", "user"]
    assert [message.content for message in request.messages] == ["Be terse", "hello"]
    assert [message.role for message in engine.messages] == [
        "system",
        "user",
        "assistant",
    ]


def test_system_instructions_message_drops_tool_call_id(monkeypatch) -> None:
    from pyclaude.core.query_engine import QueryEngine

    captured = {}

    async def fake_run_query_loop(*, context, request):
        captured["request"] = request
        return QueryResult(
            messages=[*request.messages, assistant_message("done")],
            usage=Usage(input_tokens=1, output_tokens=1),
            stop_reason="completed",
            turns_completed=1,
        )

    monkeypatch.setattr(
        "pyclaude.core.query_engine.query_loop.run_query_loop", fake_run_query_loop
    )

    engine = QueryEngine(
        context=make_context(),
        system_instructions=Message(
            role="tool",
            content="Be terse",
            timestamp=now(),
            tool_call_id="call-1",
            metadata={"source": "test"},
        ),
    )

    asyncio.run(engine.submit("hello"))

    system_message = captured["request"].messages[0]
    assert system_message.role == "system"
    assert system_message.content == "Be terse"
    assert system_message.tool_call_id is None
    assert system_message.metadata == {"source": "test"}


def test_submit_serializes_overlapping_calls(monkeypatch) -> None:
    from pyclaude.core.query_engine import QueryEngine

    requests = []
    allow_first_to_finish = asyncio.Event()
    first_started = asyncio.Event()

    async def fake_run_query_loop(*, context, request):
        requests.append(request)
        call_number = len(requests)
        if call_number == 1:
            first_started.set()
            await allow_first_to_finish.wait()
        return QueryResult(
            messages=[*request.messages, assistant_message(f"reply {call_number}")],
            usage=Usage(input_tokens=1, output_tokens=1),
            stop_reason="completed",
            turns_completed=1,
        )

    monkeypatch.setattr(
        "pyclaude.core.query_engine.query_loop.run_query_loop", fake_run_query_loop
    )

    async def run_test() -> None:
        engine = QueryEngine(context=make_context(), system_instructions="Be terse")

        first_task = asyncio.create_task(engine.submit("first"))
        await first_started.wait()
        second_task = asyncio.create_task(engine.submit("second"))
        await asyncio.sleep(0)
        allow_first_to_finish.set()

        await asyncio.gather(first_task, second_task)

        assert [message.content for message in requests[0].messages] == [
            "Be terse",
            "first",
        ]
        assert [message.content for message in requests[1].messages] == [
            "Be terse",
            "first",
            "reply 1",
            "second",
        ]
        assert [message.content for message in engine.messages] == [
            "Be terse",
            "first",
            "reply 1",
            "second",
            "reply 2",
        ]

    asyncio.run(run_test())
