from __future__ import annotations

import pytest

from app.diagnostics import DiagnosticResult
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings
from app.setup_flow import FirstRunSetupRepository, candidate_settings, core_setup_status


def test_first_run_state_is_required_until_completed(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "companion.sqlite3"))
    repository = FirstRunSetupRepository(store)

    assert repository.required() is True
    state = repository.mark_completed()
    assert state.completed is True
    assert state.revision == 2
    assert repository.required() is False


def test_candidate_settings_preserve_unrelated_local_configuration() -> None:
    original = AppSettings(
        model_name="old-model",
        model_url="http://old",
        media_enabled=True,
        media_url="http://127.0.0.1:8188",
        media_workflow="workflow.json",
        continuity_key="olivia-main",
        adaptive_memory_enabled=False,
    )

    candidate = candidate_settings(
        original,
        model_name="  new-model  ",
        model_url="  http://127.0.0.1:11434/  ",
    )

    assert candidate.model_name == "new-model"
    assert candidate.model_url == "http://127.0.0.1:11434/"
    assert candidate.media_enabled is True
    assert candidate.media_workflow == "workflow.json"
    assert candidate.continuity_key == "olivia-main"
    assert candidate.adaptive_memory_enabled is False


def test_candidate_settings_validate_blank_backend_fields() -> None:
    original = AppSettings()

    with pytest.raises(ValueError):
        candidate_settings(original, model_name="   ", model_url=original.model_url)

    with pytest.raises(ValueError):
        candidate_settings(original, model_name=original.model_name, model_url="   ")


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
