from __future__ import annotations

import json

from app.media.capabilities import inspect_workflow_catalog, inspect_workflow_profile, runnable_kinds
from app.media.profiles import WorkflowCatalog, WorkflowInputBinding, WorkflowProfile


def _workflow(path, *, motion: bool = False, reference: bool = False) -> None:
    payload: dict[str, object] = {
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
        "3": {
            "class_type": "KSampler",
            "inputs": {"seed": 1, "steps": 20, "cfg": 6.0, "denoise": 1.0},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": 512, "height": 768},
        },
        "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "test"}},
    }
    if motion:
        payload["20"] = {
            "class_type": "VHS_VideoCombine",
            "inputs": {"frame_rate": 12, "format": "video/h264-mp4"},
        }
    if reference:
        payload["12"] = {"class_type": "LoadImage", "inputs": {"image": "ref.png"}}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_capability_inspector_reports_render_reference_and_output_evidence(tmp_path) -> None:
    workflow = tmp_path / "character.json"
    _workflow(workflow, reference=True)
    profile = WorkflowProfile(
        id="character",
        workflow=str(workflow),
        kinds=["image"],
        reference_node="12",
        reference_input_key="image",
    )

    capability = inspect_workflow_profile(profile)

    assert capability.runnable is True
    assert capability.runnable_kinds == ("image",)
    assert capability.reference_supported is True
    assert set(capability.render_controls) >= {"width", "height", "steps", "cfg", "denoise"}
    assert "image" in capability.output_evidence


def test_invalid_prompt_mapping_is_not_runnable(tmp_path) -> None:
    workflow = tmp_path / "broken.json"
    _workflow(workflow)
    profile = WorkflowProfile(
        id="broken",
        workflow=str(workflow),
        kinds=["image", "video"],
        positive_node="999",
    )

    capability = inspect_workflow_profile(profile)

    assert capability.valid is True
    assert capability.runnable is False
    assert capability.runnable_kinds == ()
    assert "Positive Prompt" in " ".join(capability.warnings)


def test_explicit_custom_render_binding_is_detected(tmp_path) -> None:
    workflow = tmp_path / "motion.json"
    _workflow(workflow, motion=True)
    payload = json.loads(workflow.read_text(encoding="utf-8"))
    payload["30"] = {"class_type": "CustomMotion", "inputs": {"custom_frames": 32}}
    workflow.write_text(json.dumps(payload), encoding="utf-8")
    profile = WorkflowProfile(
        id="motion",
        workflow=str(workflow),
        kinds=["video"],
        render_bindings={
            "frames": WorkflowInputBinding(node="30", input_key="custom_frames")
        },
    )

    capability = inspect_workflow_profile(profile)

    assert capability.runnable is True
    assert "frames" in capability.render_controls
    assert "video" in capability.output_evidence


def test_catalog_runnable_kinds_excludes_broken_profiles(tmp_path) -> None:
    still = tmp_path / "still.json"
    broken = tmp_path / "broken.json"
    _workflow(still)
    _workflow(broken, motion=True)
    catalog = WorkflowCatalog(
        profiles=[
            WorkflowProfile(id="still", workflow=str(still), kinds=["image"]),
            WorkflowProfile(
                id="broken-motion",
                workflow=str(broken),
                kinds=["video"],
                seed_node="404",
            ),
        ]
    )

    capabilities = inspect_workflow_catalog(catalog)

    assert runnable_kinds(capabilities) == {"image"}


def test_motion_output_requires_frame_pipeline_evidence(tmp_path) -> None:
    workflow = tmp_path / "misleading.json"
    _workflow(workflow)
    payload = json.loads(workflow.read_text(encoding="utf-8"))
    payload["20"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {"frame_rate": 12, "format": "video/h264-mp4"},
    }
    workflow.write_text(json.dumps(payload), encoding="utf-8")
    profile = WorkflowProfile(id="misleading", workflow=str(workflow), kinds=["video"])

    capability = inspect_workflow_profile(profile)

    assert "video" not in capability.output_evidence
    assert any("kein eindeutiger Output-Node" in item for item in capability.warnings)


def test_detects_animatediff_video_and_gif_pipelines(tmp_path) -> None:
    workflow = tmp_path / "animated.json"
    _workflow(workflow)
    payload = json.loads(workflow.read_text(encoding="utf-8"))
    payload["18"] = {
        "class_type": "AnimateDiffLoader",
        "inputs": {"frame_count": 24},
    }
    payload["20"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {"frame_rate": 12, "format": "image/gif"},
    }
    workflow.write_text(json.dumps(payload), encoding="utf-8")
    profile = WorkflowProfile(id="animated", workflow=str(workflow), kinds=["gif", "video"])

    capability = inspect_workflow_profile(profile)

    assert set(capability.output_evidence) >= {"gif", "video"}
    assert set(capability.render_controls) >= {"frames", "fps"}


def test_detects_svd_and_ffmpeg_video_pipeline(tmp_path) -> None:
    workflow = tmp_path / "svd.json"
    _workflow(workflow)
    payload = json.loads(workflow.read_text(encoding="utf-8"))
    payload["18"] = {"class_type": "SVD_img2vid_Conditioning", "inputs": {"video_frames": 16}}
    payload["20"] = {
        "class_type": "FFmpegVideoEncoder",
        "inputs": {"fps": 8, "codec": "h264", "container": "mp4"},
    }
    workflow.write_text(json.dumps(payload), encoding="utf-8")
    profile = WorkflowProfile(id="svd", workflow=str(workflow), kinds=["video"])

    capability = inspect_workflow_profile(profile)

    assert "video" in capability.output_evidence
    assert set(capability.render_controls) >= {"frames", "fps"}
