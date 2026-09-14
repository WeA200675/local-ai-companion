from __future__ import annotations

import json

import httpx

from app.ai.persona import PersonaState
from app.media.comfyui import ComfyUIClient
from app.media.planner import MediaIntent
from app.media.prompting import build_visual_prompt


def test_visual_prompt_includes_intent_and_adult_guardrails() -> None:
    persona = PersonaState()
    intent = MediaIntent(
        generate=True,
        mood="dominant",
        theme="dark private lounge",
        visual_style="cinematic noir",
        wardrobe=["latex jacket", "boots"],
        intensity=0.9,
        continuity_key="persona-main",
    )

    positive, negative = build_visual_prompt(intent, persona, ["leather", "teasing"])

    assert "dominant" in positive
    assert "cinematic noir" in positive
    assert "latex jacket" in positive
    assert "persona-main" in positive
    assert "minor" in negative
    assert "explicit sex act" in negative


def test_comfyui_workflow_injection(tmp_path) -> None:
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "6": {"inputs": {"text": "old positive"}},
                "7": {"inputs": {"text": "old negative"}},
                "3": {"inputs": {"seed": 1}},
                "12": {"inputs": {"image": "old.png"}},
            }
        ),
        encoding="utf-8",
    )

    client = ComfyUIClient(
        workflow_path=workflow_path,
        reference_node="12",
        reference_input_key="image",
        output_dir=tmp_path / "generated",
    )
    workflow = client.build_workflow(
        "new positive",
        "new negative",
        seed=123456,
        reference_name="companion_refs/liked.png",
    )
    client.close()

    assert workflow["6"]["inputs"]["text"] == "new positive"
    assert workflow["7"]["inputs"]["text"] == "new negative"
    assert workflow["3"]["inputs"]["seed"] == 123456
    assert workflow["12"]["inputs"]["image"] == "companion_refs/liked.png"


def test_comfyui_upload_reference_returns_uploaded_name(tmp_path) -> None:
    reference = tmp_path / "liked.png"
    reference.write_bytes(b"fake-image")
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["content_type"] = request.headers.get("content-type", "")
        seen["body"] = request.content
        return httpx.Response(
            200,
            json={"name": "liked.png", "subfolder": "companion_refs", "type": "input"},
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = ComfyUIClient(
        base_url="http://local",
        reference_node="12",
        client=http_client,
        output_dir=tmp_path / "generated",
    )

    uploaded_name = client._upload_reference(reference)

    assert uploaded_name == "companion_refs/liked.png"
    assert seen["path"] == "/upload/image"
    assert "multipart/form-data" in str(seen["content_type"])
    assert b"liked.png" in seen["body"]
    http_client.close()
