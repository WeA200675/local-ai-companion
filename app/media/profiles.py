from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MediaKind = Literal["image", "gif", "video"]


class WorkflowProfile(BaseModel):
    """One user-owned ComfyUI workflow plus routing metadata."""

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

    @field_validator(
        "id",
        "label",
        "workflow",
        "positive_node",
        "negative_node",
        "seed_node",
        "reference_node",
        "reference_input_key",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("kinds")
    @classmethod
    def _unique_kinds(cls, value: list[MediaKind]) -> list[MediaKind]:
        return list(dict.fromkeys(value or ["image"]))

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


class WorkflowCatalog(BaseModel):
    version: int = Field(default=1, ge=1, le=100)
    profiles: list[WorkflowProfile] = Field(default_factory=list)


def load_workflow_catalog(path: str | Path | None) -> WorkflowCatalog:
    """Load a local workflow catalog. Relative workflow paths are catalog-relative."""

    if not path:
        return WorkflowCatalog()
    catalog_path = Path(path).expanduser()
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"version": 1, "profiles": payload}
    catalog = WorkflowCatalog.model_validate(payload)
    resolved = [profile.resolve_relative_to(catalog_path.parent) for profile in catalog.profiles]
    return catalog.model_copy(update={"profiles": resolved})


def choose_workflow_profile(
    profiles: list[WorkflowProfile],
    *,
    kind: str,
    character_focus: bool,
    reference_available: bool,
) -> WorkflowProfile | None:
    """Deterministically route a media intent to the best enabled local workflow."""

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
        if reference_available and profile.reference_configured:
            score += 20
        candidates.append((score, profile.id, profile))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]
