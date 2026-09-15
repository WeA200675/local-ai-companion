from __future__ import annotations

from app.media.workflow_inspector import inspect_api_workflow


def test_traces_prompt_nodes_through_intermediate_conditioning_nodes() -> None:
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "positive": ["20", 0],
                "negative": ["21", 0],
            },
        },
        "20": {
            "class_type": "ConditioningSetArea",
            "inputs": {"conditioning": ["6", 0]},
        },
        "21": {
            "class_type": "ConditioningSetArea",
            "inputs": {"conditioning": ["7", 0]},
        },
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
    }

    inspection = inspect_api_workflow(workflow)

    assert inspection.complete is True
    assert inspection.positive_node == "6"
    assert inspection.negative_node == "7"
    assert any("Zwischen-Node 20" in item for item in inspection.warnings)
    assert any("Zwischen-Node 21" in item for item in inspection.warnings)


def test_does_not_claim_complete_mapping_when_prompt_path_has_no_text_node() -> None:
    workflow = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": 123,
                "positive": ["20", 0],
                "negative": ["7", 0],
            },
        },
        "20": {"class_type": "ConditioningSetArea", "inputs": {"strength": 1.0}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
    }

    inspection = inspect_api_workflow(workflow)

    assert inspection.complete is False
    assert inspection.positive_node is None
    assert inspection.negative_node == "7"
