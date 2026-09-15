from __future__ import annotations

from math import sqrt
from typing import Literal

from pydantic import BaseModel, Field

from app.media.planner import MediaIntent

RenderQuality = Literal["draft", "balanced", "high"]


class MediaRenderPlan(BaseModel):
    """Backend-neutral numeric render plan calculated locally before ComfyUI runs."""

    kind: Literal["image", "gif", "video"] = "image"
    quality: RenderQuality = "balanced"
    width: int = Field(ge=256, le=4096)
    height: int = Field(ge=256, le=4096)
    aspect_ratio: str
    steps: int = Field(ge=1, le=200)
    cfg: float = Field(ge=0.0, le=30.0)
    denoise: float = Field(ge=0.0, le=1.0)
    frames: int = Field(default=1, ge=1, le=1000)
    fps: int = Field(default=1, ge=1, le=240)
    duration_seconds: float = Field(default=0.0, ge=0.0, le=120.0)
    megapixels: float = Field(ge=0.01, le=32.0)
    estimated_work_units: float = Field(ge=0.0)
    rationale: list[str] = Field(default_factory=list)

    def prompt_text(self) -> str:
        motion = ""
        if self.kind != "image":
            motion = f", {self.frames} frames at {self.fps} fps (~{self.duration_seconds:.1f}s)"
        return (
            f"{self.width}x{self.height} ({self.aspect_ratio}), {self.steps} steps, "
            f"CFG {self.cfg:.1f}, denoise {self.denoise:.2f}{motion}; "
            f"estimated work {self.estimated_work_units:.1f} units"
        )


class MediaRenderCalculator:
    """Compute practical local render parameters from visual intent.

    The calculator is deliberately deterministic and model/backend neutral. It
    gives ComfyUI a useful target without assuming a specific checkpoint,
    sampler, scheduler, GPU or proprietary runtime.
    """

    _QUALITY_BASE = {
        "draft": (704, 18, 4.8),
        "balanced": (896, 28, 5.8),
        "high": (1088, 38, 6.4),
    }

    @staticmethod
    def _clean_tags(preference_tags: list[str]) -> set[str]:
        return {" ".join(item.split()).casefold() for item in preference_tags if item.strip()}

    @staticmethod
    def _aspect(intent: MediaIntent, tags: set[str]) -> tuple[int, int, str, str]:
        text = " ".join(
            [
                intent.framing,
                intent.composition,
                intent.camera_angle,
                intent.theme,
                *sorted(tags),
            ]
        ).casefold()

        wide_tokens = (
            "wide frame",
            "environmental",
            "landscape",
            "establishing",
            "cinematic wide",
            "room",
        )
        square_tokens = ("square", "symmetrical portrait", "centered portrait")
        tall_tokens = (
            "full body",
            "full-body",
            "silhouette",
            "footwear",
            "low angle",
            "standing",
            "vertical",
        )

        if any(token in text for token in wide_tokens):
            return 16, 9, "16:9", "wide/environmental framing"
        if any(token in text for token in square_tokens):
            return 1, 1, "1:1", "square/centered framing"
        if any(token in text for token in tall_tokens):
            return 2, 3, "2:3", "full-body/vertical framing"
        return 4, 5, "4:5", "portrait framing"

    @staticmethod
    def _round64(value: float) -> int:
        return max(256, int(round(value / 64.0)) * 64)

    def calculate(
        self,
        intent: MediaIntent,
        preference_tags: list[str] | None = None,
        *,
        quality: RenderQuality = "balanced",
        max_megapixels: float | None = None,
    ) -> MediaRenderPlan:
        tags = self._clean_tags(preference_tags or [])
        base_long, base_steps, base_cfg = self._QUALITY_BASE[quality]
        ratio_w, ratio_h, ratio_label, ratio_reason = self._aspect(intent, tags)

        # Motion costs multiply quickly; reduce the spatial target before frame
        # calculation while keeping the composition ratio intact.
        long_edge = float(base_long)
        if intent.kind != "image":
            long_edge *= 0.82

        if ratio_w >= ratio_h:
            width = self._round64(long_edge)
            height = self._round64(long_edge * ratio_h / ratio_w)
        else:
            height = self._round64(long_edge)
            width = self._round64(long_edge * ratio_w / ratio_h)

        default_cap = 1.20 if intent.kind == "image" else 0.72
        cap = max(0.20, min(8.0, float(max_megapixels or default_cap)))
        current_mp = width * height / 1_000_000
        if current_mp > cap:
            scale = sqrt(cap / current_mp)
            width = self._round64(width * scale)
            height = self._round64(height * scale)

        intensity = max(0.0, min(1.0, float(intent.intensity)))
        steps = int(round(base_steps + (intensity - 0.5) * 8))
        steps = max(12, min(60, steps))
        cfg = max(3.0, min(9.0, base_cfg + (intensity - 0.5) * 1.2))
        denoise = 1.0

        frames = 1
        fps = 1
        duration = 0.0
        rationale = [ratio_reason, f"{quality} quality target"]
        if intent.kind != "image":
            # 2–4 seconds is long enough for a loop/reaction while keeping local
            # inference bounded. Higher intensity buys motion, not unlimited size.
            duration = 2.0 + intensity * 2.0
            fps = 12 if quality == "draft" else 16 if quality == "balanced" else 18
            frames = max(16, int(round(duration * fps / 4.0)) * 4)
            duration = frames / fps
            steps = max(12, steps - 5)
            cfg = max(3.0, cfg - 0.3)
            motion_text = " ".join([intent.motion, intent.theme]).casefold()
            if any(token in motion_text for token in ("subtle", "slow", "breath", "rain")):
                frames = max(16, frames - 8)
                duration = frames / fps
                rationale.append("subtle motion kept compact")
            else:
                rationale.append("motion duration derived from intensity")

        megapixels = width * height / 1_000_000
        frame_factor = 1.0 if intent.kind == "image" else max(1.0, frames / 8.0)
        work = megapixels * steps * frame_factor
        rationale.append(f"spatial cap {cap:.2f} MP")
        rationale.append("work estimate = megapixels × steps × motion factor")

        return MediaRenderPlan(
            kind=intent.kind,
            quality=quality,
            width=width,
            height=height,
            aspect_ratio=ratio_label,
            steps=steps,
            cfg=round(cfg, 2),
            denoise=denoise,
            frames=frames,
            fps=fps,
            duration_seconds=round(duration, 2),
            megapixels=round(megapixels, 3),
            estimated_work_units=round(work, 2),
            rationale=rationale,
        )
