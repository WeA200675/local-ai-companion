from __future__ import annotations

import json

from app.media.profiles import load_workflow_catalog
from app.media.workflow_inspector import inspect_api_workflow


def _reference_workflow(*, second_loader: bool = False, unrelated_loader: bool = False):
    workflow: dict[str, object] = {
        "1": {
            "class_type": "LoadImage",
            "inputs": {"image": "reference.png", "upload": "image"},
        },
        "2": {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["1", 0], "vae": ["10", 2]},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "steps": 20,
                "cfg": 6.5,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["2", 0],
                "model": ["10", 0],
            },
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "local.safetensors"}},
    }
    if second_loader:
        workflow["11"] = {
            "class_type": "LoadImage",
            "inputs": {"image": "second.png"},
        }
        workflow["12"] = {
            "class_type": "ImageBlend",
            "inputs": {"image1": ["1", 0], "image2": ["11", 0]},
        }
        workflow["2"] = {
            "class_type": "VAEEncode",
            "inputs": {"pixels": ["12", 0], "vae": ["10", 2]},
        }
    if unrelated_loader:
        workflow["20"] = {
            "class_type": "LoadImage",
            "inputs": {"image": "unused.png"},
        }
    return workflow


def test_inspector_detects_single_connected_filename_loader() -> None:
    inspection = inspect_api_workflow(_reference_workflow())

    assert inspection.complete is True
    assert inspection.reference_detected is True
    assert inspection.reference_node == "1"
    assert inspection.reference_input_key == "image"
    assert inspection.reference_candidates == (("1", "image"),)
    assert any("Referenzbild-Eingang" in warning for warning in inspection.warnings)


def test_inspector_ignores_unrelated_image_loader() -> None:
    inspection = inspect_api_workflow(_reference_workflow(unrelated_loader=True))

    assert inspection.reference_detected is True
    assert inspection.reference_candidates == (("1", "image"),)


def test_inspector_refuses_ambiguous_connected_loaders() -> None:
    inspection = inspect_api_workflow(_reference_workflow(second_loader=True))

    assert inspection.reference_detected is False
    assert set(inspection.reference_candidates) == {("1", "image"), ("11", "image")}
    assert any("Mehrere" in warning and "Bild-Loader" in warning for warning in inspection.warnings)


def test_catalog_load_applies_ephemeral_reference_mapping_without_overwriting_file(tmp_path) -> None:
    workflow_path = tmp_path / "reference.json"
    workflow_path.write_text(json.dumps(_reference_workflow()), encoding="utf-8")
    catalog_path = tmp_path / "profiles.json"
    catalog_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "character-auto",
                        "workflow": "reference.json",
                        "positive_node": "6",
                        "negative_node": "7",
                        "seed_node": "3",
                        "kinds": ["image"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    profile = load_workflow_catalog(catalog_path).profiles[0]

    assert profile.reference_node == "1"
    assert profile.reference_input_key == "image"
    assert profile.prefer_for_character is True
    assert "character" in profile.routing_tags

    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    assert "reference_node" not in raw["profiles"][0]
    assert "routing_tags" not in raw["profiles"][0]


def test_explicit_reference_mapping_is_never_overridden(tmp_path) -> None:
    workflow_path = tmp_path / "reference.json"
    workflow_path.write_text(json.dumps(_reference_workflow()), encoding="utf-8")
    catalog_path = tmp_path / "profiles.json"
    catalog_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "id": "explicit",
                        "workflow": "reference.json",
                        "positive_node": "6",
                        "negative_node": "7",
                        "seed_node": "3",
                        "reference_node": "99",
                        "reference_input_key": "custom_file",
                        "kinds": ["image"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    profile = load_workflow_catalog(catalog_path).profiles[0]

    assert profile.reference_node == "99"
    assert profile.reference_input_key == "custom_file"
