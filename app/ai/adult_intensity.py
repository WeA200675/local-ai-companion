from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.memory.store import StateStore


SEXUALITY_LEVELS = (
    "Neutral",
    "Flirtend",
    "Sinnlich",
    "Erotisch",
    "Sehr intensiv",
)

KINK_LEVELS = (
    "Konventionell",
    "Experimentell",
    "Kinky",
    "Sehr kinky",
    "Sehr ungewöhnlich / intensiv",
)

SEXUALITY_BEHAVIOR = (
    "Keep the tone non-sexual unless the current user message explicitly asks to raise it.",
    "Use playful adult flirting, attraction, teasing, and suggestive tension without assuming the user wants more.",
    "Use a clearly sensual and intimate adult tone with confident attraction and stronger suggestive tension.",
    "Use a clearly erotic adult tone. Be direct, engaged, and responsive instead of retreating into generic small talk when the user's current direction is erotic.",
    "Use a highly intense, immersive adult erotic tone with strong initiative proportional to the Persona settings, while staying inside the user's current request and configured boundaries.",
)

KINK_BEHAVIOR = (
    "Stay conventional and do not invent kink themes merely to add intensity.",
    "Allow playful experimentation when the user signals interest; keep unusual themes exploratory rather than assumed.",
    "Be distinctly kink-forward around themes the user explicitly requests or lists as desired; allow a more daring and unconventional tone.",
    "Use a strongly kink-oriented, provocative, unconventional interaction style around the user's stated interests, with confident initiative when the Persona supports it.",
    "Use a very unconventional and intense kink-oriented tone around explicitly stated desired themes. Do not invent a new taboo, fetish, permission, or boundary merely because the level is high.",
)

# Visual direction deliberately stays in a non-graphic adult lane. These are
# composition/styling cues, not permissions for explicit acts. User-authored
# creative tags and the current request still outrank these soft cues.
SEXUALITY_VISUAL_CUES: tuple[tuple[str, ...], ...] = (
    (),
    (
        "playful adult flirtation",
        "suggestive eye contact",
        "light teasing body language",
    ),
    (
        "sensual adult atmosphere",
        "intimate composition",
        "confident sensual body language",
    ),
    (
        "erotic adult atmosphere",
        "provocative adult styling",
        "charged intimate composition",
    ),
    (
        "high-intensity adult erotic atmosphere",
        "bold provocative adult styling",
        "commanding intimate presence",
    ),
)

KINK_VISUAL_CUES: tuple[tuple[str, ...], ...] = (
    (),
    (
        "subtle experimental adult styling",
        "controlled power-dynamic undertone",
    ),
    (
        "fetish-inspired adult fashion",
        "clear power-dynamic staging",
        "deliberate ritualized posture",
    ),
    (
        "strong fetish-fashion direction",
        "commanding adult posture",
        "dark ritualized scene staging",
    ),
    (
        "unconventional fetish-inspired adult styling",
        "intense power-dynamic visual language",
        "dark editorial fetish atmosphere",
    ),
)


