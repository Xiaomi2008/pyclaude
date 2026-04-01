from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from pyclaude.api.anthropic import AnthropicModelClient, build_provider_stream
from pyclaude.core.runtime import RuntimeContext
from pyclaude.state.config import ResolvedConfig
from pyclaude.state.persistence import InMemorySessionStore
from pyclaude.state.session import create_session_state
from pyclaude.tools.execution import AsyncToolExecutor
from pyclaude.tools.orchestration import SerialToolOrchestrator
from pyclaude.tools.registry import ToolRegistry


def build_runtime_context(*, config: ResolvedConfig, cwd: Path) -> RuntimeContext:
    tool_registry = ToolRegistry()
    tool_executor = AsyncToolExecutor(tool_registry)
    tool_orchestrator = SerialToolOrchestrator(tool_executor)
    session_store = InMemorySessionStore()

    return RuntimeContext(
        cwd=cwd,
        config=asdict(config),
        session_state=create_session_state(store=session_store),
        tool_registry=tool_registry,
        tool_orchestrator=tool_orchestrator,
        model_client=AnthropicModelClient(
            provider_stream=_build_provider_stream(config=config)
        ),
    )


def _build_provider_stream(*, config: ResolvedConfig):
    return build_provider_stream(
        api_key=config.api_key,
        model=config.model,
        base_url=config.base_url,
        temperature=config.temperature,
    )
