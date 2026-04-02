from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pyclaude.core import _refs
from pyclaude.core.messages import Message


@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class SessionState:
    session_id: str
    conversation_id: str
    turn_count: int = 0


@dataclass
class QueryRequest:
    messages: list[Message]
    max_turns: int | None = None
    model: str | None = None
    temperature: float | None = None
    tool_choice: None | Literal["auto", "none"] | str = None


@dataclass
class QueryResult:
    messages: list[Message]
    usage: Usage
    stop_reason: str
    turns_completed: int


@runtime_checkable
class EventSink(Protocol):
    def __call__(self, event: _refs.AssistantEvent) -> None: ...


@dataclass(kw_only=True)
class RuntimeContext:
    cwd: Path
    config: dict[str, Any]
    session_state: SessionState
    tool_registry: _refs.ToolRegistry
    tool_orchestrator: _refs.ToolOrchestrator
    model_client: _refs.ModelClient
    event_sink: EventSink | None = None
