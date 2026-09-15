from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.ai.model_compatibility import AdultModelCompatibilityReport
from app.diagnostics import DiagnosticResult
from app.settings import AppSettings

ReadinessState = Literal["ready", "attention", "blocked", "optional"]


@dataclass(frozen=True, slots=True)
class ReadinessItem:
    key: str
    title: str
    state: ReadinessState
    detail: str
    next_step: str = ""

    @property
    def marker(self) -> str:
        return {
            "ready": "OK",
            "attention": "PRÜFEN",
            "blocked": "FEHLER",
            "optional": "OPTIONAL",
        }[self.state]


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    items: tuple[ReadinessItem, ...]
    core_ready: bool
    media_ready: bool
    summary: str

    @property
    def next_steps(self) -> tuple[str, ...]:
        return tuple(item.next_step for item in self.items if item.next_step)


def _diagnostic_map(results: list[DiagnosticResult]) -> dict[str, DiagnosticResult]:
    return {result.name: result for result in results}


def _workflow_result(by_name: dict[str, DiagnosticResult]) -> DiagnosticResult | None:
    return by_name.get("Workflow-Profile") or by_name.get("ComfyUI-Workflow")


def build_readiness_report(
    settings: AppSettings,
    diagnostics: list[DiagnosticResult],
    compatibility: AdultModelCompatibilityReport | None,
) -> ReadinessReport:
    """Combine existing local diagnostics into a user-facing readiness report.

    No network call is made here. The function only interprets results that were
    already produced by the local diagnostics/model-compatibility workers.
    """

    by_name = _diagnostic_map(diagnostics)
    items: list[ReadinessItem] = []

    model = by_name.get("Sprachmodell")
    if model is None:
        model_item = ReadinessItem(
            key="model",
            title="Lokales Sprachmodell",
            state="attention",
            detail=f"{settings.model_name} wurde noch nicht lokal geprüft.",
            next_step="Lokale Verbindungen testen.",
        )
    elif model.ok:
        model_item = ReadinessItem(
            key="model",
            title="Lokales Sprachmodell",
            state="ready",
            detail=model.detail,
        )
    else:
        model_item = ReadinessItem(
            key="model",
            title="Lokales Sprachmodell",
            state="blocked",
            detail=model.detail,
            next_step="Ollama starten, Modellinstallation prüfen und den Verbindungstest wiederholen.",
        )
    items.append(model_item)

    if compatibility is None:
        adult_item = ReadinessItem(
            key="adult_model",
            title="Adult-/Kink-Modellkompatibilität",
            state="attention",
            detail="Für das aktuell ausgewählte Modell liegt noch kein lokaler Kompatibilitätstest vor.",
            next_step="Adult-/Kink-Modelltest ausführen.",
        )
    elif compatibility.status == "compatible":
        adult_item = ReadinessItem(
            key="adult_model",
            title="Adult-/Kink-Modellkompatibilität",
            state="ready",
            detail=f"{compatibility.score}/100 · {compatibility.summary}",
        )
    elif compatibility.status in {"limited", "unclear"}:
        adult_item = ReadinessItem(
            key="adult_model",
            title="Adult-/Kink-Modellkompatibilität",
            state="attention",
            detail=f"{compatibility.score}/100 · {compatibility.summary}",
            next_step="Im Chat praktisch testen oder ein anderes bereits lokal installiertes Modell vergleichen.",
        )
    else:
        adult_item = ReadinessItem(
            key="adult_model",
            title="Adult-/Kink-Modellkompatibilität",
            state="blocked",
            detail=f"{compatibility.score}/100 · {compatibility.summary}",
            next_step=(
                "Bei technischem Fehler zuerst Ollama/Modell stabilisieren; bei Inhaltsblockade ein anderes "
                "lokal installiertes, kompatibles Modell auswählen."
            ),
        )
    items.append(adult_item)

    output = by_name.get("Medien-Ausgabe")
    if output is None:
        output_item = ReadinessItem(
            key="output",
            title="Lokaler Medienordner",
            state="attention",
            detail=settings.media_output_dir,
            next_step="Lokale Verbindungen testen, um den Ausgabeordner zu prüfen.",
        )
    elif output.ok:
        output_item = ReadinessItem(
            key="output",
            title="Lokaler Medienordner",
            state="ready",
            detail=output.detail,
        )
    else:
        output_item = ReadinessItem(
            key="output",
            title="Lokaler Medienordner",
            state="blocked",
            detail=output.detail,
            next_step="Einen lokal beschreibbaren Medien-Ausgabeordner wählen.",
        )
    items.append(output_item)

    if not settings.media_enabled:
        media_item = ReadinessItem(
            key="media",
            title="Lokale Bild-/Motion-Pipeline",
            state="optional",
            detail="Mediengenerierung ist deaktiviert; der Text-Companion funktioniert unabhängig davon.",
            next_step="Medien nur aktivieren, wenn ComfyUI lokal eingerichtet werden soll.",
        )
        media_ready = False
    else:
        comfy = by_name.get("ComfyUI")
        workflow = _workflow_result(by_name)
        comfy_ok = bool(comfy and comfy.ok)
        workflow_ok = bool(workflow and workflow.ok)
        if comfy_ok and workflow_ok:
            media_item = ReadinessItem(
                key="media",
                title="Lokale Bild-/Motion-Pipeline",
                state="ready",
                detail=f"{comfy.detail} · {workflow.detail}",
            )
            media_ready = True
        else:
            details: list[str] = []
            next_steps: list[str] = []
            if comfy is None:
                details.append("ComfyUI wurde noch nicht geprüft")
                next_steps.append("Verbindungstest ausführen")
            elif not comfy.ok:
                details.append(comfy.detail)
                next_steps.append(f"ComfyUI lokal starten und Endpoint {settings.media_url} prüfen")
            if workflow is None:
                details.append("Workflow wurde noch nicht geprüft")
                next_steps.append("einen ComfyUI API-Workflow oder Profilkatalog konfigurieren")
            elif not workflow.ok:
                details.append(workflow.detail)
                next_steps.append("einen gültigen ComfyUI API-Workflow oder Profilkatalog konfigurieren")
            media_item = ReadinessItem(
                key="media",
                title="Lokale Bild-/Motion-Pipeline",
                state="blocked",
                detail=" · ".join(details) or "Medien-Pipeline noch nicht bereit.",
                next_step="; ".join(next_steps) + ".",
            )
            media_ready = False
    items.append(media_item)

    core_ready = model_item.state == "ready" and adult_item.state == "ready"
    if core_ready and media_ready:
        summary = "Text-Companion, Adult-/Kink-Modus und lokale Medien-Pipeline sind startklar."
    elif core_ready:
        summary = "Text-Companion und Adult-/Kink-Modus sind startklar; lokale Medien brauchen noch Setup."
    elif model_item.state == "ready" and adult_item.state == "attention":
        summary = "Der Chat ist technisch bereit; die Adult-/Kink-Eignung des Modells sollte noch bestätigt werden."
    elif model_item.state == "ready" and adult_item.state == "blocked":
        summary = "Der Chat-Backendpfad funktioniert, aber der gewünschte Adult-/Kink-Modus ist mit diesem Modell nicht startklar."
    else:
        summary = "Das lokale Sprachmodell ist noch nicht startklar."

    return ReadinessReport(
        items=tuple(items),
        core_ready=core_ready,
        media_ready=media_ready,
        summary=summary,
    )
