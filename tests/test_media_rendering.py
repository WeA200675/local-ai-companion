from __future__ import annotations

import json

from app.media.comfyui import ComfyUIClient
from app.media.planner import MediaIntent
from app.media.profiles import WorkflowInputBinding, WorkflowProfile
from app.media.rendering import MediaRenderCalculator


def test_render_calculator_uses_visual_framing_and_bounded_work() -> None:
    calculator = MediaRenderCalculator()
    portrait = calculator.calculate(
        MediaIntent(
            generate=True,
            kind="image",
            framing="full body standing portrait",
            composition="full silhouette",
            intensity=0.8,
        ),
        ["full body", "boots"],
    )
    wide = calculator.calculate(
        MediaIntent(
            generate=True,
            kind="image",
            framing="wide frame",
            composition="environmental portrait",
            intensity=0.5,
        )
    )

    assert portrait.aspect_ratio == "2:3"
    assert portrait.height > portrait.width
    assert portrait.megapixels <= 1.25
    assert portrait.steps > 20
    assert wide.aspect_ratio == "16:9"
    assert wide.width > wide.height


def test_motion_plan_calculates_frames_fps_and_lower_spatial_budget() -> None:
    calculator = MediaRenderCalculator()
    plan = calculator.calculate(
        MediaIntent(
            generate=True,
            kind="video",
            framing="portrait",
            motion="subtle slow rain and breathing",
            intensity=0.75,
        )
    )

    assert plan.frames >= 16
    assert plan.fps == 16
    assert 1.0 < plan.duration_seconds < 5.0
    assert plan.megapixels <= 0.80
    assert plan.estimated_work_units > plan.megapixels * plan.steps


def test_comfyui_auto_injects_common_render_inputs(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "old positive"}},
                "7": {"inputs": {"text": "old negative"}},
                "3": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": 1,
                        "steps": 20,
                        "cfg": 7.0,
                        "denoise": 1.0,
                    },
                },
                "5": {
                    "class_type": "EmptyLatentImage",
                    "inputs": {"width": 512, "height": 768, "batch_size": 1},
                },
            }
        ),
        encoding="utf-8",
    )
    plan = MediaRenderCalculator().calculate(
        MediaIntent(generate=True, kind="image", framing="wide frame", intensity=0.6)
    )
    trace: list[str] = []
    client = ComfyUIClient(workflow_path=workflow_path, output_dir=tmp_path / "generated")
    workflow = client.build_workflow(
        "new positive",
        "new negative",
        seed=123,
        render_plan=plan,
        render_trace=trace,
    )
    client.close()

    assert workflow["5"]["inputs"]["width"] == plan.width
    assert workflow["5"]["inputs"]["height"] == plan.height
    assert workflow["3"]["inputs"]["steps"] == plan.steps
    assert workflow["3"]["inputs"]["cfg"] == plan.cfg
    assert workflow["3"]["inputs"]["denoise"] == plan.denoise
    assert set(trace) >= {"width", "height", "steps", "cfg", "denoise"}


def test_profile_bindings_override_auto_detection_for_motion(tmp_path) -> None:
    workflow_path = tmp_path / "motion.json"
    workflow_path.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "old positive"}},
                "7": {"inputs": {"text": "old negative"}},
                "3": {"inputs": {"seed": 1}},
                "90": {"inputs": {"custom_frames": 24}},
                "91": {"inputs": {"custom_rate": 8}},
            }
        ),
        encoding="utf-8",
    )
    profile = WorkflowProfile(
        id="motion",
        workflow=str(workflow_path),
        kinds=["video"],
        render_quality="high",
        max_megapixels=0.5,
        render_bindings={
            "frames": WorkflowInputBinding(node="90", input_key="custom_frames"),
            "fps": WorkflowInputBinding(node="91", input_key="custom_rate"),
        },
    )
    plan = MediaRenderCalculator().calculate(
        MediaIntent(generate=True, kind="video", intensity=1.0),
        quality=profile.render_quality,
        max_megapixels=profile.max_megapixels,
    )
    trace: list[str] = []
    client = ComfyUIClient(output_dir=tmp_path / "generated")
    workflow = client.build_workflow(
        "positive",
        "negative",
        seed=99,
        profile=profile,
        render_plan=plan,
        render_trace=trace,
    )
    client.close()

    assert workflow["90"]["inputs"]["custom_frames"] == plan.frames
    assert workflow["91"]["inputs"]["custom_rate"] == plan.fps
    assert "frames" in trace
    assert "fps" in trace
