from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CommandMatch:
    name: str
    argument_text: str


@runtime_checkable
class CommandHandler(Protocol):
    def __call__(self, match: CommandMatch) -> str | None: ...
