from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pyclaude.commands.registry import CommandRegistry
from pyclaude.core.query_engine import QueryEngine
from pyclaude.core.runtime import QueryResult
from pyclaude.state.config import load_config_file, resolve_config
from pyclaude.state.config import ResolvedConfig
from pyclaude.state.runtime import build_runtime_context


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pyclaude")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--api-key")
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--max-turns", type=int)
    parser.add_argument("--config")
    parser.add_argument("--cwd")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = Path(args.cwd).resolve() if args.cwd else Path.cwd()
    file_config = load_config_file(args.config) if args.config else {}
    cli_config = {
        "api_key": args.api_key,
        "model": args.model,
        "base_url": args.base_url,
        "temperature": args.temperature,
        "max_turns": args.max_turns,
    }
    cli_config = {key: value for key, value in cli_config.items() if value is not None}

    try:
        resolved = resolve_config(
            cli=cli_config,
            env=dict(os.environ),
            file_config=file_config,
            defaults={},
        )
        output = asyncio.run(
            run_prompt(prompt=args.prompt, resolved_config=resolved, cwd=cwd)
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(output)
    return 0


async def run_prompt(
    *,
    prompt: str,
    resolved_config: ResolvedConfig,
    cwd: Path,
    command_registry: CommandRegistry | None = None,
) -> str:
    context = build_runtime_context(config=resolved_config, cwd=cwd)
    registry = command_registry or CommandRegistry()
    if registry.maybe_match(prompt) is not None:
        raise NotImplementedError("slash commands are not implemented yet")

    engine = QueryEngine(context=context)
    result = await engine.submit(
        prompt,
        max_turns=resolved_config.max_turns,
        model=resolved_config.model,
        temperature=resolved_config.temperature,
    )
    return render_result(result)


def render_result(result: QueryResult) -> str:
    if not result.messages:
        return ""

    message = result.messages[-1]
    if isinstance(message.content, str):
        return message.content

    text_parts = [
        block.text
        for block in message.content
        if getattr(block, "type", None) == "text"
    ]
    return "".join(text_parts)


if __name__ == "__main__":
    raise SystemExit(main())
