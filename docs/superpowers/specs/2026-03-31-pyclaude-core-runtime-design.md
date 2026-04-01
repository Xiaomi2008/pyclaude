# PyClaude Core Runtime Migration Design

## Goal

Convert the core runtime currently implemented under `src/` into pure Python code under `pyclaude/`, while preserving the existing architecture where it is valuable and deliberately introducing cleaner package boundaries where the TypeScript code is currently scattered.

This first phase targets the runtime spine only: query execution, tool orchestration, command seam definition, model API access, state/config handling, and a minimal CLI entrypoint. UI-heavy, Bun-specific, and optional subsystems are deferred.

## Scope

Included in phase 1:

- Core conversation/query loop
- Query engine abstraction for headless usage
- Tool interfaces, registry, execution, and orchestration
- Anthropic-compatible API client and retry/error handling
- Session/config/runtime state needed by the core runtime
- Minimal CLI shell that can invoke the runtime
- Command seam only, without real slash-command dispatch requirements
- A migration-friendly package layout under `pyclaude/`

Explicitly deferred:

- React/Ink UI details from `tsx` files
- Voice, remote sessions, assistant mode, coordinator mode
- Most analytics, growthbook, and feature-flag internals
- Full MCP parity beyond a seam for future integration
- Full plugin/runtime extension parity beyond interface placeholders

## Why Introduce `pyclaude/core/`

The TypeScript codebase has an architectural core, but not a single `core/` directory. The runtime spine is distributed across `src/query.ts`, `src/QueryEngine.ts`, `src/Tool.ts`, `src/tools.ts`, `src/services/api/`, `src/services/tools/`, `src/bootstrap/`, `src/state/`, and shared utilities.

The Python port should not preserve that sprawl mechanically. Instead, it should introduce `pyclaude/core/` as the explicit kernel of the runtime.

That package exists to own:

- turn lifecycle
- message model
- query orchestration
- model/tool coordination
- runtime context passed between the core engine and subsystems

It must not become a dumping ground for everything important. Tool implementations, API adapters, CLI code, and integration-specific code remain outside `pyclaude/core/`.

## Recommended Migration Strategy

Use an adapter-first migration.

Rather than redesigning the whole product in one pass or mirroring `src/` file-for-file, the Python implementation should preserve the important runtime concepts and contracts while translating them into idiomatic Python modules.

This approach is recommended because it:

- preserves the working architecture already visible in the TypeScript runtime
- reduces behavior drift in the most fragile areas: tool calling, retries, state, and turn continuation
- allows phase-1 Python code to omit Bun/React assumptions without breaking the runtime model
- creates a clear path for later parity work

## Existing TypeScript Runtime Spine

The current core path is centered around these files and directories:

- `src/main.tsx`
- `src/query.ts`
- `src/QueryEngine.ts`
- `src/Tool.ts`
- `src/tools.ts`
- `src/services/api/`
- `src/services/tools/`
- `src/commands.ts`
- `src/bootstrap/`
- `src/state/`

In plain terms, the current runtime flow is:

1. CLI entrypoint initializes config, state, and runtime services
2. User input is normalized and checked for command behavior
3. The query loop sends messages to the model API
4. Assistant tool requests are detected and executed
5. Tool results are appended back into the conversation
6. The query loop continues until the turn terminates

The Python version should preserve that behavior, even if file boundaries improve.

## Target Python Package Layout

```text
pyclaude/
  core/
    __init__.py
    messages.py
    runtime.py
    query_loop.py
    query_engine.py
  api/
    __init__.py
    client.py
    anthropic.py
    errors.py
    retries.py
    usage.py
  tools/
    __init__.py
    base.py
    registry.py
    execution.py
    orchestration.py
    builtins/
  commands/
    __init__.py
    registry.py
    base.py
  state/
    __init__.py
    config.py
    session.py
    runtime.py
    persistence.py
  cli/
    __init__.py
    main.py
```

