from __future__ import annotations

from app.ai.creative_director import CreativeDirectorConfig
from app.ai.persona import PersonaState
from app.context_inspector import build_context_snapshot
from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.settings import AppSettings


def test_context_snapshot_exposes_director_policy_and_scene_locks(tmp_path) -> None:
    store = StateStore(make_session_factory(tmp_path / "companion.sqlite3"))
    config = CreativeDirectorConfig(
        enabled=True,
        interval=3,
        intensity="wild",
        lock_look=True,
        lock_arc=True,
    )

    snapshot = build_context_snapshot(
        store=store,
        settings=AppSettings(),
        persona=PersonaState(),
        preference_tags=[],
        director_config=config,
        scene_mix_locks=["setting", "composition"],
    )

    assert snapshot.director_enabled is True
    assert snapshot.director_interval == 3
    assert snapshot.director_intensity == "wild"
    assert snapshot.director_locks == ["look", "arc"]
    assert snapshot.scene_mix_locks == ["composition", "setting"]
