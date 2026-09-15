from __future__ import annotations

import json
from pathlib import Path

from app.media.profiles import WorkflowCatalog, WorkflowProfile, load_workflow_catalog
from app.settings import AppSettings

_MANAGED_CATALOG_FILENAME = "workflow_profiles.managed.json"


def managed_catalog_path(settings: AppSettings) -> Path:
    """Return the app-owned catalog used for user routing/profile edits."""

    return settings.output_path.parent / _MANAGED_CATALOG_FILENAME


def load_current_catalog(settings: AppSettings) -> WorkflowCatalog:
    path = settings.profile_catalog_path
    return load_workflow_catalog(path) if path is not None else WorkflowCatalog()


def save_managed_catalog(
    settings: AppSettings,
    catalog: WorkflowCatalog,
) -> tuple[Path, AppSettings]:
    """Persist an app-owned copy and point settings at it.

    Imported or generated source catalogs are never modified in place. The loaded
    catalog already contains absolute workflow paths, so the managed copy remains
    stable even when the original catalog used relative paths.
    """

    target = managed_catalog_path(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = catalog.model_dump(mode="json")
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    updated = settings.model_copy(
        update={"media_profile_catalog": str(target)},
        deep=True,
    )
    return target, updated


def replace_profile(
    catalog: WorkflowCatalog,
    profile: WorkflowProfile,
) -> WorkflowCatalog:
    found = False
    profiles: list[WorkflowProfile] = []
    for current in catalog.profiles:
        if current.id == profile.id:
            profiles.append(profile.model_copy(deep=True))
            found = True
        else:
            profiles.append(current.model_copy(deep=True))
    if not found:
        raise KeyError(f"Workflow profile not found: {profile.id}")
    return catalog.model_copy(update={"profiles": profiles}, deep=True)