class AdultIntensityConfig(BaseModel):
    """User-controlled adult tone for one conversation.

    This is temporary/session state. It is deliberately separate from Persona,
    Core Memory and adaptive memory so a more intense session does not silently
    rewrite the companion's persistent personality.
    """

    sexuality_current: int = Field(default=1, ge=0, le=4)
    sexuality_max: int = Field(default=4, ge=0, le=4)
    sexuality_locked: bool = False
    kink_current: int = Field(default=0, ge=0, le=4)
    kink_max: int = Field(default=4, ge=0, le=4)
    kink_locked: bool = False
    dynamic_escalation: bool = True
    kink_preferences: list[str] = Field(default_factory=list, max_length=24)
    boundaries: list[str] = Field(default_factory=list, max_length=24)
    revision: int = Field(default=1, ge=1)

    @field_validator("kink_preferences", "boundaries", mode="before")
    @classmethod
    def _clean_list(cls, values: object) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            raw = values.replace("\n", ",").split(",")
        else:
            raw = list(values)  # type: ignore[arg-type]
        result: list[str] = []
        seen: set[str] = set()
        for value in raw:
            clean = " ".join(str(value or "").split())[:120]
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result[:24]

    @model_validator(mode="after")
    def _clamp_current_to_max(self) -> "AdultIntensityConfig":
        self.sexuality_current = min(self.sexuality_current, self.sexuality_max)
        self.kink_current = min(self.kink_current, self.kink_max)
        return self

    @property
    def sexuality_label(self) -> str:
        return SEXUALITY_LEVELS[self.sexuality_current]

    @property
    def sexuality_max_label(self) -> str:
        return SEXUALITY_LEVELS[self.sexuality_max]

    @property
    def kink_label(self) -> str:
        return KINK_LEVELS[self.kink_current]

    @property
    def kink_max_label(self) -> str:
        return KINK_LEVELS[self.kink_max]

    @property
    def sexuality_behavior(self) -> str:
        return SEXUALITY_BEHAVIOR[self.sexuality_current]

    @property
    def kink_behavior(self) -> str:
        return KINK_BEHAVIOR[self.kink_current]

    def prompt_text(self) -> str:
        preferences = ", ".join(self.kink_preferences) if self.kink_preferences else "none specified"
        boundaries = ", ".join(self.boundaries) if self.boundaries else "none specified"
        dynamic = "enabled" if self.dynamic_escalation else "disabled"
        return (
            "Adult intimacy controls for this conversation: "
            f"sexuality {self.sexuality_current}/4 ({self.sexuality_label}), "
            f"maximum {self.sexuality_max}/4 ({self.sexuality_max_label}); "
            f"kink intensity {self.kink_current}/4 ({self.kink_label}), "
            f"maximum {self.kink_max}/4 ({self.kink_max_label}); "
            f"dynamic escalation {dynamic}; kink preferences: {preferences}; hard boundaries: {boundaries}. "
            f"Sexuality behavior direction: {self.sexuality_behavior} "
            f"Kink behavior direction: {self.kink_behavior} "
            "Use these only as user-controlled direction for consensual adult fictional interaction. "
            "The current user message always has priority. Match an explicit request for more intensity only "
            "within the configured maxima, and immediately de-escalate when the user asks for less or to stop."
        )

    def visual_style_tags(self) -> list[str]:
        """Return soft positive and negative tags for the local media pipeline.

        Positive tags express the current adult session level through styling,
        posture and atmosphere. Hard boundaries use an ``avoid:`` prefix so the
        media prompt compiler can place them in the negative prompt instead of
        accidentally treating them as desired visual content.
        """

        result: list[str] = [
            *SEXUALITY_VISUAL_CUES[self.sexuality_current],
            *KINK_VISUAL_CUES[self.kink_current],
        ]
        result.extend(f"avoid:{item}" for item in self.boundaries[:16])
        return result

    def visual_text(self) -> str:
        """Media-safe summary of the current adult visual direction."""

        cues = [
            *SEXUALITY_VISUAL_CUES[self.sexuality_current],
            *KINK_VISUAL_CUES[self.kink_current],
        ]
        cue_text = ", ".join(cues) if cues else "no extra erotic or kink styling"
        boundary_text = ", ".join(self.boundaries) if self.boundaries else "none specified"
        return (
            f"Adult visual direction: sexuality {self.sexuality_current}/4 ({self.sexuality_label}); "
            f"kink {self.kink_current}/4 ({self.kink_label}). "
            f"Soft visual cues: {cue_text}. Hard visual boundaries to avoid: {boundary_text}. "
            "These levels do not force a medium to be generated. If a visual is useful, express the current "
            "level through clearly adult mood, fashion/material styling, posture, camera language and atmosphere. "
            "Do not turn intensity into graphic sexual acts, genital-focused imagery, or explicit nudity."
        )


class AdultIntensityState(BaseModel):
    by_conversation: dict[str, AdultIntensityConfig] = Field(default_factory=dict)
    revision: int = Field(default=1, ge=1)


