from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

import httpx

from app.ai.backend_health import classify_ollama_failure
from app.media.capabilities import inspect_workflow_catalog
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


def _get(
    url: str,
    *,
    timeout: float,
    client: httpx.Client | None,
) -> httpx.Response:
    if client is not None:
        return client.get(url, timeout=timeout)
    return httpx.get(url, timeout=timeout)


def _post(
    url: str,
    *,
    payload: dict[str, object],
    timeout: float,
    client: httpx.Client | None,
) -> httpx.Response:
    if client is not None:
        return client.post(url, json=payload, timeout=timeout)
    return httpx.post(url, json=payload, timeout=timeout)


def _check_model(
    settings: AppSettings,
    timeout: float,
    client: httpx.Client | None,
) -> DiagnosticResult:
    try:
        response = _get(
            f"{settings.model_url.rstrip('/')}/api/tags",
            timeout=timeout,
            client=client,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, httpx.HTTPError):
            detail = classify_ollama_failure(exc, model_name=settings.model_name).message()
        else:
            detail = f"Ollama antwortet, aber die Modellliste ist kein gültiges JSON: {exc}"
        return DiagnosticResult("Sprachmodell", False, detail)

    models = payload.get("models", []) if isinstance(payload, dict) else []
    names = {
        str(item.get("name") or item.get("model") or "")
        for item in models
        if isinstance(item, dict)
    }
    if settings.model_name in names:
        return DiagnosticResult("Sprachmodell", True, f"{settings.model_name} ist installiert")
    if names:
        return DiagnosticResult(
            "Sprachmodell",
            False,
            f"Ollama läuft, aber {settings.model_name!r} wurde nicht gefunden. Installiert: {', '.join(sorted(names))}",
        )
    return DiagnosticResult(
        "Sprachmodell",
        False,
        "Ollama läuft, meldet aber keine installierten Modelle. Prüfe `ollama list`.",
    )