Deferred until a later phase and intentionally excluded from the initial package skeleton:

- `pyclaude/core/budgets.py`
- `pyclaude/core/permissions.py`
- `pyclaude/integrations/`
- `pyclaude/compat/`

If needed during phase 1, their behavior should remain inside existing runtime modules instead of introducing placeholder packages with unclear ownership.

## Core Contracts

Phase 1 needs canonical Python runtime contracts so the implementation does not drift.

Required core types and interfaces:

- `Message`
  - fields: `role`, `content`, `timestamp`, `tool_call_id=None`, `metadata=None`
  - roles supported in phase 1: `system`, `user`, `assistant`, `tool`
  - `content` is `str | list[ContentBlock]`
- `ContentBlock`
  - supported block types in phase 1:
    - `TextBlock(type="text", text: str)`
    - `ToolCallBlock(type="tool_call", id: str, name: str, arguments: dict)`
    - `ToolResultBlock(type="tool_result", tool_call_id: str, name: str, content: str | dict, is_error: bool = False)`
- `AssistantEvent`
  - use a discriminated union in phase 1 rather than one loose dataclass
  - event variants:
    - `TextDeltaEvent(type="text_delta", text: str, raw=None)`
    - `ToolCallEvent(type="tool_call", tool_call: ToolCall, raw=None)`
    - `MessageCompleteEvent(type="message_complete", message: Message, stop_reason: str, usage: Usage, raw=None)`
    - `ErrorEvent(type="error", error: Exception | str, raw=None)`
- `ToolCall`
  - fields: `id`, `name`, `arguments`
- `ToolResult`
  - fields: `tool_call_id`, `tool_name`, `content`, `is_error=False`, `metadata=None`
- `QueryRequest`
  - fields: `messages`, `max_turns=None`, `model=None`, `temperature=None`, `tool_choice=None`
- `QueryResult`
  - fields: `messages`, `usage`, `stop_reason`, `turns_completed`
- `RuntimeContext`
  - fields: `cwd`, `config`, `session_state`, `tool_registry`, `tool_orchestrator`, `model_client`, `event_sink=None`
- `Usage`
  - fields: `input_tokens`, `output_tokens`, `cache_read_tokens=0`, `cache_write_tokens=0`
- `SessionState`
  - fields: `session_id`, `conversation_id`, `turn_count=0`
- `ModelClient.stream(request: QueryRequest) -> AsyncIterator[AssistantEvent]`
- `ToolExecutor.execute(tool_call: ToolCall, context: RuntimeContext) -> Awaitable[ToolResult]`
- `ToolOrchestrator.run(calls: list[ToolCall], context: RuntimeContext) -> Awaitable[list[ToolResult]]`

Canonical representation rule:

- `QueryRequest.messages` is the only source of truth for system instructions in phase 1
- any CLI/config/system prompt input must be normalized into a leading `Message(role="system", ...)` before entering `query_loop.py`
- `ModelClient` must not receive a separate `system_prompt` argument

Example transcript shape:

```python
[
    Message(role="system", content="You are a coding assistant", timestamp=...),
    Message(role="user", content="List Python files", timestamp=...),
    Message(
        role="assistant",
        content=[
            TextBlock(type="text", text="I will inspect the workspace."),
            ToolCallBlock(type="tool_call", id="call_1", name="glob", arguments={"pattern": "**/*.py"}),
        ],
        timestamp=..., 
    ),
    Message(
        role="tool",
        tool_call_id="call_1",
        content=[
            ToolResultBlock(type="tool_result", tool_call_id="call_1", name="glob", content={"matches": ["a.py"]}),
        ],
        timestamp=...,
    ),
]
```

Phase-1 exact shapes:

- `tool_choice`: `None | "auto" | "none" | str`
  - string values other than `auto` and `none` indicate a specific required tool name
