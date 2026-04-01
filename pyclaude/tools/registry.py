from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias

from pyclaude.core import _refs
from pyclaude.tools.base import ToolCall, ToolResult

ToolImplementation: TypeAlias = Callable[
    [ToolCall, _refs.RuntimeContext],
    ToolResult | Awaitable[ToolResult],
]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolImplementation] = {}

    def register(self, name: str, tool: ToolImplementation) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> ToolImplementation | None:
        return self._tools.get(name)
