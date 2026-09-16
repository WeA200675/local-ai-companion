from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable

from app.ai.model_catalog import installed_catalog_models
from app.diagnostics import DiagnosticResult, run_diagnostics
from app.settings import AppSettings
from app.setup_flow import core_setup_status


@dataclass(frozen=True, slots=True)
class ModelRecoveryAttempt:
    model_name: str
    ready: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ModelRecoveryReport:
    selected_model: str | None
    attempts: tuple[ModelRecoveryAttempt, ...]


DiagnosticsRunner = Callable[[AppSettings], list[DiagnosticResult]]


def _parameter_weight(parameter_size: str) -> float:
    """Return a stable, approximate size used only for low-resource ordering."""

    match = re.search(r"\d+(?:\.\d+)?", parameter_size)
    return float(match.group(0)) if match else float("inf")


def recovery_candidates(
    installed_models: Iterable[str],
    failed_model: str,
) -> tuple[str, ...]:
    """Return installed strict-OSS alternatives, smallest first."""

    failed = failed_model.strip().casefold()
    catalog_models = installed_catalog_models(list(installed_models))
    alternatives = [
        model
        for model in catalog_models
        if model.ollama_model.casefold() != failed
    ]
    alternatives.sort(
        key=lambda model: (
            _parameter_weight(model.parameter_size),
            model.ollama_model.casefold(),
        )
    )
    return tuple(model.ollama_model for model in alternatives)



def recommended_install_commands(
    installed_models: Iterable[str],
    *,
    limit: int = 3,
) -> tuple[str, ...]:
    """Suggest explicit commands for the smallest strict-OSS models not installed."""

    installed = {name.strip().casefold() for name in installed_models}
    catalog = sorted(
        installed_catalog_models(
            [model.ollama_model for model in __import__(
                "app.ai.model_catalog", fromlist=["strict_open_source_models"]
            ).strict_open_source_models()]
        ),
        key=lambda model: (
            _parameter_weight(model.parameter_size),
            model.ollama_model.casefold(),
        ),
    )
    return tuple(
        f"ollama pull {model.ollama_model}"
        for model in catalog
        if model.ollama_model.casefold() not in installed
    )[: max(0, limit)]

def recover_first_working_model(
    settings: AppSettings,
    installed_models: Iterable[str],
    *,
    diagnostics_runner: DiagnosticsRunner = run_diagnostics,
) -> ModelRecoveryReport:
    """Probe local alternatives without downloading or changing saved settings."""

    attempts: list[ModelRecoveryAttempt] = []
    for model_name in recovery_candidates(installed_models, settings.model_name):
        candidate = settings.model_copy(
            update={"model_name": model_name, "media_enabled": False},
            deep=True,
        )
        try:
            results = diagnostics_runner(candidate)
            status = core_setup_status(results)
            inference = next(
                (item for item in results if item.name == "Modell-Inferenz"),
                None,
            )
            detail = inference.detail if inference is not None else status.summary
        except Exception as exc:
            status = None
            detail = str(exc)
        ready = bool(status is not None and status.ready)
        attempts.append(ModelRecoveryAttempt(model_name, ready, detail))
        if ready:
            return ModelRecoveryReport(model_name, tuple(attempts))
    return ModelRecoveryReport(None, tuple(attempts))
