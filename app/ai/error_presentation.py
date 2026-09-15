from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocalModelErrorPresentation:
    title: str
    status: str
    retry_label: str
    detail: str


def present_local_model_error(error: str, model_name: str) -> LocalModelErrorPresentation:
    """Map an already-local model error to concise recovery UI text."""

    clean = " ".join((error or "").split())
    folded = clean.casefold()

    if "[timeout]" in folded or "nicht rechtzeitig" in folded:
        return LocalModelErrorPresentation(
            title="Lokales Modell antwortet zu langsam",
            status="Modell-Inferenz Timeout — Wiederholen verfügbar",
            retry_label="↻ Wiederholen nach Timeout",
            detail=clean,
        )

    if "http 5" in folded or "inferenz-backend" in folded or "llama-server process has terminated" in folded:
        return LocalModelErrorPresentation(
            title="Lokale Modell-Inferenz fehlgeschlagen",
            status="Ollama-Backendfehler — Wiederholen nach Fehlerbehebung verfügbar",
            retry_label="↻ Wiederholen",
            detail=clean,
        )

    if "nicht erreichbar" in folded or "connection refused" in folded or "connecterror" in folded:
        return LocalModelErrorPresentation(
            title="Ollama nicht erreichbar",
            status="Ollama nicht erreichbar — nach dem Start Wiederholen verwenden",
            retry_label="↻ Wiederholen nach Ollama-Start",
            detail=clean,
        )

    if "nicht verfügbar" in folded or "not found" in folded or "model_missing" in folded:
        return LocalModelErrorPresentation(
            title="Lokales Modell nicht verfügbar",
            status=f"Modell {model_name} nicht verfügbar — Wiederholen nach Auswahl/Installation",
            retry_label="↻ Wiederholen nach Modellwahl",
            detail=clean,
        )

    return LocalModelErrorPresentation(
        title="Lokale Modellantwort fehlgeschlagen",
        status="Lokale Antwort fehlgeschlagen — Wiederholen verfügbar",
        retry_label="↻ Wiederholen",
        detail=(
            clean
            or f"Das lokale Modell {model_name} konnte für diesen Versuch keine Antwort erzeugen."
        ),
    )
