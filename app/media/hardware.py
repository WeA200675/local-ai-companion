from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Literal

import httpx

HardwareTier = Literal["unknown", "cpu", "low", "medium", "high"]
HardwareQuality = Literal["draft", "balanced", "high"]


def _gb(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return round(float(value) / (1024**3), 2)


@dataclass(frozen=True, slots=True)
class MediaHardwareBudget:
    """Conservative local render budget inferred from ComfyUI system stats."""

    tier: HardwareTier = "unknown"
    device_type: str = "unknown"
    device_name: str = "unknown"
    vram_total_gb: float | None = None
    vram_free_gb: float | None = None
    ram_free_gb: float | None = None
    image_megapixel_cap: float = 1.20
    motion_megapixel_cap: float = 0.72
    max_motion_frames: int = 64
    max_quality: HardwareQuality = "high"
    motion_recommended: bool = True
    source: str = "unavailable"

    def summary(self) -> str:
        parts = [f"tier {self.tier}", f"device {self.device_name}"]
        if self.vram_free_gb is not None:
            parts.append(f"free VRAM {self.vram_free_gb:.1f} GB")
        elif self.vram_total_gb is not None:
            parts.append(f"VRAM {self.vram_total_gb:.1f} GB")
        if self.ram_free_gb is not None:
            parts.append(f"free RAM {self.ram_free_gb:.1f} GB")
        parts.append(f"max quality {self.max_quality}")
        parts.append(
            "motion recommended" if self.motion_recommended else "prefer still image"
        )
        return ", ".join(parts)


def budget_from_system_stats(payload: object) -> MediaHardwareBudget:
    if not isinstance(payload, dict):
        return MediaHardwareBudget(source="invalid system_stats")

    system = payload.get("system")
    system = system if isinstance(system, dict) else {}
    ram_free = _gb(system.get("ram_free"))

    devices = payload.get("devices")
    devices = devices if isinstance(devices, list) else []
    candidates: list[tuple[float, dict[str, Any]]] = []
    for raw in devices:
        if not isinstance(raw, dict):
            continue
        free = _gb(raw.get("vram_free")) or _gb(raw.get("torch_vram_free")) or 0.0
        total = _gb(raw.get("vram_total")) or _gb(raw.get("torch_vram_total")) or 0.0
        candidates.append((max(free, total), raw))

    if not candidates:
        # A reachable ComfyUI instance with no accelerator entry is treated as a
        # CPU-class budget rather than failing media generation completely.
        return MediaHardwareBudget(
            tier="cpu",
            device_type="cpu",
            device_name="CPU / no accelerator reported",
            ram_free_gb=ram_free,
            image_megapixel_cap=0.45,
            motion_megapixel_cap=0.24,
            max_motion_frames=24,
            max_quality="draft",
            motion_recommended=False,
            source="ComfyUI /system_stats",
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    device = candidates[0][1]
    device_type = str(device.get("type") or "unknown").strip().casefold() or "unknown"
    device_name = str(device.get("name") or device_type or "unknown").strip()
    vram_total = _gb(device.get("vram_total")) or _gb(device.get("torch_vram_total"))
    vram_free = _gb(device.get("vram_free")) or _gb(device.get("torch_vram_free"))

    if "cpu" in device_type or device_name.casefold().startswith("cpu"):
        tier: HardwareTier = "cpu"
    else:
        basis = vram_free if vram_free is not None else vram_total
        if basis is None:
            tier = "medium" if device_type != "unknown" else "unknown"
        elif basis < 5.5:
            tier = "low"
        elif basis < 10.0:
            tier = "medium"
        else:
            tier = "high"

    settings: dict[HardwareTier, tuple[float, float, int, HardwareQuality, bool]] = {
        "unknown": (1.20, 0.72, 64, "high", True),
        "cpu": (0.45, 0.24, 24, "draft", False),
        "low": (0.70, 0.35, 32, "balanced", False),
        "medium": (1.15, 0.65, 56, "high", True),
        "high": (1.80, 1.00, 96, "high", True),
    }
    image_cap, motion_cap, max_frames, max_quality, motion_recommended = settings[tier]
    return MediaHardwareBudget(
        tier=tier,
        device_type=device_type,
        device_name=device_name,
        vram_total_gb=vram_total,
        vram_free_gb=vram_free,
        ram_free_gb=ram_free,
        image_megapixel_cap=image_cap,
        motion_megapixel_cap=motion_cap,
        max_motion_frames=max_frames,
        max_quality=max_quality,
        motion_recommended=motion_recommended,
        source="ComfyUI /system_stats",
    )


class ComfyUIHardwareProbe:
    """Small cached probe so media planning does not hammer ComfyUI."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.5,
        cache_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_seconds = max(1.0, cache_seconds)
        self._cached: MediaHardwareBudget | None = None
        self._cached_at = 0.0

    def invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0

    def current(self) -> MediaHardwareBudget:
        now = time.monotonic()
        if self._cached is not None and now - self._cached_at < self.cache_seconds:
            return self._cached
        try:
            response = httpx.get(f"{self.base_url}/system_stats", timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            budget = budget_from_system_stats(payload)
        except (httpx.HTTPError, ValueError):
            budget = MediaHardwareBudget(source="ComfyUI unavailable")
        self._cached = budget
        self._cached_at = now
        return budget
