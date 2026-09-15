from __future__ import annotations

import json

from app.media.workflow_inspector import inspect_api_workflow, inspect_workflow_file


def _workflow(seed_key: str = "seed") -> dict[str, object]:
    return {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                seed_key: 123,
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
    }


def test_detects_prompt_and_seed_nodes_from_sampler_links() -> None:
    inspection = inspect_api_workflow(_workflow())

    assert inspection.valid is True
    assert inspection.complete is True
    assert inspection.positive_node == "6"
    assert inspection.negative_node == "7"
    assert inspection.seed_node == "3"
    assert inspection.seed_input_key == "seed"


def test_detects_noise_seed_variant() -> None:
    inspection = inspect_api_workflow(_workflow("noise_seed"))

    assert inspection.complete is True
    assert inspection.seed_input_key == "noise_seed"


def test_multiple_samplers_are_reported_transparently() -> None:
    workflow = _workflow()
    workflow["9"] = {
        "class_type": "KSamplerAdvanced",
        "inputs": {
            "noise_seed": 456,
            "positive": ["6", 0],
            "negative": ["7", 0],
        },
    }

    inspection = inspect_api_workflow(workflow)

    assert inspection.complete is True
    assert inspection.warnings
    assert "Mehrere Sampler" in inspection.warnings[0]


def test_missing_sampler_keeps_text_candidates_as_guidance() -> None:
    inspection = inspect_api_workflow(
        {
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "one"}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "two"}},
        }
    )

    assert inspection.valid is True
    assert inspection.complete is False
    assert "Text-Node-Kandidaten: 6, 7" in inspection.warnings[0]


def test_inspect_workflow_file_handles_invalid_json(tmp_path) -> None:
    path = tmp_path / "workflow.json"
    path.write_text("not-json", encoding="utf-8")

    inspection = inspect_workflow_file(path)

    assert inspection.valid is False
    assert "JSON" in inspection.error


def test_inspect_workflow_file_reads_api_workflow(tmp_path) -> None:
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(_workflow()), encoding="utf-8")

    inspection = inspect_workflow_file(path)

    assert inspection.complete is True
    assert inspection.path == path
