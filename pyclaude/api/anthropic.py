from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, AsyncIterator, Callable, Mapping
from urllib import error as urllib_error
from urllib import request as urllib_request

from pyclaude.api.errors import APIError, APIResponseError, APITransportError
from pyclaude.api.retries import RetryPolicy, next_retry_delay, should_retry
from pyclaude.api.usage import normalize_usage
from pyclaude.core.messages import (
    AssistantEvent,
    ErrorEvent,
    Message,
    MessageCompleteEvent,
    TextBlock,
    TextDeltaEvent,
    ToolCallBlock,
    ToolCallEvent,
)
from pyclaude.core.runtime import QueryRequest, Usage
from pyclaude.tools.base import ToolCall


ProviderStream = Callable[[QueryRequest], AsyncIterator[Mapping[str, Any]]]

DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TIMEOUT_SECONDS = 30.0

_urlopen = urllib_request.urlopen
_sleep = asyncio.sleep


@dataclass
class _TextState:
    text: str = ""


@dataclass
class _ToolUseState:
    id: str
    name: str
    partial_json: str = ""


@dataclass
class _StreamState:
    role: str = "assistant"
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=0, output_tokens=0))
    blocks: dict[int, _TextState | _ToolUseState] = field(default_factory=dict)
    completed_blocks: dict[int, TextBlock | ToolCallBlock] = field(default_factory=dict)
    stop_reason: str = "completed"


class AnthropicModelClient:
    def __init__(self, *, provider_stream: ProviderStream) -> None:
        self._provider_stream = provider_stream

    async def stream(self, request: QueryRequest) -> AsyncIterator[AssistantEvent]:
        state = _StreamState()

        async for chunk in self._provider_stream(request):
            chunk_type = chunk.get("type")

            if chunk_type == "message_start":
                message = _mapping(chunk.get("message"))
                state.role = str(message.get("role", "assistant"))
                state.usage = _update_usage(state.usage, _mapping(message.get("usage")))
                continue

            if chunk_type == "content_block_start":
                _start_block(state, chunk)
                continue

            if chunk_type == "content_block_delta":
                event = _apply_delta(state, chunk)
                if event is not None:
                    yield event
                continue

            if chunk_type == "content_block_stop":
                event = _stop_block(state, chunk)
                if event is not None:
                    yield event
                continue

            if chunk_type == "message_delta":
                state.stop_reason = _normalize_stop_reason(
                    _mapping(chunk.get("delta")).get("stop_reason")
                )
                state.usage = _update_usage(state.usage, _mapping(chunk.get("usage")))
                continue

            if chunk_type == "error":
                yield ErrorEvent(error=_error_message(chunk), raw=chunk)
                return

            if chunk_type == "message_stop":
                yield MessageCompleteEvent(
                    message=Message(
                        role=state.role,
                        content=[
                            state.completed_blocks[index]
                            for index in sorted(state.completed_blocks)
                        ],
                        timestamp=datetime.now(UTC),
                    ),
                    stop_reason=state.stop_reason,
                    usage=state.usage,
                    raw=chunk,
                )
                return

        yield ErrorEvent(
            error="provider stream ended without terminal message_stop",
        )


