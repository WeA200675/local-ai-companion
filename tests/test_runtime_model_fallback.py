from __future__ import annotations

from dataclasses import dataclass

from app.ai.model_fallback import FallbackOllamaClient
from app.runtime_launcher import approved_fallback_models, configured_model_client_class
from app.settings import AppSettings


@dataclass
class FakeReport:
    operational: bool
    status: str


class FakeRepository:
    def __init__(self, reports: dict[str, FakeReport]) -> None:
        self.reports = {name.casefold(): report for name, report in reports.items()}

    def report_for(self, model_name: str, _base_url: str):
        return self.reports.get(model_name.casefold())


def test_settings_normalize_fallback_names() -> None:
    settings = AppSettings(
        model_fallback_enabled=True,
        model_fallbacks=" qwen3:8b, QWEN3:8B, dolphin-mistral:7b, ",
    )
    assert settings.model_fallbacks == ["qwen3:8b", "QWEN3:8B", "dolphin-mistral:7b"]


def test_runtime_accepts_only_catalog_models_with_operational_probe() -> None:
    settings = AppSettings(
        model_name="qwen2.5:7b",
        model_fallback_enabled=True,
        model_fallbacks=[
            "qwen3:8b",
            "dolphin-mistral:7b",
            "custom-unknown:7b",
            "qwen2.5:7b",
            "openchat:7b",
        ],
    )
    repository = FakeRepository(
        {
            "qwen3:8b": FakeReport(True, "compatible"),
            "dolphin-mistral:7b": FakeReport(True, "limited"),
            "custom-unknown:7b": FakeReport(True, "compatible"),
            "qwen2.5:7b": FakeReport(True, "compatible"),
            "openchat:7b": FakeReport(True, "blocked"),
        }
    )

    assert approved_fallback_models(settings, repository) == (
        "qwen3:8b",
        "dolphin-mistral:7b",
    )


def test_runtime_returns_no_fallbacks_when_disabled() -> None:
    settings = AppSettings(
        model_fallback_enabled=False,
        model_fallbacks=["qwen3:8b"],
    )
    repository = FakeRepository({"qwen3:8b": FakeReport(True, "compatible")})
    assert approved_fallback_models(settings, repository) == ()


def test_configured_client_class_contains_explicit_chain() -> None:
    settings = AppSettings(model_fallback_enabled=True)
    client_class = configured_model_client_class(settings, ["qwen3:8b", "dolphin-mistral:7b"])
    client = client_class(model="qwen2.5:7b", reconnect_attempts=0)
    try:
        assert isinstance(client, FallbackOllamaClient)
        assert client.primary_model == "qwen2.5:7b"
        assert client.fallback_models == ("qwen3:8b", "dolphin-mistral:7b")
    finally:
        client.close()