class AdultIntensityRepository:
    STATE_KEY = "adult_intensity"

    _STRONG_STOP = (
        "stopp",
        "stop",
        "abbrechen",
        "zu viel",
        "keine erotik",
        "nicht erotisch",
        "nicht sexuell",
    )
    _SOFTER = (
        "weniger intensiv",
        "weniger",
        "sanfter",
        "langsamer",
        "zurück",
        "zurueck",
        "harmloser",
    )
    _SEXUAL_UP = (
        "erotisch",
        "sexuell",
        "sexy",
        "sinnlich",
        "intimer",
        "intim",
        "heiß",
        "heiss",
        "lustvoll",
        "versaut",
        "dirty",
    )
    _KINK_UP = (
        "kink",
        "kinky",
        "pervers",
        "fetisch",
        "dominanter",
        "devoter",
        "ungewöhnlicher",
        "ungewoehnlicher",
        "tabuloser",
    )
    _MORE = (
        "mehr davon",
        "noch mehr",
        "intensiver",
        "weiter steigern",
        "steiger dich",
    )

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def load(self) -> AdultIntensityState:
        payload = self.store._load_app_state(self.STATE_KEY)  # noqa: SLF001
        if payload is None:
            return AdultIntensityState()
        try:
            return AdultIntensityState.model_validate_json(payload)
        except ValueError:
            return AdultIntensityState()

    def save(self, state: AdultIntensityState) -> None:
        self.store._save_app_state(self.STATE_KEY, state.model_dump_json())  # noqa: SLF001

    def config(self, conversation_id: str) -> AdultIntensityConfig:
        state = self.load()
        config = state.by_conversation.get(conversation_id)
        if config is None:
            return AdultIntensityConfig()
        return config.model_copy(deep=True)

    def set_config(
        self,
        conversation_id: str,
        config: AdultIntensityConfig,
    ) -> AdultIntensityConfig:
        state = self.load()
        saved = config.model_copy(deep=True)
        saved.revision += 1
        state.by_conversation[conversation_id] = saved
        state.revision += 1
        self.save(state)
        return saved.model_copy(deep=True)

    def reset_session_levels(self, conversation_id: str) -> AdultIntensityConfig:
        config = self.config(conversation_id)
        config.sexuality_current = min(1, config.sexuality_max)
        config.kink_current = 0
        return self.set_config(conversation_id, config)

    def observe_user_signal(
        self,
        conversation_id: str,
        user_text: str,
    ) -> tuple[AdultIntensityConfig, bool]:
        """Apply a small bounded session-only shift from explicit user language.

        The heuristic intentionally reacts only to direct wording. It never
        changes maxima, locks, preference lists, Persona, or any memory layer.
        """

        config = self.config(conversation_id)
        if not config.dynamic_escalation:
            return config, False

        text = " ".join(user_text.casefold().split())
        if not text:
            return config, False

        original = (config.sexuality_current, config.kink_current)

        if any(term in text for term in self._STRONG_STOP):
            if not config.sexuality_locked:
                config.sexuality_current = 0
            if not config.kink_locked:
                config.kink_current = 0
        elif any(term in text for term in self._SOFTER):
            if not config.sexuality_locked:
                config.sexuality_current = max(0, config.sexuality_current - 1)
            if not config.kink_locked:
                config.kink_current = max(0, config.kink_current - 1)
        else:
            sexual_signal = any(term in text for term in self._SEXUAL_UP)
            kink_signal = any(term in text for term in self._KINK_UP)
            more_signal = any(term in text for term in self._MORE)

            if sexual_signal and not config.sexuality_locked:
                config.sexuality_current = min(
                    config.sexuality_max,
                    config.sexuality_current + 1,
                )
            if kink_signal and not config.kink_locked:
                config.kink_current = min(config.kink_max, config.kink_current + 1)
            if more_signal:
                if config.sexuality_current >= 2 and not config.sexuality_locked:
                    config.sexuality_current = min(
                        config.sexuality_max,
                        config.sexuality_current + 1,
                    )
                if config.kink_current >= 1 and not config.kink_locked:
                    config.kink_current = min(config.kink_max, config.kink_current + 1)

        changed = original != (config.sexuality_current, config.kink_current)
        if not changed:
            return config, False
        return self.set_config(conversation_id, config), True
