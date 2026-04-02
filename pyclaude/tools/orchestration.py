from __future__ import annotations

from pyclaude.core import _refs
from pyclaude.tools.base import ToolCall, ToolResult


class SerialToolOrchestrator:
    def __init__(self, executor: _refs.ToolExecutor) -> None:
        self._executor = executor

    async def run(
        self,
        calls: list[ToolCall],
        context: _refs.RuntimeContext,
    ) -> list[ToolResult]:
        results: list[ToolResult] = []
        for call in calls:
            try:
                results.append(await self._executor.execute(call, context))
            except Exception as exc:
                results.append(
                    ToolResult(
                        tool_call_id=call.id,
                        tool_name=call.name,
                        content=str(exc),
                        is_error=True,
                    )
                )
        return results
