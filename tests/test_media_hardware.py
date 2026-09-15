from __future__ import annotations

from app.media.hardware import MediaHardwareBudget, budget_from_system_stats
from app.media.planner import MediaIntent
from app.media.rendering import MediaRenderCalculator


def _gib(value: float) -> int:
    return int(value * 1024**3)


def test_comfyui_stats_classify_low_and_high_vram_budgets() -> None:
    low = budget_from_system_stats(
        {
            "system": {"ram_free": _gib(12)},
            "devices": [
                {
                    "name": "Example GPU 4GB",
                    "type": "cuda",
                    "vram_total": _gib(4),
                    "vram_free": _gib(3.5),
                }
            ],
        }
    )
    high = budget_from_system_stats(
        {
            "devices": [
                {
                    "name": "Example GPU 16GB",
                    "type": "cuda",
                    "vram_total": _gib(16),
                    "vram_free": _gib(12),
                }
            ]
        }
    )

    assert low.tier == "low"
    assert low.motion_recommended is False
    assert low.image_megapixel_cap < high.image_megapixel_cap
    assert high.tier == "high"
    assert high.motion_recommended is True
    assert high.max_motion_frames > low.max_motion_frames


def test_missing_accelerator_uses_conservative_cpu_budget() -> None:
    budget = budget_from_system_stats({"system": {"ram_free": _gib(8)}, "devices": []})

    assert budget.tier == "cpu"
    assert budget.max_quality == "draft"
    assert budget.motion_recommended is False
    assert budget.max_motion_frames == 24


def test_hardware_budget_caps_quality_pixels_and_motion_frames() -> None:
    calculator = MediaRenderCalculator()
    hardware = MediaHardwareBudget(
        tier="low",
        device_type="cuda",
        device_name="Example low VRAM GPU",
        vram_free_gb=4.0,
        image_megapixel_cap=0.60,
        motion_megapixel_cap=0.30,
        max_motion_frames=24,
        max_quality="balanced",
        motion_recommended=False,
        source="test",
    )
    plan = calculator.calculate(
        MediaIntent(
            generate=True,
            kind="video",
            framing="portrait",
            motion="energetic camera movement",
            intensity=1.0,
        ),
        quality="high",
        max_megapixels=1.5,
        hardware_budget=hardware,
    )

    assert plan.quality == "balanced"
    assert plan.megapixels <= 0.36
    assert plan.frames <= 24
    assert plan.hardware_tier == "low"
    assert plan.hardware_vram_free_gb == 4.0
    assert any("quality reduced" in item for item in plan.rationale)
    assert any("motion capped" in item for item in plan.rationale)


def test_avoid_tags_do_not_change_aspect_ratio() -> None:
    calculator = MediaRenderCalculator()
    plan = calculator.calculate(
        MediaIntent(generate=True, kind="image", framing="portrait"),
        ["avoid:standing", "avoid:wide frame"],
    )

    assert plan.aspect_ratio == "4:5"
