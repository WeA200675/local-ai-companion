from __future__ import annotations

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Local AI Companion — v0.1.0-alpha")
        self.resize(900, 640)
        self.setCentralWidget(QLabel("Bootstrap complete. Persona, memory and media layers are wired next."))


def main() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
