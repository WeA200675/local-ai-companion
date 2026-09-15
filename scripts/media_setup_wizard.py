from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings
from app.ui.media_setup_wizard import MediaSetupWizard


def main() -> int:
    app = QApplication(sys.argv)
    store = StateStore(make_session_factory())
    settings = store.load_settings(AppSettings.from_env())
    wizard = MediaSetupWizard(store, settings)
    wizard.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
