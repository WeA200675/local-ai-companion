from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.scene_evolution import (
    ActiveRitual,
    ActiveSceneEvolution,
    RitualRepository,
    SceneEvolutionRepository,
)


class SceneEvolutionWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: SceneEvolutionRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id
        self.assistant_count_provider = assistant_count_provider

        intro = QLabel(
            "Scene Evolution verändert eine bestehende Szene stufenweise, ohne das Szenen-Preset "
            "umzuschreiben. Licht, Raumgefühl und Bildrhythmus können sich organisch entwickeln; "
            "Persona, Memory und Character-Identität bleiben unverändert."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.automatic = QCheckBox("Automatisch weiterentwickeln")
        self.loop = QCheckBox("Am Ende wieder von vorn")
        self.interval = QSpinBox()
        self.interval.setRange(1, 10)
        self.interval.setSuffix(" Antworten")
        self.start_button = QPushButton("Evolution starten")
        self.next_button = QPushButton("Nächste Stufe")
        self.stop_button = QPushButton("Evolution beenden")
        self.save_button = QPushButton("Automatik speichern")

        form = QFormLayout()
        form.addRow("Ablauf", self.combo)
        form.addRow("Intervall", self.interval)
        form.addRow("", self.automatic)
        form.addRow("", self.loop)

        row = QHBoxLayout()
        row.addWidget(self.stop_button)
        row.addWidget(self.save_button)
        row.addStretch(1)
        row.addWidget(self.next_button)
        row.addWidget(self.start_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.start_button.clicked.connect(self.start_selected)
        self.next_button.clicked.connect(self.advance)
        self.stop_button.clicked.connect(self.stop)
        self.save_button.clicked.connect(self.save_config)
        self._reload()

    def _reload(self) -> None:
        current = str(self.combo.currentData() or "")
        self.combo.clear()
        for plan in self.repository.list_plans():
            self.combo.addItem(plan.name, plan.id)
        active = self.repository.active(self.conversation_id)
        target_id = active.plan_id if active is not None else current
        if target_id:
            index = self.combo.findData(target_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, active: ActiveSceneEvolution | None) -> None:
        enabled = active is not None
        self.next_button.setEnabled(enabled)
        self.stop_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        if active is None:
            self.status.setText("Keine Scene Evolution aktiv.")
            self.automatic.setChecked(False)
            self.loop.setChecked(False)
            self.interval.setValue(2)
            return
        self.automatic.blockSignals(True)
        self.loop.blockSignals(True)
        self.interval.blockSignals(True)
        self.automatic.setChecked(active.automatic)
        self.loop.setChecked(active.loop)
        self.interval.setValue(active.interval)
        self.automatic.blockSignals(False)
        self.loop.blockSignals(False)
        self.interval.blockSignals(False)
        auto = "automatisch" if active.automatic else "manuell"
        loop = " · Loop" if active.loop else ""
        self.status.setText(
            f"Aktiv: {active.plan_name}\n"
            f"Stufe {active.stage_index + 1}/{active.stage_count}: {active.stage_name}\n"
            f"{active.instruction}\n{auto} · Intervall {active.interval}{loop}"
        )

    def start_selected(self) -> None:
        plan_id = str(self.combo.currentData() or "")
        if not plan_id:
            return
        active = self.repository.start(
            self.conversation_id,
            plan_id,
            automatic=self.automatic.isChecked(),
            interval=self.interval.value(),
            loop=self.loop.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def save_config(self) -> None:
        active = self.repository.configure(
            self.conversation_id,
            automatic=self.automatic.isChecked(),
            interval=self.interval.value(),
            loop=self.loop.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def advance(self) -> None:
        active = self.repository.advance(
            self.conversation_id,
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def stop(self) -> None:
        self.repository.clear(self.conversation_id)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class RitualWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: RitualRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id
        self.assistant_count_provider = assistant_count_provider

        intro = QLabel(
            "Rituale sind wiederverwendbare temporäre Mini-Abläufe. Sie strukturieren einige Antworten "
            "oder Bildbeats, werden aber nicht zu Langzeit-Memory, Persona-Regeln oder versteckten Pflichten."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.automatic = QCheckBox("Schritte automatisch wechseln")
        self.loop = QCheckBox("Ritual wiederholen")
        self.interval = QSpinBox()
        self.interval.setRange(1, 6)
        self.interval.setSuffix(" Antworten")
        self.start_button = QPushButton("Ritual starten")
        self.next_button = QPushButton("Nächster Schritt")
        self.stop_button = QPushButton("Ritual beenden")
        self.save_button = QPushButton("Automatik speichern")

        form = QFormLayout()
        form.addRow("Ritual", self.combo)
        form.addRow("Intervall", self.interval)
        form.addRow("", self.automatic)
        form.addRow("", self.loop)

        row = QHBoxLayout()
        row.addWidget(self.stop_button)
        row.addWidget(self.save_button)
        row.addStretch(1)
        row.addWidget(self.next_button)
        row.addWidget(self.start_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.start_button.clicked.connect(self.start_selected)
        self.next_button.clicked.connect(self.advance)
        self.stop_button.clicked.connect(self.stop)
        self.save_button.clicked.connect(self.save_config)
        self._reload()

    def _reload(self) -> None:
        current = str(self.combo.currentData() or "")
        self.combo.clear()
        for ritual in self.repository.list_rituals():
            self.combo.addItem(ritual.name, ritual.id)
        active = self.repository.active(self.conversation_id)
        target_id = active.ritual_id if active is not None else current
        if target_id:
            index = self.combo.findData(target_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, active: ActiveRitual | None) -> None:
        enabled = active is not None
        self.next_button.setEnabled(enabled)
        self.stop_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)
        if active is None:
            self.status.setText("Kein Ritual aktiv.")
            self.automatic.setChecked(False)
            self.loop.setChecked(False)
            self.interval.setValue(1)
            return
        self.automatic.blockSignals(True)
        self.loop.blockSignals(True)
        self.interval.blockSignals(True)
        self.automatic.setChecked(active.automatic)
        self.loop.setChecked(active.loop)
        self.interval.setValue(active.interval)
        self.automatic.blockSignals(False)
        self.loop.blockSignals(False)
        self.interval.blockSignals(False)
        auto = "automatisch" if active.automatic else "manuell"
        loop = " · Loop" if active.loop else ""
        self.status.setText(
            f"Aktiv: {active.ritual_name}\n"
            f"Schritt {active.step_index + 1}/{active.step_count}: {active.step_name}\n"
            f"{active.instruction}\n{auto} · Intervall {active.interval}{loop}"
        )

    def start_selected(self) -> None:
        ritual_id = str(self.combo.currentData() or "")
        if not ritual_id:
            return
        active = self.repository.start(
            self.conversation_id,
            ritual_id,
            automatic=self.automatic.isChecked(),
            interval=self.interval.value(),
            loop=self.loop.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def save_config(self) -> None:
        active = self.repository.configure(
            self.conversation_id,
            automatic=self.automatic.isChecked(),
            interval=self.interval.value(),
            loop=self.loop.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def advance(self) -> None:
        active = self.repository.advance(
            self.conversation_id,
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def stop(self) -> None:
        self.repository.clear(self.conversation_id)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class SceneEvolutionRitualsPanel(QWidget):
    evolution_changed = Signal(object)
    ritual_changed = Signal(object)

    def __init__(
        self,
        evolution_repository: SceneEvolutionRepository,
        ritual_repository: RitualRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.evolution = SceneEvolutionWidget(
            evolution_repository,
            conversation_id,
            assistant_count_provider,
        )
        self.rituals = RitualWidget(
            ritual_repository,
            conversation_id,
            assistant_count_provider,
        )

        tabs = QTabWidget()
        tabs.addTab(self.evolution, "Scene Evolution")
        tabs.addTab(self.rituals, "Rituale")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self.evolution.changed.connect(self.evolution_changed)
        self.rituals.changed.connect(self.ritual_changed)

    def refresh_from_repositories(self) -> None:
        self.evolution.set_conversation(self.conversation_id)
        self.rituals.set_conversation(self.conversation_id)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh_from_repositories()
