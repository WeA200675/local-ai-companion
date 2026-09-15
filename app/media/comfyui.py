from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.media.profiles import WorkflowProfile
from app.media.rendering import MediaRenderPlan


class ComfyUIError(RuntimeError):
    """Raised when the local ComfyUI backend fails."""


@dataclass(frozen=True, slots=True)
class GeneratedMedia:
    path: Path
    kind: str
    prompt_id: str
    seed: int
    applied_render_parameters: tuple[str, ...] = ()


class ComfyUIClient:
    """Small local ComfyUI API adapter using exported API-format workflows.

    A legacy default workflow can be configured directly. Callers may also pass
    a WorkflowProfile per generation so different local pipelines can share one
    ComfyUI endpoint and output directory.
    """

    _AUTO_INPUT_KEYS = {
        "steps": ("steps",),
        "cfg": ("cfg", "guidance"),
        "denoise": ("denoise",),
        "frames": ("length", "frames", "frame_count", "num_frames"),
        "fps": ("fps", "frame_rate"),
    }

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8188",
        workflow_path: str | Path | None = None,
        positive_node: str = "6",
        negative_node: str = "7",
        seed_node: str = "3",
        reference_node: str = "",
        reference_input_key: str = "image",
        output_dir: str | Path = "data/generated_media",
        timeout: float = 180.0,
        poll_interval: float = 0.8,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.workflow_path = Path(workflow_path) if workflow_path else None
        self.positive_node = positive_node
        self.negative_node = negative_node
        self.seed_node = seed_node
        self.reference_node = reference_node.strip()
        self.reference_input_key = reference_input_key.strip() or "image"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._owns_client = client is None
        self._client = client or httpx.Client(timeout=timeout)

    @property
    def enabled(self) -> bool:
        return bool(self.workflow_path and self.workflow_path.exists())

    @property
    def reference_configured(self) -> bool:
        return bool(self.reference_node and self.reference_input_key)

    def can_run_profile(self, profile: WorkflowProfile) -> bool:
        return profile.enabled and profile.workflow_path.exists()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def is_available(self) -> bool:
        try:
            response = self._client.get(f"{self.base_url}/system_stats")
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def _load_workflow(self, profile: WorkflowProfile | None = None) -> dict[str, Any]:
        path = profile.workflow_path if profile is not None else self.workflow_path
        if not path:
            raise ComfyUIError("No ComfyUI workflow configured")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ComfyUIError(f"Could not load workflow: {exc}") from exc
        if not isinstance(value, dict):
            raise ComfyUIError("ComfyUI workflow must be a JSON object")
        return value

    @staticmethod
    def _set_text(workflow: dict[str, Any], node_id: str, text: str) -> None:
        try:
            inputs = workflow[node_id]["inputs"]
        except (KeyError, TypeError) as exc:
            raise ComfyUIError(f"Prompt node {node_id!r} is missing from workflow") from exc
        for key in ("text", "prompt"):
            if key in inputs:
                inputs[key] = text
                return
        raise ComfyUIError(f"Prompt node {node_id!r} has no text/prompt input")

    @staticmethod
    def _set_seed(workflow: dict[str, Any], node_id: str, seed: int) -> None:
        try:
            inputs = workflow[node_id]["inputs"]
        except (KeyError, TypeError) as exc:
            raise ComfyUIError(f"Seed node {node_id!r} is missing from workflow") from exc
        for key in ("seed", "noise_seed"):
            if key in inputs:
                inputs[key] = seed
                return
        raise ComfyUIError(f"Seed node {node_id!r} has no seed/noise_seed input")

    @staticmethod
    def _set_reference(
        workflow: dict[str, Any],
        node_id: str,
        input_key: str,
        image_name: str,
    ) -> None:
        try:
            inputs = workflow[node_id]["inputs"]
        except (KeyError, TypeError) as exc:
            raise ComfyUIError(f"Reference node {node_id!r} is missing from workflow") from exc
        if not isinstance(inputs, dict) or input_key not in inputs:
            raise ComfyUIError(
                f"Reference node {node_id!r} has no input named {input_key!r}"
            )
        inputs[input_key] = image_name

    @staticmethod
    def _is_literal_number(value: object) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _set_numeric_binding(
        cls,
        workflow: dict[str, Any],
        node_id: str,
        input_key: str,
        value: int | float,
        *,
        strict: bool,
    ) -> bool:
        node = workflow.get(node_id)
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict) or input_key not in inputs:
            if strict:
                raise ComfyUIError(
                    f"Render binding {node_id!r}.{input_key!r} is missing from workflow"
                )
            return False
        current = inputs[input_key]
        if not cls._is_literal_number(current):
            if strict:
                raise ComfyUIError(
                    f"Render binding {node_id!r}.{input_key!r} is not a literal numeric input"
                )
            return False
        inputs[input_key] = value
        return True

    @staticmethod
    def _render_values(plan: MediaRenderPlan) -> dict[str, int | float]:
        return {
            "width": plan.width,
            "height": plan.height,
            "steps": plan.steps,
            "cfg": plan.cfg,
            "denoise": plan.denoise,
            "frames": plan.frames,
            "fps": plan.fps,
        }

    @classmethod
    def _auto_dimension_node(cls, workflow: dict[str, Any]) -> str | None:
        candidates: list[tuple[int, str]] = []
        for node_id, node in workflow.items():
            if not isinstance(node_id, str) or not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            if not (
                "width" in inputs
                and "height" in inputs
                and cls._is_literal_number(inputs["width"])
                and cls._is_literal_number(inputs["height"])
            ):
                continue
            class_type = str(node.get("class_type") or "").casefold()
            preferred = int(any(token in class_type for token in ("latent", "empty", "video")))
            candidates.append((preferred, node_id))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][1]

    @classmethod
    def _auto_scalar_binding(
        cls,
        workflow: dict[str, Any],
        parameter: str,
        *,
        preferred_node: str = "",
    ) -> tuple[str, str] | None:
        keys = cls._AUTO_INPUT_KEYS.get(parameter, ())
        node_order: list[str] = []
        if preferred_node:
            node_order.append(preferred_node)
        node_order.extend(
            node_id
            for node_id in sorted(workflow)
            if isinstance(node_id, str) and node_id not in node_order
        )
        for node_id in node_order:
            node = workflow.get(node_id)
            inputs = node.get("inputs") if isinstance(node, dict) else None
            if not isinstance(inputs, dict):
                continue
            for key in keys:
                if key in inputs and cls._is_literal_number(inputs[key]):
                    return node_id, key
        return None

    @classmethod
    def _apply_render_plan(
        cls,
        workflow: dict[str, Any],
        plan: MediaRenderPlan,
        *,
        profile: WorkflowProfile | None,
        seed_node: str,
    ) -> list[str]:
        values = cls._render_values(plan)
        applied: list[str] = []
        explicit = profile.render_bindings if profile is not None else {}

        for parameter, binding in explicit.items():
            if parameter not in values:
                continue
            if cls._set_numeric_binding(
                workflow,
                binding.node,
                binding.input_key,
                values[parameter],
                strict=True,
            ):
                applied.append(parameter)

        dimension_node = cls._auto_dimension_node(workflow)
        for parameter in ("width", "height"):
            if parameter in applied or dimension_node is None:
                continue
            if cls._set_numeric_binding(
                workflow,
                dimension_node,
                parameter,
                values[parameter],
                strict=False,
            ):
                applied.append(parameter)

        for parameter in ("steps", "cfg", "denoise", "frames", "fps"):
            if parameter in applied:
                continue
            preferred = seed_node if parameter in {"steps", "cfg", "denoise"} else ""
            binding = cls._auto_scalar_binding(
                workflow,
                parameter,
                preferred_node=preferred,
            )
            if binding is None:
                continue
            node_id, input_key = binding
            if cls._set_numeric_binding(
                workflow,
                node_id,
                input_key,
                values[parameter],
                strict=False,
            ):
                applied.append(parameter)
        return applied

    def _nodes_for_profile(
        self, profile: WorkflowProfile | None
    ) -> tuple[str, str, str, str, str]:
        if profile is None:
            return (
                self.positive_node,
                self.negative_node,
                self.seed_node,
                self.reference_node,
                self.reference_input_key,
            )
        return (
            profile.positive_node,
            profile.negative_node,
            profile.seed_node,
            profile.reference_node,
            profile.reference_input_key,
        )

    def build_workflow(
        self,
        positive: str,
        negative: str,
        *,
        seed: int,
        reference_name: str | None = None,
        profile: WorkflowProfile | None = None,
        render_plan: MediaRenderPlan | None = None,
        render_trace: list[str] | None = None,
    ) -> dict[str, Any]:
        workflow = self._load_workflow(profile)
        positive_node, negative_node, seed_node, reference_node, reference_input = (
            self._nodes_for_profile(profile)
        )
        self._set_text(workflow, positive_node, positive)
        self._set_text(workflow, negative_node, negative)
        self._set_seed(workflow, seed_node, seed)
        if reference_name:
            if not reference_node or not reference_input:
                raise ComfyUIError("Reference image supplied but no reference node is configured")
            self._set_reference(workflow, reference_node, reference_input, reference_name)
        if render_plan is not None:
            applied = self._apply_render_plan(
                workflow,
                render_plan,
                profile=profile,
                seed_node=seed_node,
            )
            if render_trace is not None:
                render_trace.extend(applied)
        return workflow

    def _upload_reference(self, path: Path) -> str:
        if not path.exists() or not path.is_file():
            raise ComfyUIError(f"Reference image does not exist: {path}")
        try:
            with path.open("rb") as handle:
                response = self._client.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (path.name, handle, "application/octet-stream")},
                    data={"type": "input", "overwrite": "true"},
                )
            response.raise_for_status()
            payload = response.json()
        except (OSError, httpx.HTTPError, ValueError) as exc:
            raise ComfyUIError(f"Could not upload reference image to ComfyUI: {exc}") from exc

        if not isinstance(payload, dict):
            raise ComfyUIError("ComfyUI returned an invalid reference upload response")
        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ComfyUIError("ComfyUI reference upload did not return a file name")
        subfolder = payload.get("subfolder")
        if isinstance(subfolder, str) and subfolder.strip():
            return f"{subfolder.strip().strip('/')}/{name.strip()}"
        return name.strip()

    def generate(
        self,
        positive: str,
        negative: str,
        *,
        seed: int | None = None,
        reference_path: str | Path | None = None,
        profile: WorkflowProfile | None = None,
        render_plan: MediaRenderPlan | None = None,
    ) -> GeneratedMedia:
        if profile is not None:
            if not self.can_run_profile(profile):
                raise ComfyUIError(f"Workflow profile {profile.id!r} is not available")
        elif not self.enabled:
            raise ComfyUIError("ComfyUI media generation is not configured")

        actual_seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**63 - 1)
        reference_name = None
        if reference_path is not None:
            reference_node = profile.reference_node if profile is not None else self.reference_node
            reference_input = (
                profile.reference_input_key if profile is not None else self.reference_input_key
            )
            if not reference_node or not reference_input:
                raise ComfyUIError("Reference continuity is enabled but no workflow node is configured")
            reference_name = self._upload_reference(Path(reference_path))

        applied_render_parameters: list[str] = []
        workflow = self.build_workflow(
            positive,
            negative,
            seed=actual_seed,
            reference_name=reference_name,
            profile=profile,
            render_plan=render_plan,
            render_trace=applied_render_parameters,
        )

        try:
            response = self._client.post(f"{self.base_url}/prompt", json={"prompt": workflow})
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ComfyUIError(f"Could not queue ComfyUI workflow: {exc}") from exc

        prompt_id = payload.get("prompt_id")
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ComfyUIError("ComfyUI did not return a prompt_id")

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                history_response = self._client.get(f"{self.base_url}/history/{prompt_id}")
                history_response.raise_for_status()
                history = history_response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ComfyUIError(f"Could not read ComfyUI history: {exc}") from exc

            entry = history.get(prompt_id) if isinstance(history, dict) else None
            if isinstance(entry, dict):
                output = self._first_output_file(entry)
                if output is not None:
                    path = self._download_output(output)
                    return GeneratedMedia(
                        path=path,
                        kind=path.suffix.lower().lstrip(".") or "image",
                        prompt_id=prompt_id,
                        seed=actual_seed,
                        applied_render_parameters=tuple(applied_render_parameters),
                    )
            time.sleep(self.poll_interval)

        raise ComfyUIError("Timed out waiting for ComfyUI output")

    @staticmethod
    def _first_output_file(entry: dict[str, Any]) -> dict[str, str] | None:
        outputs = entry.get("outputs")
        if not isinstance(outputs, dict):
            return None
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for key in ("images", "gifs", "videos"):
                files = node_output.get(key)
                if isinstance(files, list) and files and isinstance(files[0], dict):
                    item = files[0]
                    filename = item.get("filename")
                    if isinstance(filename, str):
                        return {
                            "filename": filename,
                            "subfolder": str(item.get("subfolder", "")),
                            "type": str(item.get("type", "output")),
                        }
        return None

    def _download_output(self, item: dict[str, str]) -> Path:
        filename = item["filename"]
        params = (
            f"filename={quote(filename)}&subfolder={quote(item['subfolder'])}"
            f"&type={quote(item['type'])}"
        )
        try:
            response = self._client.get(f"{self.base_url}/view?{params}")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ComfyUIError(f"Could not download ComfyUI output: {exc}") from exc

        stamp = int(time.time() * 1000)
        suffix = Path(filename).suffix or ".png"
        target = self.output_dir / f"generated_{stamp}{suffix}"
        target.write_bytes(response.content)
        return target
