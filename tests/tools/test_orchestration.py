from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pyclaude.core.runtime import RuntimeContext, SessionState
from pyclaude.tools.base import ToolCall, ToolResult
from pyclaude.tools.execution import AsyncToolExecutor
from pyclaude.tools.orchestration import SerialToolOrchestrator
from pyclaude.tools.registry import ToolRegistry


class DummyModelClient:
    async def stream(self, request):
        if False:
            yield request


class DummyOrchestrator:
    async def run(self, calls, context):
        return []


def make_context() -> RuntimeContext:
    registry = ToolRegistry()
    return RuntimeContext(
        cwd=Path.cwd(),
        config={},
        session_state=SessionState(
            session_id="session", conversation_id="conversation"
        ),
        tool_registry=registry,
        tool_orchestrator=DummyOrchestrator(),
        model_client=DummyModelClient(),
    )


def test_registry_returns_registered_tool_by_name() -> None:
    async def registered_tool(
        tool_call: ToolCall, context: RuntimeContext
    ) -> ToolResult:
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=context.session_state.session_id,
        )

    registry = ToolRegistry()
    registry.register("lookup", registered_tool)

    assert registry.get("lookup") is registered_tool
    assert registry.get("missing") is None


def test_executor_awaits_registered_tool_result() -> None:
    observed: list[str] = []

    async def async_tool(tool_call: ToolCall, context: RuntimeContext) -> ToolResult:
        observed.append(f"start:{tool_call.id}")
        await asyncio.sleep(0)
        observed.append(f"finish:{tool_call.id}")
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content={"cwd": str(context.cwd)},
        )

    registry = ToolRegistry()
    registry.register("inspect", async_tool)
    executor = AsyncToolExecutor(registry)

    result = asyncio.run(
        executor.execute(
            ToolCall(id="call-1", name="inspect", arguments={}),
            make_context(),
        )
    )

    assert result == ToolResult(
        tool_call_id="call-1",
        tool_name="inspect",
        content={"cwd": str(Path.cwd())},
    )
    assert observed == ["start:call-1", "finish:call-1"]


def test_executor_raises_when_tool_is_not_registered() -> None:
    executor = AsyncToolExecutor(ToolRegistry())

    with pytest.raises(LookupError, match="missing"):
        asyncio.run(
            executor.execute(
                ToolCall(id="call-1", name="missing", arguments={}),
                make_context(),
            )
        )


def test_orchestrator_runs_multiple_calls_serially() -> None:
    events: list[str] = []

    async def tracked_tool(tool_call: ToolCall, context: RuntimeContext) -> ToolResult:
        events.append(f"start:{tool_call.id}")
        await asyncio.sleep(0)
        events.append(f"finish:{tool_call.id}")
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=tool_call.id,
        )

    registry = ToolRegistry()
    registry.register("tracked", tracked_tool)
    orchestrator = SerialToolOrchestrator(AsyncToolExecutor(registry))

    results = asyncio.run(
        orchestrator.run(
            [
                ToolCall(id="call-1", name="tracked", arguments={}),
                ToolCall(id="call-2", name="tracked", arguments={}),
            ],
            make_context(),
        )
    )

    assert results == [
        ToolResult(tool_call_id="call-1", tool_name="tracked", content="call-1"),
        ToolResult(tool_call_id="call-2", tool_name="tracked", content="call-2"),
    ]
    assert events == [
        "start:call-1",
        "finish:call-1",
        "start:call-2",
        "finish:call-2",
    ]


def test_orchestrator_returns_per_call_error_and_continues_after_failure() -> None:
    events: list[str] = []

    async def tracked_tool(tool_call: ToolCall, context: RuntimeContext) -> ToolResult:
        del context
        events.append(f"start:{tool_call.id}")
        await asyncio.sleep(0)
        if tool_call.id == "call-2":
            events.append(f"error:{tool_call.id}")
            raise RuntimeError("tool exploded")
        events.append(f"finish:{tool_call.id}")
        return ToolResult(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            content=tool_call.id,
        )

    registry = ToolRegistry()
    registry.register("tracked", tracked_tool)
    orchestrator = SerialToolOrchestrator(AsyncToolExecutor(registry))

    results = asyncio.run(
        orchestrator.run(
            [
                ToolCall(id="call-1", name="tracked", arguments={}),
                ToolCall(id="call-2", name="tracked", arguments={}),
                ToolCall(id="call-3", name="tracked", arguments={}),
            ],
            make_context(),
        )
    )

    assert results == [
        ToolResult(tool_call_id="call-1", tool_name="tracked", content="call-1"),
        ToolResult(
            tool_call_id="call-2",
            tool_name="tracked",
            content="tool exploded",
            is_error=True,
        ),
        ToolResult(tool_call_id="call-3", tool_name="tracked", content="call-3"),
    ]
    assert events == [
        "start:call-1",
        "finish:call-1",
        "start:call-2",
        "error:call-2",
        "start:call-3",
        "finish:call-3",
    ]
