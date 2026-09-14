from __future__ import annotations

import json

import httpx

from app.diagnostics import run_diagnostics
from app.settings import AppSettings


def test_local_diagnostics_success(monkeypatch, tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "positive"}},
                "7": {"inputs": {"text": "negative"}},
                "3": {"inputs": {"seed": 1}},
            }
        ),
        encoding="utf-8",
    )

    def fake_get(url: str, timeout: float):
        request = httpx.Request("GET", url)
        if url.endswith("/api/tags"):
            return httpx.Response(
                200,
                request=request,
                json={"models": [{"name": "local-model"}]},
            )
        if url.endswith("/system_stats"):
            return httpx.Response(200, request=request, json={"system": {}})
        raise AssertionError(url)

    monkeypatch.setattr("app.diagnostics.httpx.get", fake_get)
    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
    )

    results = run_diagnostics(settings, timeout=0.1)
    assert all(result.ok for result in results)


def test_local_diagnostics_reports_missing_model_and_nodes(monkeypatch, tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps({"6": {"inputs": {"text": "positive"}}}), encoding="utf-8")

    def fake_get(url: str, timeout: float):
        request = httpx.Request("GET", url)
        if url.endswith("/api/tags"):
            return httpx.Response(
                200,
                request=request,
                json={"models": [{"name": "another-model"}]},
            )
        if url.endswith("/system_stats"):
            return httpx.Response(200, request=request, json={})
        raise AssertionError(url)

    monkeypatch.setattr("app.diagnostics.httpx.get", fake_get)
    settings = AppSettings(
        model_name="wanted-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
    )

    results = run_diagnostics(settings, timeout=0.1)
    by_name = {result.name: result for result in results}
    assert by_name["Sprachmodell"].ok is False
    assert "wanted-model" in by_name["Sprachmodell"].detail
    assert by_name["ComfyUI-Workflow"].ok is False
    assert "7" in by_name["ComfyUI-Workflow"].detail
    assert "3" in by_name["ComfyUI-Workflow"].detail
