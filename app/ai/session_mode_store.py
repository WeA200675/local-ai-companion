from __future__ import annotations

from app.ai.session_modes import SessionModeState, default_session_modes
from app.memory.store import StateStore

_STATE_KEY = "session_modes_v1"


class SessionModeStore:
    """Persist temporary-mode definitions inside the existing local app_state table."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> SessionModeState:
        payload = self.store._load_app_state(_STATE_KEY)
        if payload is None:
            state = SessionModeState(modes=default_session_modes())
            self.save(state)
            return state
        try:
            state = SessionModeState.model_validate_json(payload)
        except ValueError:
            state = SessionModeState(modes=default_session_modes())
            self.save(state)
        if not state.modes:
            state.modes = default_session_modes()
        if state.active_id and state.active_mode() is None:
            state.active_id = None
        return state

    def save(self, state: SessionModeState) -> None:
        self.store._save_app_state(_STATE_KEY, state.model_dump_json())
