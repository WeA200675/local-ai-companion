from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ai.scenario_seeds import (
    ScenarioSeedEngine,
    ScenarioSeedRepository,
    ScenarioSeedSelection,
)
from app.ai.storyboard_journeys import (
    ActiveStoryboardJourney,
    StoryboardJourneyEngine,
    StoryboardJourneyRepository,
)


class _ScenarioSeedPanel(QWidget):
    """Generate one coherent temporary session bundle from compatible creative layers."""

    changed = Signal(object)

    def __init__(
        self,
        engine: ScenarioSeedEngine,
        repository: ScenarioSeedRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.repository = repository
        self.conversation_id = conversation_id
        self.assistant_count_provider = assistant_count_provider

        intro = QLabel(
            "Ein Session-Seed kombiniert Look, Impuls, Arc, Scene Mixer, Visual-Motiv, Mood, Details, "
            "Scene Evolution und Ritual aus zueinander passenden Pools. Kreative Locks bleiben erhalten. "
            "Die Auswahl ist nur temporärer Session-Kontext und verändert weder Persona noch Memory."
        )
        intro.setWordWrap(True)

        self.template_combo = QComboBox()
        self.template_combo.addItem("🎲 Überraschung — kompatibel gemischt", "")
        for template in self.engine.templates():
            self.template_combo.addItem(template.name, template.id)

        self.include_evolution = QCheckBox("Scene Evolution einbeziehen")
        self.include_evolution.setChecked(True)
        self.include_ritual = QCheckBox("Ritual einbeziehen")
        self.include_ritual.setChecked(True)
        self.automatic_sequences = QCheckBox("Evolution und Ritual automatisch weiterführen")
        self.automatic_sequences.setChecked(True)

        form = QFormLayout()
        form.addRow("Session-Thema", self.template_combo)
        form.addRow("", self.include_evolution)
        form.addRow("", self.include_ritual)
        form.addRow("", self.automatic_sequences)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        self.apply_button = QPushButton("🎲 Stimmige Session erzeugen")
        self.restore_button = QPushButton("↶ Vorherigen Zustand wiederherstellen")
        self.clear_button = QPushButton("Seed-Markierung lösen")

        buttons = QHBoxLayout()
        buttons.addWidget(self.restore_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        buttons.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(self.details, 1)
        layout.addLayout(buttons)

        self.apply_button.clicked.connect(self.apply_seed)
        self.restore_button.clicked.connect(self.restore_previous)
        self.clear_button.clicked.connect(self.clear_marker)
        self.refresh_from_repository()

    def _render(self, selection: ScenarioSeedSelection | None) -> None:
        enabled = selection is not None
        self.restore_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        if selection is None:
            self.status.setText("Kein Session-Seed aktiv. Einzelne kreative Ebenen können trotzdem aktiv sein.")
            self.details.setPlainText(
                "Ein Session-Seed ist ein reversibler Ausgangspunkt, kein Lock. Nach dem Anwenden kannst du "
                "jede kreative Ebene weiterhin einzeln verändern."
            )
            return

        media = {
            "auto": "automatisch",
            "image": "Bild bevorzugt",
            "motion": "Motion bevorzugt, sofern lokaler Workflow verfügbar",
        }[selection.media_preference]
        preserved = ", ".join(selection.preserved_layers) or "keine"
        self.status.setText(
            f"Aktiv: {selection.template_name} · Kompatibilität {selection.compatibility_score}% · "
            f"Medienmodus: {media}"
        )

        lines = [
            selection.description,
            "",
            f"Reproduzierbarer Zufalls-Seed: {selection.random_seed}",
            f"Erhaltene/gesperrte Ebenen: {preserved}",
            "",
            "Ausgewählte Ebenen:",
        ]
        for label, value in selection.layer_summary.items():
            lines.append(f"  • {label}: {value}")
        if selection.compatibility_notes:
            lines.extend(["", "Kompatibilitäts-Hinweise:"])
            lines.extend(f"  • {item}" for item in selection.compatibility_notes)
        lines.extend(
            [
                "",
                "Der Seed ist nur der Session-Ursprung. Manuelle Änderungen danach bleiben möglich und werden "
                "nicht automatisch zurückgedreht.",
            ]
        )
        self.details.setPlainText("\n".join(lines))

    def apply_seed(self) -> None:
        template_id = str(self.template_combo.currentData() or "") or None
        selection = self.engine.generate(
            self.conversation_id,
            template_id=template_id,
            include_evolution=self.include_evolution.isChecked(),
            include_ritual=self.include_ritual.isChecked(),
            automatic_sequences=self.automatic_sequences.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(selection)
        self.changed.emit(selection)

    def restore_previous(self) -> None:
        if not self.engine.restore_previous(self.conversation_id):
            return
        self._render(None)
        self.changed.emit(None)

    def clear_marker(self) -> None:
        self.repository.clear(self.conversation_id)
        self._render(None)
        self.changed.emit(None)

    def refresh_from_repository(self) -> None:
        self._render(self.repository.active(self.conversation_id))

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh_from_repository()


class StoryboardJourneyWidget(QWidget):
    """Longer reversible dramaturgy built from successive compatible Session Studio seeds."""

    changed = Signal(object)

    def __init__(
        self,
        engine: StoryboardJourneyEngine,
        repository: StoryboardJourneyRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.repository = repository
        self.conversation_id = conversation_id
        self.assistant_count_provider = assistant_count_provider
        self._rendering = False

        intro = QLabel(
            "Storyboard Journeys koordinieren mehrere Session-Studio-Kapitel zu einem längeren Spannungsbogen. "
            "Jedes Kapitel wählt erneut zueinander passende temporäre Ebenen. Persona, Core Memory, adaptives Memory "
            "und deine Intimitäts-Grenzen werden nicht verändert. Die aktuelle Benutzernachricht hat immer Vorrang."
        )
        intro.setWordWrap(True)

        self.journey_combo = QComboBox()
        for journey in self.engine.journeys():
            self.journey_combo.addItem(journey.name, journey.id)

        self.automatic = QCheckBox("Kapitel automatisch weiterführen")
        self.automatic.setChecked(True)
        self.replies_per_chapter = QSpinBox()
        self.replies_per_chapter.setRange(1, 12)
        self.replies_per_chapter.setValue(3)
        self.replies_per_chapter.setSuffix(" Antworten/Kapitel")
        self.automatic_sequences = QCheckBox(
            "Scene Evolution und Ritual innerhalb der Kapitel automatisch weiterführen"
        )
        self.automatic_sequences.setChecked(True)

        form = QFormLayout()
        form.addRow("Journey", self.journey_combo)
        form.addRow("", self.automatic)
        form.addRow("Kapiteltempo", self.replies_per_chapter)
        form.addRow("", self.automatic_sequences)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)

        self.start_button = QPushButton("▶ Journey starten")
        self.previous_button = QPushButton("← Voriges Kapitel")
        self.next_button = QPushButton("Nächstes Kapitel →")
        self.restore_button = QPushButton("↶ Journey beenden & Ursprung wiederherstellen")
        self.detach_button = QPushButton("Journey lösen · aktuellen Zustand behalten")

        navigation = QHBoxLayout()
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        navigation.addStretch(1)
        navigation.addWidget(self.start_button)

        ending = QHBoxLayout()
        ending.addWidget(self.restore_button)
        ending.addWidget(self.detach_button)
        ending.addStretch(1)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(self.details, 1)
        layout.addLayout(navigation)
        layout.addLayout(ending)

        self.start_button.clicked.connect(self.start_journey)
        self.previous_button.clicked.connect(self.previous_chapter)
        self.next_button.clicked.connect(self.next_chapter)
        self.restore_button.clicked.connect(self.restore_origin)
        self.detach_button.clicked.connect(self.detach_journey)
        self.automatic.toggled.connect(self._configure_active)
        self.replies_per_chapter.valueChanged.connect(self._configure_active)
        self.automatic_sequences.toggled.connect(self._configure_active)

        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self._poll_automatic_progression)
        self.timer.start()
        self.refresh_from_repository()

    def _journey_definition(self, journey_id: str):
        return self.engine.journey(journey_id)

    def _render(self, active: ActiveStoryboardJourney | None) -> None:
        self._rendering = True
        try:
            enabled = active is not None
            self.previous_button.setEnabled(bool(active and active.chapter_index > 0))
            self.next_button.setEnabled(bool(active and not active.completed))
            self.restore_button.setEnabled(enabled)
            self.detach_button.setEnabled(enabled)

            if active is None:
                self.status.setText(
                    "Keine Storyboard Journey aktiv. Ein einzelner Session-Seed kann unabhängig davon aktiv sein."
                )
                selected = self._journey_definition(str(self.journey_combo.currentData() or ""))
                if selected is None:
                    self.details.clear()
                    return
                lines = [selected.description, "", "Kapitel:"]
                lines.extend(
                    f"  {index}. {chapter.name} · {chapter.scenario_template_id}"
                    for index, chapter in enumerate(selected.chapters, start=1)
                )
                self.details.setPlainText("\n".join(lines))
                return

            combo_index = self.journey_combo.findData(active.journey_id)
            if combo_index >= 0:
                self.journey_combo.setCurrentIndex(combo_index)
            self.automatic.setChecked(active.automatic)
            self.replies_per_chapter.setValue(active.replies_per_chapter)
            self.automatic_sequences.setChecked(active.automatic_sequences)

            state = "abgeschlossen" if active.completed else "aktiv"
            mode = (
                f"automatisch · alle {active.replies_per_chapter} Antworten"
                if active.automatic
                else "manuell"
            )
            self.status.setText(
                f"{active.journey_name} · Kapitel {active.chapter_index + 1}/{active.chapter_count}: "
                f"{active.chapter_name} · {state} · {mode}"
            )
            definition = self._journey_definition(active.journey_id)
            lines = [
                active.description,
                "",
                f"Aktuelles Kapitel: {active.chapter_name}",
                active.chapter_instruction,
                f"Session-Studio-Profil: {active.scenario_template_id}",
                f"Journey-RNG: {active.random_seed}",
                "",
                "Kapitelplan:",
            ]
            if definition is not None:
                for index, chapter in enumerate(definition.chapters):
                    marker = "▶" if index == active.chapter_index else "•"
                    lines.append(
                        f"  {marker} {index + 1}. {chapter.name} · {chapter.scenario_template_id}"
                    )
            lines.extend(
                [
                    "",
                    "Ein Kapitelwechsel verändert nur temporäre Kreativ-Layer. 'Ursprung wiederherstellen' "
                    "kehrt zum Zustand vor dem Journey-Start zurück; 'Journey lösen' behält den aktuellen Zustand.",
                ]
            )
            self.details.setPlainText("\n".join(lines))
        finally:
            self._rendering = False

    def start_journey(self) -> None:
        journey_id = str(self.journey_combo.currentData() or "")
        if not journey_id:
            return
        active = self.engine.start(
            self.conversation_id,
            journey_id,
            automatic=self.automatic.isChecked(),
            replies_per_chapter=self.replies_per_chapter.value(),
            automatic_sequences=self.automatic_sequences.isChecked(),
            assistant_count=self.assistant_count_provider(),
        )
        self._render(active)
        self.changed.emit(active)

    def previous_chapter(self) -> None:
        active = self.engine.previous(
            self.conversation_id,
            assistant_count=self.assistant_count_provider(),
        )
        if active is None:
            return
        self._render(active)
        self.changed.emit(active)

    def next_chapter(self) -> None:
        active = self.engine.advance(
            self.conversation_id,
            assistant_count=self.assistant_count_provider(),
        )
        if active is None:
            return
        self._render(active)
        self.changed.emit(active)

    def restore_origin(self) -> None:
        if not self.engine.restore_origin(self.conversation_id):
            return
        self._render(None)
        self.changed.emit(None)

    def detach_silently(self) -> None:
        self.engine.detach(self.conversation_id)
        self._render(None)

    def detach_journey(self) -> None:
        if self.repository.active(self.conversation_id) is None:
            return
        self.detach_silently()
        self.changed.emit(None)

    def _configure_active(self, *_args) -> None:
        if self._rendering:
            return
        active = self.engine.configure(
            self.conversation_id,
            automatic=self.automatic.isChecked(),
            replies_per_chapter=self.replies_per_chapter.value(),
            automatic_sequences=self.automatic_sequences.isChecked(),
        )
        if active is not None:
            self._render(active)
            self.changed.emit(active)

    def _poll_automatic_progression(self) -> None:
        active = self.repository.active(self.conversation_id)
        if active is None or not active.automatic or active.completed:
            return
        advanced = self.engine.maybe_advance(
            self.conversation_id,
            assistant_count=self.assistant_count_provider(),
        )
        if advanced is None:
            return
        self._render(advanced)
        self.changed.emit(advanced)

    def refresh_from_repository(self) -> None:
        self._render(self.repository.active(self.conversation_id))

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.refresh_from_repository()


class ScenarioSeedWidget(QWidget):
    """Session Studio with single-session seeds and longer Storyboard Journeys."""

    changed = Signal(object)

    def __init__(
        self,
        engine: ScenarioSeedEngine,
        repository: ScenarioSeedRepository,
        conversation_id: str,
        assistant_count_provider: Callable[[], int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.engine = engine
        self.repository = repository
        self.conversation_id = conversation_id
        self.assistant_count_provider = assistant_count_provider

        self.seed_panel = _ScenarioSeedPanel(
            engine,
            repository,
            conversation_id,
            assistant_count_provider,
        )
        self.storyboard_repository = StoryboardJourneyRepository(repository.store)
        self.storyboard_engine = StoryboardJourneyEngine(
            self.storyboard_repository,
            engine,
        )
        self.journey_panel = StoryboardJourneyWidget(
            self.storyboard_engine,
            self.storyboard_repository,
            conversation_id,
            assistant_count_provider,
        )

        tabs = QTabWidget()
        tabs.addTab(self.seed_panel, "Session Seed")
        tabs.addTab(self.journey_panel, "Storyboard Journey")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

        self.seed_panel.changed.connect(self._seed_changed)
        self.journey_panel.changed.connect(self._journey_changed)

    def _seed_changed(self, selection: object) -> None:
        # An explicit manual seed action outranks automatic Journey direction.
        if self.storyboard_repository.active(self.conversation_id) is not None:
            self.journey_panel.detach_silently()
        self.changed.emit(selection)

    def _journey_changed(self, active: object) -> None:
        self.seed_panel.refresh_from_repository()
        self.changed.emit(active)

    def refresh_from_repository(self) -> None:
        self.seed_panel.refresh_from_repository()
        self.journey_panel.refresh_from_repository()

    def set_conversation(self, conversation_id: str) -> None:
        self.conversation_id = conversation_id
        self.seed_panel.set_conversation(conversation_id)
        self.journey_panel.set_conversation(conversation_id)
