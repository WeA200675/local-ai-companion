from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class AppSettings(BaseModel):
    """User-editable local runtime configuration.

    Settings are persisted in the local SQLite database. Environment variables
    remain useful as first-run defaults and for portable/test installations.
    """

    model_name: str = "qwen2.5:7b"
    model_url: str = "http://127.0.0.1:11434"
    model_fallback_enabled: bool = False
    model_fallbacks: list[str] = Field(default_factory=list)
    chat_temperature: float = Field(default=0.85, ge=0.0, le=2.0)
    chat_history_messages: int = Field(default=60, ge=10, le=500)
    chat_num_ctx: int = Field(default=0, ge=0, le=262144)
    chat_num_predict: int = Field(default=0, ge=0, le=32768)
    media_enabled: bool = False
    media_url: str = "http://127.0.0.1:8188"
    media_workflow: str = ""
    media_profile_catalog: str = ""
    media_positive_node: str = "6"
    media_negative_node: str = "7"
    media_seed_node: str = "3"
    media_output_dir: str = "data/generated_media"
    continuity_enabled: bool = True
    continuity_key: str = "persona-main"
    media_reference_enabled: bool = False
    media_reference_node: str = ""
    media_reference_input_key: str = "image"
    learning_snapshots: bool = True
    adaptive_memory_enabled: bool = True
    adaptive_memory_interval: int = Field(default=3, ge=1, le=20)
    media_history_limit: int = Field(default=200, ge=10, le=5000)

    @field_validator("model_name", "model_url", "media_url", "continuity_key")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("value must not be blank")
        return clean

    @field_validator("model_fallbacks", mode="before")
    @classmethod
    def _normalize_model_fallbacks(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_items = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            raw_items = [value]
        result: list[str] = []
        seen: set[str] = set()
        for raw in raw_items:
            name = str(raw or "").strip()
            folded = name.casefold()
            if not name or folded in seen:
                continue
            seen.add(folded)
            result.append(name)
        return result

    @field_validator(
        "media_positive_node",
        "media_negative_node",
        "media_seed_node",
        "media_output_dir",
        "media_workflow",
        "media_profile_catalog",
        "media_reference_node",
        "media_reference_input_key",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def from_env(cls) -> "AppSettings":
        workflow = os.getenv("LOCAL_MEDIA_WORKFLOW", "").strip()
        profile_catalog = os.getenv("LOCAL_MEDIA_PROFILE_CATALOG", "").strip()
        media_enabled_raw = os.getenv("LOCAL_MEDIA_ENABLED")
        media_enabled = bool(workflow or profile_catalog)
        if media_enabled_raw is not None:
            media_enabled = media_enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
        return cls(
            model_name=os.getenv("LOCAL_AI_MODEL", "qwen2.5:7b"),
            model_url=os.getenv("LOCAL_AI_URL", "http://127.0.0.1:11434"),
            model_fallback_enabled=os.getenv("LOCAL_AI_FALLBACK_ENABLED", "0").strip().lower()
            in {"1", "true", "yes", "on"},
            model_fallbacks=os.getenv("LOCAL_AI_FALLBACK_MODELS", ""),
            chat_temperature=float(os.getenv("LOCAL_CHAT_TEMPERATURE", "0.85")),
            chat_history_messages=int(os.getenv("LOCAL_CHAT_HISTORY_MESSAGES", "60")),
            chat_num_ctx=int(os.getenv("LOCAL_CHAT_NUM_CTX", "0")),
            chat_num_predict=int(os.getenv("LOCAL_CHAT_NUM_PREDICT", "0")),
            media_enabled=media_enabled,
            media_url=os.getenv("LOCAL_MEDIA_URL", "http://127.0.0.1:8188"),
            media_workflow=workflow,
            media_profile_catalog=profile_catalog,
            media_positive_node=os.getenv("LOCAL_MEDIA_POSITIVE_NODE", "6"),
            media_negative_node=os.getenv("LOCAL_MEDIA_NEGATIVE_NODE", "7"),
            media_seed_node=os.getenv("LOCAL_MEDIA_SEED_NODE", "3"),
            media_output_dir=os.getenv("LOCAL_MEDIA_OUTPUT", "data/generated_media"),
            continuity_enabled=os.getenv("LOCAL_MEDIA_CONTINUITY", "1").strip().lower()
            not in {"0", "false", "no", "off"},
            continuity_key=os.getenv("LOCAL_MEDIA_CONTINUITY_KEY", "persona-main"),
            media_reference_enabled=os.getenv("LOCAL_MEDIA_REFERENCE", "0").strip().lower()
            in {"1", "true", "yes", "on"},
            media_reference_node=os.getenv("LOCAL_MEDIA_REFERENCE_NODE", ""),
            media_reference_input_key=os.getenv("LOCAL_MEDIA_REFERENCE_INPUT", "image"),
            learning_snapshots=os.getenv("LOCAL_LEARNING_SNAPSHOTS", "1").strip().lower()
            not in {"0", "false", "no", "off"},
            adaptive_memory_enabled=os.getenv("LOCAL_ADAPTIVE_MEMORY", "1").strip().lower()
            not in {"0", "false", "no", "off"},
            adaptive_memory_interval=int(os.getenv("LOCAL_ADAPTIVE_MEMORY_INTERVAL", "3")),
        )

    @property
    def workflow_path(self) -> Path | None:
        return Path(self.media_workflow).expanduser() if self.media_workflow else None

    @property
    def profile_catalog_path(self) -> Path | None:
        return Path(self.media_profile_catalog).expanduser() if self.media_profile_catalog else None

    @property
    def output_path(self) -> Path:
        return Path(self.media_output_dir).expanduser()
