from __future__ import annotations

from typing import Any

from app.media.comfyui_resilient import (
    ResilientComfyUIClient,
    ResilientComfyUIError,
)


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


def present_resilient_comfyui_error(error: ResilientComfyUIError) -> str:
    stage = error.stage
    prompt = f" · Prompt-ID {error.prompt_id}" if error.prompt_id else ""
    actions = {
        "prepare": "Prüfe Workflow-Profil, Referenz-Mapping und lokale Dateien.",
        "reference_upload": "Prüfe das lokale Referenzbild und ob ComfyUI erreichbar ist.",
        "queue": (
            "Prüfe ComfyUI und die Queue. Der Render wurde absichtlich nicht automatisch erneut eingereiht, "
            "damit kein teurer Doppeljob entsteht."
        ),
        "history": "ComfyUI wurde beim Lesen der Render-Historie bereits automatisch erneut kontaktiert.",
        "execution": "Prüfe den genannten ComfyUI-Node, Workflow-Abhängigkeiten und verfügbaren VRAM/RAM.",
        "output download": "Der Render kann fertig sein; prüfe ComfyUI-History und Ausgabeordner.",
        "timeout": "Der bekannte Queue-Eintrag wurde bestmöglich gezielt bereinigt; prüfe die lokale ComfyUI-Queue.",
    }
    action = actions.get(stage, "Prüfe den lokalen ComfyUI-Status und den ausgewählten Workflow.")
    return f"[COMFYUI/{stage}{prompt}] {error} {action}"


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
