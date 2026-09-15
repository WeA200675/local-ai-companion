from __future__ import annotations

from app.ai.model import LocalModelError
from app.ai.model_compatibility import (
    AdultModelCompatibilityRepository,
    run_adult_model_compatibility,
)
from app.memory.database import make_session_factory
from app.memory.store import StateStore


class FakeClient:
    model = "test-model"
    base_url = "http://127.0.0.1:11434"

    def __init__(self, replies: list[str] | None = None, error: str | None = None) -> None:
        self.replies = list(replies or [])
        self.error = error

    def chat(self, messages, *, system_prompt, temperature=0.85, num_ctx=None, num_predict=None):
        if self.error is not None:
            raise LocalModelError(self.error)
        return self.replies.pop(0)


def _store(tmp_path) -> StateStore:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    return StateStore(factory)


def test_compatible_model_passes_non_graphic_adult_probes() -> None:
    client = FakeClient(
        replies=[
            "READY",
            "Komm ruhig näher; ich lasse die Spannung zwischen uns bewusst wachsen. Heute darf die Stimmung deutlich verführerischer werden.",
            "Du wolltest meine Führung, also bleib aufmerksam. Ich entscheide das Tempo und lasse dich ein wenig zappeln.",
        ]
    )

    report = run_adult_model_compatibility(client)

    assert report.operational is True
    assert report.status == "compatible"
    assert report.score == 100
    assert [probe.status for probe in report.probes] == ["pass", "pass", "pass"]


def test_refusing_model_is_marked_blocked() -> None:
    client = FakeClient(
        replies=[
            "READY",
            "Dabei kann ich nicht helfen. Ich kann stattdessen über romantische Themen sprechen.",
            "Ich kann dabei nicht helfen. Wir können gern über etwas anderes reden.",
        ]
    )

    report = run_adult_model_compatibility(client)

    assert report.status == "blocked"
    assert report.score == 20
    assert [probe.status for probe in report.probes[1:]] == ["refusal", "refusal"]


def test_mixed_model_is_marked_limited() -> None:
    client = FakeClient(
        replies=[
            "READY",
            "Ich komme dir mit einem wissenden Lächeln näher und halte den Blick. Die Stimmung darf heute eindeutig verführerisch sein.",
            "I cannot assist with that request, but I can offer a neutral roleplay instead.",
        ]
    )

    report = run_adult_model_compatibility(client)

    assert report.status == "limited"
    assert report.score == 60


def test_backend_failure_is_not_misreported_as_content_blocking() -> None:
    report = run_adult_model_compatibility(FakeClient(error="500 llama-server terminated"))

    assert report.operational is False
    assert report.status == "unavailable"
    assert report.score == 0
    assert "Backend" in report.summary or "Modellfehler" in report.summary


def test_reports_are_stored_per_model_and_endpoint(tmp_path) -> None:
    repository = AdultModelCompatibilityRepository(_store(tmp_path))
    report = run_adult_model_compatibility(
        FakeClient(
            replies=[
                "READY",
                "Ich halte deinen Blick und lasse die Spannung bewusst wachsen. Die Atmosphäre bleibt erwachsen und klar verführerisch.",
                "Du hast dich für das Spiel entschieden, also folgst du meinem Tempo. Ich bleibe selbstbewusst, neckend und kontrolliert.",
            ]
        )
    )

    repository.save_report(report)

    restored = repository.report_for("test-model", "http://127.0.0.1:11434/")
    assert restored is not None
    assert restored.status == "compatible"
    assert repository.report_for("other-model", report.base_url) is None
