from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from pyclaude.core.messages import (
    Message,
    MessageCompleteEvent,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from pyclaude.core.runtime import QueryRequest, QueryResult, RuntimeContext, Usage
from pyclaude.tools.base import ToolCall, ToolResult


async def run_query_loop(
    *, context: RuntimeContext, request: QueryRequest
) -> QueryResult:
    messages = list(request.messages)
    usage = Usage(input_tokens=0, output_tokens=0)
    turns_completed = 0

    while True:
        if request.max_turns is not None and turns_completed >= request.max_turns:
            return QueryResult(
                messages=messages,
                usage=usage,
                stop_reason="max_turns",
                turns_completed=turns_completed,
            )

        complete_event = await _collect_cycle(
            context=context, request=replace(request, messages=messages)
        )
        messages.append(complete_event.message)
        usage = _merge_usage(usage, complete_event.usage)
        turns_completed += 1
        context.session_state.turn_count += 1

        tool_calls = _tool_calls_from_message(complete_event.message)
        if not tool_calls:
            return QueryResult(
                messages=messages,
                usage=usage,
                stop_reason=complete_event.stop_reason,
                turns_completed=turns_completed,
            )

        tool_results = await _run_tools(context=context, calls=tool_calls)
        for result in tool_results:
            messages.append(_tool_result_message(result))


async def _collect_cycle(
    *, context: RuntimeContext, request: QueryRequest
) -> MessageCompleteEvent:
    complete_event: MessageCompleteEvent | None = None
    content_blocks: list[TextBlock | ToolCallBlock] = []
    pending_text: list[str] = []

    async for event in context.model_client.stream(request):
        if context.event_sink is not None:
            context.event_sink(event)
        if getattr(event, "type", None) == "error":
            raise RuntimeError(str(event.error))
        if getattr(event, "type", None) == "text_delta":
            pending_text.append(event.text)
            continue
        if getattr(event, "type", None) == "tool_call":
            _flush_text_block(content_blocks, pending_text)
            content_blocks.append(
                ToolCallBlock(
                    id=event.tool_call.id,
                    name=event.tool_call.name,
                    arguments=event.tool_call.arguments,
                )
            )
            continue
        if getattr(event, "type", None) == "message_complete":
            complete_event = event

    if complete_event is None:
        raise RuntimeError("model stream ended without message_complete")

    _flush_text_block(content_blocks, pending_text)
    if content_blocks:
        complete_event = replace(
            complete_event,
            message=replace(complete_event.message, content=content_blocks),
        )

    return complete_event


def _tool_calls_from_message(message: Message) -> list[ToolCall]:
    if not isinstance(message.content, list):
        return []

    calls: list[ToolCall] = []
    for block in message.content:
        if getattr(block, "type", None) == "tool_call":
            calls.append(
                ToolCall(id=block.id, name=block.name, arguments=block.arguments)
            )
    return calls


async def _run_tools(
    *, context: RuntimeContext, calls: list[ToolCall]
) -> list[ToolResult]:
    return await context.tool_orchestrator.run(calls, context)


def _tool_result_message(result: ToolResult) -> Message:
    return Message(
        role="tool",
        content=[
            ToolResultBlock(
                tool_call_id=result.tool_call_id,
                name=result.tool_name,
                content=result.content,
                is_error=result.is_error,
            )
        ],
        timestamp=datetime.now(UTC),
        tool_call_id=result.tool_call_id,
        metadata=result.metadata,
    )


def _merge_usage(left: Usage, right: Usage) -> Usage:
    return Usage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cache_read_tokens=left.cache_read_tokens + right.cache_read_tokens,
        cache_write_tokens=left.cache_write_tokens + right.cache_write_tokens,
    )


def _flush_text_block(
    content_blocks: list[TextBlock | ToolCallBlock], pending_text: list[str]
) -> None:
    if not pending_text:
        return
    content_blocks.append(TextBlock(text="".join(pending_text)))
    pending_text.clear()
