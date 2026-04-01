from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from pyclaude.core import query_loop
from pyclaude.core.messages import Message
from pyclaude.core.runtime import QueryRequest, QueryResult, RuntimeContext


class QueryEngine:
    def __init__(
        self,
        *,
        context: RuntimeContext,
        system_instructions: str | Message | None = None,
    ) -> None:
        self.context = context
        self.messages: list[Message] = []
        self._submit_lock = asyncio.Lock()
        if system_instructions is not None:
            self.messages.append(_normalize_system_message(system_instructions))

    async def submit(
        self,
        prompt: str | Message | list[Message],
        *,
        max_turns: int | None = None,
        model: str | None = None,
        temperature: float | None = None,
        tool_choice: None | str = None,
    ) -> QueryResult:
        async with self._submit_lock:
            request = QueryRequest(
                messages=[*self.messages, *_normalize_prompt(prompt)],
                max_turns=max_turns,
                model=model,
                temperature=temperature,
                tool_choice=tool_choice,
            )
            result = await query_loop.run_query_loop(
                context=self.context, request=request
            )
            self.messages = list(result.messages)
            return result


def _normalize_prompt(prompt: str | Message | list[Message]) -> list[Message]:
    if isinstance(prompt, str):
        return [Message(role="user", content=prompt, timestamp=_now())]
    if isinstance(prompt, Message):
        return [prompt]
    if isinstance(prompt, list) and all(
        isinstance(message, Message) for message in prompt
    ):
        return list(prompt)
    raise TypeError("prompt must be a string, Message, or list[Message]")


def _normalize_system_message(system_instructions: str | Message) -> Message:
    if isinstance(system_instructions, str):
        return Message(
            role="system",
            content=system_instructions,
            timestamp=_now(),
        )
    if isinstance(system_instructions, Message):
        return Message(
            role="system",
            content=system_instructions.content,
            timestamp=system_instructions.timestamp,
            metadata=system_instructions.metadata,
        )
    raise TypeError("system_instructions must be a string or Message")


def _now() -> datetime:
    return datetime.now(UTC)