def build_provider_stream(
    *,
    api_key: str,
    model: str,
    base_url: str | None = None,
    temperature: float | None = None,
    retry_policy: RetryPolicy | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> ProviderStream:
    async def provider_stream(
        request: QueryRequest,
    ) -> AsyncIterator[Mapping[str, Any]]:
        payload = _build_payload(
            request,
            default_model=model,
            default_temperature=temperature,
        )

        try:
            chunks = await _request_with_retries(
                api_key=api_key,
                base_url=base_url or DEFAULT_ANTHROPIC_BASE_URL,
                payload=payload,
                retry_policy=retry_policy or RetryPolicy(),
                timeout_seconds=timeout_seconds,
            )
        except APIError as exc:
            yield {
                "type": "error",
                "error": {"message": str(exc)},
            }
            return

        for chunk in chunks:
            yield chunk

    return provider_stream


async def _request_with_retries(
    *,
    api_key: str,
    base_url: str,
    payload: Mapping[str, Any],
    retry_policy: RetryPolicy,
    timeout_seconds: float,
) -> list[Mapping[str, Any]]:
    attempt = 1

    while True:
        try:
            return await asyncio.to_thread(
                _execute_request,
                api_key=api_key,
                base_url=base_url,
                payload=payload,
                timeout_seconds=timeout_seconds,
            )
        except APIError as exc:
            if not should_retry(exc, attempt=attempt, policy=retry_policy):
                raise
            await _sleep(next_retry_delay(attempt=attempt, policy=retry_policy))
            attempt += 1


def _execute_request(
    *,
    api_key: str,
    base_url: str,
    payload: Mapping[str, Any],
    timeout_seconds: float,
) -> list[Mapping[str, Any]]:
    request = urllib_request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "accept": "text/event-stream",
            "x-api-key": api_key,
            "anthropic-version": DEFAULT_ANTHROPIC_VERSION,
        },
    )

    try:
        with _urlopen(request, timeout=timeout_seconds) as response:
            return _parse_event_stream(response)
    except APIError:
        raise
    except urllib_error.HTTPError as exc:
        raise _classify_http_error(exc) from exc
    except (urllib_error.URLError, OSError, TimeoutError) as exc:
        raise APITransportError(f"Anthropic transport error: {exc}") from exc


def _build_payload(
    request: QueryRequest,
    *,
    default_model: str,
    default_temperature: float | None,
) -> dict[str, Any]:
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []

    for message in request.messages:
        if message.role == "system":
            system_text = _system_text(message)
            if system_text:
                system_parts.append(system_text)
            continue

        role = "user" if message.role == "tool" else message.role
        messages.append({"role": role, "content": _serialize_message_content(message)})

    payload: dict[str, Any] = {
        "model": request.model or default_model,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "stream": True,
        "messages": messages,
    }

    temperature = (
        request.temperature if request.temperature is not None else default_temperature
    )
    if temperature is not None:
        payload["temperature"] = temperature
    if system_parts:
        payload["system"] = "\n\n".join(system_parts)
    return payload


def _serialize_message_content(message: Message) -> list[dict[str, Any]]:
    if isinstance(message.content, str):
        return [{"type": "text", "text": message.content}]

    blocks: list[dict[str, Any]] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            blocks.append({"type": "text", "text": block.text})
        elif getattr(block, "type", None) == "tool_call":
            blocks.append(
                {
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.arguments,
                }
            )
        elif getattr(block, "type", None) == "tool_result":
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.tool_call_id,
                    "content": _tool_result_content(block.content),
                    "is_error": block.is_error,
                }
            )
    return blocks


def _tool_result_content(content: str | dict[str, Any]) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, sort_keys=True)


def _system_text(message: Message) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    )


def _parse_event_stream(response: Any) -> list[Mapping[str, Any]]:
    chunks: list[Mapping[str, Any]] = []
    data_lines: list[str] = []

    while True:
        raw_line = response.readline()
        if raw_line == b"":
            break

        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line == "":
            chunk = _parse_sse_data(data_lines)
            if chunk is not None:
                chunks.append(chunk)
            data_lines.clear()
            continue

        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    chunk = _parse_sse_data(data_lines)
    if chunk is not None:
        chunks.append(chunk)
    return chunks


def _parse_sse_data(data_lines: list[str]) -> Mapping[str, Any] | None:
    if not data_lines:
        return None

    payload = "\n".join(data_lines)
    if payload == "[DONE]":
        return None

    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise APITransportError(
            "Anthropic transport returned invalid JSON event"
        ) from exc

    if not isinstance(decoded, Mapping):
        raise APITransportError("Anthropic transport returned non-object event")
    return decoded


def _classify_http_error(exc: urllib_error.HTTPError) -> APIResponseError:
    body = _read_http_error_body(exc)
    message = (
        _extract_error_message(body) or exc.reason or "Anthropic API request failed"
    )

    if exc.code in {401, 403}:
        return APIResponseError(
            f"Anthropic authentication failed ({exc.code}): {message}",
            status_code=exc.code,
            body=body,
        )

    return APIResponseError(
        f"Anthropic API request failed ({exc.code}): {message}",
        status_code=exc.code,
        body=body,
    )


