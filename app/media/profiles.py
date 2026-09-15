from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MediaKind = Literal["image", "gif", "video"]
RenderQuality = Literal["draft", "balanced", "high"]
RoutingFocus = Literal[
    "portrait",
    "full_body",
    "detail",
    "environment",
    "character",
    "motion",
]
_RENDER_KEYS = {"width", "height", "steps", "cfg", "denoise", "frames", "fps"}


class WorkflowInputBinding(BaseModel):
    """Explicit mapping from a calculated render value to one ComfyUI input."""

    node: str
    input_key: str

    @field_validator("node", "input_key", mode="before")
    @classmethod
    def _clean(cls, value: object) -> str:
        clean = str(value or "").strip()
        if not clean:
            raise ValueError("binding values must not be blank")
        return clean


class WorkflowProfile(BaseModel):
    """One user-owned ComfyUI workflow plus routing and render metadata."""

    id: str = Field(min_length=1, max_length=80)
    label: str = Field(default="", max_length=120)
    kinds: list[MediaKind] = Field(default_factory=lambda: ["image"])
    workflow: str
    positive_node: str = "6"
    negative_node: str = "7"
    seed_node: str = "3"
    reference_node: str = ""
    reference_input_key: str = "image"
    prefer_for_character: bool = False
    priority: int = Field(default=0, ge=-100, le=100)
    enabled: bool = True

    # Optional provenance/suitability metadata. It never implies a license: the
    # confirmation flag only records an explicit local user confirmation.
    checkpoint_name: str = ""
    checkpoint_license_confirmed: bool = False
    routing_tags: list[RoutingFocus] = Field(default_factory=list)

    # Optional local render policy. Old catalogs remain valid; when no explicit
    # bindings are supplied ComfyUIClient attempts safe common-input detection.
    render_quality: RenderQuality = "balanced"
    max_megapixels: float | None = Field(default=None, ge=0.20, le=8.0)
    render_bindings: dict[str, WorkflowInputBinding] = Field(default_factory=dict)

    @field_validator(
        "id",
        "label",
        "workflow",
        "positive_node",
        "negative_node",
        "seed_node",
        "reference_node",
        "reference_input_key",
        "checkpoint_name",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("kinds", "routing_tags")
    @classmethod
    def _unique_lists(cls, value: list[object]) -> list[object]:
        return list(dict.fromkeys(value))

    @field_validator("kinds")
    @classmethod
    def _nonempty_kinds(cls, value: list[MediaKind]) -> list[MediaKind]:
        return value or ["image"]

    @field_validator("render_bindings")
    @classmethod
    def _valid_render_bindings(
        cls, value: dict[str, WorkflowInputBinding]
    ) -> dict[str, WorkflowInputBinding]:
        unsupported = sorted(set(value) - _RENDER_KEYS)
        if unsupported:
            raise ValueError(f"unsupported render binding(s): {', '.join(unsupported)}")
        return value

    @property
    def workflow_path(self) -> Path:
        return Path(self.workflow).expanduser()

    @property
    def reference_configured(self) -> bool:
        return bool(self.reference_node and self.reference_input_key)

    def resolve_relative_to(self, base_dir: Path) -> "WorkflowProfile":
        path = self.workflow_path
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        return self.model_copy(update={"workflow": str(path)})

    def with_detected_reference_mapping(self) -> "WorkflowProfile":
        """Return an ephemeral runtime profile with a safe detected image loader.

        Explicit catalog mappings always win. Detection is deliberately limited
        to one filename-style LoadImage/ImageLoader node that is connected to the
        selected sampler; ambiguous workflows remain untouched.
        """

        if self.reference_configured or not self.workflow_path.exists():
            return self
        from app.media.workflow_inspector import inspect_workflow_file

        inspection = inspect_workflow_file(self.workflow_path)
        if not inspection.reference_detected:
            return self
        routing_tags = list(self.routing_tags)
        if "character" not in routing_tags:
            routing_tags.append("character")
        return self.model_copy(
            update={
                "reference_node": inspection.reference_node or "",
                "reference_input_key": inspection.reference_input_key or "image",
                "prefer_for_character": True,
                "routing_tags": routing_tags,
            }
        )


class WorkflowCatalog(BaseModel):
    version: int = Field(default=1, ge=1, le=100)
    profiles: list[WorkflowProfile] = Field(default_factory=list)


def load_workflow_catalog(path: str | Path | None) -> WorkflowCatalog:
    """Load a local workflow catalog. Relative workflow paths are catalog-relative.

    A single safe connected LoadImage-style input may be added ephemerally to a
    loaded profile when the catalog did not configure a reference mapping. This
    does not rewrite the user's catalog file and never overrides explicit fields.
    """

    if not path:
        return WorkflowCatalog()
    catalog_path = Path(path).expanduser()
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"version": 1, "profiles": payload}
    catalog = WorkflowCatalog.model_validate(payload)
    resolved = [
        profile.resolve_relative_to(catalog_path.parent).with_detected_reference_mapping()
        for profile in catalog.profiles
    ]
    return catalog.model_copy(update={"profiles": resolved})


def choose_workflow_profile(
    profiles: list[WorkflowProfile],
    *,
    kind: str,
    character_focus: bool,
    reference_available: bool,
    reference_supported_ids: set[str] | None = None,
    focus_tags: set[str] | None = None,
    performance_scores: dict[str, int] | None = None,
) -> WorkflowProfile | None:
    """Deterministically route a media intent to the best enabled local workflow.

    Routing combines explicit priority, reference/character suitability, optional
    declared routing tags, and bounded scores learned from explicit local media
    feedback. Feedback remains soft: it cannot make an invalid workflow runnable.
    """

    requested_focus = focus_tags or set()
    learned = performance_scores or {}
    candidates: list[tuple[int, str, WorkflowProfile]] = []
    for profile in profiles:
        if not profile.enabled or kind not in profile.kinds:
            continue
        if not profile.workflow_path.exists():
            continue

        score = profile.priority
        if character_focus:
            score += 40 if profile.prefer_for_character else 0
        elif profile.prefer_for_character:
            score -= 15
        reference_supported = (
            profile.reference_configured
            if reference_supported_ids is None
            else profile.id in reference_supported_ids
        )
        if reference_available and reference_supported:
            score += 20

        declared = set(profile.routing_tags)
        overlap = declared.intersection(requested_focus)
        if overlap:
            score += 12 * len(overlap)
        elif declared and requested_focus:
            score -= 4

        score += max(-40, min(40, int(learned.get(profile.id, 0))))
        candidates.append((score, profile.id, profile))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]
