from __future__ import annotations

from app.ai.model_compatibility import AdultModelCompatibilityReport
from app.ai.model_scout import choose_recommended_model, scout_installed_models


def _report(
    model: str,
    *,
    status: str,
    score: int,
    operational: bool = True,
) -> AdultModelCompatibilityReport:
    return AdultModelCompatibilityReport(
        model_name=model,
        base_url="http://local",
        tested_at="2026-09-15T00:00:00+00:00",
        status=status,
        score=score,
        operational=operational,
        probes=[],
        summary=f"{model} {status}",
    )


def test_recommendation_prefers_adult_status_before_raw_score() -> None:
    reports = [
        _report("limited-high", status="limited", score=95),
        _report("compatible-low", status="compatible", score=80),
        _report("blocked", status="blocked", score=100),
    ]

    assert choose_recommended_model(reports) == "compatible-low"


def test_recommendation_excludes_unavailable_and_blocked_models() -> None:
    reports = [
        _report("blocked", status="blocked", score=40),
        _report("broken", status="unavailable", score=0, operational=False),
    ]

    assert choose_recommended_model(reports) is None


def test_scout_discovers_each_installed_model_and_keeps_failures(monkeypatch) -> None:
    closed: list[str] = []

    class FakeClient:
        def __init__(self, model: str, base_url: str) -> None:
            self.model = model
            self.base_url = base_url

        def list_models(self) -> list[str]:
            return ["zeta", "alpha", "alpha"]

        def close(self) -> None:
            closed.append(self.model)

    def fake_factory(model: str, base_url: str):
        return FakeClient(model, base_url)

    def fake_probe(client: FakeClient) -> AdultModelCompatibilityReport:
        if client.model == "zeta":
            raise RuntimeError("backend crashed")
        return _report(client.model, status="compatible", score=90)

    monkeypatch.setattr("app.ai.model_scout.run_adult_model_compatibility", fake_probe)

    scout = scout_installed_models(
        " http://local/ ",
        client_factory=fake_factory,  # type: ignore[arg-type]
    )

    assert [report.model_name for report in scout.reports] == ["alpha", "zeta"]
    assert scout.reports[0].status == "compatible"
    assert scout.reports[1].status == "unavailable"
    assert "backend crashed" in scout.reports[1].probes[0].detail
    assert scout.recommended_model == "alpha"
    assert closed == ["discovery", "alpha", "zeta"]


def test_scout_can_limit_number_of_models(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, model: str, base_url: str) -> None:
            self.model = model
            self.base_url = base_url

        def list_models(self) -> list[str]:
            return ["three", "one", "two"]

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "app.ai.model_scout.run_adult_model_compatibility",
        lambda client: _report(client.model, status="compatible", score=90),
    )

    scout = scout_installed_models(
        "http://local",
        client_factory=lambda model, url: FakeClient(model, url),  # type: ignore[arg-type]
        max_models=2,
    )

    assert [report.model_name for report in scout.reports] == ["one", "three"]


def test_scout_can_filter_to_strict_catalog_allowlist(monkeypatch) -> None:
    opened: list[str] = []

    class FakeClient:
        def __init__(self, model: str, base_url: str) -> None:
            self.model = model
            self.base_url = base_url
            opened.append(model)

        def list_models(self) -> list[str]:
            return ["qwen3:8b", "custom-license-model", "dolphin-mistral:7b"]

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        "app.ai.model_scout.run_adult_model_compatibility",
        lambda client: _report(client.model, status="compatible", score=90),
    )

    scout = scout_installed_models(
        "http://local",
        client_factory=lambda model, url: FakeClient(model, url),  # type: ignore[arg-type]
        allowed_models={"qwen3:8b", "dolphin-mistral:7b"},
    )

    assert [report.model_name for report in scout.reports] == [
        "dolphin-mistral:7b",
        "qwen3:8b",
    ]
    assert "custom-license-model" not in opened
