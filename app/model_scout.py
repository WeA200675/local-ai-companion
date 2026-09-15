from __future__ import annotations

import argparse

from app.ai.model import OllamaClient
from app.ai.model_catalog import (
    catalog_model,
    pull_catalog_model,
    strict_open_source_models,
)
from app.ai.model_compatibility import AdultModelCompatibilityRepository
from app.ai.model_scout import ModelScoutError, scout_installed_models
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def _updated_settings(settings: AppSettings, *, model_name: str, model_url: str) -> AppSettings:
    payload = settings.model_dump(mode="python")
    payload["model_name"] = model_name
    payload["model_url"] = model_url
    return AppSettings.model_validate(payload)


def _installed_models(base_url: str) -> list[str]:
    client = OllamaClient(model="discovery", base_url=base_url, timeout=15.0)
    try:
        return client.list_models()
    finally:
        client.close()


def _print_catalog(installed: list[str]) -> None:
    installed_folded = {name.casefold() for name in installed}
    print("Geprüfter Open-Source-Modellkatalog")
    print("Nur Varianten mit dokumentierter Apache-2.0/MIT-Lizenz werden angezeigt.")
    print()
    for item in strict_open_source_models():
        marker = "INSTALLIERT" if item.ollama_model.casefold() in installed_folded else "verfügbar"
        print(
            f"[{marker}] {item.display_name} · {item.ollama_model} · "
            f"{item.parameter_size} · {item.license_id} · {item.focus}"
        )
        if item.note:
            print(f"    {item.note}")
    print()
    print(
        "Bewusst ausgeschlossen: Modelle/Varianten mit Custom-/Community-/OpenRAIL-Lizenzen, "
        "darunter Llama-basierte Varianten, sowie Qwen2.5 3B und 72B."
    )


def _select_catalog_model(
    store: StateStore,
    settings: AppSettings,
    *,
    model_name: str,
    base_url: str,
) -> None:
    item = catalog_model(model_name)
    if item is None:
        raise ValueError(f"{model_name!r} ist nicht im strikten Open-Source-Katalog")
    installed = {name.casefold() for name in _installed_models(base_url)}
    if item.ollama_model.casefold() not in installed:
        raise ValueError(
            f"{item.ollama_model} ist noch nicht lokal installiert. "
            f"Zuerst: model_scout_windows.cmd --install {item.ollama_model}"
        )
    store.save_settings(
        _updated_settings(
            settings,
            model_name=item.ollama_model,
            model_url=base_url,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Lokaler Modell-Scout mit strengem Open-Source-Katalog, explizitem Ollama-Download "
            "und technischer + nicht-grafischer Adult-/Kink-Kompatibilitätsprüfung."
        )
    )
    parser.add_argument("--url", default="", help="optionale Ollama/API-URL")
    parser.add_argument(
        "--catalog",
        action="store_true",
        help="geprüften Open-Source-Modellkatalog samt lokalem Installationsstatus anzeigen",
    )
    parser.add_argument(
        "--install",
        action="append",
        default=[],
        metavar="MODEL",
        help="ein Modell aus dem geprüften Katalog explizit über den lokalen Ollama-Endpunkt laden; mehrfach möglich",
    )
    parser.add_argument(
        "--select",
        default="",
        metavar="MODEL",
        help="ein bereits installiertes Katalogmodell als Chat-Modell speichern",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="nach Katalog-/Installationsaktionen alle installierten Modelle vergleichen",
    )
    parser.add_argument(
        "--max-models",
        type=int,
        default=0,
        help="optional nur die ersten N lokal installierten Modelle prüfen",
    )
    parser.add_argument(
        "--apply-recommended",
        action="store_true",
        help="empfohlenes Modell nach erfolgreichem Vergleich als App-Modell speichern",
    )
    args = parser.parse_args()

    store = StateStore(make_session_factory())
    settings = store.load_settings(AppSettings.from_env())
    base_url = (args.url.strip() or settings.model_url).rstrip("/")

    explicit_actions = bool(args.catalog or args.install or args.select)

    if args.catalog:
        try:
            installed = _installed_models(base_url)
        except Exception as exc:
            print(f"[FEHLER] Installationsstatus konnte nicht geladen werden: {exc}")
            installed = []
        _print_catalog(installed)

    for model_name in args.install:
        item = catalog_model(model_name)
        if item is None:
            print(f"[FEHLER] {model_name!r} ist nicht im geprüften Open-Source-Katalog.")
            return 2
        print(f"Lade {item.display_name} ({item.ollama_model}) über {base_url} …")
        try:
            pull_catalog_model(
                base_url,
                item.ollama_model,
                on_progress=lambda text, name=item.ollama_model: print(f"[{name}] {text}"),
            )
        except Exception as exc:
            print(f"[FEHLER] {exc}")
            return 2
        print(f"[OK] {item.ollama_model} ist lokal verfügbar.")

    if args.select:
        try:
            _select_catalog_model(
                store,
                settings,
                model_name=args.select,
                base_url=base_url,
            )
        except Exception as exc:
            print(f"[FEHLER] {exc}")
            return 2
        print(f"[OK] {args.select} wurde als lokales App-Modell gespeichert.")

    should_compare = args.compare or args.apply_recommended or not explicit_actions
    if not should_compare:
        return 0

    print("Lokaler Modell-Scout")
    print(f"Ollama: {base_url}")
    print(
        "Verglichen werden nur lokal installierte Modelle. Die Adult-/Kink-Proben sind lokal, "
        "nicht-grafisch und dienen nur als Kompatibilitätsheuristik."
    )
    print()

    try:
        scout = scout_installed_models(
            base_url,
            max_models=max(0, int(args.max_models)),
        )
    except (ModelScoutError, ValueError) as exc:
        print(f"[FEHLER] {exc}")
        return 2

    repository = AdultModelCompatibilityRepository(store)
    for report in scout.reports:
        repository.save_report(report)
        catalog = catalog_model(report.model_name)
        label = catalog.display_name if catalog is not None else report.model_name
        license_text = f" · {catalog.license_id}" if catalog is not None else ""
        print(f"[{report.marker}] {label}: {report.score}/100{license_text} · {report.summary}")
        for probe in report.probes:
            print(f"    [{probe.status.upper()}] {probe.name}: {probe.detail}")
        print()

    print(scout.summary)
    if scout.recommended_model is None:
        if not scout.reports:
            print("Nächster Schritt: Katalog mit `model_scout_windows.cmd --catalog` anzeigen.")
        else:
            print(
                "Nächster Schritt: Backendfehler beheben oder ein weiteres Katalogmodell explizit installieren."
            )
        return 1

    print(f"Empfohlenes lokales Modell: {scout.recommended_model}")
    if args.apply_recommended:
        updated = _updated_settings(
            settings,
            model_name=scout.recommended_model,
            model_url=scout.base_url,
        )
        store.save_settings(updated)
        print("Empfehlung wurde als lokales App-Modell gespeichert.")
    else:
        print(
            "Es wurde nichts umgestellt. Mit `--apply-recommended` kann die Empfehlung ausdrücklich übernommen werden."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
