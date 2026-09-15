from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_windows_entry_points_bootstrap_missing_venv() -> None:
    for path in (
        "scripts/run_windows.ps1",
        "scripts/model_scout_windows.ps1",
        "scripts/media_setup_wizard.ps1",
    ):
        content = _text(path)
        assert "setup_windows.ps1" in content
        assert "-NoRun" in content
        assert "Test-Path $venvPython" in content
        assert "Modelle werden nicht automatisch geladen" in content


def test_setup_script_is_windows_powershell_console_safe() -> None:
    content = _text("scripts/setup_windows.ps1")
    content.encode("ascii")
    assert "Pruefe Python" in content
    assert "laedt Modelle nicht automatisch" in content
