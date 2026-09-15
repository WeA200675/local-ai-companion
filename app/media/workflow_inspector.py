from __future__ import annotations

from collections import deque
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


def _linked_node_ids(inputs: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for value in inputs.values():
        node_id = _linked_node_id(value)
        if node_id is not None and node_id not in result:
            result.append(node_id)
    return result


def _is_text_node(node: object) -> bool:
    inputs = _node_inputs(node)
    if inputs is None:
        return False
    return any(key in inputs for key in ("text", "prompt"))


def _upstream_text_nodes(
    workflow: dict[str, Any],
    start_node: str,
    *,
    max_depth: int = 12,
) -> list[str]:
    """Return nearest text/prompt nodes reachable upstream from one graph input."""

    queue: deque[tuple[str, int]] = deque([(start_node, 0)])
    seen: set[str] = set()
    found: list[str] = []
    found_depth: int | None = None

    while queue:
        node_id, depth = queue.popleft()
        if node_id in seen or depth > max_depth:
            continue
        seen.add(node_id)
        node = workflow.get(node_id)
        if _is_text_node(node):
            if found_depth is None:
                found_depth = depth
            if depth == found_depth:
                found.append(node_id)
            continue
        if found_depth is not None or depth == max_depth:
            continue
        inputs = _node_inputs(node)
        if inputs is None:
            continue
        for upstream in sorted(_linked_node_ids(inputs)):
            if upstream not in seen:
                queue.append((upstream, depth + 1))
    return found


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

    scored: list[tuple[int, tuple[str, str, str, str], list[str], list[str]]] = []
    for candidate in candidates:
        _sampler_id, positive_start, negative_start, _seed_key = candidate
        positive_nodes = _upstream_text_nodes(workflow, positive_start)
        negative_nodes = _upstream_text_nodes(workflow, negative_start)
        score = int(bool(positive_nodes)) + int(bool(negative_nodes))
        scored.append((score, candidate, positive_nodes, negative_nodes))
    scored.sort(key=lambda item: (-item[0], item[1][0]))
    _score, selected, positive_nodes, negative_nodes = scored[0]
    sampler_id, positive_start, negative_start, seed_key = selected

    if len(candidates) > 1:
        warnings.append(
            f"Mehrere Sampler gefunden ({len(candidates)}). Verwendet wird Node {sampler_id}; bitte vor dem Speichern prüfen."
        )

    positive_node = positive_nodes[0] if positive_nodes else None
    negative_node = negative_nodes[0] if negative_nodes else None
    if positive_node is None:
        warnings.append(
            f"Vom positiven Sampler-Eingang über Node {positive_start} wurde kein eindeutiger text/prompt-Node gefunden."
        )
    elif positive_node != positive_start:
        warnings.append(
            f"Positive Prompt Node {positive_node} wurde über die Zwischen-Node {positive_start} zurückverfolgt."
        )
    if len(positive_nodes) > 1:
        warnings.append(
            f"Mehrere gleich nahe positive Text-Nodes gefunden: {', '.join(positive_nodes)}; verwendet wird {positive_node}."
        )

    if negative_node is None:
        warnings.append(
            f"Vom negativen Sampler-Eingang über Node {negative_start} wurde kein eindeutiger text/prompt-Node gefunden."
        )
    elif negative_node != negative_start:
        warnings.append(
            f"Negative Prompt Node {negative_node} wurde über die Zwischen-Node {negative_start} zurückverfolgt."
        )
    if len(negative_nodes) > 1:
        warnings.append(
            f"Mehrere gleich nahe negative Text-Nodes gefunden: {', '.join(negative_nodes)}; verwendet wird {negative_node}."
        )

    return WorkflowInspection(
        path=path,
        valid=True,
        positive_node=positive_node,
        negative_node=negative_node,
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
