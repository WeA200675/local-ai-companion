from __future__ import annotations

import json
from pathlib import Path

from app.ai.persona import PersonaState
from app.media.capabilities import WorkflowCapability
from app.media.comfyui import ComfyUIError, GeneratedMedia
from app.media.hardware import MediaHardwareBudget
from app.media.planner import MediaIntent
from app.media.profiles import CheckpointSuitability, WorkflowProfile
from app.media.service import MediaService
from app.media.workflow_routing import (
    WorkflowHealthRepository,
    WorkflowRouter,
    classify_render_failure,
    select_media_kind,
    workflow_suitability_score,
)
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _workflow(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "3": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20}},
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
                "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "still"}},
            }
        ),
        encoding="utf-8",
    )


def _capability(
    profile: WorkflowProfile,
    path: Path,
    *,
    kind: str = "image",
    reference_supported: bool | None = None,
) -> WorkflowCapability:
    return WorkflowCapability(
        profile_id=profile.id,
        label=profile.label or profile.id,
        workflow=path,
        enabled=True,
        valid=True,
        runnable=True,
        declared_kinds=(kind,),
        output_evidence=(kind,),
        reference_supported=(
            profile.reference_configured
            if reference_supported is None
            else reference_supported
        ),
        render_controls=("width", "height", "steps", "cfg", "denoise"),
        missing_render_controls=("frames", "fps"),
        warnings=(),
        error="",
    )


def test_checkpoint_suitability_and_technical_score_are_explainable(tmp_path) -> None:
    path = tmp_path / "portrait.json"
    _workflow(path)
    portrait = WorkflowProfile(
        id="portrait",
        workflow=str(path),
        checkpoint_suitability=CheckpointSuitability(
            portrait=1.0, full_body=0.2, detail=0.8, environment=0.2
        ),
        routing_tags=["portrait"],
    )
    capability = _capability(portrait, path)

    assert portrait.checkpoint_suitability.score_for({"portrait"}) == 1.0
    assert workflow_suitability_score(capability, kind="image", reference_needed=False) > 70
    assert "technical suitability" in WorkflowRouter(
        [portrait], {"portrait": capability}
    ).route(
        MediaIntent(generate=True, framing="portrait close-up"),
        hardware=MediaHardwareBudget(),
        reference_available=False,
    ).selected.reasons[0]


def test_health_quarantine_and_successful_probe_release_are_local(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "state.sqlite3"))
    health = WorkflowHealthRepository(store)
    for _ in range(3):
        health.record_failure("broken", "confirmed execution failure", threshold=3)

    assert health.get("broken").quarantined is True
    health.record_probe("broken", succeeded=True)
    released = health.get("broken")
    assert released.quarantined is False
    assert released.consecutive_failures == 0
    assert released.successes == 1


def test_router_prefers_reference_continuity_and_hardware_fit(tmp_path) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _workflow(first_path)
    _workflow(second_path)
    generic = WorkflowProfile(
        id="generic",
        workflow=str(first_path),
        checkpoint_suitability=CheckpointSuitability(portrait=0.9),
        priority=8,
    )
    anchor = WorkflowProfile(
        id="anchor",
        workflow=str(second_path),
        reference_node="12",
        reference_input_key="image",
        prefer_for_character=True,
        min_vram_gb=8,
        preferred_vram_gb=12,
        checkpoint_suitability=CheckpointSuitability(portrait=0.7),
    )
    capabilities = {
        "generic": _capability(generic, first_path),
        "anchor": _capability(anchor, second_path, reference_supported=True),
    }
    decision = WorkflowRouter([generic, anchor], capabilities).route(
        MediaIntent(generate=True, continuity_key="persona-main", framing="portrait"),
        hardware=MediaHardwareBudget(vram_free_gb=16, vram_total_gb=16, tier="high"),
        reference_available=True,
    )

    assert decision.selected is not None
    assert decision.selected.profile.id == "anchor"
    assert "checkpoint suitability" in decision.explain()
    assert decision.fallback_profile_ids == ("generic",)


def test_kind_selection_quality_ladder_and_failure_policy() -> None:
    low = MediaHardwareBudget(tier="low", motion_recommended=False)
    intent = MediaIntent(generate=True, kind="video", motion="camera drift")
    selected = select_media_kind(intent, ("image", "video"), hardware=low, explicit_motion=False)
    assert selected.selected == "image"
    assert "still image" in selected.reason

    profile = WorkflowProfile(id="ladder", workflow="local.json", render_quality="high")
    assert profile.quality_attempts() == ("high", "balanced", "draft")
    assert classify_render_failure(ComfyUIError("CUDA out of memory")).degrade_quality is True
    assert classify_render_failure(ComfyUIError("queue timeout")).safe_to_fallback is False


def test_service_fallback_degradation_and_history_explanation(tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _workflow(first)
    _workflow(second)
    catalog = tmp_path / "profiles.json"
    catalog.write_text(
        json.dumps(
            {
                "profiles": [
                    {"id": "first", "workflow": "first.json", "priority": 10},
                    {"id": "second", "workflow": "second.json", "priority": 0},
                ]
            }
        ),
        encoding="utf-8",
    )
    store = StateStore(make_session_factory(tmp_path / "state.sqlite3"))
    settings = AppSettings(
        media_enabled=True,
        media_profile_catalog=str(catalog),
        media_output_dir=str(tmp_path / "generated"),
    )

    class Backend:
        enabled = True
        reference_configured = False

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def generate(self, _positive, _negative, *, profile, render_plan, **_kwargs):
            self.calls.append((profile.id, render_plan.quality))
            if profile.id == "first":
                raise ComfyUIError("Node render failed")
            path = Path(render_plan.kind + ".png")
            path.write_bytes(b"generated")
            return GeneratedMedia(path, "image", "prompt-1", 42)

    backend = Backend()
    service = MediaService(object(), backend, store=store, settings=settings)
    service.hardware_budget = lambda: MediaHardwareBudget(tier="high", motion_recommended=True)  # type: ignore[method-assign]
    result = service.generate_for_exchange(
        user_text="show a portrait",
        assistant_text="Here is a portrait.",
        persona=PersonaState(),
        forced_intent=MediaIntent(generate=True, kind="image", framing="portrait close-up"),
    )

    assert result is not None
    assert result.workflow_profile == "second"
    assert backend.calls[:2] == [("first", "balanced"), ("first", "draft")]
    assert backend.calls[-1][0] == "second"
    event = store.list_media_events(limit=1)[0]
    intent = event["intent"]
    assert "routing_explanation" in intent
    assert "Fallback-Kette" not in intent["routing_explanation"]
    assert intent["routing_attempts"][-1]["status"] == "success"
