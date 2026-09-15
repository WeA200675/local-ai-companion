from __future__ import annotations

import json

import httpx
import pytest

from app.media.standard_workflow import (
    StandardWorkflowError,
    build_standard_image_workflow,
    discover_checkpoint_inventory,
    generated_workflow_path,
    parse_checkpoint_inventory,
    save_standard_image_workflow,
)
from app.media.workflow_inspector import inspect_api_workflow, inspect_workflow_file


def _object_info() -> dict[str, object]:
    return {
        "CheckpointLoaderSimple": {
            "input": {
                "required": {
                    "ckpt_name": [["models/a.safetensors", "b.ckpt"], {}],
                }
            }
        },
        "KSampler": {
            "input": {
                "required": {
                    "sampler_name": [["dpmpp_2m", "euler"], {}],
                    "scheduler": [["karras", "normal"], {}],
                }
            }
        },
    }


def test_parse_checkpoint_inventory_reads_standard_object_info() -> None:
    inventory = parse_checkpoint_inventory(_object_info())
    assert inventory.checkpoints == ("models/a.safetensors", "b.ckpt")
    assert inventory.sampler_names == ("dpmpp_2m", "euler")
    assert inventory.schedulers == ("karras", "normal")
    assert inventory.ready is True


def test_discovery_uses_local_object_info_only() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, request=request, json=_object_info())

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        inventory = discover_checkpoint_inventory("http://127.0.0.1:8188", client=client)

    assert inventory.checkpoints == ("models/a.safetensors", "b.ckpt")
    assert requested == ["/object_info"]


def test_discovery_falls_back_to_scoped_object_info() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/object_info":
            return httpx.Response(404, request=request)
        if request.url.path.endswith("CheckpointLoaderSimple"):
            return httpx.Response(
                200,
                request=request,
                json={"input": {"required": {"ckpt_name": [["one.safetensors"], {}]}}},
            )
        if request.url.path.endswith("KSampler"):
            return httpx.Response(
                200,
                request=request,
                json={
                    "input": {
                        "required": {
                            "sampler_name": [["euler"], {}],
                            "scheduler": [["normal"], {}],
                        }
                    }
                },
            )
        return httpx.Response(404, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        inventory = discover_checkpoint_inventory("http://local", client=client)

    assert inventory.checkpoints == ("one.safetensors",)
    assert inventory.sampler_names == ("euler",)
    assert inventory.schedulers == ("normal",)


def test_discovery_rejects_empty_checkpoint_inventory() -> None:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, request=request, json={})
        )
    ) as client:
        with pytest.raises(StandardWorkflowError):
            discover_checkpoint_inventory("http://local", client=client)


def test_builder_creates_complete_standard_api_workflow() -> None:
    workflow = build_standard_image_workflow(
        "portrait.safetensors",
        sampler_names=("dpmpp_2m", "euler"),
        schedulers=("karras", "normal"),
    )

    inspection = inspect_api_workflow(workflow)
    assert inspection.complete is True
    assert inspection.positive_node == "2"
    assert inspection.negative_node == "3"
    assert inspection.seed_node == "5"
    assert workflow["1"]["inputs"]["ckpt_name"] == "portrait.safetensors"
    assert workflow["5"]["inputs"]["sampler_name"] == "euler"
    assert workflow["5"]["inputs"]["scheduler"] == "normal"
    assert workflow["4"]["inputs"]["width"] == 768
    assert workflow["4"]["inputs"]["height"] == 1024


def test_saved_generated_workflow_is_inspectable_and_stays_outside_media_outputs(tmp_path) -> None:
    output_dir = tmp_path / "generated_media"
    path = save_standard_image_workflow(
        output_dir,
        "folder/My Model v1.safetensors",
        sampler_names=("euler",),
        schedulers=("normal",),
    )

    assert path == generated_workflow_path(output_dir, "folder/My Model v1.safetensors")
    assert path.parent == tmp_path / "generated_workflows"
    assert path.exists()
    assert inspect_workflow_file(path).complete is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["7"]["class_type"] == "SaveImage"
