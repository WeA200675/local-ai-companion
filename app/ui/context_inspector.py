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
        snapshot = build_context_snapshot(
            store=self.store,
            settings=self.chat.settings,
            persona=self.chat.persona,
            preference_tags=list(self.chat.preference_tags),
            session_mode=self.chat.session_mode,
            scene_preset=self.chat.scene_preset,
            variety_card=self.chat.variety_card,
            conversations=self.chat.conversations,
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
