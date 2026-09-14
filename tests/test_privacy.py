from __future__ import annotations

from app.memory.database import make_session_factory
from app.memory.store import StateStore
from app.privacy import PrivacyConfig, PrivacyStore


def test_privacy_passphrase_is_hashed_and_verifiable() -> None:
    config = PrivacyConfig()
    config.set_passphrase("private-companion")

    assert config.enabled is True
    assert config.has_passphrase is True
    assert "private-companion" not in config.model_dump_json()
    assert config.verify("private-companion") is True
    assert config.verify("wrong-passphrase") is False


def test_privacy_requires_minimum_passphrase_length() -> None:
    config = PrivacyConfig()
    try:
        config.set_passphrase("short")
    except ValueError:
        pass
    else:
        raise AssertionError("short passphrase should have been rejected")

    assert config.enabled is False
    assert config.has_passphrase is False


def test_privacy_clear_removes_hash_and_auto_lock() -> None:
    config = PrivacyConfig(auto_lock_minutes=15)
    config.set_passphrase("long-enough")
    config.clear_passphrase()

    assert config.enabled is False
    assert config.has_passphrase is False
    assert config.auto_lock_minutes == 0
    assert config.verify("long-enough") is False


def test_privacy_config_round_trip_uses_local_app_state(tmp_path) -> None:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    store = StateStore(factory)
    repository = PrivacyStore(store)

    config = PrivacyConfig(auto_lock_minutes=7)
    config.set_passphrase("local-secret")
    repository.save(config)

    loaded = repository.load()
    assert loaded.enabled is True
    assert loaded.auto_lock_minutes == 7
    assert loaded.verify("local-secret") is True
    assert loaded.verify("other-secret") is False
