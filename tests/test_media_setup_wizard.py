from __future__ import annotations

from app.ui.media_setup_wizard import MediaSetupWorker, MediaSetupWizard


def test_media_setup_wizard_exports_expected_qt_types() -> None:
    assert MediaSetupWizard.__name__ == "MediaSetupWizard"
    assert MediaSetupWorker.__name__ == "MediaSetupWorker"