def _read_http_error_body(exc: urllib_error.HTTPError) -> object | None:
    if exc.fp is None:
        return None

    try:
        payload = exc.read()
    except OSError:
        return None

    if not payload:
        return None

    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return payload.decode("utf-8", errors="replace")


def _extract_error_message(body: object | None) -> str | None:
    if isinstance(body, Mapping):
        error = body.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message

        message = body.get("message")
        if isinstance(message, str) and message:
            return message

    if isinstance(body, str) and body:
        return body

    return None


def _start_block(state: _StreamState, chunk: Mapping[str, Any]) -> None:
    index = _require_index(chunk)
    block = _mapping(chunk.get("content_block"))
    block_type = block.get("type")

    if block_type == "text":
        state.blocks[index] = _TextState()
        return

    if block_type == "tool_use":
        state.blocks[index] = _ToolUseState(
            id=str(block["id"]),
            name=str(block["name"]),
        )


def _apply_delta(
    state: _StreamState, chunk: Mapping[str, Any]
) -> TextDeltaEvent | None:
    index = _require_index(chunk)
    block = state.blocks.get(index)
    delta = _mapping(chunk.get("delta"))
    delta_type = delta.get("type")

    if isinstance(block, _TextState) and delta_type == "text_delta":
        text = str(delta.get("text", ""))
        block.text += text
        return TextDeltaEvent(text=text, raw=chunk)

    if isinstance(block, _ToolUseState) and delta_type == "input_json_delta":
        block.partial_json += str(delta.get("partial_json", ""))

    return None


def _stop_block(state: _StreamState, chunk: Mapping[str, Any]) -> ToolCallEvent | None:
    index = _require_index(chunk)
    block = state.blocks.get(index)

    if isinstance(block, _TextState):
        state.completed_blocks[index] = TextBlock(text=block.text)
        return None

    if isinstance(block, _ToolUseState):
        arguments = _parse_tool_arguments(block.partial_json)
        tool_call = ToolCall(id=block.id, name=block.name, arguments=arguments)
        state.completed_blocks[index] = ToolCallBlock(
            id=block.id,
            name=block.name,
            arguments=arguments,
        )
        return ToolCallEvent(tool_call=tool_call, raw=chunk)

    return None


def _parse_tool_arguments(partial_json: str) -> dict[str, Any]:
    if partial_json == "":
        return {}
    parsed = json.loads(partial_json)
    if not isinstance(parsed, dict):
        raise ValueError("tool_use input must decode to an object")
    return parsed


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _require_index(chunk: Mapping[str, Any]) -> int:
    index = chunk.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        raise ValueError("provider chunk index must be an integer")
    return index


def _normalize_stop_reason(value: Any) -> str:
    if value == "tool_use":
        return "tool_calls"
    if value == "max_tokens":
        return "max_tokens"
    if value in {None, "end_turn", "stop_sequence"}:
        return "completed"
    return str(value)


def _error_message(chunk: Mapping[str, Any]) -> str:
    payload = _mapping(chunk.get("error"))
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    return "Anthropic provider error"


def _update_usage(current: Usage, payload: Mapping[str, Any]) -> Usage:
    if not payload:
        return current

    normalized = normalize_usage(payload)
    return Usage(
        input_tokens=(
            normalized.input_tokens
            if _has_any_key(payload, "input_tokens", "prompt_tokens")
            else current.input_tokens
        ),
        output_tokens=(
            normalized.output_tokens
            if _has_any_key(payload, "output_tokens", "completion_tokens")
            else current.output_tokens
        ),
        cache_read_tokens=(
            normalized.cache_read_tokens
            if _has_any_key(payload, "cache_read_tokens", "cache_read_input_tokens")
            else current.cache_read_tokens
        ),
        cache_write_tokens=(
            normalized.cache_write_tokens
            if _has_any_key(
                payload, "cache_write_tokens", "cache_creation_input_tokens"
            )
            else current.cache_write_tokens
        ),
    )


def _has_any_key(payload: Mapping[str, Any], *names: str) -> bool:
    return any(name in payload for name in names)
