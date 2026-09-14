from app.ai.persona import PersonaState
from app.memory.database import make_session_factory
from app.memory.snapshots import SnapshotStore


def test_restore_creates_pre_restore_backup(tmp_path):
    SessionFactory = make_session_factory(tmp_path / "test.sqlite3")
    with SessionFactory() as session:
        store = SnapshotStore(session)
        original = PersonaState()
        first = store.save(original, kind="initial")

        changed = original.model_copy(deep=True)
        changed.dominance.current = 0.95
        store.save(changed, kind="manual")

        restored = store.restore(changed, first.id)

        assert restored.dominance.current == original.dominance.current
        latest = store.latest()
        assert latest is not None
        assert latest.kind == "restored"

        rows = session.query(type(latest)).order_by(type(latest).id).all()
        assert rows[-2].kind == "pre_restore"
        assert rows[-2].restore_target_id == first.id
