from __future__ import annotations

from app.diagnostics import DiagnosticResult
from app.settings import AppSettings
from app.setup_flow import candidate_settings, core_setup_status, setup_required


def test_first_run_is_required_until_completed() -> None:
    assert setup_required(AppSettings()) is True
    assert setup_required(AppSettings(setup_completed=True)) is False


def test_candidate_settings_preserve_unrelated_local_configuration() -> None:
    original = AppSettings(
        model_name="old-model",
        model_url="http://old",
        media_enabled=True,
        media_url="http://127.0.0.1:8188",
        media_workflow="workflow.json",
        continuity_key="olivia-main",
        adaptive_memory_enabled=False,
        setup_completed=False,
    )

    candidate = candidate_settings(
        original,
        model_name="  new-model  ",
        model_url="  http://127.0.0.1:11434/  ",
        completed=True,
    )

    assert candidate.model_name == "new-model"
    assert candidate.model_url == "http://127.0.0.1:11434/"
    assert candidate.setup_completed is True
    assert candidate.media_enabled is True
    assert candidate.media_workflow == "workflow.json"
    assert candidate.continuity_key == "olivia-main"
    assert candidate.adaptive_memory_enabled is False


def test_core_setup_requires_inventory_and_real_inference() -> None:
    results = [
        DiagnosticResult("Sprachmodell", True, "installed"),
        DiagnosticResult("Modell-Inferenz", False, "backend failed"),
    ]

    status = core_setup_status(results)

    assert status.inventory_ok is True
    assert status.inference_ok is False
    assert status.ready is False
    assert "noch nicht bereit" in status.summary


def test_core_setup_is_ready_after_real_inference() -> None:
    results = [
        DiagnosticResult("Sprachmodell", True, "installed"),
        DiagnosticResult("Modell-Inferenz", True, "real inference ok"),
        DiagnosticResult("ComfyUI", False, "optional backend offline"),
    ]

    status = core_setup_status(results)

    assert status.ready is True
    assert "Mini-Inferenz" in status.summary
