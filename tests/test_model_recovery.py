from __future__ import annotations

from app.ai.model_recovery import (
    recommended_install_commands,
    recovery_candidates,
    recover_first_working_model,
)
from app.diagnostics import DiagnosticResult
from app.settings import AppSettings


def test_recovery_candidates_only_include_installed_strict_catalog_models() -> None:
    candidates = recovery_candidates(
        ["qwen2.5:7b", "unknown-private:3b", "qwen3:4b", "qwen2.5:1.5b"],
        "qwen2.5:7b",
    )

    assert candidates == ("qwen2.5:1.5b", "qwen3:4b")


def test_recovery_stops_at_first_model_with_real_inference() -> None:
    tested: list[str] = []

    def diagnostics(settings: AppSettings) -> list[DiagnosticResult]:
        tested.append(settings.model_name)
        works = settings.model_name == "qwen3:4b"
        return [
            DiagnosticResult("Sprachmodell", True, "installed"),
            DiagnosticResult("Modell-Inferenz", works, "ok" if works else "native crash"),
        ]

    report = recover_first_working_model(
        AppSettings(model_name="qwen2.5:7b"),
        ["qwen2.5:7b", "qwen3:4b", "qwen2.5:1.5b"],
        diagnostics_runner=diagnostics,
    )

    assert report.selected_model == "qwen3:4b"
    assert tested == ["qwen2.5:1.5b", "qwen3:4b"]
    assert [attempt.ready for attempt in report.attempts] == [False, True]


def test_recovery_does_not_download_or_probe_unknown_models() -> None:
    tested: list[str] = []

    def diagnostics(settings: AppSettings) -> list[DiagnosticResult]:
        tested.append(settings.model_name)
        raise AssertionError("must not run")

    report = recover_first_working_model(
        AppSettings(model_name="qwen2.5:7b"),
        ["qwen2.5:7b", "custom:latest"],
        diagnostics_runner=diagnostics,
    )

    assert report.selected_model is None
    assert report.attempts == ()
    assert tested == []


def test_install_suggestions_are_small_explicit_catalog_commands() -> None:
    commands = recommended_install_commands(["qwen2.5:0.5b"], limit=3)

    assert len(commands) == 3
    assert commands[0] == "ollama pull deepseek-r1:1.5b"
    assert "ollama pull qwen2.5:0.5b" not in commands
    assert all(command.startswith("ollama pull ") for command in commands)
