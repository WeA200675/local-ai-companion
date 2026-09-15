from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings
from app.setup_flow import setup_required
from app.ui.first_run_setup import FirstRunSetupDialog


def run_setup(*, force: bool = False) -> int:
    session_factory = make_session_factory()
    store = StateStore(session_factory)
    settings = store.load_settings(AppSettings.from_env())
    if not force and not setup_required(settings):
        return 0

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)
        app.setApplicationName("Local AI Companion Setup")

    dialog = FirstRunSetupDialog(store, settings)
    dialog.exec()

    if owns_app:
        app.processEvents()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local-only first-run setup for Local AI Companion"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="show the setup dialog even when first-run setup was already completed",
    )
    args = parser.parse_args()
    return run_setup(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
