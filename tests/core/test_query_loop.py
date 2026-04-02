from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pyclaude.core.messages import (
    Message,
    MessageCompleteEvent,
    TextBlock,
    TextDeltaEvent,
    ToolCallEvent,
    ToolCallBlock,
)
from pyclaude.core.runtime import QueryRequest, RuntimeContext, SessionState, Usage
from pyclaude.tools.base import ToolCall, ToolResult
from pyclaude.tools.registry import ToolRegistry


def now() -> datetime:
    return datetime.now(UTC)


class FakeModelClient:
    def __init__(self, streams):
        self._streams = list(streams)
        self.requests: list[QueryRequest] = []

    async def stream(self, request: QueryRequest):
        self.requests.append(request)
        events = self._streams.pop(0)
        for event in events:
            yield event


class FakeToolOrchestrator:
    def __init__(self, *, results=None, error: Exception | None = None):
        self._results = list(results or [])
        self._error = error
        self.calls: list[list[ToolCall]] = []

    async def run(
        self, calls: list[ToolCall], context: RuntimeContext
    ) -> list[ToolResult]:
        self.calls.append(calls)
        if self._error is not None:
            raise self._error
        return self._results.pop(0)


def make_context(
    *, model_client: FakeModelClient, tool_orchestrator: FakeToolOrchestrator
) -> RuntimeContext:
    return RuntimeContext(
        cwd=Path.cwd(),
        config={},
        session_state=SessionState(
            session_id="session", conversation_id="conversation"
        ),
        tool_registry=ToolRegistry(),
        tool_orchestrator=tool_orchestrator,
        model_client=model_client,
    )


def assistant_message(*content: TextBlock | ToolCallBlock) -> Message:
    return Message(role="assistant", content=list(content), timestamp=now())


