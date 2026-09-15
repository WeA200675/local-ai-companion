from __future__ import annotations

from collections.abc import Sequence

import app.main as desktop_main
from app.ai.model_catalog import catalog_model
from app.ai.model_fallback import FallbackOllamaClient
from app.ai.model_compatibility import AdultModelCompatibilityRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings

_ALLOWED_FALLBACK_STATUSES = {"compatible", "limited", "unclear"}


def approved_fallback_models(
    settings: AppSettings,
    repository: AdultModelCompatibilityRepository,
) -> tuple[str, ...]:
    """Return configured fallbacks that remain strict-OSS and locally tested."""

    if not settings.model_fallback_enabled:
        return ()

    primary = settings.model_name.casefold()
    result: list[str] = []
    seen = {primary}
    for raw in settings.model_fallbacks:
        name = raw.strip()
        folded = name.casefold()
        if not name or folded in seen:
            continue
        if catalog_model(name) is None:
            continue
        report = repository.report_for(name, settings.model_url)
        if report is None or not report.operational or report.status not in _ALLOWED_FALLBACK_STATUSES:
            continue
        seen.add(folded)
        result.append(name)
    return tuple(result)


def configured_model_client_class(settings: AppSettings, fallbacks: Sequence[str]):
    """Create the concrete client class used by MainWindow._build_services."""

    fallback_chain = tuple(fallbacks)
    if not settings.model_fallback_enabled or not fallback_chain:
        return desktop_main.OllamaClient

    class ConfiguredFallbackClient(FallbackOllamaClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs.setdefault("fallback_models", fallback_chain)
            super().__init__(*args, **kwargs)

    ConfiguredFallbackClient.__name__ = "ConfiguredFallbackOllamaClient"
    return ConfiguredFallbackClient


def main() -> int:
    store = StateStore(make_session_factory())
    settings = store.load_settings(AppSettings.from_env())
    compatibility_repository = AdultModelCompatibilityRepository(store)
    fallbacks = approved_fallback_models(settings, compatibility_repository)

    # app.main imports OllamaClient as a module global. Replacing that global
    # before constructing MainWindow keeps the rest of the application unchanged
    # while making the normal Windows launch path use the configured fallback chain.
    desktop_main.OllamaClient = configured_model_client_class(settings, fallbacks)
    return desktop_main.main()


if __name__ == "__main__":
    raise SystemExit(main())
