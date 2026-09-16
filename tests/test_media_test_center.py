from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.media.capabilities import WorkflowCapability
from app.media.test_center import build_media_test_report


def _capability(*, runnable: bool) -> WorkflowCapability:
    return WorkflowCapability(
        profile_id="motion",
        label="Motion Workflow",
        workflow=Path("motion.json"),
        enabled=True,
        valid=True,
        runnable=runnable,
        declared_kinds=("video",),
        output_evidence=("video",),
        reference_supported=True,
        render_controls=("width", "height", "frames", "fps"),
        missing_render_controls=("steps", "cfg", "denoise"),
        warnings=("example warning",),
        error="" if runnable else "mapping failed",
    )


def test_media_test_report_summarizes_runtime_capabilities() -> None:
    service = SimpleNamespace(
        backend=SimpleNamespace(enabled=True),
        enabled=True,
        available_media_kinds=("image", "video"),
        workflow_capabilities={"motion": _capability(runnable=True)},
    )

    report = build_media_test_report(service)
    rendered = report.render_text()

    assert report.ready_profiles == 1
    assert report.failed_profiles == 0
    assert "Verfügbare Arten: image, video" in rendered
    assert "Output-Evidenz: video" in rendered
    assert "Rendersteuerung: width, height, frames, fps" in rendered


def test_media_test_report_keeps_broken_profiles_visible() -> None:
    service = SimpleNamespace(
        backend=SimpleNamespace(enabled=False),
        enabled=False,
        available_media_kinds=(),
        workflow_capabilities={"motion": _capability(runnable=False)},
    )

    report = build_media_test_report(service)

    assert report.failed_profiles == 1
    assert "[FEHLER] Motion Workflow" in report.render_text()
    assert "Fehler: mapping failed" in report.render_text()


def test_desktop_navigation_contains_media_test_center() -> None:
    source = Path("app/main.py").read_text(encoding="utf-8")

    assert 'self.tabs.addTab(self.media_test_center, "Medien-Test")' in source
    assert "self.media_test_center.set_service(new_media_service)" in source
