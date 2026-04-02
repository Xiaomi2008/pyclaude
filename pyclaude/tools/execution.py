from __future__ import annotations

from inspect import isawaitable

from pyclaude.core import _refs
from pyclaude.tools.base import ToolCall, ToolResult
from pyclaude.tools.registry import ToolRegistry


class AsyncToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def execute(
        self,
        tool_call: ToolCall,
        context: _refs.RuntimeContext,
    ) -> ToolResult:
        tool = self._registry.get(tool_call.name)
        if tool is None:
            raise LookupError(f"tool is not registered: {tool_call.name}")

        result = tool(tool_call, context)
        if isawaitable(result):
            return await result
        return result
