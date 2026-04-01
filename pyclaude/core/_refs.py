from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyclaude.api.client import ModelClient
    from pyclaude.core.messages import AssistantEvent
    from pyclaude.core.runtime import RuntimeContext, Usage
    from pyclaude.tools.base import ToolCall, ToolExecutor, ToolOrchestrator
    from pyclaude.tools.registry import ToolRegistry


def __getattr__(name: str):
    if name == "AssistantEvent":
        from pyclaude.core.messages import AssistantEvent

        return AssistantEvent
    if name == "ModelClient":
        from pyclaude.api.client import ModelClient

        return ModelClient
    if name == "RuntimeContext":
        from pyclaude.core.runtime import RuntimeContext

        return RuntimeContext
    if name == "ToolCall":
        from pyclaude.tools.base import ToolCall

        return ToolCall
    if name == "ToolExecutor":
        from pyclaude.tools.base import ToolExecutor

        return ToolExecutor
    if name == "ToolRegistry":
        from pyclaude.tools.registry import ToolRegistry

        return ToolRegistry
    if name == "ToolOrchestrator":
        from pyclaude.tools.base import ToolOrchestrator

        return ToolOrchestrator
    if name == "Usage":
        from pyclaude.core.runtime import Usage

        return Usage
    raise AttributeError(name)
