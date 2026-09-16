from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re

from app.memory.conversations import ConversationRepository


def _safe_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return clean[:80] or "conversation"


def export_conversation(
    repository: ConversationRepository,
    *,
    conversation_id: str | None = None,
    output_dir: str | Path = "data/exports",
    format: str = "markdown",
) -> Path:
    target_id = conversation_id or repository.active_id()
    thread = repository.get(target_id, include_archived=True)
    if thread is None:
        raise KeyError(f"Conversation {target_id!r} not found")
    messages = repository.list_messages(limit=max(100, thread.message_count + 10), conversation_id=target_id)
    destination = Path(output_dir).expanduser()
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{_safe_name(thread.title)}_{stamp}"

    if format == "markdown":
        path = destination / f"{base}.md"
        lines = [
            f"# {thread.title}",
            "",
            f"Exported locally: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]
        for message in messages:
            speaker = "User" if message.role == "user" else "Companion"
            lines.extend((f"## {speaker}", "", message.content, ""))
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    if format == "json":
        path = destination / f"{base}.json"
        payload = {
            "format": "local-ai-companion-conversation",
            "version": 1,
            "conversation": {
                "id": thread.id,
                "title": thread.title,
                "archived": thread.archived,
                "created_at": thread.created_at.isoformat(),
                "updated_at": thread.updated_at.isoformat(),
            },
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    raise ValueError("format must be 'markdown' or 'json'")
