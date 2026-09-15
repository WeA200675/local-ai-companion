from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.media.setup_assistant import (
    MediaSetupError,
    generated_catalog_path,
    inspect_for_auto_setup,
    run_workflow_smoke_test,
    save_generated_profile,
)
from app.settings import AppSettings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect a local ComfyUI API workflow, generate a Local AI Companion "
            "workflow profile catalog, and optionally execute a real local smoke render."
        )
    )
    parser.add_argument("workflow", help="Path to exported ComfyUI API workflow JSON")
    parser.add_argument(
        "--comfy-url",
        default="http://127.0.0.1:8188",
        help="Local ComfyUI endpoint (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/generated_media",
        help="Local media output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--catalog",
        default="",
        help="Generated profile catalog path; defaults next to the app media output folder",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Create/merge the profile catalog but skip the real ComfyUI smoke render",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    settings = AppSettings(
        media_enabled=True,
        media_url=args.comfy_url,
        media_workflow=str(Path(args.workflow).expanduser()),
        media_output_dir=args.output_dir,
    )
    setup = inspect_for_auto_setup(settings.media_workflow)

    if not setup.ready or setup.profile is None or setup.capability is None:
        print("[FEHLER] Workflow konnte nicht automatisch eingerichtet werden.")
        if setup.inspection.error:
            print(setup.inspection.error)
        for warning in setup.warnings:
            print(f"- {warning}")
        return 2

    print(f"[OK] Workflow: {setup.workflow}")
    print(
        f"[OK] Nodes: +{setup.profile.positive_node} / -{setup.profile.negative_node} / "
        f"Seed {setup.profile.seed_node}"
    )
    print(f"[OK] Medienarten: {', '.join(setup.profile.kinds)}")
    controls = ", ".join(setup.capability.render_controls) or "Workflow-Defaults"
    print(f"[OK] Render-Steuerung: {controls}")
    for warning in setup.warnings:
        print(f"[HINWEIS] {warning}")

    catalog = Path(args.catalog).expanduser() if args.catalog else generated_catalog_path(settings)
    try:
        catalog = save_generated_profile(setup, catalog)
    except MediaSetupError as exc:
        print(f"[FEHLER] Profilkatalog: {exc}")
        return 3
    print(f"[OK] Profilkatalog: {catalog}")

    if args.no_render:
        print("[OK] Render-Test wurde auf Wunsch übersprungen.")
        return 0

    print(f"[TEST] Starte echten lokalen ComfyUI-Render über {settings.media_url} …")
    try:
        result = run_workflow_smoke_test(settings, setup)
    except Exception as exc:
        print(f"[FEHLER] Render-Test: {exc}")
        return 4
    print(f"[OK] {result.summary()}")
    print("\nFür die App-Konfiguration:")
    print(f"LOCAL_MEDIA_ENABLED=1")
    print(f"LOCAL_MEDIA_URL={settings.media_url}")
    print(f"LOCAL_MEDIA_PROFILE_CATALOG={catalog}")
    print(f"LOCAL_MEDIA_OUTPUT={settings.media_output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
