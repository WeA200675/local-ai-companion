from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.look_presets import LookPreset, LookPresetRepository
from app.ai.scene_mixer import SceneMix, SceneMixerRepository
from app.ai.session_arcs import ActiveArc, SessionArcRepository


class LookPresetWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: LookPresetRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Look-Presets verändern nur Kleidung und visuellen Stil dieser Unterhaltung. "
            "Die stabile Character-Identität, Persona und Memories bleiben unverändert."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.activate_button = QPushButton("Look aktivieren")
        self.base_button = QPushButton("Basis-Look")

        row = QHBoxLayout()
        row.addWidget(self.base_button)
        row.addStretch(1)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.activate_button.clicked.connect(self.activate_selected)
        self.base_button.clicked.connect(self.clear)
        self._reload()

    def _reload(self) -> None:
        active = self.repository.active(self.conversation_id)
        active_id = active.id if active else None
        self.combo.clear()
        for preset in self.repository.list_presets():
            self.combo.addItem(preset.name, preset.id)
        if active_id:
            index = self.combo.findData(active_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, active: LookPreset | None) -> None:
        if active is None:
            self.status.setText("Aktiv: Basis-Look aus Character Studio / aktuellem Kontext")
            return
        wardrobe = ", ".join(active.wardrobe) or "nicht festgelegt"
        self.status.setText(f"Aktiv: {active.name}\nWardrobe: {wardrobe}\n{active.description}")

    def activate_selected(self) -> None:
        preset_id = str(self.combo.currentData() or "")
        if not preset_id:
            return
        active = self.repository.set_active(self.conversation_id, preset_id)
        self._render(active)
        self.changed.emit(active)

    def clear(self) -> None:
        self.repository.set_active(self.conversation_id, None)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class SessionArcWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: SessionArcRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Session-Arcs geben einer Unterhaltung mehrere temporäre Phasen. Mit „Nächste Phase“ "
            "entwickelt sich Tempo und Inszenierung weiter, ohne Persona oder Langzeit-Memory umzuschreiben."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.activate_button = QPushButton("Arc starten")
        self.next_button = QPushButton("Nächste Phase")
        self.clear_button = QPushButton("Arc beenden")

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.next_button)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.activate_button.clicked.connect(self.activate_selected)
        self.next_button.clicked.connect(self.advance)
        self.clear_button.clicked.connect(self.clear)
        self._reload()

    def _reload(self) -> None:
        active = self.repository.active(self.conversation_id)
        self.combo.clear()
        for arc in self.repository.list_arcs():
            self.combo.addItem(arc.name, arc.id)
        if active is not None:
            index = self.combo.findData(active.arc_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, active: ActiveArc | None) -> None:
        enabled = active is not None
        self.next_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        if active is None:
            self.status.setText("Kein Session-Arc aktiv.")
            return
        self.status.setText(
            f"Aktiv: {active.arc_name}\nPhase {active.stage_index + 1}/{active.stage_count}: "
            f"{active.stage_name}\n{active.instruction}"
        )

    def activate_selected(self) -> None:
        arc_id = str(self.combo.currentData() or "")
        if not arc_id:
            return
        active = self.repository.activate(self.conversation_id, arc_id)
        self._render(active)
        self.changed.emit(active)

    def advance(self) -> None:
        active = self.repository.advance(self.conversation_id)
        self._render(active)
        self.changed.emit(active)

    def clear(self) -> None:
        self.repository.clear(self.conversation_id)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class SceneMixerWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: SceneMixerRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Der Scene Mixer kombiniert lokal Setting, Licht, Bildaufbau und Atmosphäre. "
            "Er ergänzt eine aktive Szene, ersetzt sie aber nicht und lernt die Mischung nicht dauerhaft."
        )
        intro.setWordWrap(True)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.draw_button = QPushButton("🎲 Neue Szene mischen")
        self.clear_button = QPushButton("Mixer ausschalten")

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.draw_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear)
        self._render(self.repository.active(self.conversation_id))

    def _render(self, mix: SceneMix | None) -> None:
        self.clear_button.setEnabled(mix is not None)
        if mix is None:
            self.status.setText("Kein gemischter Szenen-Layer aktiv.")
            return
        parts = " · ".join(f"{key}: {value}" for key, value in mix.components.items())
        self.status.setText(f"Aktiv: {mix.title}\n{parts}\n\n{mix.context}")

    def draw(self) -> None:
        mix = self.repository.draw(self.conversation_id)
        self._render(mix)
        self.changed.emit(mix)

    def clear(self) -> None:
        self.repository.clear(self.conversation_id)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._render(self.repository.active(conversation_id))


class CreativeVarietyWidget(QWidget):
    look_changed = Signal(object)
    arc_changed = Signal(object)
    scene_mix_changed = Signal(object)

    def __init__(
        self,
        look_repository: LookPresetRepository,
        arc_repository: SessionArcRepository,
        mixer_repository: SceneMixerRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.looks = LookPresetWidget(look_repository, conversation_id)
        self.arcs = SessionArcWidget(arc_repository, conversation_id)
        self.mixer = SceneMixerWidget(mixer_repository, conversation_id)

        tabs = QTabWidget()
        tabs.addTab(self.looks, "Looks")
        tabs.addTab(self.arcs, "Session-Arcs")
        tabs.addTab(self.mixer, "Scene Mixer")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self.looks.changed.connect(self.look_changed)
        self.arcs.changed.connect(self.arc_changed)
        self.mixer.changed.connect(self.scene_mix_changed)

    def set_conversation(self, conversation_id: str) -> None:
        self.looks.set_conversation(conversation_id)
        self.arcs.set_conversation(conversation_id)
        self.mixer.set_conversation(conversation_id)
        self.look_changed.emit(self.looks.repository.active(conversation_id))
        self.arc_changed.emit(self.arcs.repository.active(conversation_id))
        self.scene_mix_changed.emit(self.mixer.repository.active(conversation_id))
