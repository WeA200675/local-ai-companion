from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

import httpx

from app.media.profiles import WorkflowProfile, load_workflow_catalog
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


def _load_json_object(path: Path) -> tuple[dict[str, object] | None, str | None]:
    if not path.exists():
        return None, f"Datei fehlt: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"JSON konnte nicht gelesen werden: {exc}"
    if not isinstance(payload, dict):
        return None, "Workflow ist kein JSON-Objekt"
    return payload, None


def _validate_profile(profile: WorkflowProfile) -> str | None:
    payload, error = _load_json_object(profile.workflow_path)
    if error is not None or payload is None:
        return f"{profile.id}: {error}"

    missing = [
        node
        for node in (profile.positive_node, profile.negative_node, profile.seed_node)
        if node not in payload
    ]
    if missing:
        return f"{profile.id}: Node-IDs fehlen: {', '.join(missing)}"

    if profile.reference_configured:
        node = payload.get(profile.reference_node)
        if not isinstance(node, dict):
            return f"{profile.id}: Referenzbild-Node fehlt: {profile.reference_node}"
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or profile.reference_input_key not in inputs:
            return (
                f"{profile.id}: Referenzbild-Node {profile.reference_node} hat keinen "
                f"Input {profile.reference_input_key!r}"
            )
    return None


def _check_profile_catalog(settings: AppSettings) -> DiagnosticResult | None:
    path = settings.profile_catalog_path
    if path is None:
        return None
    if not path.exists():
        return DiagnosticResult("Workflow-Profile", False, f"Katalog fehlt: {path}")
    try:
        catalog = load_workflow_catalog(path)
    except (OSError, ValueError) as exc:
        return DiagnosticResult("Workflow-Profile", False, f"Katalog ungültig: {exc}")

    enabled = [profile for profile in catalog.profiles if profile.enabled]
    if not enabled:
        return DiagnosticResult("Workflow-Profile", False, "Katalog enthält keine aktiven Profile")
    ids = [profile.id for profile in enabled]
    if len(ids) != len(set(ids)):
        return DiagnosticResult("Workflow-Profile", False, "Profil-IDs müssen eindeutig sein")

    errors = [error for profile in enabled if (error := _validate_profile(profile))]
    if errors:
        return DiagnosticResult("Workflow-Profile", False, "; ".join(errors[:4]))

    capabilities = sorted({kind for profile in enabled for kind in profile.kinds})
    return DiagnosticResult(
        "Workflow-Profile",
        True,
        f"{len(enabled)} Profil(e) bereit: {', '.join(capabilities)}",
    )


def _check_legacy_workflow(settings: AppSettings) -> DiagnosticResult:
    path = settings.workflow_path
    if path is None:
        return DiagnosticResult("ComfyUI-Workflow", False, "Kein API-Workflow konfiguriert")
    payload, error = _load_json_object(path)
    if error is not None or payload is None:
        return DiagnosticResult("ComfyUI-Workflow", False, error or "Workflow ungültig")

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

    if settings.media_reference_enabled:
        node_id = settings.media_reference_node.strip()
        input_key = settings.media_reference_input_key.strip()
        if not node_id:
            return DiagnosticResult(
                "ComfyUI-Workflow",
                False,
                "Referenzbild-Continuity ist aktiv, aber keine Referenzbild-Node ist konfiguriert",
            )
        node = payload.get(node_id)
        if not isinstance(node, dict):
            return DiagnosticResult(
                "ComfyUI-Workflow",
                False,
                f"Referenzbild-Node fehlt: {node_id}",
            )
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or not input_key or input_key not in inputs:
            return DiagnosticResult(
                "ComfyUI-Workflow",
                False,
                f"Referenzbild-Node {node_id} hat keinen Input {input_key!r}",
            )

    return DiagnosticResult("ComfyUI-Workflow", True, f"Workflow geladen: {path.name}")


def _check_workflow(settings: AppSettings) -> DiagnosticResult:
    if not settings.media_enabled:
        return DiagnosticResult("ComfyUI-Workflow", True, "Mediengenerierung ist deaktiviert")
    profile_result = _check_profile_catalog(settings)
    if profile_result is not None:
        return profile_result
    return _check_legacy_workflow(settings)


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
