from __future__ import annotations

from pyclaude.core.runtime import SessionState


class InMemorySessionStore:
    def __init__(self) -> None:
        self._session_state: SessionState | None = None

    def load(self) -> SessionState | None:
        return self._session_state

    def save(self, session_state: SessionState) -> SessionState:
        self._session_state = session_state
        return session_state
