from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkflowInspection:
    path: Path | None
    valid: bool
    positive_node: str | None
    negative_node: str | None
    seed_node: str | None
    seed_input_key: str | None
    sampler_node: str | None
    warnings: tuple[str, ...] = ()
    error: str = ""

    @property
    def complete(self) -> bool:
        return bool(
            self.valid
            and self.positive_node
            and self.negative_node
            and self.seed_node
        )


def _node_inputs(node: object) -> dict[str, Any] | None:
    if not isinstance(node, dict):
        return None
    inputs = node.get("inputs")
    return inputs if isinstance(inputs, dict) else None


def _linked_node_id(value: object) -> str | None:
    if not isinstance(value, (list, tuple)) or not value:
        return None
    node_id = value[0]
    if isinstance(node_id, (str, int)):
        return str(node_id)
    return None


def _is_text_node(node: object) -> bool:
    inputs = _node_inputs(node)
    if inputs is None:
        return False
    return any(key in inputs for key in ("text", "prompt"))


def _sampler_candidates(workflow: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    candidates: list[tuple[str, str, str, str]] = []
    for node_id, node in workflow.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            continue
        inputs = _node_inputs(node)
        if inputs is None:
            continue
        class_type = str(node.get("class_type") or "").casefold()
        has_sampler_shape = (
            "positive" in inputs
            and "negative" in inputs
            and ("seed" in inputs or "noise_seed" in inputs)
        )
        if "ksampler" not in class_type and not has_sampler_shape:
            continue
        positive = _linked_node_id(inputs.get("positive"))
        negative = _linked_node_id(inputs.get("negative"))
        seed_key = "seed" if "seed" in inputs else "noise_seed" if "noise_seed" in inputs else ""
        if positive and negative and seed_key:
            candidates.append((node_id, positive, negative, seed_key))
    return candidates


def inspect_api_workflow(workflow: object, *, path: Path | None = None) -> WorkflowInspection:
    if not isinstance(workflow, dict) or not workflow:
        return WorkflowInspection(
            path=path,
            valid=False,
            positive_node=None,
            negative_node=None,
            seed_node=None,
            seed_input_key=None,
            sampler_node=None,
            error="Workflow ist kein nicht-leeres JSON-Objekt im ComfyUI-API-Format.",
        )

    candidates = _sampler_candidates(workflow)
    warnings: list[str] = []
    if not candidates:
        text_nodes = [str(node_id) for node_id, node in workflow.items() if _is_text_node(node)]
        detail = ""
        if text_nodes:
            detail = f" Erkannte Text-Node-Kandidaten: {', '.join(text_nodes[:8])}."
        return WorkflowInspection(
            path=path,
            valid=True,
            positive_node=None,
            negative_node=None,
            seed_node=None,
            seed_input_key=None,
            sampler_node=None,
            warnings=(
                "Kein eindeutig verknüpfter KSampler mit positive/negative und seed/noise_seed gefunden."
                + detail,
            ),
        )

    scored: list[tuple[int, tuple[str, str, str, str]]] = []
    for candidate in candidates:
        sampler_id, positive_id, negative_id, _seed_key = candidate
        score = 0
        if positive_id in workflow and _is_text_node(workflow[positive_id]):
            score += 1
        if negative_id in workflow and _is_text_node(workflow[negative_id]):
            score += 1
        scored.append((score, candidate))
    scored.sort(key=lambda item: (-item[0], item[1][0]))
    _score, selected = scored[0]
    sampler_id, positive_id, negative_id, seed_key = selected

    if len(candidates) > 1:
        warnings.append(
            f"Mehrere Sampler gefunden ({len(candidates)}). Verwendet wird Node {sampler_id}; bitte vor dem Speichern prüfen."
        )
    if positive_id not in workflow or not _is_text_node(workflow.get(positive_id)):
        warnings.append(
            f"Positive-Verknüpfung zeigt auf Node {positive_id}, dort wurde aber kein text/prompt-Input erkannt."
        )
    if negative_id not in workflow or not _is_text_node(workflow.get(negative_id)):
        warnings.append(
            f"Negative-Verknüpfung zeigt auf Node {negative_id}, dort wurde aber kein text/prompt-Input erkannt."
        )

    return WorkflowInspection(
        path=path,
        valid=True,
        positive_node=positive_id,
        negative_node=negative_id,
        seed_node=sampler_id,
        seed_input_key=seed_key,
        sampler_node=sampler_id,
        warnings=tuple(warnings),
    )


def inspect_workflow_file(path: str | Path) -> WorkflowInspection:
    workflow_path = Path(path).expanduser()
    if not workflow_path.exists() or not workflow_path.is_file():
        return WorkflowInspection(
            path=workflow_path,
            valid=False,
            positive_node=None,
            negative_node=None,
            seed_node=None,
            seed_input_key=None,
            sampler_node=None,
            error=f"Workflow-Datei fehlt: {workflow_path}",
        )
    try:
        payload = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return WorkflowInspection(
            path=workflow_path,
            valid=False,
            positive_node=None,
            negative_node=None,
            seed_node=None,
            seed_input_key=None,
            sampler_node=None,
            error=f"Workflow konnte nicht als JSON gelesen werden: {exc}",
        )
    return inspect_api_workflow(payload, path=workflow_path)
