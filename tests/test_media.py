from __future__ import annotations

import json

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
            }
        ),
        encoding="utf-8",
    )

    client = ComfyUIClient(
        workflow_path=workflow_path,
        output_dir=tmp_path / "generated",
    )
    workflow = client.build_workflow("new positive", "new negative", seed=123456)
    client.close()

    assert workflow["6"]["inputs"]["text"] == "new positive"
    assert workflow["7"]["inputs"]["text"] == "new negative"
    assert workflow["3"]["inputs"]["seed"] == 123456
