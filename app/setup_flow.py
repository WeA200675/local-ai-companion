from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.diagnostics import DiagnosticResult
from app.memory.store import StateStore
from app.settings import AppSettings


class FirstRunSetupState(BaseModel):
    completed: bool = False
    revision: int = Field(default=1, ge=1)


class FirstRunSetupRepository:
    STATE_KEY = "first_run_setup"

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> FirstRunSetupState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return FirstRunSetupState()
        try:
            return FirstRunSetupState.model_validate_json(payload)
        except ValueError:
            return FirstRunSetupState()

    def required(self) -> bool:
        return not self.load().completed

    def mark_completed(self) -> FirstRunSetupState:
        state = self.load()
        state.completed = True
        state.revision += 1
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001
        return state.model_copy(deep=True)


@dataclass(frozen=True, slots=True)
class CoreSetupStatus:
    inventory_ok: bool
    inference_ok: bool
    ready: bool
    summary: str


def candidate_settings(
    settings: AppSettings,
    *,
    model_name: str,
    model_url: str,
) -> AppSettings:
    """Return validated first-run model choices without disturbing other settings."""

    payload = settings.model_dump(mode="python")
    payload["model_name"] = model_name.strip()
    payload["model_url"] = model_url.strip()
    return AppSettings.model_validate(payload)


def core_setup_status(results: list[DiagnosticResult]) -> CoreSetupStatus:
    by_name = {item.name: item for item in results}
    inventory = by_name.get("Sprachmodell")
    inference = by_name.get("Modell-Inferenz")
    inventory_ok = bool(inventory and inventory.ok)
    inference_ok = bool(inference and inference.ok)
    ready = inventory_ok and inference_ok

    if ready:
        summary = "Ollama, Modellauswahl und echte lokale Mini-Inferenz sind bereit."
    elif inventory_ok:
        summary = "Das Modell ist installiert, aber die echte lokale Inferenz ist noch nicht bereit."
    elif inventory is None:
        summary = "Der lokale Ollama-/Modellpfad wurde noch nicht geprüft."
    else:
        summary = "Ollama oder das ausgewählte lokale Modell ist noch nicht bereit."

    return CoreSetupStatus(
        inventory_ok=inventory_ok,
        inference_ok=inference_ok,
        ready=ready,
        summary=summary,
    )
