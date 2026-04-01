from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeAlias

from pyclaude.core import _refs

MessageRole: TypeAlias = Literal["system", "user", "assistant", "tool"]


@dataclass(kw_only=True)
class TextBlock:
    type: Literal["text"] = "text"
    text: str


@dataclass(kw_only=True)
class ToolCallBlock:
    type: Literal["tool_call"] = "tool_call"
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(kw_only=True)
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_call_id: str
    name: str
    content: str | dict[str, Any]
    is_error: bool = False


ContentBlock: TypeAlias = TextBlock | ToolCallBlock | ToolResultBlock


@dataclass
class Message:
    role: MessageRole
    content: str | list[ContentBlock]
    timestamp: datetime
    tool_call_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(kw_only=True)
class TextDeltaEvent:
    type: Literal["text_delta"] = "text_delta"
    text: str
    raw: Any | None = None


@dataclass(kw_only=True)
class ToolCallEvent:
    type: Literal["tool_call"] = "tool_call"
    tool_call: _refs.ToolCall
    raw: Any | None = None


@dataclass(kw_only=True)
class MessageCompleteEvent:
    type: Literal["message_complete"] = "message_complete"
    message: Message
    stop_reason: str
    usage: _refs.Usage
    raw: Any | None = None


@dataclass(kw_only=True)
class ErrorEvent:
    type: Literal["error"] = "error"
    error: Exception | str
    raw: Any | None = None


AssistantEvent: TypeAlias = (
    TextDeltaEvent | ToolCallEvent | MessageCompleteEvent | ErrorEvent
)
