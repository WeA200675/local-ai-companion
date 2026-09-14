from __future__ import annotations

from app.media.continuity import CharacterProfile
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def test_appearance_revision_only_changes_for_real_edits() -> None:
    profile = CharacterProfile.create("persona-main")
    original_revision = profile.appearance_revision

    assert profile.set_appearance(profile.appearance_prompt) is False
    assert profile.appearance_revision == original_revision

    assert profile.set_appearance("clearly adult recurring character, silver hair, dark tailored look") is True
    assert profile.appearance_revision == original_revision + 1
    assert "silver hair" in profile.appearance_prompt


def test_seed_rotation_preserves_identity_metadata() -> None:
    profile = CharacterProfile.create("persona-main")
    profile.set_appearance("clearly adult recurring character, black hair, elegant styling")
    profile.set_reference(4, "data/generated_media/reference.png")
    old_seed = profile.seed

    new_seed = profile.rotate_seed()

    assert new_seed != old_seed
    assert profile.seed == new_seed
    assert profile.reference_media_id == 4
    assert profile.reference_media_path == "data/generated_media/reference.png"
    assert "black hair" in profile.appearance_prompt


def test_character_studio_fields_persist_through_state_store(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    profile = store.load_character_profile("nova-main")
    profile.set_appearance("clearly adult recurring character, auburn hair, green eyes")
    profile.rotate_seed()
    store.save_character_profile(profile)

    loaded = store.load_character_profile("nova-main")

    assert loaded.appearance_prompt == profile.appearance_prompt
    assert loaded.appearance_revision == profile.appearance_revision
    assert loaded.seed == profile.seed
