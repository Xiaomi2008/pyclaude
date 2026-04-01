from __future__ import annotations

from uuid import uuid4

from pyclaude.core.runtime import SessionState
from pyclaude.state.persistence import InMemorySessionStore


def create_session_state(*, store: InMemorySessionStore | None = None) -> SessionState:
    if store is not None and (session_state := store.load()) is not None:
        return session_state

    session_state = SessionState(
        session_id=f"session-{uuid4().hex}",
        conversation_id=f"conversation-{uuid4().hex}",
    )

    if store is not None:
        store.save(session_state)

    return session_state
