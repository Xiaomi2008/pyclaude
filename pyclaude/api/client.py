from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from pyclaude.core.messages import AssistantEvent
from pyclaude.core.runtime import QueryRequest


@runtime_checkable
class ModelClient(Protocol):
    def stream(self, request: QueryRequest) -> AsyncIterator[AssistantEvent]: ...
