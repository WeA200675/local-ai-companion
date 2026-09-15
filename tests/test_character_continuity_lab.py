from __future__ import annotations

import json

import httpx
import pytest

from app.media.character_continuity_lab import (
    CharacterContinuityLabError,
    default_character_continuity_probes,
    run_character_continuity_suite,
)
from app.media.continuity import CharacterProfile
from app.media.hardware import MediaHardwareBudget
from app.media.profiles import WorkflowProfile
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _workflow() -> dict[str, object]:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": "placeholder.png"}},
        "2": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["1", 0], "vae": ["10", 2]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 1,
                "steps": 20,
                "cfg": 6.5,
                "denoise": 1.0,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["2", 0],
                "model": ["10", 0],
            },
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "local.safetensors"}},
        "11": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["3", 0], "vae": ["10", 2]},
        },
        "12": {
            "class_type": "SaveImage",
            "inputs": {"images": ["11", 0], "filename_prefix": "continuity-test"},
        },
    }


def _budget() -> MediaHardwareBudget:
    return MediaHardwareBudget(
        tier="medium",
        device_type="cuda",
        device_name="test gpu",
        image_megapixel_cap=0.65,
        motion_megapixel_cap=0.30,
        max_motion_frames=32,
        max_quality="balanced",
        motion_recommended=True,
        source="test",
    )


def test_probe_suite_changes_framing_but_keeps_character_key() -> None:
    probes = default_character_continuity_probes("persona-main")

    assert [probe.id for probe in probes] == ["portrait", "full_body", "environment"]
    assert {probe.intent.continuity_key for probe in probes} == {"persona-main"}
    assert {probe.focus_tag for probe in probes} == {"portrait", "full_body", "environment"}
    assert all(probe.intent.kind == "image" for probe in probes)


def test_suite_uploads_reference_renders_and_records_character_metadata(tmp_path) -> None:
    workflow_path = tmp_path / "reference-workflow.json"
    workflow_path.write_text(json.dumps(_workflow()), encoding="utf-8")
    reference = tmp_path / "reference.png"
    reference.write_bytes(b"reference-image")

    profile = WorkflowProfile(
        id="character-reference",
        label="Character Reference",
        workflow=str(workflow_path),
        kinds=["image"],
        positive_node="6",
        negative_node="7",
        seed_node="3",
        reference_node="1",
        reference_input_key="image",
        prefer_for_character=True,
        checkpoint_name="local.safetensors",
        routing_tags=["character"],
    )
    character = CharacterProfile(
        key="persona-main",
        seed=12345,
        appearance_prompt="adult woman, shoulder-length dark hair, angular face",
        reference_media_id=7,
        reference_media_path=str(reference),
    )
    store = StateStore(make_session_factory(tmp_path / "companion.sqlite3"))
    store.save_character_profile(character)
    settings = AppSettings(
        media_enabled=True,
        media_url="http://local",
        media_output_dir=str(tmp_path / "generated"),
    )
    probes = default_character_continuity_probes(character.key)[:1]
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/upload/image":
            seen["uploaded"] = True
            return httpx.Response(200, json={"name": "reference.png", "subfolder": "", "type": "input"})
        if request.url.path == "/prompt":
            payload = json.loads(request.content.decode("utf-8"))
            prompt = payload["prompt"]
            seen["reference_input"] = prompt["1"]["inputs"]["image"]
            seen["positive"] = prompt["6"]["inputs"]["text"]
            seen["negative"] = prompt["7"]["inputs"]["text"]
            seen["seed"] = prompt["3"]["inputs"]["seed"]
            return httpx.Response(200, json={"prompt_id": "continuity-1"})
        if request.url.path == "/history/continuity-1":
            return httpx.Response(
                200,
                json={
                    "continuity-1": {
                        "outputs": {
                            "12": {
                                "images": [
                                    {
                                        "filename": "continuity.png",
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        if request.url.path == "/view":
            return httpx.Response(200, content=b"generated-image")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    results = run_character_continuity_suite(
        settings,
        profile,
        character,
        store,
        probes=probes,
        hardware_budget=_budget(),
        http_client=http_client,
    )
    http_client.close()

    assert len(results) == 1
    assert results[0].generated.path.exists()
    assert seen["uploaded"] is True
    assert seen["reference_input"] == "reference.png"
    assert "shoulder-length dark hair" in str(seen["positive"])
    assert "child" in str(seen["negative"])

    events = store.list_media_events(limit=10)
    assert len(events) == 1
    event = events[0]
    assert event["continuity_key"] == "persona-main"
    assert event["intent"]["workflow_profile"] == "character-reference"
    assert event["intent"]["workflow_checkpoint"] == "local.safetensors"
    assert event["intent"]["workflow_focus_tags"] == ["character", "portrait"]
    assert event["intent"]["character_continuity_probe"] == "portrait"
    assert event["intent"]["character_reference_media_id"] == 7

    updated_character = store.load_character_profile("persona-main")
    assert updated_character.generation_count == 1
    assert updated_character.last_media_path == str(results[0].generated.path)


def test_suite_requires_existing_reference_and_reference_capable_profile(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(json.dumps(_workflow()), encoding="utf-8")
    store = StateStore(make_session_factory(tmp_path / "companion.sqlite3"))
    settings = AppSettings(media_output_dir=str(tmp_path / "generated"))
    character = CharacterProfile(key="persona-main", seed=123)

    profile = WorkflowProfile(
        id="no-reference",
        workflow=str(workflow_path),
        positive_node="6",
        negative_node="7",
        seed_node="3",
    )
    with pytest.raises(CharacterContinuityLabError, match="Referenzbild-Eingang"):
        run_character_continuity_suite(settings, profile, character, store, hardware_budget=_budget())

    profile = profile.model_copy(update={"reference_node": "1", "reference_input_key": "image"})
    with pytest.raises(CharacterContinuityLabError, match="Referenzbild"):
        run_character_continuity_suite(settings, profile, character, store, hardware_budget=_budget())
