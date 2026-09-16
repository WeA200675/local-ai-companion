from __future__ import annotations

import json

from app.media.motion_profiles import with_detected_motion_profile
from app.media.profiles import WorkflowProfile, load_workflow_catalog


def _workflow(path, *, animated: bool) -> None:
    payload = {
        "3": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 12, "cfg": 6}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "still"}},
    }
    if animated:
        payload["18"] = {"class_type": "AnimateDiffLoader", "inputs": {"frame_count": 24}}
        payload["20"] = {
            "class_type": "VHS_VideoCombine",
            "inputs": {"frame_rate": 12, "format": "video/h264-mp4"},
        }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_detected_motion_enriches_ephemeral_profile(tmp_path) -> None:
    workflow = tmp_path / "motion.json"
    _workflow(workflow, animated=True)
    original = WorkflowProfile(id="motion", workflow=str(workflow), kinds=["image"])

    enriched = with_detected_motion_profile(original)

    assert original.kinds == ["image"]
    assert set(enriched.kinds) == {"image", "video"}
    assert "motion" in enriched.routing_tags


def test_still_workflow_is_not_promoted_to_motion(tmp_path) -> None:
    workflow = tmp_path / "still.json"
    _workflow(workflow, animated=False)
    profile = WorkflowProfile(id="still", workflow=str(workflow), kinds=["image"])

    assert with_detected_motion_profile(profile) == profile


def test_catalog_load_applies_motion_detection_without_rewrite(tmp_path) -> None:
    workflow = tmp_path / "motion.json"
    catalog = tmp_path / "catalog.json"
    _workflow(workflow, animated=True)
    payload = {"version": 1, "profiles": [{"id": "auto", "workflow": "motion.json"}]}
    catalog.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_workflow_catalog(catalog)

    assert "video" in loaded.profiles[0].kinds
    assert "motion" in loaded.profiles[0].routing_tags
    assert json.loads(catalog.read_text(encoding="utf-8")) == payload
