from __future__ import annotations

from app.ai.model_catalog import catalog_model, strict_open_source_models


def test_catalog_has_unique_ollama_names() -> None:
    models = strict_open_source_models()
    names = [item.ollama_model.casefold() for item in models]
    assert len(names) == len(set(names))


def test_catalog_uses_only_strict_permissive_license_metadata() -> None:
    models = strict_open_source_models()
    assert models
    for item in models:
        assert "Apache-2.0" in item.license_id or "MIT" in item.license_id
        assert "llama" not in item.license_id.casefold()
        assert "community" not in item.license_id.casefold()
        assert "openrail" not in item.license_id.casefold()


def test_non_apache_qwen25_variants_are_excluded() -> None:
    assert catalog_model("qwen2.5:3b") is None
    assert catalog_model("qwen2.5:72b") is None
    assert catalog_model("qwen2.5:7b") is not None


def test_uncensored_suffix_is_source_backed_and_not_a_ranking_flag() -> None:
    marked = [item for item in strict_open_source_models() if item.uncensored]
    assert [item.ollama_model for item in marked] == ["dolphin-mistral:7b"]
    assert marked[0].display_name.endswith(" (unzensiert)")
    assert "Ollama" in marked[0].note


def test_custom_license_uncensored_llama_models_are_not_in_catalog() -> None:
    assert catalog_model("llama2-uncensored:7b") is None
    assert catalog_model("wizard-vicuna-uncensored:7b") is None
    assert catalog_model("wizardlm-uncensored:13b") is None
