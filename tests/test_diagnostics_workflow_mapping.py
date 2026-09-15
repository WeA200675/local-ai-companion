from __future__ import annotations

import json

import httpx

from app.diagnostics import run_diagnostics
from app.settings import AppSettings


def _fake_get(url: str, timeout: float):
    request = httpx.Request("GET", url)
    if url.endswith("/api/tags"):
        return httpx.Response(200, request=request, json={"models": [{"name": "local-model"}]})
    if url.endswith("/system_stats"):
        return httpx.Response(200, request=request, json={})
    raise AssertionError(url)


def test_diagnostics_reject_prompt_node_without_text_input(monkeypatch, tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {"inputs": {"wrong": "positive"}},
                "7": {"inputs": {"text": "negative"}},
                "3": {"inputs": {"seed": 1}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.diagnostics.httpx.get", _fake_get)
    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
    )

    by_name = {item.name: item for item in run_diagnostics(settings, timeout=0.1)}

    assert by_name["ComfyUI-Workflow"].ok is False
    assert "text/prompt" in by_name["ComfyUI-Workflow"].detail


def test_diagnostics_reject_seed_node_without_seed_input(monkeypatch, tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "positive"}},
                "7": {"inputs": {"text": "negative"}},
                "3": {"inputs": {"wrong": 1}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("app.diagnostics.httpx.get", _fake_get)
    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
    )

    by_name = {item.name: item for item in run_diagnostics(settings, timeout=0.1)}

    assert by_name["ComfyUI-Workflow"].ok is False
    assert "seed/noise_seed" in by_name["ComfyUI-Workflow"].detail