def completed(
    message: Message, *, stop_reason: str = "completed"
) -> MessageCompleteEvent:
    return MessageCompleteEvent(
        message=message,
        stop_reason=stop_reason,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def text_delta(text: str) -> TextDeltaEvent:
    return TextDeltaEvent(text=text)


def tool_call_event(
    *, call_id: str, name: str, arguments: dict[str, str]
) -> ToolCallEvent:
    return ToolCallEvent(
        tool_call=ToolCall(id=call_id, name=name, arguments=arguments),
    )


def assert_tool_result_block(
    message: Message,
    *,
    tool_call_id: str,
    name: str,
    content: str,
    is_error: bool = False,
) -> None:
    assert len(message.content) == 1
    block = message.content[0]
    assert getattr(block, "type", None) == "tool_result"
    assert block.tool_call_id == tool_call_id
    assert block.name == name
    assert block.content == content
    assert block.is_error is is_error


def test_plain_assistant_response_completes() -> None:
    from pyclaude.core.query_loop import run_query_loop

    model_client = FakeModelClient(
        streams=[
            [
                text_delta("hello"),
                text_delta(" from model"),
                completed(
                    assistant_message(),
                ),
            ]
        ]
    )
    context = make_context(
        model_client=model_client,
        tool_orchestrator=FakeToolOrchestrator(),
    )
    request = QueryRequest(
        messages=[Message(role="user", content="hi", timestamp=now())],
    )

    result = asyncio.run(run_query_loop(context=context, request=request))

    assert result.stop_reason == "completed"
    assert result.turns_completed == 1
    assert len(result.messages) == 2
    assert result.messages[-1].role == "assistant"
    assert result.messages[-1].content == [TextBlock(text="hello from model")]
    assert len(model_client.requests) == 1


def test_assistant_emits_one_tool_call_and_loop_resumes_after_tool_result() -> None:
    from pyclaude.core.query_loop import run_query_loop

    model_client = FakeModelClient(
        streams=[
            [
                tool_call_event(
                    call_id="call-1",
                    name="lookup",
                    arguments={"q": "weather"},
                ),
                completed(
                    assistant_message(),
                    stop_reason="tool_use",
                ),
            ],
            [
                text_delta("it is "),
                text_delta("sunny"),
                completed(
                    assistant_message(),
                ),
            ],
        ]
    )
    orchestrator = FakeToolOrchestrator(
        results=[
            [
                ToolResult(
                    tool_call_id="call-1",
                    tool_name="lookup",
                    content="72F",
                )
            ]
        ]
    )
    context = make_context(model_client=model_client, tool_orchestrator=orchestrator)
    request = QueryRequest(
        messages=[Message(role="user", content="weather?", timestamp=now())]
    )

    result = asyncio.run(run_query_loop(context=context, request=request))

    assert result.stop_reason == "completed"
    assert result.turns_completed == 2
    assert len(model_client.requests) == 2
    assert len(orchestrator.calls) == 1
    assert [call.id for call in orchestrator.calls[0]] == ["call-1"]
    assert [call.name for call in orchestrator.calls[0]] == ["lookup"]
    assert [call.arguments for call in orchestrator.calls[0]] == [{"q": "weather"}]
    assert result.messages[1].content == [
        ToolCallBlock(id="call-1", name="lookup", arguments={"q": "weather"})
    ]
    assert result.messages[2].role == "tool"
    assert result.messages[2].tool_call_id == "call-1"
    assert_tool_result_block(
        result.messages[2],
        tool_call_id="call-1",
        name="lookup",
        content="72F",
    )
    assert result.messages[-1].content == [TextBlock(text="it is sunny")]


def test_tool_failure_returns_error_shaped_tool_result_and_continues() -> None:
    from pyclaude.core.query_loop import run_query_loop

    model_client = FakeModelClient(
        streams=[
            [
                tool_call_event(
                    call_id="call-1",
                    name="lookup",
                    arguments={"q": "weather"},
                ),
                completed(
                    assistant_message(),
                    stop_reason="tool_use",
                ),
            ],
            [
                text_delta("lookup failed, "),
                text_delta("but I can explain that"),
                completed(
                    assistant_message(),
                ),
            ],
        ]
    )
    context = make_context(
        model_client=model_client,
        tool_orchestrator=FakeToolOrchestrator(
            results=[
                [
                    ToolResult(
                        tool_call_id="call-1",
                        tool_name="lookup",
                        content="tool exploded",
                        is_error=True,
                    )
                ]
            ]
        ),
    )
    request = QueryRequest(
        messages=[Message(role="user", content="weather?", timestamp=now())]
    )

    result = asyncio.run(run_query_loop(context=context, request=request))

    assert result.stop_reason == "completed"
    assert result.turns_completed == 2
    assert result.messages[2].role == "tool"
    assert result.messages[2].tool_call_id == "call-1"
    assert_tool_result_block(
        result.messages[2],
        tool_call_id="call-1",
        name="lookup",
        content="tool exploded",
        is_error=True,
    )
    assert result.messages[-1].content == [
        TextBlock(text="lookup failed, but I can explain that")
    ]


def test_multi_tool_turn_preserves_successful_results_around_failure() -> None:
    from pyclaude.core.query_loop import run_query_loop
    from pyclaude.tools.execution import AsyncToolExecutor
    from pyclaude.tools.orchestration import SerialToolOrchestrator

    async def lookup_tool(tool_call: ToolCall, context: RuntimeContext) -> ToolResult:
        del context
        if tool_call.id == "call-2":
            raise RuntimeError("lookup failed")
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=tool_call.arguments["q"],
        )

    model_client = FakeModelClient(
        streams=[
            [
                tool_call_event(
                    call_id="call-1",
                    name="lookup",
                    arguments={"q": "weather"},
                ),
                tool_call_event(
                    call_id="call-2",
                    name="lookup",
                    arguments={"q": "forecast"},
                ),
                tool_call_event(
                    call_id="call-3",
                    name="lookup",
                    arguments={"q": "alerts"},
                ),
                completed(
                    assistant_message(),
                    stop_reason="tool_use",
                ),
            ],
            [completed(assistant_message(TextBlock(text="processed tool results")))],
        ]
    )
    registry = ToolRegistry()
    registry.register("lookup", lookup_tool)
    context = RuntimeContext(
        cwd=Path.cwd(),
        config={},
        session_state=SessionState(
            session_id="session", conversation_id="conversation"
        ),
        tool_registry=registry,
        tool_orchestrator=SerialToolOrchestrator(AsyncToolExecutor(registry)),
        model_client=model_client,
    )
    request = QueryRequest(
        messages=[Message(role="user", content="weather?", timestamp=now())]
    )

    result = asyncio.run(run_query_loop(context=context, request=request))

    assert result.stop_reason == "completed"
    assert result.turns_completed == 2
    assert_tool_result_block(
        result.messages[2],
        tool_call_id="call-1",
        name="lookup",
        content="weather",
    )
    assert_tool_result_block(
        result.messages[3],
        tool_call_id="call-2",
        name="lookup",
        content="lookup failed",
        is_error=True,
    )
    assert_tool_result_block(
        result.messages[4],
        tool_call_id="call-3",
        name="lookup",
        content="alerts",
    )
    assert result.messages[-1].content == [TextBlock(text="processed tool results")]


def test_max_turns_stops_before_starting_a_new_model_cycle() -> None:
    from pyclaude.core.query_loop import run_query_loop

    model_client = FakeModelClient(
        streams=[
            [
                tool_call_event(
                    call_id="call-1",
                    name="lookup",
                    arguments={"q": "weather"},
                ),
                completed(
                    assistant_message(),
                    stop_reason="tool_use",
                ),
            ],
            [completed(assistant_message(TextBlock(text="should not happen")))],
        ]
    )
    orchestrator = FakeToolOrchestrator(
        results=[
            [
                ToolResult(
                    tool_call_id="call-1",
                    tool_name="lookup",
                    content="72F",
                )
            ]
        ]
    )
    context = make_context(model_client=model_client, tool_orchestrator=orchestrator)
    request = QueryRequest(
        messages=[Message(role="user", content="weather?", timestamp=now())],
        max_turns=1,
    )

    result = asyncio.run(run_query_loop(context=context, request=request))

    assert result.stop_reason == "max_turns"
    assert result.turns_completed == 1
    assert len(model_client.requests) == 1
    assert_tool_result_block(
        result.messages[2],
        tool_call_id="call-1",
        name="lookup",
        content="72F",
    )
