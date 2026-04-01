# PyClaude Core Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the phase-1 Python runtime under `pyclaude/` with a tested core query loop, async tool orchestration seam, Anthropic-compatible model client, and a prompt-driven CLI.

**Architecture:** Keep the Python port centered on `pyclaude/core/`, with all model interaction going through a `ModelClient` protocol and all tool execution going through an async `ToolOrchestrator`. The first runnable slice uses a direct CLI-to-query-engine path, keeps session state in memory, and proves tool turns with fakes before real built-in tools or slash commands are added.

**Tech Stack:** Python 3.12+, `pytest`, `pytest-asyncio`, standard-library `dataclasses`, `typing.Protocol`, `asyncio`, and an Anthropic-compatible HTTP client adapter.

---

### Task 1: Create the package skeleton

**Files:**
- Create: `pyclaude/__init__.py`
- Create: `pyclaude/core/__init__.py`
- Create: `pyclaude/api/__init__.py`
- Create: `pyclaude/tools/__init__.py`
- Create: `pyclaude/tools/builtins/__init__.py`
- Create: `pyclaude/commands/__init__.py`
- Create: `pyclaude/state/__init__.py`
- Create: `pyclaude/cli/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create the package directories and empty package files**

Create the directories and `__init__.py` files listed above.

- [ ] **Step 2: Verify imports resolve**

Run: `python -c "import pyclaude, pyclaude.core, pyclaude.api, pyclaude.tools, pyclaude.state, pyclaude.cli"`
Expected: command exits successfully with no import errors


### Task 2: Define the canonical core contracts

**Files:**
- Create: `pyclaude/core/messages.py`
- Create: `pyclaude/core/runtime.py`
- Create: `pyclaude/api/client.py`
- Create: `pyclaude/tools/base.py`
- Test: `tests/core/test_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

Add tests in `tests/core/test_contracts.py` that assert these names exist and can be instantiated:

```python
from pyclaude.core.messages import Message, TextBlock, ToolCallBlock, ToolResultBlock
from pyclaude.core.runtime import QueryRequest, QueryResult, RuntimeContext, SessionState, Usage
from pyclaude.api.client import ModelClient
from pyclaude.tools.base import ToolCall, ToolResult, ToolExecutor, ToolOrchestrator


def test_message_contracts_exist():
    msg = Message(role="user", content="hi", timestamp=0.0)
    assert msg.role == "user"


def test_runtime_contracts_exist():
    usage = Usage(input_tokens=1, output_tokens=2)
    state = SessionState(session_id="s1", conversation_id="c1")
    req = QueryRequest(messages=[])
    assert usage.output_tokens == 2
    assert state.turn_count == 0
    assert req.messages == []
```

- [ ] **Step 2: Run the contract tests to confirm they fail**

Run: `pytest tests/core/test_contracts.py -q`
Expected: FAIL with import or symbol errors

- [ ] **Step 3: Implement the minimal dataclasses and protocols**

Add:

- message/content block dataclasses in `pyclaude/core/messages.py`
- `Usage`, `SessionState`, `QueryRequest`, `QueryResult`, `RuntimeContext` in `pyclaude/core/runtime.py`
- `ModelClient` protocol in `pyclaude/api/client.py`
- `ToolCall`, `ToolResult`, `ToolExecutor`, `ToolOrchestrator` protocols in `pyclaude/tools/base.py`

- [ ] **Step 4: Re-run the contract tests**

Run: `pytest tests/core/test_contracts.py -q`
Expected: PASS


### Task 3: Add config loading and precedence rules

**Files:**
- Create: `pyclaude/state/config.py`
- Test: `tests/state/test_config.py`

- [ ] **Step 1: Write failing config tests for precedence**

Cover:

- required `api_key` and `model`
- optional `base_url`, `temperature`, `max_turns`
- precedence `CLI > env > config file > defaults`

Example test shape:

```python
def test_cli_overrides_env_and_file():
    resolved = resolve_config(
        cli={"model": "cli-model"},
        env={"PYCLAUDE_MODEL": "env-model"},
        file_config={"model": "file-model", "api_key": "k"},
    )
    assert resolved.model == "cli-model"
```

