from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.media.comfyui_resilient import (
    ResilientComfyUIClient,
    ResilientComfyUIError,
)


@dataclass(frozen=True, slots=True)
class MediaBackendPresentation:
    """Stable, user-facing description of one classified media failure."""

    category: str
    title: str
    action: str


class VisibleMediaBackendError(RuntimeError):
    """Failure that is intentionally allowed to reach the chat media worker."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        prompt_id: str = "",
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.prompt_id = prompt_id


def classify_resilient_comfyui_error(error: ResilientComfyUIError) -> MediaBackendPresentation:
    """Map backend details to a concise category without hiding the original cause."""

    stage = error.stage
    detail = str(error).casefold()
    if stage == "prepare":
        return MediaBackendPresentation(
            "configuration",
            "Workflow oder lokale Medienkonfiguration ist unvollständig",
            "Prüfe Workflow-Profil, Referenz-Mapping und lokale Dateien.",
        )
    if stage == "reference_upload":
        return MediaBackendPresentation(
            "reference",
            "Referenzbild konnte nicht an ComfyUI übergeben werden",
            "Prüfe das lokale Referenzbild, Dateirechte und ob ComfyUI erreichbar ist.",
        )
    if stage == "queue":
        return MediaBackendPresentation(
            "unreachable",
            "ComfyUI konnte den Renderauftrag nicht sicher annehmen",
            "Prüfe ComfyUI und die Queue. Der Auftrag wird nicht automatisch erneut eingereiht, damit kein Doppeljob entsteht.",
        )
    if stage == "history":
        return MediaBackendPresentation(
            "unreachable",
            "ComfyUI ist beim Lesen des Renderstatus nicht erreichbar",
            "Die Statusabfrage wurde bereits sicher mit frischen Verbindungen wiederholt.",
        )
    if stage == "execution":
        resource_markers = (
            "out of memory",
            "cuda oom",
            "cuda error",
            "allocation",
            "allocate memory",
            "not enough memory",
            "vram",
        )
        if any(marker in detail for marker in resource_markers):
            return MediaBackendPresentation(
                "resources",
                "VRAM/RAM reicht für diesen Render nicht aus",
                "Reduziere Auflösung, Steps oder Workflow-Komplexität und prüfe andere GPU-Prozesse.",
            )
        return MediaBackendPresentation(
            "workflow",
            "ComfyUI-Workflow oder Node ist fehlgeschlagen",
            "Prüfe den genannten Node, Custom-Node-Abhängigkeiten und den ausgewählten Workflow.",
        )
    if stage == "output download":
        return MediaBackendPresentation(
            "output",
            "Render-Ausgabe konnte nicht geladen werden",
            "Der Render kann fertig sein; prüfe ComfyUI-History und Ausgabeordner.",
        )
    if stage == "timeout":
        return MediaBackendPresentation(
            "timeout",
            "ComfyUI-Render hat das Zeitlimit überschritten",
            "Der bekannte Queue-Eintrag wurde bestmöglich gezielt bereinigt; prüfe die lokale Queue.",
        )
    return MediaBackendPresentation(
        "unknown",
        "Lokale Medienerzeugung ist fehlgeschlagen",
        "Prüfe den lokalen ComfyUI-Status und den ausgewählten Workflow.",
    )


def present_resilient_comfyui_error(error: ResilientComfyUIError) -> str:
    presentation = classify_resilient_comfyui_error(error)
    prompt = f" · Prompt-ID {error.prompt_id}" if error.prompt_id else ""
    return (
        f"[COMFYUI/{presentation.category}{prompt}] {presentation.title}. "
        f"{error} {presentation.action}"
    )


class VisibleResilientComfyUIClient(ResilientComfyUIClient):
    """Runtime client that keeps chat alive but makes media failures visible.

    `MediaService` historically treats plain `ComfyUIError` as an optional-media
    skip. The resilient runtime has already classified/retried its failure, so
    hiding it would erase the diagnostic. This wrapper translates only those
    classified failures into an ordinary worker exception; `MediaWorker` catches
    it and displays the problem without crashing the chat.
    """

    def generate(self, *args: Any, **kwargs: Any):
        try:
            return super().generate(*args, **kwargs)
        except ResilientComfyUIError as exc:
            raise VisibleMediaBackendError(
                present_resilient_comfyui_error(exc),
                stage=exc.stage,
                prompt_id=exc.prompt_id,
            ) from exc
