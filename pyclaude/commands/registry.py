from __future__ import annotations

from pyclaude.commands.base import CommandHandler, CommandMatch


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        self._handlers[name] = handler

    def maybe_match(self, prompt: str) -> CommandMatch | None:
        del prompt
        return None
