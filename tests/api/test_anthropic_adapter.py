from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncIterator, get_type_hints

from pyclaude.api.errors import APITransportError
from pyclaude.api.client import ModelClient
from pyclaude.core.messages import (
    AssistantEvent,
    ErrorEvent,
    MessageCompleteEvent,
    TextDeltaEvent,
    ToolCallEvent,
)
from pyclaude.core.runtime import QueryRequest, Usage
from pyclaude.state.config import ResolvedConfig


def now() -> datetime:
    return datetime.now(UTC)


async def collect_events(stream) -> list[Any]:
    return [event async for event in stream]


def make_request() -> QueryRequest:
    from pyclaude.core.messages import Message

    return QueryRequest(
        messages=[Message(role="user", content="hi", timestamp=now())],
        model="claude-test",
    )


def test_adapter_satisfies_model_client_protocol() -> None:
    from pyclaude.api.anthropic import AnthropicModelClient

    async def provider_stream(request: QueryRequest):
        if False:
            yield request

    adapter = AnthropicModelClient(provider_stream=provider_stream)

    assert isinstance(adapter, ModelClient)


def test_adapter_stream_uses_model_client_return_annotation_shape() -> None:
    from pyclaude.api.anthropic import AnthropicModelClient

    assert get_type_hints(AnthropicModelClient.stream) == {
        "request": QueryRequest,
        "return": AsyncIterator[AssistantEvent],
    }


def test_adapter_normalizes_text_and_tool_stream_into_phase_1_events() -> None:
    from pyclaude.api.anthropic import AnthropicModelClient

    seen_requests: list[QueryRequest] = []

    async def provider_stream(request: QueryRequest):
        seen_requests.append(request)
        yield {
            "type": "message_start",
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 10, "output_tokens": 0},
            },
        }
        yield {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }
        yield {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "hello "},
        }
        yield {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "world"},
        }
        yield {"type": "content_block_stop", "index": 0}
        yield {
            "type": "content_block_start",
            "index": 1,
            "content_block": {
                "type": "tool_use",
                "id": "tool-1",
                "name": "lookup",
                "input": {},
            },
        }
        yield {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"q": "weather"}'},
        }
        yield {"type": "content_block_stop", "index": 1}
        yield {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 7},
        }
        yield {"type": "message_stop"}

    adapter = AnthropicModelClient(provider_stream=provider_stream)

    events = asyncio.run(collect_events(adapter.stream(make_request())))

    assert seen_requests and seen_requests[0].model == "claude-test"
    assert [type(event) for event in events] == [
        TextDeltaEvent,
        TextDeltaEvent,
        ToolCallEvent,
        MessageCompleteEvent,
    ]
    assert [event.type for event in events] == [
        "text_delta",
        "text_delta",
        "tool_call",
        "message_complete",
    ]

    text_one = events[0]
    text_two = events[1]
    tool_event = events[2]
    complete = events[3]

    assert text_one.text == "hello "
    assert text_two.text == "world"
    assert tool_event.tool_call.id == "tool-1"
    assert tool_event.tool_call.name == "lookup"
    assert tool_event.tool_call.arguments == {"q": "weather"}

    assert complete.stop_reason == "tool_calls"
    assert complete.usage == Usage(input_tokens=10, output_tokens=7)
    assert complete.message.role == "assistant"
    assert complete.message.content[0].type == "text"
    assert complete.message.content[0].text == "hello world"
    assert complete.message.content[1].type == "tool_call"
    assert complete.message.content[1].id == "tool-1"
    assert complete.message.content[1].name == "lookup"
    assert complete.message.content[1].arguments == {"q": "weather"}


def test_adapter_emits_error_event_for_provider_error_chunk() -> None:
    from pyclaude.api.anthropic import AnthropicModelClient

    async def provider_stream(request: QueryRequest):
        del request
        yield {
            "type": "error",
            "error": {"type": "overloaded_error", "message": "busy"},
        }

    adapter = AnthropicModelClient(provider_stream=provider_stream)

    events = asyncio.run(collect_events(adapter.stream(make_request())))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].type == "error"
    assert str(events[0].error) == "busy"