- `metadata` on `Message` and `ToolResult`: optional `dict[str, Any]`, but phase 1 core runtime must not depend on any specific keys
- `session_state`: only the three `SessionState` fields above are required by the core runtime in phase 1
- `usage`: always normalized into the `Usage` shape above before leaving `pyclaude/api/`

## Phase-1 Config Contract

Phase 1 needs a minimal, normative config schema.

Required config fields:

- `api_key: str`
- `model: str`

Optional config fields:

- `base_url: str | None = None`
- `temperature: float | None = None`
- `max_turns: int | None = None`

Allowed config sources in phase 1:

- CLI arguments
- environment variables
- a local config file
- built-in defaults

Resolution precedence in phase 1:

1. CLI arguments
2. environment variables
3. config file
4. defaults

The core runtime should receive only resolved config values. Source-merging logic belongs in CLI/bootstrap code, not inside `pyclaude/core/`.

## Streaming Contract

Phase 1 streaming semantics must be normative.

Allowed event order for one assistant turn:

1. zero or more `text_delta` and `tool_call` events in any provider order
2. exactly one terminal event: `message_complete` or `error`

Rules:

- `text_delta` appends assistant text for the current in-progress assistant message
- `tool_call` emits one complete tool call payload at a time; arguments must already be fully assembled before emission
- `message_complete` must include the final assembled assistant message plus a `stop_reason`
- `error` is terminal for that stream and must contain enough information for retry classification
- no events may occur after `message_complete` or `error`
- the Anthropic adapter may buffer provider chunks as needed, but it must expose only normalized phase-1 events to `query_loop.py`

Allowed `QueryResult.stop_reason` values in phase 1:

- `completed`
- `tool_calls`
- `max_turns`
- `api_error`
- `aborted`

If the model requests one or more tools, the final event for that assistant turn should normally complete with `stop_reason="tool_calls"`.

These contracts should be represented as dataclasses and protocols or abstract base classes, with tests written against the contracts before the concrete Anthropic adapter or real built-in tools are attached.

## Source-to-Target Mapping

### Query and conversation runtime

- `src/query.ts` -> `pyclaude/core/query_loop.py`
- `src/QueryEngine.ts` -> `pyclaude/core/query_engine.py`
- selected message helpers from `src/utils/messages*` -> `pyclaude/core/messages.py`
- selected runtime context and turn-scoped data -> `pyclaude/core/runtime.py`

### Tool system

- `src/Tool.ts` -> `pyclaude/tools/base.py`
- `src/tools.ts` -> `pyclaude/tools/registry.py`
- `src/services/tools/toolExecution.ts` -> `pyclaude/tools/execution.py`
- `src/services/tools/toolOrchestration.ts` -> `pyclaude/tools/orchestration.py`

### Model API layer

- `src/services/api/claude.ts` -> `pyclaude/api/anthropic.py`
- `src/services/api/client.ts` -> `pyclaude/api/client.py`
- `src/services/api/errors.ts` -> `pyclaude/api/errors.py`
- `src/services/api/withRetry.ts` -> `pyclaude/api/retries.py`
- usage/logging pieces needed by core runtime -> `pyclaude/api/usage.py`

### Commands and CLI

- `src/commands.ts` -> `pyclaude/commands/registry.py`
- minimal command interfaces -> `pyclaude/commands/base.py`
- `src/main.tsx` -> `pyclaude/cli/main.py`

### State and configuration

- selected parts of `src/bootstrap/state.ts` -> `pyclaude/state/runtime.py`
- selected parts of `src/state/` -> `pyclaude/state/session.py`
- selected config loading pieces -> `pyclaude/state/config.py`
- persistence helpers -> `pyclaude/state/persistence.py`

## Architectural Boundaries

### `pyclaude/core/`

Owns the conversation kernel.

Responsibilities:

- maintain message history for a conversation
- coordinate model calls and tool execution
- enforce turn lifecycle, retry, and continuation behavior
- expose a headless engine API reusable by CLI and tests

