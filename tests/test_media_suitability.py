from __future__ import annotations

from pathlib import Path

from app.media.comfyui import GeneratedMedia
from app.media.profiles import WorkflowProfile
from app.media.rendering import MediaRenderCalculator
from app.media.suitability import _record_result, default_suitability_probes
from app.media.workflow_routing import WorkflowPerformanceRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_suitability_suite_covers_core_image_jobs() -> None:
    probes = default_suitability_probes()
    assert [probe.focus_tag for probe in probes] == [
        "portrait",
        "full_body",
        "detail",
        "environment",
    ]
    assert len({probe.seed for probe in probes}) == len(probes)
    for probe in probes:
        assert "minor" in probe.negative
        assert "explicit sex act" in probe.negative
        assert probe.intent.kind == "image"


def test_suitability_intents_drive_expected_aspect_ratios() -> None:
    calculator = MediaRenderCalculator()
    ratios = {
        probe.focus_tag: calculator.calculate(probe.intent, [], quality="draft").aspect_ratio
        for probe in default_suitability_probes()
    }
    assert ratios["full_body"] == "2:3"
    assert ratios["environment"] == "16:9"
    assert ratios["detail"] in {"4:5", "1:1"}


def test_recorded_probe_feedback_enters_workflow_routing(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "state.sqlite3"))
    workflow = tmp_path / "workflow.json"
    workflow.write_text("{}", encoding="utf-8")
    profile = WorkflowProfile(
        id="probe-profile",
        workflow=str(workflow),
        checkpoint_name="local.safetensors",
    )
    probe = default_suitability_probes()[0]
    plan = MediaRenderCalculator().calculate(probe.intent, [], quality="draft")
    generated = GeneratedMedia(
        path=Path(tmp_path / "portrait.png"),
        kind="png",
        prompt_id="probe-1",
        seed=probe.seed,
        applied_render_parameters=("width", "height", "steps"),
    )
    media_id = _record_result(store, profile, probe, generated, plan)
    store.set_media_feedback(media_id, "positive")

    performance = WorkflowPerformanceRepository(store).performance(
        profile.id,
        ["portrait"],
    )
    assert performance.samples == 1
    assert performance.matching_positive == 1
    assert performance.score > 0


def test_probe_history_keeps_checkpoint_and_focus_metadata(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "state.sqlite3"))
    workflow = tmp_path / "workflow.json"
    workflow.write_text("{}", encoding="utf-8")
    profile = WorkflowProfile(
        id="probe-profile",
        workflow=str(workflow),
        checkpoint_name="local.safetensors",
        routing_tags=["portrait"],
    )
    probe = default_suitability_probes()[0]
    plan = MediaRenderCalculator().calculate(probe.intent, [], quality="draft")
    generated = GeneratedMedia(
        path=tmp_path / "portrait.png",
        kind="png",
        prompt_id="probe-2",
        seed=probe.seed,
    )
    _record_result(store, profile, probe, generated, plan)

    event = store.list_media_events(limit=1)[0]
    intent = event["intent"]
    assert isinstance(intent, dict)
    assert intent["workflow_profile"] == "probe-profile"
    assert intent["workflow_checkpoint"] == "local.safetensors"
    assert intent["workflow_focus_tags"] == ["portrait"]
    assert intent["suitability_probe"] == "portrait"
