from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.creative_director import CreativeDirector, CreativeDirectorRepository
from app.ai.creative_recipes import CreativeRecipeManager
from app.ai.look_presets import LookPreset, LookPresetRepository
from app.ai.scene_mixer import SceneMix, SceneMixerRepository
from app.ai.session_arcs import ActiveArc, SessionArcRepository
from app.ai.visual_motifs import VisualMotif, VisualMotifRepository
from app.ui.creative_director import CreativeDirectorWidget


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
            "Einzelne Dimensionen können festgehalten werden, während der Rest weiter variiert."
        )
        intro.setWordWrap(True)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.draw_button = QPushButton("🎲 Neue Szene mischen")
        self.clear_button = QPushButton("Mixer ausschalten")

        self.lock_setting = QCheckBox("Setting sperren")
        self.lock_lighting = QCheckBox("Licht sperren")
        self.lock_composition = QCheckBox("Komposition sperren")
        self.lock_atmosphere = QCheckBox("Atmosphäre sperren")
        lock_row = QHBoxLayout()
        lock_row.addWidget(self.lock_setting)
        lock_row.addWidget(self.lock_lighting)
        lock_row.addWidget(self.lock_composition)
        lock_row.addWidget(self.lock_atmosphere)

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.draw_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.status)
        layout.addLayout(lock_row)
        layout.addStretch(1)
        layout.addLayout(row)

        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear)
        self.lock_setting.toggled.connect(
            lambda checked: self._set_locked("setting", checked)
        )
        self.lock_lighting.toggled.connect(
            lambda checked: self._set_locked("lighting", checked)
        )
        self.lock_composition.toggled.connect(
            lambda checked: self._set_locked("composition", checked)
        )
        self.lock_atmosphere.toggled.connect(
            lambda checked: self._set_locked("atmosphere", checked)
        )
        self._reload()

    def _reload(self) -> None:
        locks = self.repository.locked_dimensions(self.conversation_id)
        controls = {
            "setting": self.lock_setting,
            "lighting": self.lock_lighting,
            "composition": self.lock_composition,
            "atmosphere": self.lock_atmosphere,
        }
        for dimension, control in controls.items():
            control.blockSignals(True)
            control.setChecked(dimension in locks)
            control.blockSignals(False)
        self._render(self.repository.active(self.conversation_id))

    def _set_locked(self, dimension: str, locked: bool) -> None:
        self.repository.set_dimension_locked(self.conversation_id, dimension, locked)
        self._render(self.repository.active(self.conversation_id))

    def _render(self, mix: SceneMix | None) -> None:
        self.clear_button.setEnabled(mix is not None)
        locks = self.repository.locked_dimensions(self.conversation_id)
        lock_text = ", ".join(sorted(locks)) or "keine"
        if mix is None:
            self.status.setText(
                f"Kein gemischter Szenen-Layer aktiv. Gesperrte Dimensionen: {lock_text}"
            )
            return
        parts = " · ".join(f"{key}: {value}" for key, value in mix.components.items())
        self.status.setText(
            f"Aktiv: {mix.title}\n{parts}\nGesperrt: {lock_text}\n\n{mix.context}"
        )

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
        self._reload()