Non-responsibilities:

- direct HTTP client implementations
- built-in tool implementations
- CLI parsing and presentation
- plugin or MCP specifics

### `pyclaude/api/`

Owns external model transport.

Responsibilities:

- create/configure Anthropic-compatible clients
- stream responses into internal event/message representations
- centralize retry policy and API-specific error mapping
- report token/usage accounting needed by the runtime

### `pyclaude/tools/`

Owns tool contracts and execution.

Responsibilities:

- define the tool interface and capability flags
- register built-in tools
- validate/execute tool calls
- serialize or parallelize calls where safe
- normalize tool results back into the message model

Orchestration boundary:

- canonical dependency shape for phase 1 is `query_loop -> ToolOrchestrator -> ToolExecutor`
- `pyclaude/core/query_loop.py` detects tool-call blocks and decides whether the model loop should continue
- `pyclaude/tools/orchestration.py` owns tool batch execution strategy and invokes `ToolExecutor`
- orchestration is async and must support IO-bound tools naturally
- phase 1 default policy is serial execution unless a later tool explicitly declares concurrency safety
- the core loop alone decides whether to retry, stop, or resume the model after tool execution

### `pyclaude/commands/`

Owns slash-command dispatch.

Responsibilities:

- parse and resolve commands
- return command behavior or prompt transformations
- stay thin enough that command logic can call `pyclaude/core/` instead of duplicating it

Phase-1 delivery note:

- this package is stub-only for the initial runnable slice
- the first CLI milestone may call `pyclaude/core/query_engine.py` directly without real command dispatch
- command routing becomes active only in a follow-up phase after the prompt-driven CLI works
- phase 1 includes only a command seam, not real slash-command behavior

### `pyclaude/state/`

Owns configuration and persisted runtime/session data.

Responsibilities:

- load config from files and environment
- hold session identifiers and runtime flags
- keep phase-1 session/conversation state in memory by default

Minimum persistence scope for phase 1:

- required persistence: config loading from files and environment
- optional persistence: session metadata if it falls out naturally from CLI wiring
- not required in phase 1: durable transcript storage, resumable conversations, or full session history persistence

### `pyclaude/cli/`

Owns process entry only.

Responsibilities:

- parse arguments
- load config and runtime dependencies
- invoke the query engine directly for the initial runnable slice
- optionally invoke the command registry only in the follow-up command phase

This layer should remain intentionally thin.

## Minimum Shippable Feature Set

Phase 1 does not need broad feature parity. It needs a small, exact, testable feature set.

Required runtime behavior:

- prompt-only turns must work end-to-end
- tool-using turns must work end-to-end in tests using fake tools
- the CLI must be able to submit a prompt and print the final assistant response

Required built-in tools for phase 1:

- none required for the first runnable slice
- real built-in tools can land after the loop works, starting with `bash`, `read`, and `glob`

Required commands for phase 1:

- no slash commands are required for the first runnable slice
- the command layer only needs enough structure to avoid blocking later command ports

This means the first production-capable milestone is a prompt-driven CLI plus a tested tool loop. Real built-in tools and slash commands are incremental follow-up work, not blockers for the initial port.

## Data Flow

The phase-1 Python runtime should follow this flow:

Initial runnable slice:

1. `pyclaude/cli/main.py` parses args and builds runtime dependencies
2. `pyclaude/core/query_engine.py` accepts a prompt and conversation state
3. `pyclaude/core/query_loop.py` calls `RuntimeContext.model_client`
4. streamed assistant events are normalized into internal message structures
5. tool-call blocks are passed to `pyclaude/tools/orchestration.py`
6. orchestration invokes `pyclaude/tools/execution.py`
7. tool results are converted back into internal message objects
8. the loop continues until the assistant completes the turn

Follow-up slice:

1. `pyclaude/cli/main.py` passes input through `pyclaude/commands/registry.py`
2. command dispatch either handles the input locally or forwards it to `pyclaude/core/query_engine.py`

