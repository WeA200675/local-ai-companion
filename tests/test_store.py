from app.ai.persona import PersonaState
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_store_round_trip(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)

    persona = PersonaState(name="Nova")
    persona.evolve("dominance", 0.5)
    store.save_persona(persona)
    store.save_preference_tags(["latex", "teasing", "latex"])
    store.append_message("user", "hello")
    store.append_message("assistant", "hi")

    loaded = store.load_persona()
    assert loaded.name == "Nova"
    assert loaded.revision == persona.revision
    assert store.load_preference_tags() == ["latex", "teasing"]
    assert [(m.role, m.content) for m in store.list_messages()] == [
        ("user", "hello"),
        ("assistant", "hi"),
    ]

    store.clear_messages()
    assert store.list_messages() == []