class VisualMotifWidget(QWidget):
    changed = Signal(object)

    def __init__(
        self,
        repository: VisualMotifRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Visuelle Motive variieren Ausdruck, Haltung und Kamerawirkung. Sie sind temporär, "
            "beeinflussen lokale Bildplanung und verändern weder Character-Identität noch Memory."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.activate_button = QPushButton("Motiv aktivieren")
        self.draw_button = QPushButton("🎲 Motiv wechseln")
        self.clear_button = QPushButton("Basis-Motiv")

        row = QHBoxLayout()
        row.addWidget(self.clear_button)
        row.addStretch(1)
        row.addWidget(self.draw_button)
        row.addWidget(self.activate_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(row)

        self.activate_button.clicked.connect(self.activate_selected)
        self.draw_button.clicked.connect(self.draw)
        self.clear_button.clicked.connect(self.clear)
        self._reload()

    def _reload(self) -> None:
        active = self.repository.active(self.conversation_id)
        active_id = active.id if active else None
        self.combo.clear()
        for motif in self.repository.list_motifs():
            self.combo.addItem(motif.name, motif.id)
        if active_id:
            index = self.combo.findData(active_id)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self._render(active)

    def _render(self, motif: VisualMotif | None) -> None:
        if motif is None:
            self.status.setText("Kein zusätzliches Visual-Motiv aktiv.")
            return
        self.status.setText(
            f"Aktiv: {motif.name}\n{motif.description}\n{motif.prompt_text()}"
        )

    def activate_selected(self) -> None:
        motif_id = str(self.combo.currentData() or "")
        if not motif_id:
            return
        motif = self.repository.set_active(self.conversation_id, motif_id)
        self._render(motif)
        self.changed.emit(motif)

    def draw(self) -> None:
        motif = self.repository.draw(self.conversation_id)
        self._reload()
        self.changed.emit(motif)

    def clear(self) -> None:
        self.repository.set_active(self.conversation_id, None)
        self._render(None)
        self.changed.emit(None)

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self._reload()


class CreativeRecipeWidget(QWidget):
    applied = Signal(object)

    def __init__(
        self,
        manager: CreativeRecipeManager,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self.repository = manager.repository
        self.conversation_id = conversation_id
        self._recipes = {}

        intro = QLabel(
            "Creative Recipes speichern komplette temporäre Lieblingskombinationen aus Look, Impuls, "
            "Session-Arc, Visual-Motiv und Scene Mixer. Persona, Memory und stabile Character-Identität "
            "werden niemals Bestandteil eines Rezepts."
        )
        intro.setWordWrap(True)
        self.combo = QComboBox()
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Name für aktuelle Kombination")
        self.capture_button = QPushButton("Aktuelle Kombination speichern")
        self.apply_button = QPushButton("Recipe anwenden")
        self.delete_button = QPushButton("Eigenes Recipe löschen")

        capture_row = QHBoxLayout()
        capture_row.addWidget(self.name, 1)
        capture_row.addWidget(self.capture_button)
        action_row = QHBoxLayout()
        action_row.addWidget(self.delete_button)
        action_row.addStretch(1)
        action_row.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(self.combo)
        layout.addWidget(self.status)
        layout.addLayout(capture_row)
        layout.addStretch(1)
        layout.addLayout(action_row)

        self.combo.currentIndexChanged.connect(self._render_selected)
        self.capture_button.clicked.connect(self.capture)
        self.apply_button.clicked.connect(self.apply_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.refresh()

    def refresh(self, select_id: str | None = None) -> None:
        recipes = self.repository.list_recipes()
        self._recipes = {recipe.id: recipe for recipe in recipes}
        current_id = select_id or str(self.combo.currentData() or "")
        self.combo.blockSignals(True)
        self.combo.clear()
        for recipe in recipes:
            source = "Standard" if recipe.builtin else "Eigenes"
            self.combo.addItem(f"{recipe.name} · {source}", recipe.id)
        index = self.combo.findData(current_id)
        if index >= 0:
            self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)
        self._render_selected()

    def _selected(self):
        return self._recipes.get(str(self.combo.currentData() or ""))

    def _render_selected(self) -> None:
        recipe = self._selected()
        if recipe is None:
            self.status.setText("Kein Recipe ausgewählt.")
            self.delete_button.setEnabled(False)
            self.apply_button.setEnabled(False)
            return
        parts = [
            f"Look: {recipe.look_id or 'Basis'}",
            f"Impuls: {recipe.variety_id or 'Basis'}",
            f"Arc: {recipe.arc_id or 'aus'}",
            f"Visual-Motiv: {recipe.visual_motif_id or 'Basis'}",
            "Scene Mixer: gespeichert" if recipe.scene_mix else (
                "Scene Mixer: neu mischen" if recipe.draw_scene_mix else "Scene Mixer: aus"
            ),
        ]
        self.status.setText(f"{recipe.name}\n{recipe.description}\n" + " · ".join(parts))
        self.delete_button.setEnabled(not recipe.builtin)
        self.apply_button.setEnabled(True)

    def capture(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.information(self, "Creative Recipe", "Bitte einen Namen für das Recipe eingeben.")
            return
        try:
            recipe = self.manager.capture_current(self.conversation_id, name=name)
        except ValueError as exc:
            QMessageBox.warning(self, "Creative Recipe", str(exc))
            return
        self.name.clear()
        self.refresh(select_id=recipe.id)

    def apply_selected(self) -> None:
        recipe = self._selected()
        if recipe is None:
            return
        try:
            applied = self.manager.apply(self.conversation_id, recipe.id)
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Creative Recipe", str(exc))
            return
        self.status.setText(f"Recipe angewendet: {applied.name}")
        self.applied.emit(applied)

    def delete_selected(self) -> None:
        recipe = self._selected()
        if recipe is None or recipe.builtin:
            return
        answer = QMessageBox.question(
            self,
            "Creative Recipe löschen",
            f"Eigenes Recipe „{recipe.name}“ wirklich löschen?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.repository.delete_custom(recipe.id)
        self.refresh()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()


class CreativeVarietyWidget(QWidget):
    look_changed = Signal(object)
    arc_changed = Signal(object)
    scene_mix_changed = Signal(object)
    visual_motif_changed = Signal(object)
    director_applied = Signal(object)
    recipe_applied = Signal(object)

    def __init__(
        self,
        look_repository: LookPresetRepository,
        arc_repository: SessionArcRepository,
        mixer_repository: SceneMixerRepository,
        motif_repository: VisualMotifRepository,
        director: CreativeDirector,
        director_repository: CreativeDirectorRepository,
        recipe_manager: CreativeRecipeManager,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.conversation_id = conversation_id
        self.director = CreativeDirectorWidget(
            director,
            director_repository,
            conversation_id,
        )
        self.recipes = CreativeRecipeWidget(recipe_manager, conversation_id)
        self.looks = LookPresetWidget(look_repository, conversation_id)
        self.arcs = SessionArcWidget(arc_repository, conversation_id)
        self.motifs = VisualMotifWidget(motif_repository, conversation_id)
        self.mixer = SceneMixerWidget(mixer_repository, conversation_id)

        tabs = QTabWidget()
        tabs.addTab(self.director, "Regie")
        tabs.addTab(self.recipes, "Recipes")
        tabs.addTab(self.looks, "Looks")
        tabs.addTab(self.arcs, "Session-Arcs")
        tabs.addTab(self.motifs, "Visual-Motive")
        tabs.addTab(self.mixer, "Scene Mixer")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        self.looks.changed.connect(self.look_changed)
        self.arcs.changed.connect(self.arc_changed)
        self.motifs.changed.connect(self.visual_motif_changed)
        self.mixer.changed.connect(self.scene_mix_changed)
        self.director.applied.connect(self._director_applied)
        self.recipes.applied.connect(self._recipe_applied)

    def _director_applied(self, result: object) -> None:
        self.refresh_from_repositories()
        self.director_applied.emit(result)

    def _recipe_applied(self, result: object) -> None:
        self.refresh_from_repositories()
        self.recipe_applied.emit(result)

    def refresh_from_repositories(self) -> None:
        conversation_id = self.conversation_id
        self.looks.set_conversation(conversation_id)
        self.arcs.set_conversation(conversation_id)
        self.motifs.set_conversation(conversation_id)
        self.mixer.set_conversation(conversation_id)
        self.director.set_conversation(conversation_id)
        self.recipes.set_conversation(conversation_id)
        self.look_changed.emit(self.looks.repository.active(conversation_id))
        self.arc_changed.emit(self.arcs.repository.active(conversation_id))
        self.visual_motif_changed.emit(self.motifs.repository.active(conversation_id))
        self.scene_mix_changed.emit(self.mixer.repository.active(conversation_id))

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh_from_repositories()
