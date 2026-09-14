from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

import httpx

from app.settings import AppSettings


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    name: str
    ok: bool
    detail: str

    @property
    def marker(self) -> str:
        return "OK" if self.ok else "FEHLER"


def _check_model(settings: AppSettings, timeout: float) -> DiagnosticResult:
    try:
        response = httpx.get(f"{settings.model_url.rstrip('/')}/api/tags", timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return DiagnosticResult("Sprachmodell", False, f"Endpoint nicht erreichbar: {exc}")

    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = {
        str(item.get("name") or item.get("model") or "")
        for item in models
        if isinstance(item, dict)
    }
    if settings.model_name in names:
        return DiagnosticResult("Sprachmodell", True, f"{settings.model_name} ist verfügbar")
    if names:
        return DiagnosticResult(
            "Sprachmodell",
            False,
            f"Endpoint läuft, aber {settings.model_name!r} wurde nicht gefunden",
        )
    return DiagnosticResult(
        "Sprachmodell",
        False,
        "Endpoint läuft, meldet aber keine installierten Modelle",
    )


def _check_workflow(settings: AppSettings) -> DiagnosticResult:
    if not settings.media_enabled:
        return DiagnosticResult("ComfyUI-Workflow", True, "Mediengenerierung ist deaktiviert")
    path = settings.workflow_path
    if path is None:
        return DiagnosticResult("ComfyUI-Workflow", False, "Kein API-Workflow konfiguriert")
    if not path.exists():
        return DiagnosticResult("ComfyUI-Workflow", False, f"Datei fehlt: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return DiagnosticResult("ComfyUI-Workflow", False, f"JSON konnte nicht gelesen werden: {exc}")
    if not isinstance(payload, dict):
        return DiagnosticResult("ComfyUI-Workflow", False, "Workflow ist kein JSON-Objekt")
    missing = [
        node
        for node in (
            settings.media_positive_node,
            settings.media_negative_node,
            settings.media_seed_node,
        )
        if node not in payload
    ]
    if missing:
        return DiagnosticResult(
            "ComfyUI-Workflow",
            False,
            f"Konfigurierte Node-IDs fehlen: {', '.join(missing)}",
        )
    return DiagnosticResult("ComfyUI-Workflow", True, f"Workflow geladen: {path.name}")


def _check_comfyui(settings: AppSettings, timeout: float) -> DiagnosticResult:
    if not settings.media_enabled:
        return DiagnosticResult("ComfyUI", True, "Mediengenerierung ist deaktiviert")
    try:
        response = httpx.get(f"{settings.media_url.rstrip('/')}/system_stats", timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return DiagnosticResult("ComfyUI", False, f"Endpoint nicht erreichbar: {exc}")
    return DiagnosticResult("ComfyUI", True, "Lokaler ComfyUI-Endpoint antwortet")


def _check_output(settings: AppSettings) -> DiagnosticResult:
    try:
        path = settings.output_path
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="companion-check-", dir=path, delete=True):
            pass
    except OSError as exc:
        return DiagnosticResult("Medien-Ausgabe", False, f"Ordner nicht beschreibbar: {exc}")
    return DiagnosticResult("Medien-Ausgabe", True, f"Beschreibbar: {path}")


def run_diagnostics(settings: AppSettings, timeout: float = 5.0) -> list[DiagnosticResult]:
    """Run short local-only preflight checks without contacting cloud services."""

    return [
        _check_model(settings, timeout),
        _check_workflow(settings),
        _check_comfyui(settings, timeout),
        _check_output(settings),
    ]
