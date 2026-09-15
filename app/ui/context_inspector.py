from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.context_inspector import ContextSnapshot, build_context_snapshot
from app.memory.store import StateStore
from app.ui.mode_chat import ModeAwareChatWidget


_TRAIT_LABELS = {
    "dominance": "Dominanz",
    "strictness": "Strenge",
    "teasing": "Neckisch",
    "initiative": "Initiative",
    "persistence": "Beharrlichkeit",
    "creativity": "Kreativität",
    "autonomy": "Autonomie",
}


class ContextInspectorWidget(QWidget):
    """Read-only transparency view of the context used for the next local request."""

    def __init__(
        self,
        store: StateStore,
        chat: ModeAwareChatWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.chat = chat

        intro = QLabel(
            "Zeigt transparent, welche lokalen Kontextschichten die nächste Chat-Anfrage beeinflussen. "
            "Tokenwerte sind nur eine lokale Näherung; der Tokenizer des gewählten Modells ist maßgeblich."
        )
        intro.setWordWrap(True)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.refresh_button = QPushButton("Kontext aktualisieren")

        header = QHBoxLayout()
        header.addWidget(self.status, 1)
        header.addWidget(self.refresh_button)

        self.overview = QPlainTextEdit()
        self.overview.setReadOnly(True)
        self.prompt = QPlainTextEdit()
        self.prompt.setReadOnly(True)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)

        tabs = QTabWidget()
        tabs.addTab(self.overview, "Übersicht")
        tabs.addTab(self.prompt, "Effektiver Prompt")
        tabs.addTab(self.history, "Chat-Kontext")

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(header)
        layout.addWidget(tabs, 1)

        self.refresh_button.clicked.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        director_config = None
        scene_locks: list[str] = []
        conversation_id = None
        anti_repetition_enabled = False
        anti_repetition_context = ""
        twist_auto_enabled = False
        twist_interval: int | None = None
        if self.chat.conversations is not None:
            conversation_id = self.chat.conversations.active_id()
        if conversation_id and self.chat.creative_director is not None:
            director_config = self.chat.creative_director.repository.config(conversation_id)
        if conversation_id and self.chat.mixer_repository is not None:
            scene_locks = sorted(
                self.chat.mixer_repository.locked_dimensions(conversation_id)
            )
        if conversation_id and self.chat.anti_repetition_repository is not None:
            anti_config = self.chat.anti_repetition_repository.config(conversation_id)
            anti_repetition_enabled = anti_config.enabled
            anti_repetition_context = self.chat.anti_repetition_repository.guidance(
                conversation_id,
                self.chat._creative_signature(),  # noqa: SLF001 - inspector mirrors chat context
            )
        if conversation_id and self.chat.twist_repository is not None:
            twist_config = self.chat.twist_repository.config(conversation_id)
            twist_auto_enabled = twist_config.enabled
            twist_interval = twist_config.interval

        snapshot = build_context_snapshot(
            store=self.store,
            settings=self.chat.settings,
            persona=self.chat.persona,
            preference_tags=list(self.chat.preference_tags),
            session_mode=self.chat.session_mode,
            scene_preset=self.chat.scene_preset,
            variety_card=self.chat.variety_card,
            look_preset=self.chat.look_preset,
            active_arc=self.chat.active_arc,
            scene_mix=self.chat.scene_mix,
            visual_motif=self.chat.visual_motif,
            mood_grade=self.chat.mood_grade,
            detail_accent=self.chat.detail_accent,
            session_moment=self.chat.session_moment,
            twist_card=self.chat.twist_card,
            twist_auto_enabled=twist_auto_enabled,
            twist_interval=twist_interval,
            anti_repetition_context=anti_repetition_context,
            anti_repetition_enabled=anti_repetition_enabled,
            conversations=self.chat.conversations,
            director_config=director_config,
            scene_mix_locks=scene_locks,
        )
        self._render(snapshot)

    def _render(self, snapshot: ContextSnapshot) -> None:
        context_window = (
            str(snapshot.context_window)
            if snapshot.context_window is not None
            else "Modellstandard / nicht explizit gesetzt"
        )
        response_budget = (
            str(snapshot.response_budget)
            if snapshot.response_budget is not None
            else "Modellstandard / nicht explizit gesetzt"
        )
        remaining = (
            str(snapshot.approx_remaining_tokens)
            if snapshot.approx_remaining_tokens is not None
            else "nicht berechenbar ohne explizites Kontextfenster"
        )
        director = "aus"
        if snapshot.director_enabled:
            director = (
                f"an · alle {snapshot.director_interval} Antworten · "
                f"{snapshot.director_intensity}"
            )
        anti = "an" if snapshot.anti_repetition_enabled else "aus"
        if snapshot.anti_repetition_enabled and snapshot.anti_repetition_context:
            anti += " · Hinweis aktiv"
        twist_auto = "aus"
        if snapshot.twist_auto_enabled:
            twist_auto = f"an · frühestens alle {snapshot.twist_interval} Antworten"

        lines = [
            f"Modell: {snapshot.model_name}",
            f"Unterhaltung: {snapshot.conversation_title or 'Legacy/Hauptchat'}",
            f"Kontextfenster: {context_window}",
            f"Antwortbudget: {response_budget}",
            f"Geschätzter Input: ~{snapshot.approx_input_tokens} Token",
            f"Geschätzter Rest nach reserviertem Antwortbudget: {remaining}",
            "",
            f"Session-Modus: {snapshot.session_mode or 'Basis'}",
            f"Szene: {snapshot.scene_name or 'Basis'}",
            f"Impuls-Deck: {snapshot.variety_name or 'Basis'}",
            f"Look-Preset: {snapshot.look_name or 'Basis'}",
            f"Session-Arc: {snapshot.arc_name or 'aus'}"
            + (f" · {snapshot.arc_stage}" if snapshot.arc_stage else ""),
            f"Visual-Motiv: {snapshot.visual_motif_name or 'Basis'}",
            f"Mood-Grade: {snapshot.mood_grade_name or 'Basis'}",
            f"Detail-Akzent: {snapshot.detail_accent_name or 'aus'}",
            f"Gespeicherter Wiedereinstieg: {snapshot.session_moment_name or 'aus'}",
            f"Twist für nächste Antwort: {snapshot.twist_name or 'keiner'}",
            f"Twist-Automatik: {twist_auto}",
            f"Scene Mixer: {snapshot.scene_mix_name or 'aus'}",
            f"Kreative Regie: {director}",
            f"Anti-Wiederholung: {anti}",
            f"Regie-Sperren: {', '.join(snapshot.director_locks) or 'keine'}",
            f"Scene-Mixer-Sperren: {', '.join(snapshot.scene_mix_locks) or 'keine'}",
            f"Aktive Stil-/Präferenz-Tags: {', '.join(snapshot.effective_tags) or 'keine'}",
            "",
            "Persona — Basis → effektiv:",
        ]
        for name, base_value in snapshot.base_traits.items():
            effective = snapshot.effective_traits[name]
            locked = " 🔒" if name in snapshot.locked_traits else ""
            lines.append(
                f"  {_TRAIT_LABELS.get(name, name)}: {base_value:.2f} → {effective:.2f}{locked}"
            )

        lines.extend(
            [
                "",
                f"Core Memory aktiv: {len(snapshot.core_memory)}",
                *[f"  • {item}" for item in snapshot.core_memory],
                "",
                f"Adaptives Memory aktiv: {len(snapshot.adaptive_memory)}",
                *[f"  • {item}" for item in snapshot.adaptive_memory],
            ]
        )
        if snapshot.scene_context:
            lines.extend(["", "Temporärer Szenenkontext:", f"  {snapshot.scene_context}"])
        if snapshot.variety_context:
            lines.extend(["", "Temporärer Abwechslungs-Impuls:", f"  {snapshot.variety_context}"])
        if snapshot.look_context:
            lines.extend(["", "Temporärer Look:", f"  {snapshot.look_context}"])
        if snapshot.arc_context:
            lines.extend(["", "Aktuelle Arc-Phase:", f"  {snapshot.arc_context}"])
        if snapshot.visual_motif_context:
            lines.extend(["", "Aktuelles Visual-Motiv:", f"  {snapshot.visual_motif_context}"])
        if snapshot.mood_grade_context:
            lines.extend(["", "Aktuelles Mood-Grade:", f"  {snapshot.mood_grade_context}"])
        if snapshot.detail_accent_context:
            lines.extend(["", "Aktueller Detail-Akzent:", f"  {snapshot.detail_accent_context}"])
        if snapshot.session_moment_context:
            lines.extend(["", "Aktiver Session-Moment:", f"  {snapshot.session_moment_context}"])
        if snapshot.twist_context:
            lines.extend(["", "Einmaliger Twist:", f"  {snapshot.twist_context}"])
        if snapshot.scene_mix_context:
            lines.extend(["", "Scene-Mixer-Layer:", f"  {snapshot.scene_mix_context}"])
        if snapshot.anti_repetition_context:
            lines.extend(
                ["", "Lokaler Anti-Wiederholungs-Hinweis:", f"  {snapshot.anti_repetition_context}"]
            )
        if snapshot.warnings:
            lines.extend(["", "Hinweise:", *[f"  ⚠ {item}" for item in snapshot.warnings]])

        self.overview.setPlainText("\n".join(lines))
        self.prompt.setPlainText(snapshot.system_prompt)

        history_lines = [
            f"Im nächsten Request berücksichtigte Chat-Nachrichten: {len(snapshot.history)}",
            "",
        ]
        for index, item in enumerate(snapshot.history, start=1):
            history_lines.append(
                f"{index:>3}. {item.role:<9} ~{item.approx_tokens:>4} Token  {item.preview}"
            )
        if not snapshot.history:
            history_lines.append("Noch kein Chat-Kontext vorhanden.")
        self.history.setPlainText("\n".join(history_lines))

        warning_suffix = f" · {len(snapshot.warnings)} Hinweis(e)" if snapshot.warnings else ""
        self.status.setText(
            f"~{snapshot.approx_input_tokens} Input-Token · {len(snapshot.history)} Nachrichten"
            f" · {len(snapshot.core_memory)} Core · {len(snapshot.adaptive_memory)} adaptiv"
            f"{warning_suffix}"
        )

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API name
        self.refresh()
        super().showEvent(event)
