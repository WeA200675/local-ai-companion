from __future__ import annotations

from collections.abc import Iterable

from app.ai.persona import PersonaState
from app.media.planner import MediaIntent


def build_visual_prompt(
    intent: MediaIntent,
    persona: PersonaState,
    preference_tags: Iterable[str] = (),
) -> tuple[str, str]:
    """Compile a model-agnostic visual intent into positive/negative prompts.

    The generated prompt is intentionally backend-neutral. ComfyUI workflows can
    decide how to route it into CLIP/T5 encoders, LoRAs, ControlNet, etc.
    """

    tags = [tag.strip() for tag in preference_tags if tag.strip()]
    wardrobe = ", ".join(item.strip() for item in intent.wardrobe if item.strip())
    style = (
        "cinematic adult fetish-inspired portrait, mature adult subject, dramatic lighting, "
        "high detail, coherent anatomy, expressive pose, tasteful sensual atmosphere"
    )
    personality = (
        f"dominant presence {persona.dominance.current:.2f}, "
        f"strict mood {persona.strictness.current:.2f}, "
        f"teasing energy {persona.teasing.current:.2f}, "
        f"creative styling {persona.creativity.current:.2f}"
    )
    tag_text = ", ".join(tags[:20]) if tags else "dark elegant styling"
    continuity = (
        f", consistent character identity {intent.continuity_key}"
        if intent.continuity_key
        else ""
    )
    wardrobe_text = f", wardrobe: {wardrobe}" if wardrobe else ""
    motion_text = f", motion direction: {intent.motion}" if intent.motion else ""
    direction = (
        f"framing: {intent.framing or 'portrait'}, "
        f"camera angle: {intent.camera_angle or 'eye level'}, "
        f"lighting direction: {intent.lighting or 'cinematic'}, "
        f"composition: {intent.composition or 'balanced composition'}"
    )
    positive = (
        f"{style}, visual style: {intent.visual_style or 'cinematic'}, mood: {intent.mood}, "
        f"theme: {intent.theme or 'private adult scene'}, intensity {intent.intensity:.2f}, "
        f"{direction}, {personality}, user style preferences: {tag_text}"
        f"{wardrobe_text}{motion_text}{continuity}"
    )

    # Keep the visual generator in a clearly adult, non-explicit lane and avoid
    # common generation defects. The companion may be provocative without
    # requiring graphic sexual imagery.
    negative = (
        "minor, child, teen, young-looking, explicit sex act, graphic nudity, genital focus, "
        "non-consensual violence, gore, injury, text, watermark, logo, low quality, blurry, "
        "bad anatomy, malformed hands, extra fingers, duplicate limbs"
    )
    return positive, negative
