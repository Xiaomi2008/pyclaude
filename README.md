# PyClaude

`pyclaude` is an early-stage Python runtime that connects a prompt-driven CLI to config resolution, runtime wiring, tool orchestration, and an Anthropic-backed query path. This README covers the verified behavior in this worktree without assuming packaging or features that are not yet present.

## Status

The phase-1 Python core runtime is implemented and tested in this worktree. The project is still early-stage, and the documented commands and behavior here reflect the current repo state without assuming packaging or features that are not yet present.

## What's Included

- A prompt-driven CLI that parses flags, resolves config, builds runtime context, submits a prompt through `QueryEngine`, and prints the final assistant text.
- Config loading with `defaults -> file_config -> env -> cli` precedence, plus required `api_key` and `model` values.
- A query engine and loop that normalize prompts, preserve in-engine history, accumulate usage across turns, and continue after per-tool failures when the orchestrator returns error-shaped tool results.
- A tool stack with a registry, sync-or-async executor support, and serial orchestration that wraps tool exceptions per call and keeps later calls running.
- An Anthropic adapter that normalizes streamed provider chunks into assistant events and includes targeted tests for retries, usage accounting, adapter behavior, config, orchestration, query flow, and CLI behavior.

## Quick Start

Use Python 3.10 or newer for this worktree. The codebase uses PEP 604 unions like `str | None` and built-in generics like `list[str]`, and there is no stricter version metadata checked in here.

Create and activate a virtual environment from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

There is no verified packaged install flow yet because this worktree does not include `pyproject.toml`, `requirements.txt`, or `requirements-dev.txt`. The verified minimal workflow is to run `pyclaude` in place from the checkout root.

Set the required environment variables before using the prompt-driven examples below:

```bash
export PYCLAUDE_API_KEY=test-key
export PYCLAUDE_MODEL=claude-test
```

From an activated virtualenv at the repository root, the concrete checkout-based setup/run command is:

```bash
python3 -m pyclaude.cli.main --prompt hello --api-key "$PYCLAUDE_API_KEY" --model "$PYCLAUDE_MODEL" --cwd .
```

This worktree does not include `requirements-dev.txt` or other dependency metadata to bootstrap `pytest`, so the verified portable test path here is to let `uv` provision pytest for an ad hoc run from the checkout root. Install `uv` first if it is not already available on your machine.

```bash
uv run --with pytest python -m pytest tests/cli/test_main.py -q
```

## Configuration

Supported environment variables:

- `PYCLAUDE_API_KEY`
- `PYCLAUDE_MODEL`
- `PYCLAUDE_BASE_URL`
- `PYCLAUDE_TEMPERATURE`
- `PYCLAUDE_MAX_TURNS`

You can also supply config with CLI flags or a JSON config file. The config file must contain a JSON object, unsupported fields are ignored, and resolution order is `defaults -> file_config -> env -> cli`.

## Basic Usage

Run the module entry point directly with a prompt:

```bash
python3 -m pyclaude.cli.main \
  --prompt "Explain the current runtime wiring" \
  --api-key "$PYCLAUDE_API_KEY" \
  --model "$PYCLAUDE_MODEL" \
  --cwd .
```

With safe placeholder values such as `PYCLAUDE_API_KEY=test-key` and `PYCLAUDE_MODEL=claude-test`, the command still reaches the live Anthropic transport and is currently expected to fail with `Anthropic authentication failed (401): invalid x-api-key`. Use real credentials if you want the prompt run to succeed.

Optional CLI flags from `pyclaude/cli/main.py` are `--base-url`, `--temperature`, `--max-turns`, `--config`, and `--cwd`. Slash-command handling is not implemented in the current CLI flow.

## Project Layout

- `pyclaude/core/` - query-facing runtime pieces such as prompt normalization, query submission, and the turn loop.
- `pyclaude/api/` - provider transport, retries, usage accounting, and adapter normalization for Anthropic-backed requests.
- `pyclaude/tools/` - tool interfaces, registry lookup, execution, and serial orchestration behavior.
- `pyclaude/state/` - config resolution, runtime-context construction, and in-memory session state helpers.
- `pyclaude/cli/` - argparse-based entrypoint and prompt execution flow.
- `tests/` - targeted tests covering contracts, config, CLI behavior, query flow, retries, usage, and adapter behavior.

## Development

Keep contributor changes aligned with the verified runtime behavior in this worktree, and use the existing targeted suites under `tests/` plus repo-relative `uv run --with pytest python -m pytest ... -q` commands when checking affected areas.

## Current Limitations

- Packaged installation metadata is not present yet, so there is no verified install command beyond running from a checkout.
- Slash-command handling is not implemented in the current CLI flow.
- Session state is built fresh in memory for each runtime context; persistent storage is not documented here.
- Tool calls run serially through the current orchestrator rather than in parallel.

## Roadmap

- Future README updates can expand setup and contributor guidance once packaging and dependency metadata are added to the repo.

## Contributing

Contributions should preserve the user-first README structure, keep claims tied to verified repo behavior, and update the documented commands when the actual setup or runtime contract changes.
