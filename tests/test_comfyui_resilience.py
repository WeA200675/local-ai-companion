from __future__ import annotations

import json

import httpx
import pytest

from app.media.comfyui_resilient import ResilientComfyUIClient, ResilientComfyUIError


def _workflow(path) -> None:
    path.write_text(
        json.dumps(
            {
                "3": {
                    "class_type": "KSampler",
                    "inputs": {
                        "seed": 1,
                        "steps": 15,
                        "cfg": 6.0,
                        "positive": ["6", 0],
                        "negative": ["7", 0],
                    },
                },
                "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "positive"}},
                "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "negative"}},
            }
        ),
        encoding="utf-8",
    )


def _finished_history(prompt_id: str) -> dict[str, object]:
    return {
        prompt_id: {
            "status": {"status_str": "success", "completed": True, "messages": []},
            "outputs": {
                "9": {
                    "images": [
                        {
                            "filename": "result.png",
                            "subfolder": "",
                            "type": "output",
                        }
                    ]
                }
            },
        }
    }


def test_history_reads_retry_without_duplicate_queue(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    _workflow(workflow)
    calls = {"queue": 0, "history": 0, "view": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            calls["queue"] += 1
            return httpx.Response(200, request=request, json={"prompt_id": "p1"})
        if request.url.path == "/history/p1":
            calls["history"] += 1
            if calls["history"] <= 2:
                return httpx.Response(503, request=request, json={"error": "busy"})
            return httpx.Response(200, request=request, json=_finished_history("p1"))
        if request.url.path == "/view":
            calls["view"] += 1
            return httpx.Response(200, request=request, content=b"png")
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = ResilientComfyUIClient(
            base_url="http://local",
            workflow_path=workflow,
            output_dir=tmp_path / "generated",
            client=http_client,
            read_retries=3,
            retry_backoff_seconds=0,
            poll_interval=0,
        )
        result = client.generate("positive", "negative", seed=42)

    assert result.path.read_bytes() == b"png"
    assert calls == {"queue": 1, "history": 3, "view": 1}


def test_queue_post_is_never_blindly_replayed(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    _workflow(workflow)
    queue_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal queue_calls
        if request.url.path == "/prompt":
            queue_calls += 1
            return httpx.Response(500, request=request, json={"error": "backend crash"})
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = ResilientComfyUIClient(
            base_url="http://local",
            workflow_path=workflow,
            output_dir=tmp_path / "generated",
            client=http_client,
            read_retries=3,
            retry_backoff_seconds=0,
        )
        with pytest.raises(ResilientComfyUIError) as exc_info:
            client.generate("positive", "negative", seed=42)

    assert exc_info.value.stage == "queue"
    assert "nicht automatisch wiederholt" in str(exc_info.value)
    assert queue_calls == 1


def test_execution_error_is_reported_immediately_with_node_context(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    _workflow(workflow)
    history_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal history_calls
        if request.url.path == "/prompt":
            return httpx.Response(200, request=request, json={"prompt_id": "bad"})
        if request.url.path == "/history/bad":
            history_calls += 1
            return httpx.Response(
                200,
                request=request,
                json={
                    "bad": {
                        "status": {
                            "status_str": "error",
                            "completed": False,
                            "messages": [
                                [
                                    "execution_error",
                                    {
                                        "node_id": "3",
                                        "exception_message": "CUDA out of memory",
                                    },
                                ]
                            ],
                        },
                        "outputs": {},
                    }
                },
            )
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = ResilientComfyUIClient(
            base_url="http://local",
            workflow_path=workflow,
            output_dir=tmp_path / "generated",
            client=http_client,
            poll_interval=0,
        )
        with pytest.raises(ResilientComfyUIError) as exc_info:
            client.generate("positive", "negative", seed=42)

    error = exc_info.value
    assert error.stage == "execution"
    assert error.prompt_id == "bad"
    assert "Node 3" in str(error)
    assert "CUDA out of memory" in str(error)
    assert history_calls == 1


def test_timeout_attempts_targeted_queue_cleanup(tmp_path) -> None:
    workflow = tmp_path / "workflow.json"
    _workflow(workflow)
    calls = {"queue": 0, "cleanup": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/prompt":
            calls["queue"] += 1
            return httpx.Response(200, request=request, json={"prompt_id": "slow"})
        if request.url.path == "/history/slow":
            return httpx.Response(200, request=request, json={})
        if request.url.path == "/queue":
            calls["cleanup"] += 1
            payload = json.loads(request.content.decode("utf-8"))
            assert payload == {"delete": ["slow"]}
            return httpx.Response(200, request=request, json={})
        raise AssertionError(request.url)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = ResilientComfyUIClient(
            base_url="http://local",
            workflow_path=workflow,
            output_dir=tmp_path / "generated",
            client=http_client,
            timeout=0.01,
            poll_interval=0,
            read_retries=0,
        )
        with pytest.raises(ResilientComfyUIError) as exc_info:
            client.generate("positive", "negative", seed=42)

    assert exc_info.value.stage == "timeout"
    assert exc_info.value.prompt_id == "slow"
    assert calls["queue"] == 1
    assert calls["cleanup"] == 1
