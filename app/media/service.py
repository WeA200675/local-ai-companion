from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.ai.model import ChatMessage, LocalModelError, OllamaClient
from app.ai.persona import PersonaState
from app.media.comfyui import ComfyUIClient, ComfyUIError, GeneratedMedia
from app.media.planner import MediaIntent, MediaPlanner
from app.media.prompting import build_visual_prompt
from app.memory.store import StateStore
from app.settings import AppSettings


@dataclass(frozen=True, slots=True)
class MediaResult:
    intent: MediaIntent
    generated: GeneratedMedia
    history_id: int | None = None

    @property
    def path(self) -> Path:
        return self.generated.path


class MediaService:
    """Coordinates local visual planning, preference memory and generation."""

    def __init__(
        self,
        model: OllamaClient,
        backend: ComfyUIClient,
        *,
        store: StateStore | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self.model = model
        self.backend = backend
        self.store = store
        self.settings = settings or AppSettings()
        self.planner = MediaPlanner()

    @property
    def enabled(self) -> bool:
        return self.settings.media_enabled and self.backend.enabled

    def close(self) -> None:
        self.backend.close()

    def _visual_cues(self, limit: int = 8) -> tuple[list[str], list[str]]:
        if self.store is None:
            return [], []
        profile = self.store.load_visual_preferences()
        liked = [
            cue
            for cue in profile.top_liked(limit * 2)
            if profile.liked.get(cue, 0) > profile.disliked.get(cue, 0)
        ][:limit]
        disliked = [
            cue
            for cue in profile.top_disliked(limit * 2)
            if profile.disliked.get(cue, 0) > profile.liked.get(cue, 0)
        ][:limit]
        return liked, disliked

    def _reference_path(self, continuity_key: str | None) -> Path | None:
        """Select the newest liked local image for this recurring character."""

        if (
            not continuity_key
            or not self.settings.media_reference_enabled
            or self.store is None
        ):
            return None
        for event in self.store.list_media_events(limit=self.settings.media_history_limit):
            if event.get("continuity_key") != continuity_key:
                continue
            if event.get("feedback") != "positive":
                continue
            path = Path(str(event.get("path") or "")).expanduser()
            if path.exists() and path.is_file():
                return path
        return None

    def plan(
        self,
        *,
        user_text: str,
        assistant_text: str,
        persona: PersonaState,
        preference_tags: Iterable[str] = (),
    ) -> MediaIntent:
        if not self.enabled:
            return MediaIntent(generate=False, reason="media backend disabled")

        tags = [tag.strip() for tag in preference_tags if tag.strip()]
        liked_cues, disliked_cues = self._visual_cues()
        planner_prompt = f"""You are the visual director for a private local adult companion app.
Return exactly one JSON object matching this schema:
{{
  "generate": boolean,
  "kind": "image" | "gif" | "video",
  "mood": string,
  "theme": string,
  "visual_style": string,
  "wardrobe": [string],
  "intensity": number from 0 to 1,
  "continuity_key": string or null,
  "reason": string
}}

Decide whether a visual would genuinely improve this specific exchange. Prefer image unless motion is important.
Keep every depicted person clearly adult. Visuals may be provocative, fetish-inspired, dominant, teasing, sensual, or dark, but do not plan graphic sexual acts, genital-focused imagery, minors, coercive violence, gore, or injury.
Use historical image feedback as a soft style preference only; the user's current request and scene context take priority.
When the recurring companion character is depicted and continuity is enabled, use continuity_key "{self.settings.continuity_key}". Otherwise use null.
Do not include prose outside the JSON object."""
        context = (
            f"Persona name: {persona.name}\n"
            f"Dominance: {persona.dominance.current:.2f}\n"
            f"Strictness: {persona.strictness.current:.2f}\n"
            f"Teasing: {persona.teasing.current:.2f}\n"
            f"Creativity: {persona.creativity.current:.2f}\n"
            f"Visual continuity enabled: {self.settings.continuity_enabled}\n"
            f"Preference tags: {', '.join(tags[:24]) if tags else 'none'}\n"
            f"Historically liked visual cues: {', '.join(liked_cues) if liked_cues else 'none yet'}\n"
            f"Historically disliked visual cues: {', '.join(disliked_cues) if disliked_cues else 'none yet'}\n\n"
            f"User message:\n{user_text}\n\n"
            f"Companion reply:\n{assistant_text}"
        )
        try:
            payload = self.model.chat_json(
                [ChatMessage(role="user", content=context)],
                system_prompt=planner_prompt,
                temperature=0.2,
            )
            intent = self.planner.from_model_payload(payload)
            if not self.settings.continuity_enabled and intent.continuity_key:
                intent = intent.model_copy(update={"continuity_key": None})
            return intent
        except (LocalModelError, ValueError):
            return MediaIntent(generate=False, reason="planner failed")

    def generate_for_exchange(
        self,
        *,
        user_text: str,
        assistant_text: str,
        persona: PersonaState,
        preference_tags: Iterable[str] = (),
    ) -> MediaResult | None:
        intent = self.plan(
            user_text=user_text,
            assistant_text=assistant_text,
            persona=persona,
            preference_tags=preference_tags,
        )
        if not intent.generate:
            return None

        positive, negative = build_visual_prompt(intent, persona, preference_tags)
        liked_cues, disliked_cues = self._visual_cues(limit=6)
        if liked_cues:
            positive = f"{positive}, preferred visual cues: {', '.join(liked_cues)}"
        if disliked_cues:
            negative = f"{negative}, user-disliked visual cues: {', '.join(disliked_cues)}"

        continuity_key = intent.continuity_key if self.settings.continuity_enabled else None
        profile = None
        seed = None
        if continuity_key and self.store is not None:
            profile = self.store.load_character_profile(continuity_key)
            seed = profile.seed
            positive = f"{positive}, {profile.appearance_prompt}"

        reference_path = self._reference_path(continuity_key)
        try:
            generated = self.backend.generate(
                positive,
                negative,
                seed=seed,
                reference_path=reference_path,
            )
        except ComfyUIError:
            return None

        if profile is not None and self.store is not None:
            profile.register_generation(str(generated.path))
            self.store.save_character_profile(profile)

        history_id = None
        if self.store is not None:
            history_id = self.store.record_media_event(
                path=str(generated.path),
                kind=generated.kind,
                prompt_id=generated.prompt_id,
                seed=generated.seed,
                continuity_key=continuity_key,
                intent=intent.model_dump(mode="json"),
            )

        return MediaResult(intent=intent, generated=generated, history_id=history_id)
