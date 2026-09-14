from __future__ import annotations

import json

import httpx

from app.diagnostics import run_diagnostics
from app.media.comfyui import ComfyUIClient
from app.media.profiles import choose_workflow_profile, load_workflow_catalog
from app.settings import AppSettings


def _write_workflow(path, *, positive="6", negative="7", seed="3", reference=None):
    payload = {
        positive: {"inputs": {"text": "positive"}},
        negative: {"inputs": {"text": "negative"}},
        seed: {"inputs": {"seed": 1}},
    }
    if reference is not None:
        payload[reference] = {"inputs": {"image": "placeholder.png"}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_catalog_resolves_relative_paths_and_routes_by_kind_and_character(tmp_path) -> None:
    still = tmp_path / "still.json"
    character = tmp_path / "character.json"
    motion = tmp_path / "motion.json"
    _write_workflow(still)
    _write_workflow(character, reference="12")
    _write_workflow(motion)

    catalog_path = tmp_path / "profiles.json"
    catalog_path.write_text(
        json.dumps(
            {
                "version": 1,
                "profiles": [
                    {
                        "id": "still",
                        "label": "Standard image",
                        "kinds": ["image"],
                        "workflow": "still.json",
                        "priority": 5,
                    },
                    {
                        "id": "character",
                        "label": "Character detail",
                        "kinds": ["image"],
                        "workflow": "character.json",
                        "reference_node": "12",
                        "reference_input_key": "image",
                        "prefer_for_character": True,
                        "priority": 0,
                    },
                    {
                        "id": "motion",
                        "label": "Short motion",
                        "kinds": ["gif", "video"],
                        "workflow": "motion.json",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    catalog = load_workflow_catalog(catalog_path)
    assert catalog.profiles[0].workflow_path == still.resolve()

    standard = choose_workflow_profile(
        catalog.profiles,
        kind="image",
        character_focus=False,
        reference_available=False,
    )
    character_pick = choose_workflow_profile(
        catalog.profiles,
        kind="image",
        character_focus=True,
        reference_available=True,
    )
    motion_pick = choose_workflow_profile(
        catalog.profiles,
        kind="video",
        character_focus=False,
        reference_available=False,
    )

    assert standard is not None and standard.id == "still"
    assert character_pick is not None and character_pick.id == "character"
    assert motion_pick is not None and motion_pick.id == "motion"


def test_comfyui_build_workflow_uses_profile_specific_nodes(tmp_path) -> None:
    workflow = tmp_path / "custom.json"
    _write_workflow(workflow, positive="20", negative="21", seed="22", reference="23")
    catalog_path = tmp_path / "profiles.json"
    catalog_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "character",
                        "kinds": ["image"],
                        "workflow": "custom.json",
                        "positive_node": "20",
                        "negative_node": "21",
                        "seed_node": "22",
                        "reference_node": "23",
                        "reference_input_key": "image",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    profile = load_workflow_catalog(catalog_path).profiles[0]
    client = ComfyUIClient(output_dir=tmp_path / "generated")
    built = client.build_workflow(
        "new positive",
        "new negative",
        seed=42,
        reference_name="reference.png",
        profile=profile,
    )
    client.close()

    assert built["20"]["inputs"]["text"] == "new positive"
    assert built["21"]["inputs"]["text"] == "new negative"
    assert built["22"]["inputs"]["seed"] == 42
    assert built["23"]["inputs"]["image"] == "reference.png"


def test_diagnostics_accept_profile_catalog_without_legacy_workflow(monkeypatch, tmp_path) -> None:
    still = tmp_path / "still.json"
    motion = tmp_path / "motion.json"
    _write_workflow(still)
    _write_workflow(motion)
    catalog = tmp_path / "profiles.json"
    catalog.write_text(
        json.dumps(
            {
                "profiles": [
                    {"id": "still", "kinds": ["image"], "workflow": "still.json"},
                    {"id": "motion", "kinds": ["video"], "workflow": "motion.json"},
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_get(url: str, timeout: float):
        request = httpx.Request("GET", url)
        if url.endswith("/api/tags"):
            return httpx.Response(200, request=request, json={"models": [{"name": "local-model"}]})
        if url.endswith("/system_stats"):
            return httpx.Response(200, request=request, json={})
        raise AssertionError(url)

    monkeypatch.setattr("app.diagnostics.httpx.get", fake_get)
    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow="",
        media_profile_catalog=str(catalog),
        media_output_dir=str(tmp_path / "generated"),
    )
    results = run_diagnostics(settings, timeout=0.1)
    by_name = {result.name: result for result in results}

    assert by_name["Workflow-Profile"].ok is True
    assert "image" in by_name["Workflow-Profile"].detail
    assert "video" in by_name["Workflow-Profile"].detail
