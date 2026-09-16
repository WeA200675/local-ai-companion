from __future__ import annotations

import argparse

from app.conversation_export import export_conversation
from app.memory.conversations import ConversationRepository
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a local companion conversation")
    parser.add_argument("--conversation", default=None, help="conversation id; default: active")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", default="data/exports")
    args = parser.parse_args()

    store = StateStore(make_session_factory())
    repository = ConversationRepository(store)
    path = export_conversation(
        repository,
        conversation_id=args.conversation,
        output_dir=args.output,
        format=args.format,
    )
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
