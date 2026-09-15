from __future__ import annotations

import json

from app.media.profile_manager import (
    load_current_catalog,
    managed_catalog_path,
    replace_profile,
    save_managed_catalog,
)
from app.settings import AppSettings


def _workflow(path) -> None:
    path.write_text(
        json.dumps(
            {
                "3": {"inputs": {"seed": 1}},
                "6": {"inputs": {"text": "positive"}},
                "7": {"inputs": {"text": "negative"}},
            }
        ),
        encoding="utf-8",
    )


def test_managed_catalog_does_not_overwrite_source_catalog(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    _workflow(workflow)
    source = tmp_path / "source_profiles.json"
    source_payload = {
        "version": 1,
        "profiles": [
            {
                "id": "portrait",
                "label": "Portrait source",
                "workflow": "workflow.json",
                "kinds": ["image"],
                "priority": 5,
                "routing_tags": ["portrait"],
            }
        ],
    }
    source.write_text(json.dumps(source_payload, indent=2), encoding="utf-8")
    before = source.read_text(encoding="utf-8")
    settings = AppSettings(
        media_profile_catalog=str(source),
        media_output_dir=str(tmp_path / "data" / "generated_media"),
    )

    catalog = load_current_catalog(settings)
    original = catalog.profiles[0]
    edited = original.model_copy(
        update={
            "priority": 42,
            "routing_tags": ["portrait", "character"],
            "prefer_for_character": True,
            "render_quality": "high",
        }
    )
    catalog = replace_profile(catalog, edited)
    target, updated = save_managed_catalog(settings, catalog)

    assert source.read_text(encoding="utf-8") == before
    assert target == tmp_path / "data" / "workflow_profiles.managed.json"
    assert target.exists()
    assert updated.media_profile_catalog == str(target)

    managed = load_current_catalog(updated)
    profile = managed.profiles[0]
    assert profile.priority == 42
    assert profile.routing_tags == ["portrait", "character"]
    assert profile.prefer_for_character is True
    assert profile.render_quality == "high"
    assert profile.workflow_path == workflow.resolve()


def test_replace_profile_preserves_other_profiles(tmp_path) -> None:
    workflow_a = tmp_path / "a.json"
    workflow_b = tmp_path / "b.json"
    _workflow(workflow_a)
    _workflow(workflow_b)
    source = tmp_path / "profiles.json"
    source.write_text(
        json.dumps(
            {
                "profiles": [
                    {"id": "a", "workflow": str(workflow_a), "priority": 1},
                    {"id": "b", "workflow": str(workflow_b), "priority": 2},
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = AppSettings(media_profile_catalog=str(source))
    catalog = load_current_catalog(settings)

    changed = catalog.profiles[0].model_copy(update={"enabled": False, "priority": -7})
    result = replace_profile(catalog, changed)

    assert result.profiles[0].enabled is False
    assert result.profiles[0].priority == -7
    assert result.profiles[1].enabled is True
    assert result.profiles[1].priority == 2


def test_managed_catalog_path_is_app_owned_next_to_media_output(tmp_path) -> None:
    settings = AppSettings(media_output_dir=str(tmp_path / "media" / "generated"))
    assert managed_catalog_path(settings) == tmp_path / "media" / "workflow_profiles.managed.json"
