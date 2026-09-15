from __future__ import annotations

import argparse

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


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Vergleicht bereits lokal installierte Ollama-Modelle mit technischer Inferenz "
            "und den nicht-grafischen Adult-/Kink-Kompatibilitätsproben der App."
        )
    )
    parser.add_argument("--url", default="", help="optionale Ollama/API-URL")
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
    base_url = args.url.strip() or settings.model_url

    print("Lokaler Modell-Scout")
    print(f"Ollama: {base_url}")
    print(
        "Es werden nur bereits installierte Modelle geprüft; es erfolgt kein Download und kein Cloud-Aufruf."
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
        print(
            f"[{report.marker}] {report.model_name}: {report.score}/100 · {report.summary}"
        )
        for probe in report.probes:
            print(f"    [{probe.status.upper()}] {probe.name}: {probe.detail}")
        print()

    print(scout.summary)
    if scout.recommended_model is None:
        if not scout.reports:
            print("Nächster Schritt: Mit `ollama list` prüfen, ob lokale Modelle installiert sind.")
        else:
            print(
                "Nächster Schritt: Backendfehler beheben oder ein weiteres lokal installiertes Modell vergleichen."
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
