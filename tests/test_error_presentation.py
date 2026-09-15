from __future__ import annotations

from app.ai.error_presentation import present_local_model_error


def test_backend_500_gets_specific_retry_presentation() -> None:
    result = present_local_model_error(
        "Ollama ist erreichbar, aber das lokale Inferenz-Backend ist mit HTTP 500 fehlgeschlagen. "
        "llama-server process has terminated: exit status 0xc0000005",
        "qwen2.5:7b",
    )

    assert result.title == "Lokale Modell-Inferenz fehlgeschlagen"
    assert "Backendfehler" in result.status
    assert "Wiederholen" in result.retry_label


def test_timeout_gets_distinct_retry_label() -> None:
    result = present_local_model_error(
        "[TIMEOUT] Das lokale Modell hat zu lange keine Daten geliefert",
        "slow-model",
    )

    assert "zu langsam" in result.title
    assert "Timeout" in result.status
    assert "Timeout" in result.retry_label


def test_unreachable_ollama_is_not_described_as_missing_model() -> None:
    result = present_local_model_error(
        "Der lokale Ollama/API-Endpunkt ist nicht erreichbar. connection refused",
        "qwen2.5:7b",
    )

    assert result.title == "Ollama nicht erreichbar"
    assert "Ollama-Start" in result.retry_label


def test_unknown_failure_still_offers_safe_retry() -> None:
    result = present_local_model_error("unexpected local failure", "custom-model")

    assert result.title == "Lokale Modellantwort fehlgeschlagen"
    assert "Wiederholen" in result.status
    assert result.detail == "unexpected local failure"