- [ ] **Step 2: Run the config tests to confirm they fail**

Run: `pytest tests/state/test_config.py -q`
Expected: FAIL with missing module or function errors

- [ ] **Step 3: Implement the config schema and resolver**

Add a `ResolvedConfig` dataclass plus a resolver function that merges CLI, env, file config, and defaults in the required order.

- [ ] **Step 4: Re-run the config tests**

Run: `pytest tests/state/test_config.py -q`
Expected: PASS


### Task 4: Implement the async tool execution seam

**Files:**
- Create: `pyclaude/tools/registry.py`
- Create: `pyclaude/tools/execution.py`
- Create: `pyclaude/tools/orchestration.py`
- Test: `tests/tools/test_orchestration.py`

- [ ] **Step 1: Write failing orchestration tests**

Cover:

- registry lookup by tool name
- async execution returning `ToolResult`
- serial default behavior for multiple tool calls

Example test shape:

```python
@pytest.mark.asyncio
async def test_orchestrator_runs_calls_serially_by_default():
    results = await orchestrator.run([call1, call2], context)
    assert [r.tool_name for r in results] == ["one", "two"]
```

- [ ] **Step 2: Run the orchestration tests to confirm they fail**

Run: `pytest tests/tools/test_orchestration.py -q`
Expected: FAIL

- [ ] **Step 3: Implement the registry, executor, and orchestrator**

Requirements:

- registry stores tool implementations by name
- executor validates tool existence and invokes the tool asynchronously
- orchestrator depends on the executor
- orchestrator runs serially by default in phase 1

- [ ] **Step 4: Re-run the orchestration tests**

Run: `pytest tests/tools/test_orchestration.py -q`
Expected: PASS


### Task 5: Implement query loop behavior against fake model streams

**Files:**
- Create: `pyclaude/core/query_loop.py`
- Test: `tests/core/test_query_loop.py`

- [ ] **Step 1: Write failing query loop tests**

Cover these cases with fake `ModelClient` and fake `ToolOrchestrator`:

- plain assistant response completes
- assistant emits one tool call and loop resumes after tool result
- tool failure returns an error-shaped tool result and continues deterministically
- `max_turns` stops before starting a new model cycle

Example test shape:

```python
@pytest.mark.asyncio
async def test_plain_turn_completes():
    result = await run_query_loop(context=context, request=request)
    assert result.stop_reason == "completed"
```

- [ ] **Step 2: Run the query loop tests to confirm they fail**

Run: `pytest tests/core/test_query_loop.py -q`
Expected: FAIL

- [ ] **Step 3: Implement the core async loop**

Requirements:

- consume `RuntimeContext.model_client.stream(...)`
- collect assistant events into a final assistant message
- detect tool calls from the completed message
- delegate tool batches to `RuntimeContext.tool_orchestrator`
- append tool-result messages and continue until completion or `max_turns`

- [ ] **Step 4: Re-run the query loop tests**

Run: `pytest tests/core/test_query_loop.py -q`
Expected: PASS


### Task 6: Add the QueryEngine wrapper

**Files:**
- Create: `pyclaude/core/query_engine.py`
- Test: `tests/core/test_query_engine.py`

- [ ] **Step 1: Write failing QueryEngine tests**

Cover:

- prompt input is normalized into `Message` objects
- system instructions become a leading `system` message
- conversation history persists within the engine instance

- [ ] **Step 2: Run the QueryEngine tests to confirm they fail**

Run: `pytest tests/core/test_query_engine.py -q`
Expected: FAIL

- [ ] **Step 3: Implement the QueryEngine wrapper**

Requirements:

- hold mutable conversation history in memory
- expose an async submission method
- delegate actual loop execution to `pyclaude/core/query_loop.py`

- [ ] **Step 4: Re-run the QueryEngine tests**

Run: `pytest tests/core/test_query_engine.py -q`
Expected: PASS


### Task 7: Implement API errors, retries, and usage normalization

