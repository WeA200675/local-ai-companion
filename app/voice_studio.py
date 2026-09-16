from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.memory.conversation_facade import ConversationStateFacade
from app.memory.conversations import ConversationRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.ui.voice import VoiceStudio


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI Companion — Voice Studio")
    store = StateStore(make_session_factory())
    conversations = ConversationRepository(store)
    chat_store = ConversationStateFacade(store, conversations)
    window = VoiceStudio(store, chat_store)
    window.setWindowTitle("Local AI Companion — Voice Studio")
    window.resize(760, 560)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