def _check_model_inference(
    settings: AppSettings,
    timeout: float,
    inventory: DiagnosticResult,
    client: httpx.Client | None,
) -> DiagnosticResult:
    if not inventory.ok:
        return DiagnosticResult(
            "Modell-Inferenz",
            False,
            "Nicht ausgeführt, weil der Ollama-Endpoint oder das konfigurierte Modell noch nicht bereit ist.",
        )

    inference_timeout = max(45.0, timeout)
    payload: dict[str, object] = {
        "model": settings.model_name,
        "messages": [
            {
                "role": "user",
                "content": "Antworte kurz mit OK. Dies ist nur ein lokaler technischer Funktionstest.",
            }
        ],
        "stream": False,
        "keep_alive": "5m",
        "options": {
            "temperature": 0,
            "num_predict": 8,
        },
    }
    try:
        response = _post(
            f"{settings.model_url.rstrip('/')}/api/chat",
            payload=payload,
            timeout=inference_timeout,
            client=client,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        failure = classify_ollama_failure(
            exc,
            model_name=settings.model_name,
            timeout_seconds=inference_timeout,
        )
        return DiagnosticResult("Modell-Inferenz", False, failure.message())
    except ValueError as exc:
        return DiagnosticResult(
            "Modell-Inferenz",
            False,
            f"Ollama antwortete auf die Inferenz, aber nicht mit gültigem JSON: {exc}",
        )

    message = data.get("message") if isinstance(data, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        error = data.get("error") if isinstance(data, dict) else None
        detail = (
            f"Ollama meldete: {' '.join(error.split())}"
            if isinstance(error, str) and error.strip()
            else "Ollama lieferte eine leere oder ungültige Chat-Antwort."
        )
        return DiagnosticResult("Modell-Inferenz", False, detail)

    return DiagnosticResult(
        "Modell-Inferenz",
        True,
        f"{settings.model_name} hat eine echte lokale Mini-Inferenz erfolgreich abgeschlossen.",
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


def _validate_prompt_seed_mapping(
    payload: dict[str, object],
    positive_node: str,
    negative_node: str,
    seed_node: str,
) -> str | None:
    for label, node_id in (
        ("Positive Prompt", positive_node),
        ("Negative Prompt", negative_node),
    ):
        node = payload.get(node_id)
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict) or not any(key in inputs for key in ("text", "prompt")):
            return f"{label} Node {node_id} hat keinen text/prompt-Input"

    seed = payload.get(seed_node)
    seed_inputs = seed.get("inputs") if isinstance(seed, dict) else None
    if not isinstance(seed_inputs, dict) or not any(
        key in seed_inputs for key in ("seed", "noise_seed")
    ):
        return f"Seed Node {seed_node} hat keinen seed/noise_seed-Input"
    return None


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

    mapping_error = _validate_prompt_seed_mapping(
        payload,
        profile.positive_node,
        profile.negative_node,
        profile.seed_node,
    )
    if mapping_error:
        return f"{profile.id}: {mapping_error}"

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


def _check_media_capabilities(settings: AppSettings) -> DiagnosticResult | None:
    path = settings.profile_catalog_path
    if path is None:
        return None
    if not path.exists():
        return DiagnosticResult("Medien-Fähigkeiten", False, f"Katalog fehlt: {path}")
    try:
        catalog = load_workflow_catalog(path)
    except (OSError, ValueError) as exc:
        return DiagnosticResult("Medien-Fähigkeiten", False, f"Katalog ungültig: {exc}")

    capabilities = inspect_workflow_catalog(catalog)
    enabled = [item for item in capabilities if item.enabled]
    if not enabled:
        return DiagnosticResult("Medien-Fähigkeiten", False, "Keine aktiven Workflow-Profile")

    lines: list[str] = []
    all_ready = True
    for capability in enabled:
        all_ready = all_ready and capability.runnable
        line = capability.summary()
        evidence = "/".join(capability.output_evidence) or "kein eindeutiger Output erkannt"
        line += f" · Output-Evidenz: {evidence}"
        if capability.missing_render_controls:
            line += " · Workflow-Defaults: " + ",".join(capability.missing_render_controls)
        if capability.error:
            line += f" · Fehler: {capability.error}"
        if capability.warnings:
            line += " · Hinweise: " + " | ".join(capability.warnings[:3])
        lines.append(line)

    ready_kinds = sorted(
        {
            kind
            for capability in enabled
            if capability.runnable
            for kind in capability.runnable_kinds
        }
    )
    prefix = f"Bereit: {', '.join(ready_kinds) if ready_kinds else 'keine Medienart'}"
    return DiagnosticResult(
        "Medien-Fähigkeiten",
        all_ready and bool(ready_kinds),
        prefix + "\n" + "\n".join(lines),
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

    mapping_error = _validate_prompt_seed_mapping(
        payload,
        settings.media_positive_node,
        settings.media_negative_node,
        settings.media_seed_node,
    )
    if mapping_error:
        return DiagnosticResult("ComfyUI-Workflow", False, mapping_error)

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


def _check_comfyui(
    settings: AppSettings,
    timeout: float,
    client: httpx.Client | None,
) -> DiagnosticResult:
    if not settings.media_enabled:
        return DiagnosticResult("ComfyUI", True, "Mediengenerierung ist deaktiviert")
    try:
        response = _get(
            f"{settings.media_url.rstrip('/')}/system_stats",
            timeout=timeout,
            client=client,
        )
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


def run_diagnostics(
    settings: AppSettings,
    timeout: float = 5.0,
    *,
    client: httpx.Client | None = None,
) -> list[DiagnosticResult]:
    """Run local-only preflight checks, including one real mini model inference."""

    model_inventory = _check_model(settings, timeout, client)
    model_inference = _check_model_inference(settings, timeout, model_inventory, client)
    results = [
        model_inventory,
        model_inference,
        _check_workflow(settings),
    ]
    media_capabilities = _check_media_capabilities(settings)
    if media_capabilities is not None:
        results.append(media_capabilities)
    results.extend(
        [
            _check_comfyui(settings, timeout, client),
            _check_output(settings),
        ]
    )
    return results