**Files:**
- Create: `pyclaude/api/errors.py`
- Create: `pyclaude/api/retries.py`
- Create: `pyclaude/api/usage.py`
- Test: `tests/api/test_retries.py`
- Test: `tests/api/test_usage.py`

- [ ] **Step 1: Write failing API support tests**

Cover:

- retryable vs non-retryable API error classification
- usage normalization into the canonical `Usage` shape

- [ ] **Step 2: Run the API support tests to confirm they fail**

Run: `pytest tests/api/test_retries.py tests/api/test_usage.py -q`
Expected: FAIL

- [ ] **Step 3: Implement the support modules**

Add focused helpers for:

- error classes/classification
- retry policy decisions
- provider payload to `Usage` normalization

- [ ] **Step 4: Re-run the API support tests**

Run: `pytest tests/api/test_retries.py tests/api/test_usage.py -q`
Expected: PASS


### Task 8: Implement the Anthropic-compatible adapter

**Files:**
- Create: `pyclaude/api/anthropic.py`
- Test: `tests/api/test_anthropic_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

Cover:

- adapter satisfies the `ModelClient` protocol
- provider stream chunks normalize into phase-1 `AssistantEvent` variants
- `message_complete` carries the final assembled assistant message and usage

- [ ] **Step 2: Run the adapter tests to confirm they fail**

Run: `pytest tests/api/test_anthropic_adapter.py -q`
Expected: FAIL

- [ ] **Step 3: Implement the adapter**

Requirements:

- expose `stream(request)` only through the protocol shape
- normalize provider data into `TextDeltaEvent`, `ToolCallEvent`, `MessageCompleteEvent`, or `ErrorEvent`
- keep provider-specific parsing inside `pyclaude/api/anthropic.py`

- [ ] **Step 4: Re-run the adapter tests**

Run: `pytest tests/api/test_anthropic_adapter.py -q`
Expected: PASS


### Task 9: Build the minimal prompt-driven CLI

**Files:**
- Create: `pyclaude/cli/main.py`
- Create: `pyclaude/state/session.py`
- Create: `pyclaude/state/runtime.py`
- Create: `pyclaude/state/persistence.py`
- Create: `pyclaude/commands/base.py`
- Create: `pyclaude/commands/registry.py`
- Test: `tests/cli/test_main.py`

- [ ] **Step 1: Write failing CLI smoke tests**

Cover:

- CLI accepts a prompt
- CLI resolves config before building runtime dependencies
- CLI invokes `QueryEngine` directly for the first runnable slice

- [ ] **Step 2: Run the CLI tests to confirm they fail**

Run: `pytest tests/cli/test_main.py -q`
Expected: FAIL

- [ ] **Step 3: Implement the minimal CLI and runtime wiring**

Requirements:

- keep session state in memory
- construct `RuntimeContext` from resolved config
- wire in the Anthropic adapter as `model_client`
- include only a stub command seam, not real slash-command behavior

- [ ] **Step 4: Re-run the CLI tests**

Run: `pytest tests/cli/test_main.py -q`
Expected: PASS


### Task 10: Run the full phase-1 verification suite

**Files:**
- Modify: `docs/superpowers/specs/2026-03-31-pyclaude-core-runtime-design.md`

- [ ] **Step 1: Run the full targeted test suite**

Run: `pytest tests/core/test_contracts.py tests/state/test_config.py tests/tools/test_orchestration.py tests/core/test_query_loop.py tests/core/test_query_engine.py tests/api/test_retries.py tests/api/test_usage.py tests/api/test_anthropic_adapter.py tests/cli/test_main.py -q`
Expected: PASS

- [ ] **Step 2: Run a minimal manual CLI smoke check**

Run: `python -m pyclaude.cli.main --prompt "hello"`
Expected: command prints a final assistant response or a clearly classified config/auth error

- [ ] **Step 3: Update the spec with implementation notes if the delivered slice intentionally differs**

Record only real, intentional deviations from the spec in `docs/superpowers/specs/2026-03-31-pyclaude-core-runtime-design.md`.
