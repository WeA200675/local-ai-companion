from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.media.profiles import RoutingFocus, WorkflowCatalog, WorkflowProfile
from app.memory.store import StateStore

_PROFILE_POLICY_KEY = "media_workflow_profile_policy"


class WorkflowProfileOverride(BaseModel):
    """User-owned runtime routing overrides kept outside workflow catalog files."""

    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=-100, le=100)
    prefer_for_character: bool | None = None
    routing_tags: list[RoutingFocus] | None = None
    render_quality: Literal["draft", "balanced", "high"] | None = None

    @field_validator("routing_tags")
    @classmethod
    def _unique_tags(
        cls, value: list[RoutingFocus] | None
    ) -> list[RoutingFocus] | None:
        return None if value is None else list(dict.fromkeys(value))

    @property
    def is_empty(self) -> bool:
        return all(
            value is None
            for value in (
                self.enabled,
                self.priority,
                self.prefer_for_character,
                self.routing_tags,
                self.render_quality,
            )
        )


class WorkflowProfilePolicy(BaseModel):
    revision: int = Field(default=1, ge=1)
    overrides: dict[str, WorkflowProfileOverride] = Field(default_factory=dict)


class WorkflowProfilePolicyRepository:
    """Persist user routing choices without modifying imported ComfyUI catalogs."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> WorkflowProfilePolicy:
        payload = self.store._load_app_state(_PROFILE_POLICY_KEY)  # noqa: SLF001
        if payload is None:
            return WorkflowProfilePolicy()
        try:
            return WorkflowProfilePolicy.model_validate_json(payload)
        except ValueError:
            return WorkflowProfilePolicy()

    def save(self, policy: WorkflowProfilePolicy) -> WorkflowProfilePolicy:
        clean = {
            profile_id: override
            for profile_id, override in policy.overrides.items()
            if profile_id.strip() and not override.is_empty
        }
        stored = policy.model_copy(
            update={"revision": policy.revision + 1, "overrides": clean},
            deep=True,
        )
        self.store._save_app_state(_PROFILE_POLICY_KEY, stored.model_dump_json())  # noqa: SLF001
        return stored

    def override_for(self, profile_id: str) -> WorkflowProfileOverride | None:
        return self.load().overrides.get(profile_id)

    def set_override(
        self,
        profile_id: str,
        override: WorkflowProfileOverride,
    ) -> WorkflowProfilePolicy:
        key = profile_id.strip()
        if not key:
            raise ValueError("Workflow profile id must not be blank")
        policy = self.load()
        overrides = dict(policy.overrides)
        if override.is_empty:
            overrides.pop(key, None)
        else:
            overrides[key] = override.model_copy(deep=True)
        return self.save(policy.model_copy(update={"overrides": overrides}, deep=True))

    def clear_override(self, profile_id: str) -> WorkflowProfilePolicy:
        return self.set_override(profile_id, WorkflowProfileOverride())


def apply_profile_override(
    profile: WorkflowProfile,
    override: WorkflowProfileOverride | None,
) -> WorkflowProfile:
    if override is None or override.is_empty:
        return profile
    updates: dict[str, object] = {}
    for field in (
        "enabled",
        "priority",
        "prefer_for_character",
        "routing_tags",
        "render_quality",
    ):
        value = getattr(override, field)
        if value is not None:
            updates[field] = value
    return profile.model_copy(update=updates, deep=True) if updates else profile


def apply_catalog_policy(
    catalog: WorkflowCatalog,
    policy: WorkflowProfilePolicy,
) -> WorkflowCatalog:
    profiles = [
        apply_profile_override(profile, policy.overrides.get(profile.id))
        for profile in catalog.profiles
    ]
    return catalog.model_copy(update={"profiles": profiles}, deep=True)


def effective_profile_catalog(
    catalog: WorkflowCatalog,
    repository: WorkflowProfilePolicyRepository | None,
) -> WorkflowCatalog:
    return catalog if repository is None else apply_catalog_policy(catalog, repository.load())
