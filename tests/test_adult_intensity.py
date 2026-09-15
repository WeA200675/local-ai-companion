from __future__ import annotations

from app.ai.adult_intensity import AdultIntensityConfig, AdultIntensityRepository
from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt
from app.memory.database import make_session_factory
from app.memory.store import StateStore


def _repository(tmp_path) -> AdultIntensityRepository:
    factory = make_session_factory(tmp_path / "companion.sqlite3")
    return AdultIntensityRepository(StateStore(factory))


def test_defaults_start_gently_but_allow_user_controlled_growth(tmp_path) -> None:
    repository = _repository(tmp_path)
    config = repository.config("chat-a")

    assert config.sexuality_current == 1
    assert config.sexuality_max == 4
    assert config.kink_current == 0
    assert config.kink_max == 4
    assert config.dynamic_escalation is True


def test_config_clamps_current_levels_to_user_maxima(tmp_path) -> None:
    repository = _repository(tmp_path)
    saved = repository.set_config(
        "chat-a",
        AdultIntensityConfig(
            sexuality_current=4,
            sexuality_max=2,
            kink_current=4,
            kink_max=1,
        ),
    )

    assert saved.sexuality_current == 2
    assert saved.kink_current == 1


def test_dynamic_escalation_is_bounded_and_conversation_scoped(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.set_config(
        "chat-a",
        AdultIntensityConfig(
            sexuality_current=1,
            sexuality_max=3,
            kink_current=0,
            kink_max=2,
            dynamic_escalation=True,
        ),
    )

    config, changed = repository.observe_user_signal(
        "chat-a",
        "Ich möchte es erotischer und kinky.",
    )

    assert changed is True
    assert config.sexuality_current == 2
    assert config.kink_current == 1
    assert repository.config("chat-b").sexuality_current == 1
    assert repository.config("chat-b").kink_current == 0


def test_dynamic_escalation_respects_locks_and_maxima(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.set_config(
        "chat-a",
        AdultIntensityConfig(
            sexuality_current=2,
            sexuality_max=2,
            sexuality_locked=False,
            kink_current=1,
            kink_max=4,
            kink_locked=True,
        ),
    )

    config, _ = repository.observe_user_signal(
        "chat-a",
        "Noch mehr, intensiver und perverser.",
    )

    assert config.sexuality_current == 2
    assert config.kink_current == 1


def test_stop_signal_deescalates_session_without_rewriting_limits(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.set_config(
        "chat-a",
        AdultIntensityConfig(
            sexuality_current=4,
            sexuality_max=4,
            kink_current=3,
            kink_max=4,
        ),
    )

    config, changed = repository.observe_user_signal("chat-a", "Stopp, das ist zu viel.")

    assert changed is True
    assert config.sexuality_current == 0
    assert config.kink_current == 0
    assert config.sexuality_max == 4
    assert config.kink_max == 4


def test_disabled_dynamic_escalation_does_not_change_levels(tmp_path) -> None:
    repository = _repository(tmp_path)
    repository.set_config(
        "chat-a",
        AdultIntensityConfig(
            sexuality_current=1,
            kink_current=0,
            dynamic_escalation=False,
        ),
    )

    config, changed = repository.observe_user_signal(
        "chat-a",
        "Mach es erotischer und kinky.",
    )

    assert changed is False
    assert config.sexuality_current == 1
    assert config.kink_current == 0


def test_prompt_exposes_adult_intensity_as_temporary_user_control() -> None:
    config = AdultIntensityConfig(
        sexuality_current=3,
        sexuality_max=4,
        kink_current=2,
        kink_max=3,
        kink_preferences=["roleplay"],
        boundaries=["example boundary"],
    )
    prompt = build_system_prompt(
        PersonaState(),
        adult_intensity_context=config.prompt_text(),
    )

    assert "Adult intimacy controls" in prompt
    assert "sexuality 3/4" in prompt
    assert "kink intensity 2/4" in prompt
    assert "consensual adult fictional interaction" in prompt
    assert "Never exceed the configured sexuality or kink maximum" in prompt
    assert "must never silently change persona traits, memories, or user preferences" in prompt
