from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Protocol, runtime_checkable

from pyclaude.core import _refs


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    tool_name: str
    content: str | dict[str, Any]
    is_error: bool = False
    metadata: dict[str, Any] | None = None


@runtime_checkable
class ToolExecutor(Protocol):
    def execute(
        self,
        tool_call: ToolCall,
        context: _refs.RuntimeContext,
    ) -> Awaitable[ToolResult]: ...


@runtime_checkable
class ToolOrchestrator(Protocol):
    def run(
        self,
        calls: list[ToolCall],
        context: _refs.RuntimeContext,
    ) -> Awaitable[list[ToolResult]]: ...
