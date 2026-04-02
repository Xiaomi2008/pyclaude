from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
import sys
from typing import (
    Any,
    Literal,
    Protocol,
    get_args,
    get_origin,
    get_type_hints,
    runtime_checkable,
)

import pytest


MODULE_ORDERS = [
    [
        "pyclaude.core.messages",
        "pyclaude.core.runtime",
        "pyclaude.tools.base",
        "pyclaude.api.client",
    ],
    [
        "pyclaude.tools.base",
        "pyclaude.core.runtime",
        "pyclaude.api.client",
        "pyclaude.core.messages",
    ],
    [
        "pyclaude.api.client",
        "pyclaude.core.messages",
        "pyclaude.tools.base",
        "pyclaude.core.runtime",
    ],
]


def load_module(name: str):
    try:
        return import_module(name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"expected module {name} to exist: {exc}")


def clear_contract_modules() -> None:
    for name in list(sys.modules):
        if name.startswith("pyclaude."):
            sys.modules.pop(name, None)


def snapshot_contract_modules() -> dict[str, object]:
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "pyclaude" or name.startswith("pyclaude.")
    }


def restore_contract_modules(snapshot: dict[str, object]) -> None:
    for name in list(sys.modules):
        if name == "pyclaude" or name.startswith("pyclaude."):
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)

    for name in sorted(snapshot, key=lambda module_name: module_name.count(".")):
        if "." not in name:
            continue
        parent_name, child_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        child = sys.modules.get(name)
        if parent is not None and child is not None:
            setattr(parent, child_name, child)


def exercise_contract_import_orders() -> None:
    snapshot = snapshot_contract_modules()

    try:
        for order in MODULE_ORDERS:
            clear_contract_modules()
            imported = [import_module(name) for name in order]
            assert [module.__name__ for module in imported] == order
    finally:
        restore_contract_modules(snapshot)


def assert_dataclass_fields(
    cls: type[Any],
    expected: dict[str, Any],
) -> None:
    assert is_dataclass(cls)
    hints = get_type_hints(cls, include_extras=True)
    actual = {field.name: hints[field.name] for field in fields(cls)}
    assert actual == expected


def test_message_contracts_are_defined() -> None:
    module = load_module("pyclaude.core.messages")
    runtime_module = load_module("pyclaude.core.runtime")
    tools_module = load_module("pyclaude.tools.base")

    Message = module.Message
    TextBlock = module.TextBlock
    ToolCallBlock = module.ToolCallBlock
    ToolResultBlock = module.ToolResultBlock
    TextDeltaEvent = module.TextDeltaEvent
    ToolCallEvent = module.ToolCallEvent
    MessageCompleteEvent = module.MessageCompleteEvent
    ErrorEvent = module.ErrorEvent

    assert get_args(module.MessageRole) == ("system", "user", "assistant", "tool")

    assert_dataclass_fields(
        TextBlock,
        {"type": Literal["text"], "text": str},
    )
    assert_dataclass_fields(
        ToolCallBlock,
        {
            "type": Literal["tool_call"],
            "id": str,
            "name": str,
            "arguments": dict[str, Any],
        },
    )
    assert_dataclass_fields(
        ToolResultBlock,
        {
            "type": Literal["tool_result"],
            "tool_call_id": str,
            "name": str,
            "content": str | dict[str, Any],
            "is_error": bool,
        },
    )
    assert_dataclass_fields(
        Message,
        {
            "role": module.MessageRole,
            "content": str | list[module.ContentBlock],
            "timestamp": datetime,
            "tool_call_id": str | None,
            "metadata": dict[str, Any] | None,
        },
    )
    assert_dataclass_fields(
        TextDeltaEvent,
        {"type": Literal["text_delta"], "text": str, "raw": Any | None},
    )
    assert_dataclass_fields(
        ToolCallEvent,
        {
            "type": Literal["tool_call"],
            "tool_call": tools_module.ToolCall,
            "raw": Any | None,
        },
    )
    assert_dataclass_fields(
        MessageCompleteEvent,
        {
            "type": Literal["message_complete"],
            "message": Message,
            "stop_reason": str,
            "usage": runtime_module.Usage,
            "raw": Any | None,
        },
    )
    assert_dataclass_fields(
        ErrorEvent,
        {"type": Literal["error"], "error": Exception | str, "raw": Any | None},
    )

    message = Message(
        role="assistant",
        content=[TextBlock(text="hello")],
        timestamp=datetime.now(UTC),
    )
    assert message.tool_call_id is None
    assert message.metadata is None

    tool_result = tools_module.ToolResult(
        tool_call_id="call-1",
        tool_name="ls",
        content="done",
    )
    assert tool_result.is_error is False
    assert tool_result.metadata is None

    usage = runtime_module.Usage(input_tokens=1, output_tokens=2)
    assert usage.cache_read_tokens == 0
    assert usage.cache_write_tokens == 0

    event_args = get_args(module.AssistantEvent)
    assert event_args == (
        TextDeltaEvent,
        ToolCallEvent,
        MessageCompleteEvent,
        ErrorEvent,
    )


def test_contract_modules_import_cleanly_in_any_order() -> None:
    exercise_contract_import_orders()


