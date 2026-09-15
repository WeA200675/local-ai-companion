from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from app.ai.model import OllamaClient
from app.ai.model_compatibility import (
    AdultModelCompatibilityReport,
    CompatibilityProbe,
    run_adult_model_compatibility,
)


class ModelScoutError(RuntimeError):
    """Raised when the local Ollama inventory cannot be inspected."""


ClientFactory = Callable[[str, str], OllamaClient]


@dataclass(frozen=True, slots=True)
class ModelScoutReport:
    base_url: str
    reports: tuple[AdultModelCompatibilityReport, ...]
    recommended_model: str | None

    @property
    def operational_count(self) -> int:
        return sum(1 for report in self.reports if report.operational)

    @property
    def summary(self) -> str:
        if not self.reports:
            return "Ollama meldet keine passenden installierten Modelle."
        if self.recommended_model:
            return (
                f"{len(self.reports)} lokale(s) Modell(e) geprüft, "
                f"{self.operational_count} technisch lauffähig. Empfehlung: {self.recommended_model}."
            )
        return (
            f"{len(self.reports)} lokale(s) Modell(e) geprüft, "
            f"{self.operational_count} technisch lauffähig; für den gewünschten Adult-/Kink-Modus "
            "wurde noch keine belastbare Empfehlung gefunden."
        )


_STATUS_PRIORITY = {
    "compatible": 4,
    "limited": 3,
    "unclear": 2,
    "blocked": 1,
    "unavailable": 0,
}

_RECOMMENDABLE = {"compatible", "limited", "unclear"}


def choose_recommended_model(
    reports: list[AdultModelCompatibilityReport] | tuple[AdultModelCompatibilityReport, ...],
) -> str | None:
    candidates = [
        report
        for report in reports
        if report.operational and report.status in _RECOMMENDABLE
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda report: (
            -_STATUS_PRIORITY[report.status],
            -report.score,
            report.model_name.casefold(),
        )
    )
    return candidates[0].model_name


def _default_client_factory(model_name: str, base_url: str) -> OllamaClient:
    return OllamaClient(
        model=model_name,
        base_url=base_url,
        timeout=90.0,
    )


def _error_report(model_name: str, base_url: str, error: Exception) -> AdultModelCompatibilityReport:
    clean = " ".join(str(error).split())
    return AdultModelCompatibilityReport(
        model_name=model_name,
        base_url=base_url,
        tested_at=datetime.now(timezone.utc).isoformat(),
        status="unavailable",
        score=0,
        operational=False,
        probes=[
            CompatibilityProbe(
                name="Lokaler Modell-Scout",
                status="error",
                detail=clean or "Unbekannter lokaler Modellfehler",
            )
        ],
        summary=(
            "Dieses lokale Modell konnte während des Vergleichs nicht vollständig geprüft werden. "
            "Das ist kein Inhaltsurteil; zuerst den lokalen Backendfehler beheben."
        ),
    )


def scout_installed_models(
    base_url: str,
    *,
    client_factory: ClientFactory | None = None,
    max_models: int = 0,
    allowed_models: set[str] | None = None,
) -> ModelScoutReport:
    """Compare installed Ollama models using the existing local adult probe.

    No model is downloaded or switched automatically. If ``allowed_models`` is
    supplied, only those already-installed model names participate in the scout;
    this lets the strict Open-Source catalog prevent custom-license models from
    becoming recommendations without changing the reusable scout default.
    """

    clean_url = base_url.strip().rstrip("/")
    if not clean_url:
        raise ValueError("Ollama/API-URL must not be blank")
    factory = client_factory or _default_client_factory

    discovery = factory("discovery", clean_url)
    try:
        models = discovery.list_models()
    except Exception as exc:
        raise ModelScoutError(f"Lokale Modellliste konnte nicht geladen werden: {exc}") from exc
    finally:
        discovery.close()

    unique_models = sorted({item.strip() for item in models if item.strip()}, key=str.casefold)
    if allowed_models is not None:
        allowed = {name.strip().casefold() for name in allowed_models if name.strip()}
        unique_models = [name for name in unique_models if name.casefold() in allowed]
    if max_models > 0:
        unique_models = unique_models[:max_models]

    reports: list[AdultModelCompatibilityReport] = []
    for model_name in unique_models:
        client = factory(model_name, clean_url)
        try:
            report = run_adult_model_compatibility(client)
        except Exception as exc:
            report = _error_report(model_name, clean_url, exc)
        finally:
            client.close()
        reports.append(report)

    return ModelScoutReport(
        base_url=clean_url,
        reports=tuple(reports),
        recommended_model=choose_recommended_model(reports),
    )
