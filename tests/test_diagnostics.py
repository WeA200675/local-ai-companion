from __future__ import annotations

import json

import httpx

from app.diagnostics import run_diagnostics
from app.settings import AppSettings


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_local_diagnostics_success(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "positive"}},
                "7": {"inputs": {"text": "negative"}},
                "3": {"inputs": {"seed": 1}},
                "12": {"inputs": {"image": "example.png"}},
            }
        ),
        encoding="utf-8",
    )
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "local-model"}]})
        if request.url.path == "/api/chat":
            seen.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(200, json={"message": {"content": "OK"}})
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={"system": {}})
        raise AssertionError(request.url)

    client = _client(handler)
    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
        media_reference_enabled=True,
        media_reference_node="12",
        media_reference_input_key="image",
    )

    results = run_diagnostics(settings, timeout=0.1, client=client)
    by_name = {result.name: result for result in results}
    assert all(result.ok for result in results)
    assert by_name["Modell-Inferenz"].ok is True
    assert seen["model"] == "local-model"
    assert seen["stream"] is False
    assert seen["options"] == {"temperature": 0, "num_predict": 8}
    client.close()


def test_local_diagnostics_reports_missing_model_and_nodes(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps({"6": {"inputs": {"text": "positive"}}}), encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "another-model"}]})
        if request.url.path == "/api/chat":
            raise AssertionError("inference should be skipped when the model is absent")
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={})
        raise AssertionError(request.url)

    client = _client(handler)
    settings = AppSettings(
        model_name="wanted-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
    )

    results = run_diagnostics(settings, timeout=0.1, client=client)
    by_name = {result.name: result for result in results}
    assert by_name["Sprachmodell"].ok is False
    assert "wanted-model" in by_name["Sprachmodell"].detail
    assert by_name["Modell-Inferenz"].ok is False
    assert "Nicht ausgeführt" in by_name["Modell-Inferenz"].detail
    assert by_name["ComfyUI-Workflow"].ok is False
    assert "7" in by_name["ComfyUI-Workflow"].detail
    assert "3" in by_name["ComfyUI-Workflow"].detail
    client.close()


def test_local_diagnostics_reports_bad_reference_input(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "positive"}},
                "7": {"inputs": {"text": "negative"}},
                "3": {"inputs": {"seed": 1}},
                "12": {"inputs": {"wrong": "example.png"}},
            }
        ),
        encoding="utf-8",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "local-model"}]})
        if request.url.path == "/api/chat":
            return httpx.Response(200, json={"message": {"content": "OK"}})
        if request.url.path == "/system_stats":
            return httpx.Response(200, json={})
        raise AssertionError(request.url)

    client = _client(handler)
    settings = AppSettings(
        model_name="local-model",
        media_enabled=True,
        media_workflow=str(workflow),
        media_output_dir=str(tmp_path / "generated"),
        media_reference_enabled=True,
        media_reference_node="12",
        media_reference_input_key="image",
    )

    results = run_diagnostics(settings, timeout=0.1, client=client)
    by_name = {result.name: result for result in results}
    assert by_name["Modell-Inferenz"].ok is True
    assert by_name["ComfyUI-Workflow"].ok is False
    assert "image" in by_name["ComfyUI-Workflow"].detail
    client.close()


def test_model_inference_reports_ollama_500_as_backend_failure(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}]})
        if request.url.path == "/api/chat":
            return httpx.Response(
                500,
                json={
                    "error": "llama-server process has terminated: exit status 0xc0000005"
                },
            )
        raise AssertionError(request.url)

    client = _client(handler)
    settings = AppSettings(
        model_name="qwen2.5:7b",
        media_enabled=False,
        media_output_dir=str(tmp_path / "generated"),
    )

    results = run_diagnostics(settings, timeout=0.1, client=client)
    inference = next(result for result in results if result.name == "Modell-Inferenz")
    assert inference.ok is False
    assert "HTTP 500" in inference.detail
    assert "llama-server process has terminated" in inference.detail
    assert "ollama run qwen2.5:7b" in inference.detail
    assert "unterhalb der Companion-App" in inference.detail
    client.close()


def test_model_inference_reports_timeout_with_next_action(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "slow-model"}]})
        if request.url.path == "/api/chat":
            raise httpx.ReadTimeout("timed out", request=request)
        raise AssertionError(request.url)

    client = _client(handler)
    settings = AppSettings(
        model_name="slow-model",
        media_enabled=False,
        media_output_dir=str(tmp_path / "generated"),
    )

    results = run_diagnostics(settings, timeout=0.1, client=client)
    inference = next(result for result in results if result.name == "Modell-Inferenz")
    assert inference.ok is False
    assert "45" in inference.detail
    assert "ollama ps" in inference.detail
    assert "ollama run slow-model" in inference.detail
    client.close()