def test_adapter_emits_terminal_error_when_provider_stream_ends_early() -> None:
    from pyclaude.api.anthropic import AnthropicModelClient

    async def provider_stream(request: QueryRequest):
        del request
        yield {
            "type": "message_start",
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 10, "output_tokens": 0},
            },
        }

    adapter = AnthropicModelClient(provider_stream=provider_stream)

    events = asyncio.run(collect_events(adapter.stream(make_request())))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].type == "error"
    assert "message_stop" in str(events[0].error)


def test_update_usage_respects_explicit_zero_values() -> None:
    from pyclaude.api.anthropic import _update_usage

    current = Usage(
        input_tokens=11,
        output_tokens=7,
        cache_read_tokens=3,
        cache_write_tokens=2,
    )

    updated = _update_usage(
        current,
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
    )

    assert updated == Usage(
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_write_tokens=0,
    )


def test_adapter_preserves_max_tokens_stop_reason() -> None:
    from pyclaude.api.anthropic import AnthropicModelClient

    async def provider_stream(request: QueryRequest):
        del request
        yield {
            "type": "message_start",
            "message": {
                "role": "assistant",
                "usage": {"input_tokens": 10, "output_tokens": 0},
            },
        }
        yield {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }
        yield {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "partial response"},
        }
        yield {"type": "content_block_stop", "index": 0}
        yield {
            "type": "message_delta",
            "delta": {"stop_reason": "max_tokens"},
            "usage": {"output_tokens": 7},
        }
        yield {"type": "message_stop"}

    adapter = AnthropicModelClient(provider_stream=provider_stream)

    events = asyncio.run(collect_events(adapter.stream(make_request())))

    complete = events[-1]
    assert isinstance(complete, MessageCompleteEvent)
    assert complete.stop_reason == "max_tokens"


def test_runtime_provider_stream_uses_live_http_transport_and_retries(
    monkeypatch,
) -> None:
    from pyclaude.state.runtime import build_runtime_context

    attempts: list[object] = []
    requests: list[object] = []

    class FakeResponse:
        status = 200

        def __init__(self, lines: list[bytes]) -> None:
            self._buffer = io.BytesIO(b"".join(lines))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def readline(self) -> bytes:
            return self._buffer.readline()

    def fake_urlopen(request, timeout: float):
        attempts.append(timeout)
        requests.append(request)
        if len(attempts) == 1:
            raise APITransportError("temporary network drop")
        return FakeResponse(
            [
                b"event: message_start\n",
                b'data: {"type":"message_start","message":{"role":"assistant","usage":{"input_tokens":3,"output_tokens":0}}}\n\n',
                b"event: content_block_start\n",
                b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
                b"event: content_block_delta\n",
                b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello from live transport"}}\n\n',
                b"event: content_block_stop\n",
                b'data: {"type":"content_block_stop","index":0}\n\n',
                b"event: message_delta\n",
                b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}\n\n',
                b"event: message_stop\n",
                b'data: {"type":"message_stop"}\n\n',
            ]
        )

    async def no_sleep(delay: float) -> None:
        attempts.append(delay)

    monkeypatch.setattr("pyclaude.api.anthropic._urlopen", fake_urlopen)
    monkeypatch.setattr("pyclaude.api.anthropic._sleep", no_sleep)

    context = build_runtime_context(
        config=ResolvedConfig(
            api_key="test-key",
            model="claude-configured",
            base_url="https://example.invalid/v1/messages",
            temperature=0.25,
        ),
        cwd=Path("/tmp/runtime-http"),
    )

    events = asyncio.run(
        collect_events(
            context.model_client.stream(
                QueryRequest(
                    messages=make_request().messages,
                    model="claude-request",
                    temperature=0.75,
                )
            )
        )
    )

    request = requests[-1]
    payload = json.loads(request.data.decode("utf-8"))
    headers = {name.lower(): value for name, value in request.header_items()}

    assert len(requests) == 2
    assert attempts[1] == 0.5
    assert request.full_url == "https://example.invalid/v1/messages"
    assert headers["X-api-key".lower()] == "test-key"
    assert headers["Anthropic-version".lower()] == "2023-06-01"
    assert payload["model"] == "claude-request"
    assert payload["temperature"] == 0.75
    assert payload["stream"] is True
    assert payload["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    ]
    assert [type(event) for event in events] == [TextDeltaEvent, MessageCompleteEvent]
    assert events[0].text == "hello from live transport"
    assert events[1].usage == Usage(input_tokens=3, output_tokens=5)