def test_contract_import_order_probe_restores_previously_loaded_modules() -> None:
    original_messages = import_module("pyclaude.core.messages")
    original_runtime = import_module("pyclaude.core.runtime")
    original_tools = import_module("pyclaude.tools.base")
    original_client = import_module("pyclaude.api.client")

    exercise_contract_import_orders()

    assert import_module("pyclaude.core.messages") is original_messages
    assert import_module("pyclaude.core.runtime") is original_runtime
    assert import_module("pyclaude.tools.base") is original_tools
    assert import_module("pyclaude.api.client") is original_client


def test_runtime_contracts_are_defined() -> None:
    messages_module = load_module("pyclaude.core.messages")
    runtime_module = load_module("pyclaude.core.runtime")
    tools_module = load_module("pyclaude.tools.base")
    registry_module = load_module("pyclaude.tools.registry")
    client_module = load_module("pyclaude.api.client")

    assert not hasattr(messages_module, "Usage")

    assert_dataclass_fields(
        runtime_module.SessionState,
        {
            "session_id": str,
            "conversation_id": str,
            "turn_count": int,
        },
    )
    assert_dataclass_fields(
        runtime_module.QueryRequest,
        {
            "messages": list[messages_module.Message],
            "max_turns": int | None,
            "model": str | None,
            "temperature": float | None,
            "tool_choice": None | Literal["auto", "none"] | str,
        },
    )
    assert_dataclass_fields(
        runtime_module.QueryResult,
        {
            "messages": list[messages_module.Message],
            "usage": runtime_module.Usage,
            "stop_reason": str,
            "turns_completed": int,
        },
    )
    assert_dataclass_fields(
        runtime_module.Usage,
        {
            "input_tokens": int,
            "output_tokens": int,
            "cache_read_tokens": int,
            "cache_write_tokens": int,
        },
    )
    assert_dataclass_fields(
        runtime_module.RuntimeContext,
        {
            "cwd": Path,
            "config": dict[str, Any],
            "session_state": runtime_module.SessionState,
            "tool_registry": registry_module.ToolRegistry,
            "tool_orchestrator": tools_module.ToolOrchestrator,
            "model_client": client_module.ModelClient,
            "event_sink": runtime_module.EventSink | None,
        },
    )

    request = runtime_module.QueryRequest(messages=[])
    assert request.max_turns is None
    assert request.model is None
    assert request.temperature is None
    assert request.tool_choice is None

    session = runtime_module.SessionState(session_id="s1", conversation_id="c1")
    assert session.turn_count == 0


def test_protocol_contracts_are_defined() -> None:
    messages_module = load_module("pyclaude.core.messages")
    runtime_module = load_module("pyclaude.core.runtime")
    client_module = load_module("pyclaude.api.client")
    tools_module = load_module("pyclaude.tools.base")

    assert not hasattr(messages_module, "ToolCall")
    assert not hasattr(messages_module, "ToolResult")

    assert_dataclass_fields(
        tools_module.ToolCall,
        {"id": str, "name": str, "arguments": dict[str, Any]},
    )
    assert_dataclass_fields(
        tools_module.ToolResult,
        {
            "tool_call_id": str,
            "tool_name": str,
            "content": str | dict[str, Any],
            "is_error": bool,
            "metadata": dict[str, Any] | None,
        },
    )

    assert issubclass(client_module.ModelClient, Protocol)
    assert issubclass(runtime_module.EventSink, Protocol)
    assert issubclass(tools_module.ToolExecutor, Protocol)
    assert issubclass(tools_module.ToolOrchestrator, Protocol)

    sink_hints = get_type_hints(runtime_module.EventSink.__call__)

    stream_hints = get_type_hints(client_module.ModelClient.stream)
    execute_hints = get_type_hints(tools_module.ToolExecutor.execute)
    run_hints = get_type_hints(tools_module.ToolOrchestrator.run)

    assert stream_hints == {
        "request": runtime_module.QueryRequest,
        "return": client_module.AsyncIterator[messages_module.AssistantEvent],
    }
    assert sink_hints == {
        "event": messages_module.AssistantEvent,
        "return": type(None),
    }
    assert execute_hints == {
        "tool_call": tools_module.ToolCall,
        "context": runtime_module.RuntimeContext,
        "return": tools_module.Awaitable[tools_module.ToolResult],
    }
    assert run_hints == {
        "calls": list[tools_module.ToolCall],
        "context": runtime_module.RuntimeContext,
        "return": tools_module.Awaitable[list[tools_module.ToolResult]],
    }

    @runtime_checkable
    class EventSink(Protocol):
        def __call__(self, event: messages_module.AssistantEvent) -> None: ...

    class DummyClient:
        async def stream(self, request: runtime_module.QueryRequest):
            if False:
                yield messages_module.TextDeltaEvent(text="unused")

    class DummyExecutor:
        async def execute(
            self,
            tool_call: tools_module.ToolCall,
            context: runtime_module.RuntimeContext,
        ) -> tools_module.ToolResult:
            return tools_module.ToolResult(
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
                content="ok",
            )

    class DummyOrchestrator:
        async def run(
            self,
            calls: list[tools_module.ToolCall],
            context: runtime_module.RuntimeContext,
        ) -> list[tools_module.ToolResult]:
            return [
                tools_module.ToolResult(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    content="ok",
                )
                for call in calls
            ]

    assert isinstance(DummyClient(), client_module.ModelClient)
    assert isinstance(DummyExecutor(), tools_module.ToolExecutor)
    assert isinstance(DummyOrchestrator(), tools_module.ToolOrchestrator)
    assert isinstance(lambda event: None, EventSink)
