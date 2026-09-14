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
    media_enabled: bool = False
    media_url: str = "http://127.0.0.1:8188"
    media_workflow: str = ""
    media_positive_node: str = "6"
    media_negative_node: str = "7"
    media_seed_node: str = "3"
    media_output_dir: str = "data/generated_media"
    continuity_enabled: bool = True
    continuity_key: str = "persona-main"
    learning_snapshots: bool = True
    media_history_limit: int = Field(default=200, ge=10, le=5000)

    @field_validator("model_name", "model_url", "media_url", "continuity_key")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("value must not be blank")
        return clean

    @field_validator(
        "media_positive_node",
        "media_negative_node",
        "media_seed_node",
        "media_output_dir",
        "media_workflow",
        mode="before",
    )
    @classmethod
    def _strip_strings(cls, value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def from_env(cls) -> "AppSettings":
        workflow = os.getenv("LOCAL_MEDIA_WORKFLOW", "").strip()
        media_enabled_raw = os.getenv("LOCAL_MEDIA_ENABLED")
        media_enabled = bool(workflow)
        if media_enabled_raw is not None:
            media_enabled = media_enabled_raw.strip().lower() in {"1", "true", "yes", "on"}
        return cls(
            model_name=os.getenv("LOCAL_AI_MODEL", "qwen2.5:7b"),
            model_url=os.getenv("LOCAL_AI_URL", "http://127.0.0.1:11434"),
            media_enabled=media_enabled,
            media_url=os.getenv("LOCAL_MEDIA_URL", "http://127.0.0.1:8188"),
            media_workflow=workflow,
            media_positive_node=os.getenv("LOCAL_MEDIA_POSITIVE_NODE", "6"),
            media_negative_node=os.getenv("LOCAL_MEDIA_NEGATIVE_NODE", "7"),
            media_seed_node=os.getenv("LOCAL_MEDIA_SEED_NODE", "3"),
            media_output_dir=os.getenv("LOCAL_MEDIA_OUTPUT", "data/generated_media"),
            continuity_enabled=os.getenv("LOCAL_MEDIA_CONTINUITY", "1").strip().lower()
            not in {"0", "false", "no", "off"},
            continuity_key=os.getenv("LOCAL_MEDIA_CONTINUITY_KEY", "persona-main"),
            learning_snapshots=os.getenv("LOCAL_LEARNING_SNAPSHOTS", "1").strip().lower()
            not in {"0", "false", "no", "off"},
        )

    @property
    def workflow_path(self) -> Path | None:
        return Path(self.media_workflow).expanduser() if self.media_workflow else None

    @property
    def output_path(self) -> Path:
        return Path(self.media_output_dir).expanduser()
