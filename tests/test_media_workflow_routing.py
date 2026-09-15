from __future__ import annotations

import json

from app.media.planner import MediaIntent
from app.media.profiles import WorkflowProfile, choose_workflow_profile
from app.media.setup_assistant import inspect_for_auto_setup
from app.media.standard_workflow import build_standard_image_workflow
from app.media.workflow_routing import WorkflowPerformanceRepository, intent_focus_tags
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _intent(**updates) -> MediaIntent:
    data = {
        "generate": True,
        "kind": "image",
        "mood": "cinematic",
        "theme": "adult editorial studio",
        "visual_style": "photographic",
        "wardrobe": [],
        "intensity": 0.5,
        "continuity_key": None,
        "reason": "test",
        "framing": "portrait close-up",
        "camera_angle": "eye level",
        "lighting": "soft",
        "composition": "centered",
        "motion": "",
    }
    data.update(updates)
    return MediaIntent.model_validate(data)


def test_focus_tags_derive_visual_job() -> None:
    intent = _intent(
        framing="full-body head-to-toe composition with material detail",
        continuity_key="persona-main",
        motion="slow camera drift",
        kind="video",
    )
    tags = set(intent_focus_tags(intent))
    assert "full_body" in tags
    assert "detail" in tags
    assert "character" in tags
    assert "motion" in tags


def test_declared_focus_routes_matching_workflow(tmp_path) -> None:
    portrait_workflow = tmp_path / "portrait.json"
    full_workflow = tmp_path / "full.json"
    portrait_workflow.write_text("{}", encoding="utf-8")
    full_workflow.write_text("{}", encoding="utf-8")

    portrait = WorkflowProfile(
        id="portrait",
        workflow=str(portrait_workflow),
        routing_tags=["portrait"],
    )
    full = WorkflowProfile(
        id="full",
        workflow=str(full_workflow),
        routing_tags=["full_body"],
    )

    selected = choose_workflow_profile(
        [portrait, full],
        kind="image",
        character_focus=False,
        reference_available=False,
        focus_tags={"full_body"},
    )
    assert selected is not None
    assert selected.id == "full"


def test_feedback_score_prefers_workflow_that_succeeded_for_same_focus(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "state.sqlite3"))
    for feedback, profile_id in (
        ("negative", "portrait-a"),
        ("positive", "portrait-b"),
        ("positive", "portrait-b"),
    ):
        media_id = store.record_media_event(
            path=f"{profile_id}.png",
            kind="png",
            prompt_id=profile_id,
            seed=1,
            continuity_key="persona-main",
            intent={
                "workflow_profile": profile_id,
                "workflow_focus_tags": ["portrait", "character"],
            },
        )
        store.set_media_feedback(media_id, feedback)

    repository = WorkflowPerformanceRepository(store)
    scores = repository.scores(["portrait-a", "portrait-b"], ["portrait"])
    assert scores["portrait-b"] > scores["portrait-a"]

    a_path = tmp_path / "a.json"
    b_path = tmp_path / "b.json"
    a_path.write_text("{}", encoding="utf-8")
    b_path.write_text("{}", encoding="utf-8")
    selected = choose_workflow_profile(
        [
            WorkflowProfile(id="portrait-a", workflow=str(a_path)),
            WorkflowProfile(id="portrait-b", workflow=str(b_path)),
        ],
        kind="image",
        character_focus=True,
        reference_available=False,
        focus_tags={"portrait", "character"},
        performance_scores=scores,
    )
    assert selected is not None
    assert selected.id == "portrait-b"


def test_unrated_media_does_not_change_performance(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "state.sqlite3"))
    store.record_media_event(
        path="neutral.png",
        kind="png",
        prompt_id="neutral",
        seed=1,
        continuity_key=None,
        intent={
            "workflow_profile": "neutral",
            "workflow_focus_tags": ["detail"],
        },
    )
    performance = WorkflowPerformanceRepository(store).performance("neutral", ["detail"])
    assert performance.samples == 0
    assert performance.score == 0


def test_auto_setup_records_checkpoint_provenance_without_license_claim(tmp_path) -> None:
    workflow_path = tmp_path / "generated.json"
    workflow_path.write_text(
        json.dumps(build_standard_image_workflow("local-model.safetensors")),
        encoding="utf-8",
    )
    setup = inspect_for_auto_setup(workflow_path)
    assert setup.ready
    assert setup.profile is not None
    assert setup.profile.checkpoint_name == "local-model.safetensors"
    assert setup.profile.checkpoint_license_confirmed is False
