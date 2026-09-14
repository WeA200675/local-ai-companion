from __future__ import annotations

from app.ai.persona import PersonaState
from app.ai.visual_motifs import VisualMotifRepository
from app.context_inspector import build_context_snapshot
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def test_context_snapshot_exposes_visual_motif(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    motifs = VisualMotifRepository(store)
    motif = motifs.set_active("chat-a", "mirror-offset")
    assert motif is not None

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(),
        persona=PersonaState(),
        preference_tags=["cinematic"],
        visual_motif=motif,
    )

    assert snapshot.visual_motif_name == "Mirror Offset"
    assert "camera:" in snapshot.visual_motif_context
    assert any("mirror" in tag.casefold() for tag in snapshot.effective_tags)
    assert any("camera" in tag.casefold() for tag in snapshot.effective_tags)