`pyclaude/api/anthropic.py` is only a concrete implementation of the `ModelClient` protocol. It is wired in by CLI/bootstrap code and must not be called directly by `pyclaude/core/query_loop.py`.

## Error Handling Design

The Python port should preserve the TypeScript architecture's bias toward centralized error classification.

Rules:

- API transport errors are owned by `pyclaude/api/errors.py`
- retry decisions are owned by `pyclaude/api/retries.py`
- tool execution failures are normalized into structured tool-result errors rather than raw exceptions whenever possible
- core runtime code should distinguish between:
  - fatal configuration/runtime errors
  - retryable API failures
  - model-generated tool requests that fail during execution
  - user-visible command/tool validation errors

The query loop should continue to be the single place that decides whether a turn stops, retries, or resumes after tool execution.

## Turn Counting

`max_turns` must be deterministic in phase 1.

- one turn equals one completed assistant/model cycle
- a cycle that ends with tool calls still counts as one completed turn
- after tool results are appended and the model is invoked again, that next assistant cycle counts as the next turn
- the limit is checked before starting a new model cycle
- if the limit has been reached, the loop returns with `stop_reason="max_turns"` without starting another model request

## Testing Strategy

The Python port should be test-first at subsystem boundaries.

Priority test layers:

1. message normalization and message model tests
2. query loop continuation tests with fake model responses
3. tool execution/orchestration tests with fake tools
4. API retry/error classification tests
5. thin CLI smoke tests

Deferred to the follow-up command phase:

- command registry tests
- slash-command behavior tests

The highest-value early tests are the ones that prove the agent loop works:

- assistant response with no tool use completes correctly
- assistant response with one tool call loops back correctly
- assistant response with multiple tool calls respects orchestration rules
- tool failure is represented correctly and returned to the loop
- retryable API failures are retried, non-retryable ones are surfaced

## Implementation Phases

### Phase 1: Skeleton and contracts

- create the `pyclaude/` package tree
- define core message types and runtime interfaces
- define tool and API abstractions
- write tests for the contracts using fake implementations

### Phase 2: Core loop

- implement `query_loop.py`
- implement `query_engine.py`
- add tests for turn progression and tool continuation using fake `ModelClient` and fake `ToolExecutor`

### Phase 3: Tool runtime

- implement tool registry, execution, and orchestration
- keep initial tests based on fake tools first
- optionally add the first real built-in tools after orchestration behavior is stable
- wire `ToolOrchestrator` as the only tool dependency consumed by `query_loop.py`

### Phase 4: API layer

- implement Anthropic-compatible client adapter
- add retry/error/usage handling
- plug the real API adapter into the already-tested core loop contracts

### Phase 5: CLI and commands

- implement a minimal CLI entrypoint
- keep the initial CLI prompt-driven
- add command registry structure without requiring broad command parity
- keep session state in memory for the first working slice

### Phase 6: Deferred integration seams

- add MCP/plugin extension seams without blocking the core runtime
- document deferred parity areas explicitly

## Non-Goals for Phase 1

- reproducing the current TUI
- replicating every feature flag and optional subsystem
- porting all utility modules from `src/utils/`
- matching TypeScript file structure one-to-one

## Success Criteria

Phase 1 is successful when:

- `pyclaude/` contains a clean Python package layout centered on `pyclaude/core/`
- a user can invoke a minimal Python CLI that drives the headless query engine
- the query engine can complete a plain assistant turn against a real `ModelClient`
- the query engine can complete a tool-using turn in tests using fake tools
- core tests cover the loop, tool execution, retries, and state transitions
- the design preserves a path to later parity without forcing Bun/React-specific structures into Python

Clarification:

- a tested tool loop with fake tools is part of phase 1 ship criteria
- real built-in tools are not required for initial phase 1 completion
- real slash commands are not required for initial phase 1 completion
