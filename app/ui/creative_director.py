from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.ai.creative_director import (
    CreativeDirector,
    CreativeDirectorConfig,
    CreativeDirectorRepository,
    CreativeDirectorResult,
)


class CreativeDirectorWidget(QWidget):
    """User-facing controls for opt-in automatic creative rotation."""

    applied = Signal(object)
    config_changed = Signal()

    def __init__(
        self,
        director: CreativeDirector,
        repository: CreativeDirectorRepository,
        conversation_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.director = director
        self.repository = repository
        self.conversation_id = conversation_id

        intro = QLabel(
            "Die kreative Regie kann temporäre Looks, Impulse, Session-Arcs, Scene-Mixer-Layer "
            "und visuelle Motive selbstständig variieren. Sie ist standardmäßig aus, verändert weder "
            "Persona noch Memory und respektiert alle Sperren."
        )
        intro.setWordWrap(True)

        self.enabled = QCheckBox("Automatische Regie aktiv")
        self.interval = QSpinBox()
        self.interval.setRange(2, 20)
        self.interval.setSuffix(" Antworten")
        self.intensity = QComboBox()
        self.intensity.addItem("Sanft — 1 Layer", "gentle")
        self.intensity.addItem("Ausgewogen — 2 Layer", "balanced")
        self.intensity.addItem("Wild — bis zu 5 Layer", "wild")

        form = QFormLayout()
        form.addRow("Automatik", self.enabled)
        form.addRow("Wechselintervall", self.interval)
        form.addRow("Intensität", self.intensity)

        self.lock_look = QCheckBox("Look festhalten")
        self.lock_variety = QCheckBox("Impuls festhalten")
        self.lock_arc = QCheckBox("Session-Arc festhalten")
        self.lock_scene = QCheckBox("Scene Mixer festhalten")
        self.lock_motif = QCheckBox("Visual-Motiv festhalten")
        lock_row = QHBoxLayout()
        lock_row.addWidget(self.lock_look)
        lock_row.addWidget(self.lock_variety)
        lock_row.addWidget(self.lock_arc)
        lock_row.addWidget(self.lock_scene)
        lock_row.addWidget(self.lock_motif)

        self.favorite_look = QComboBox()
        self.favorite_arc = QComboBox()
        self.favorite_motif = QComboBox()
        self.favorite_look_button = QPushButton("⭐ Look-Favorit umschalten")
        self.favorite_arc_button = QPushButton("⭐ Arc-Favorit umschalten")
        self.favorite_motif_button = QPushButton("⭐ Motiv-Favorit umschalten")
        favorite_form = QFormLayout()
        favorite_form.addRow("Look-Favoriten", self.favorite_look)
        favorite_form.addRow("", self.favorite_look_button)
        favorite_form.addRow("Arc-Favoriten", self.favorite_arc)
        favorite_form.addRow("", self.favorite_arc_button)
        favorite_form.addRow("Motiv-Favoriten", self.favorite_motif)
        favorite_form.addRow("", self.favorite_motif_button)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.save_button = QPushButton("Regie-Einstellungen speichern")
        self.surprise_button = QPushButton("🎲 Überrasch mich")
        self.surprise_button.setToolTip(
            "Ändert sofort alle nicht gesperrten kreativen Layer dieser Unterhaltung."
        )

        action_row = QHBoxLayout()
        action_row.addWidget(self.save_button)
        action_row.addStretch(1)
        action_row.addWidget(self.surprise_button)

        note = QLabel(
            "Favoriten werden bei automatisch oder manuell gewürfelten Looks, Arcs und visuellen Motiven "
            "bevorzugt. Wenn keine Favoriten gesetzt sind, bleibt der gesamte Pool verfügbar. Automatische "
            "Änderungen gelten jeweils für die nächste Antwort und werden im Kontext-Inspector sichtbar."
        )
        note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addLayout(lock_row)
        layout.addLayout(favorite_form)
        layout.addWidget(self.status)
        layout.addStretch(1)
        layout.addLayout(action_row)
        layout.addWidget(note)

        self.save_button.clicked.connect(self.save_config)
        self.surprise_button.clicked.connect(self.surprise)
        self.favorite_look_button.clicked.connect(self.toggle_favorite_look)
        self.favorite_arc_button.clicked.connect(self.toggle_favorite_arc)
        self.favorite_motif_button.clicked.connect(self.toggle_favorite_motif)
        self.refresh()

    def _populate_favorites(self) -> None:
        current_look = self.favorite_look.currentData()
        current_arc = self.favorite_arc.currentData()
        current_motif = self.favorite_motif.currentData()
        self.favorite_look.clear()
        for preset in self.director.looks.list_presets():
            self.favorite_look.addItem(preset.name, preset.id)
        self.favorite_arc.clear()
        for arc in self.director.arcs.list_arcs():
            self.favorite_arc.addItem(arc.name, arc.id)
        self.favorite_motif.clear()
        if self.director.motifs is not None:
            for motif in self.director.motifs.list_motifs():
                self.favorite_motif.addItem(motif.name, motif.id)
        self.favorite_motif.setEnabled(self.director.motifs is not None)
        self.favorite_motif_button.setEnabled(self.director.motifs is not None)
        if current_look:
            index = self.favorite_look.findData(current_look)
            if index >= 0:
                self.favorite_look.setCurrentIndex(index)
        if current_arc:
            index = self.favorite_arc.findData(current_arc)
            if index >= 0:
                self.favorite_arc.setCurrentIndex(index)
        if current_motif:
            index = self.favorite_motif.findData(current_motif)
            if index >= 0:
                self.favorite_motif.setCurrentIndex(index)

    def refresh(self) -> None:
        self._populate_favorites()
        config = self.repository.config(self.conversation_id)
        self.enabled.setChecked(config.enabled)
        self.interval.setValue(config.interval)
        index = self.intensity.findData(config.intensity)
        self.intensity.setCurrentIndex(max(0, index))
        self.lock_look.setChecked(config.lock_look)
        self.lock_variety.setChecked(config.lock_variety)
        self.lock_arc.setChecked(config.lock_arc)
        self.lock_scene.setChecked(config.lock_scene_mix)
        self.lock_motif.setChecked(config.lock_visual_motif)
        self.lock_motif.setEnabled(self.director.motifs is not None)
        self._render_status(config)

    def _render_status(self, config: CreativeDirectorConfig, message: str = "") -> None:
        auto = "an" if config.enabled else "aus"
        locks = [
            name
            for name, locked in (
                ("Look", config.lock_look),
                ("Impuls", config.lock_variety),
                ("Arc", config.lock_arc),
                ("Scene Mixer", config.lock_scene_mix),
                ("Visual-Motiv", config.lock_visual_motif),
            )
            if locked
        ]
        details = (
            f"Automatik: {auto} · Intervall: {config.interval} · Intensität: {config.intensity} · "
            f"gesperrt: {', '.join(locks) or 'nichts'} · "
            f"Favoriten: {len(config.favorite_look_ids)} Looks / {len(config.favorite_arc_ids)} Arcs / "
            f"{len(config.favorite_visual_motif_ids)} Motive"
        )
        self.status.setText(f"{message}\n{details}".strip())

    def _config_from_controls(self) -> CreativeDirectorConfig:
        config = self.repository.config(self.conversation_id)
        config.enabled = self.enabled.isChecked()
        config.interval = self.interval.value()
        config.intensity = str(self.intensity.currentData() or "balanced")  # type: ignore[assignment]
        config.lock_look = self.lock_look.isChecked()
        config.lock_variety = self.lock_variety.isChecked()
        config.lock_arc = self.lock_arc.isChecked()
        config.lock_scene_mix = self.lock_scene.isChecked()
        config.lock_visual_motif = self.lock_motif.isChecked()
        return config

    def save_config(self) -> None:
        config = self._config_from_controls()
        self.repository.set_config(self.conversation_id, config)
        self._render_status(config, "Regie-Einstellungen lokal gespeichert.")
        self.config_changed.emit()

    def surprise(self) -> None:
        self.save_config()
        result = self.director.apply(self.conversation_id, automatic=False)
        self._render_result(result)
        self.applied.emit(result)

    def _render_result(self, result: CreativeDirectorResult) -> None:
        labels = {
            "look": "Look",
            "variety": "Impuls",
            "arc": "Arc",
            "scene_mix": "Scene Mixer",
            "visual_motif": "Visual-Motiv",
        }
        changed = ", ".join(labels.get(item, item) for item in result.changed)
        config = self.repository.config(self.conversation_id)
        message = (
            f"Überraschung angewendet: {changed}."
            if changed
            else "Keine Änderung — alle kreativen Layer sind gesperrt."
        )
        self._render_status(config, message)

    def toggle_favorite_look(self) -> None:
        preset_id = str(self.favorite_look.currentData() or "")
        if not preset_id:
            return
        config = self.repository.config(self.conversation_id)
        favorite = preset_id not in set(config.favorite_look_ids)
        self.repository.set_favorite_look(self.conversation_id, preset_id, favorite)
        self.refresh()
        self._render_status(
            self.repository.config(self.conversation_id),
            "Look-Favorit hinzugefügt." if favorite else "Look-Favorit entfernt.",
        )

    def toggle_favorite_arc(self) -> None:
        arc_id = str(self.favorite_arc.currentData() or "")
        if not arc_id:
            return
        config = self.repository.config(self.conversation_id)
        favorite = arc_id not in set(config.favorite_arc_ids)
        self.repository.set_favorite_arc(self.conversation_id, arc_id, favorite)
        self.refresh()
        self._render_status(
            self.repository.config(self.conversation_id),
            "Arc-Favorit hinzugefügt." if favorite else "Arc-Favorit entfernt.",
        )

    def toggle_favorite_motif(self) -> None:
        motif_id = str(self.favorite_motif.currentData() or "")
        if not motif_id:
            return
        config = self.repository.config(self.conversation_id)
        favorite = motif_id not in set(config.favorite_visual_motif_ids)
        self.repository.set_favorite_visual_motif(self.conversation_id, motif_id, favorite)
        self.refresh()
        self._render_status(
            self.repository.config(self.conversation_id),
            "Motiv-Favorit hinzugefügt." if favorite else "Motiv-Favorit entfernt.",
        )

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh()
