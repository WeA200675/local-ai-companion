from app.ai.persona import PersonaState
from app.ai.prompting import build_system_prompt


def test_storyboard_context_is_temporary_and_user_overridable() -> None:
    prompt = build_system_prompt(
        PersonaState(),
        adult_intensity_context="Sexuality level 2/4, maximum 3/4.",
        storyboard_context=(
            "Rain to Dawn — chapter 2/4, Mirror Clue: keep one continuity-safe clue in focus."
        ),
    )

    assert "Active storyboard journey chapter" in prompt
    assert "Rain to Dawn" in prompt
    assert "never rush future chapters" in prompt
    assert "override the user's current request" in prompt
    assert "configured sexuality or kink maximum" in prompt
