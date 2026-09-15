from __future__ import annotations

from app.ai.model_compatibility import AdultModelCompatibilityReport
from app.diagnostics import DiagnosticResult
from app.readiness import build_readiness_report
from app.settings import AppSettings


def _compatibility(status: str = "compatible", score: int = 100) -> AdultModelCompatibilityReport:
    return AdultModelCompatibilityReport(
        model_name="qwen2.5:7b",
        base_url="http://127.0.0.1:11434",
        tested_at="2026-09-15T00:00:00+00:00",
        status=status,
        score=score,
        operational=status != "unavailable",
        probes=[],
        summary=f"compatibility {status}",
    )


def _diagnostics(*, model: bool = True, comfy: bool = True, workflow: bool = True) -> list[DiagnosticResult]:
    return [
        DiagnosticResult("Sprachmodell", model, "model detail"),
        DiagnosticResult("ComfyUI-Workflow", workflow, "workflow detail"),
        DiagnosticResult("ComfyUI", comfy, "comfy detail"),
        DiagnosticResult("Medien-Ausgabe", True, "output detail"),
    ]


def test_full_readiness_marks_text_adult_and_media_ready() -> None:
    settings = AppSettings(media_enabled=True, media_workflow="workflow.json")

    report = build_readiness_report(settings, _diagnostics(), _compatibility())

    assert report.core_ready is True
    assert report.media_ready is True
    assert "startklar" in report.summary
    assert all(item.state == "ready" for item in report.items)


def test_media_failures_do_not_hide_ready_adult_text_companion() -> None:
    settings = AppSettings(media_enabled=True)

    report = build_readiness_report(
        settings,
        _diagnostics(comfy=False, workflow=False),
        _compatibility(),
    )

    assert report.core_ready is True
    assert report.media_ready is False
    media = next(item for item in report.items if item.key == "media")
    assert media.state == "blocked"
    assert "ComfyUI lokal starten" in media.next_step
    assert "Workflow" in media.next_step
    assert "Medien brauchen noch Setup" in report.summary


def test_disabled_media_is_optional_not_a_core_failure() -> None:
    settings = AppSettings(media_enabled=False)

    report = build_readiness_report(settings, _diagnostics(), _compatibility())

    media = next(item for item in report.items if item.key == "media")
    assert report.core_ready is True
    assert report.media_ready is False
    assert media.state == "optional"


def test_missing_adult_test_is_visible_as_attention() -> None:
    settings = AppSettings(media_enabled=False)

    report = build_readiness_report(settings, _diagnostics(), None)

    adult = next(item for item in report.items if item.key == "adult_model")
    assert report.core_ready is False
    assert adult.state == "attention"
    assert "Adult-/Kink-Modelltest" in adult.next_step
    assert "technisch bereit" in report.summary


def test_blocked_adult_model_prevents_core_ready() -> None:
    settings = AppSettings(media_enabled=False)

    report = build_readiness_report(
        settings,
        _diagnostics(),
        _compatibility(status="blocked", score=20),
    )

    adult = next(item for item in report.items if item.key == "adult_model")
    assert report.core_ready is False
    assert adult.state == "blocked"
    assert "Adult-/Kink-Modus" in report.summary


def test_workflow_profile_diagnostic_counts_as_media_workflow() -> None:
    settings = AppSettings(media_enabled=True, media_profile_catalog="profiles.json")
    diagnostics = [
        DiagnosticResult("Sprachmodell", True, "model detail"),
        DiagnosticResult("Workflow-Profile", True, "profiles ready"),
        DiagnosticResult("ComfyUI", True, "comfy detail"),
        DiagnosticResult("Medien-Ausgabe", True, "output detail"),
    ]

    report = build_readiness_report(settings, diagnostics, _compatibility())

    assert report.media_ready is True
