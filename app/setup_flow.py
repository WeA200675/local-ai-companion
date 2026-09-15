from __future__ import annotations

from dataclasses import dataclass

from app.diagnostics import DiagnosticResult
from app.settings import AppSettings


@dataclass(frozen=True, slots=True)
class CoreSetupStatus:
    inventory_ok: bool
    inference_ok: bool
    ready: bool
    summary: str


def setup_required(settings: AppSettings) -> bool:
    return not settings.setup_completed


def candidate_settings(
    settings: AppSettings,
    *,
    model_name: str,
    model_url: str,
    completed: bool | None = None,
) -> AppSettings:
    """Return first-run model choices without disturbing unrelated local settings."""

    update: dict[str, object] = {
        "model_name": model_name.strip(),
        "model_url": model_url.strip(),
    }
    if completed is not None:
        update["setup_completed"] = completed
    return settings.model_copy(update=update)


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
