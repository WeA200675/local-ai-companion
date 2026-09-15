from __future__ import annotations

import json

import httpx

from app.media.hardware import MediaHardwareBudget
from app.media.profiles import load_workflow_catalog
from app.media.setup_assistant import (
    generated_catalog_path,
    inspect_for_auto_setup,
    run_workflow_smoke_test,
    save_generated_profile,
)
from app.settings import AppSettings


def _workflow_payload() -> dict[str, object]:
    return {
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old positive", "clip": ["1", 1]},
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "old negative", "clip": ["1", 1]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 1,
                "steps": 20,
                "cfg": 7.0,
                "denoise": 1.0,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 768, "height": 1024, "batch_size": 1},
        },
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "test"},
        },
    }


def test_auto_setup_detects_nodes_kinds_and_render_controls(tmp_path) -> None:
    workflow = tmp_path / "Portrait Workflow.json"
    workflow.write_text(json.dumps(_workflow_payload()), encoding="utf-8")

    setup = inspect_for_auto_setup(workflow)

    assert setup.ready is True
    assert setup.profile is not None
    assert setup.capability is not None
    assert setup.profile.id == "auto-portrait-workflow"
    assert setup.profile.positive_node == "6"
    assert setup.profile.negative_node == "7"
    assert setup.profile.seed_node == "3"
    assert setup.kinds == ("image",)
    assert set(setup.capability.render_controls) >= {"width", "height", "steps", "cfg", "denoise"}


def test_generated_catalog_is_app_owned_and_mergeable(tmp_path) -> None:
    workflow_a = tmp_path / "still.json"
    workflow_b = tmp_path / "second.json"
    workflow_a.write_text(json.dumps(_workflow_payload()), encoding="utf-8")
    workflow_b.write_text(json.dumps(_workflow_payload()), encoding="utf-8")
    setup_a = inspect_for_auto_setup(workflow_a)
    setup_b = inspect_for_auto_setup(workflow_b)
    settings = AppSettings(media_output_dir=str(tmp_path / "generated"))
    target = generated_catalog_path(settings)

    save_generated_profile(setup_a, target)
    save_generated_profile(setup_b, target)
    catalog = load_workflow_catalog(target)

    assert target == tmp_path / "workflow_profiles.generated.json"
    assert {profile.id for profile in catalog.profiles} == {"auto-still", "auto-second"}
    assert all(profile.workflow_path.is_absolute() for profile in catalog.profiles)


def test_smoke_test_queues_real_workflow_and_downloads_result(tmp_path) -> None:
    workflow = tmp_path / "still.json"
    workflow.write_text(json.dumps(_workflow_payload()), encoding="utf-8")
    setup = inspect_for_auto_setup(workflow)
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            payload = json.loads(request.content.decode("utf-8"))
            prompt = payload["prompt"]
            seen["positive"] = prompt["6"]["inputs"]["text"]
            seen["negative"] = prompt["7"]["inputs"]["text"]
            seen["seed"] = prompt["3"]["inputs"]["seed"]
            seen["width"] = prompt["5"]["inputs"]["width"]
            seen["height"] = prompt["5"]["inputs"]["height"]
            return httpx.Response(200, json={"prompt_id": "prompt-1"})
        if request.url.path == "/history/prompt-1":
            return httpx.Response(
                200,
                json={
                    "prompt-1": {
                        "outputs": {
                            "9": {
                                "images": [
                                    {
                                        "filename": "smoke.png",
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
            return httpx.Response(200, content=b"fake-png")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    settings = AppSettings(
        media_enabled=True,
        media_url="http://local",
        media_output_dir=str(tmp_path / "generated"),
    )
    budget = MediaHardwareBudget(
        tier="low",
        device_type="cuda",
        device_name="test gpu",
        image_megapixel_cap=0.35,
        motion_megapixel_cap=0.20,
        max_motion_frames=24,
        max_quality="draft",
        motion_recommended=False,
        source="test",
    )

    result = run_workflow_smoke_test(
        settings,
        setup,
        hardware_budget=budget,
        http_client=http_client,
    )

    assert result.generated.path.exists()
    assert result.generated.path.read_bytes() == b"fake-png"
    assert result.generated.kind == "png"
    assert result.generated.seed == 424242
    assert result.hardware.tier == "low"
    assert result.render_plan.megapixels <= 0.40
    assert set(result.generated.applied_render_parameters) >= {
        "width",
        "height",
        "steps",
        "cfg",
        "denoise",
    }
    assert seen["seed"] == 424242
    assert "empty studio chair" in str(seen["positive"])
    assert "child" in str(seen["negative"])
    assert int(seen["width"]) == result.render_plan.width
    assert int(seen["height"]) == result.render_plan.height
    http_client.close()
