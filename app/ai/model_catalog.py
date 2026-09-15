from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

import httpx


@dataclass(frozen=True, slots=True)
class CatalogModel:
    ollama_model: str
    title: str
    family: str
    parameter_size: str
    license_id: str
    focus: str
    source_url: str
    uncensored: bool = False
    note: str = ""

    @property
    def display_name(self) -> str:
        suffix = " (unzensiert)" if self.uncensored else ""
        return f"{self.title}{suffix}"


# Strict catalog: only model variants whose upstream/Ollama metadata documents
# a permissive Apache-2.0 or MIT model license (or a permissive MIT fine-tune on
# an Apache-2.0 base). Custom/non-OSI families are intentionally omitted here.
OPEN_SOURCE_MODEL_CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel("qwen3:1.7b", "Qwen3 1.7B", "Qwen3", "1.7B", "Apache-2.0", "leichter multilingualer Companion", "https://ollama.com/library/qwen3"),
    CatalogModel("qwen3:4b", "Qwen3 4B", "Qwen3", "4B", "Apache-2.0", "multilingual, Rollenspiel, gute Effizienz", "https://ollama.com/library/qwen3"),
    CatalogModel("qwen3:8b", "Qwen3 8B", "Qwen3", "8B", "Apache-2.0", "starker Allround-/Companion-Kandidat", "https://ollama.com/library/qwen3"),
    CatalogModel("qwen3:14b", "Qwen3 14B", "Qwen3", "14B", "Apache-2.0", "höhere Dialogqualität", "https://ollama.com/library/qwen3"),
    CatalogModel("qwen3:30b", "Qwen3 30B-A3B", "Qwen3", "30B MoE", "Apache-2.0", "starke Qualität bei MoE-Inferenz", "https://ollama.com/library/qwen3"),
    CatalogModel("qwen3:32b", "Qwen3 32B", "Qwen3", "32B", "Apache-2.0", "großes lokales Dialogmodell", "https://ollama.com/library/qwen3"),
    CatalogModel("qwen2.5:0.5b", "Qwen2.5 0.5B", "Qwen2.5", "0.5B", "Apache-2.0", "Notfall-/Low-RAM-Fallback", "https://ollama.com/library/qwen2.5"),
    CatalogModel("qwen2.5:1.5b", "Qwen2.5 1.5B", "Qwen2.5", "1.5B", "Apache-2.0", "leichter multilingualer Fallback", "https://ollama.com/library/qwen2.5"),
    CatalogModel("qwen2.5:7b", "Qwen2.5 7B", "Qwen2.5", "7B", "Apache-2.0", "bewährter multilingualer Companion", "https://ollama.com/library/qwen2.5"),
    CatalogModel("qwen2.5:14b", "Qwen2.5 14B", "Qwen2.5", "14B", "Apache-2.0", "stärkere Dialog-/Rollenspielqualität", "https://ollama.com/library/qwen2.5"),
    CatalogModel("qwen2.5:32b", "Qwen2.5 32B", "Qwen2.5", "32B", "Apache-2.0", "großes lokales Dialogmodell", "https://ollama.com/library/qwen2.5"),
    CatalogModel("deepseek-r1:1.5b", "DeepSeek-R1 Distill Qwen 1.5B", "DeepSeek-R1", "1.5B", "MIT + Apache-2.0 base", "Reasoning-Fallback", "https://ollama.com/library/deepseek-r1"),
    CatalogModel("deepseek-r1:7b", "DeepSeek-R1 Distill Qwen 7B", "DeepSeek-R1", "7B", "MIT + Apache-2.0 base", "Reasoning und Dialog", "https://ollama.com/library/deepseek-r1"),
    CatalogModel("deepseek-r1:8b", "DeepSeek-R1 0528 Qwen3 8B", "DeepSeek-R1", "8B", "MIT + Apache-2.0 base", "Reasoning mit Qwen3-Basis", "https://ollama.com/library/deepseek-r1"),
    CatalogModel("deepseek-r1:14b", "DeepSeek-R1 Distill Qwen 14B", "DeepSeek-R1", "14B", "MIT + Apache-2.0 base", "stärkeres lokales Reasoning", "https://ollama.com/library/deepseek-r1"),
    CatalogModel("deepseek-r1:32b", "DeepSeek-R1 Distill Qwen 32B", "DeepSeek-R1", "32B", "MIT + Apache-2.0 base", "großes lokales Reasoning", "https://ollama.com/library/deepseek-r1"),
    CatalogModel("mistral-nemo:12b", "Mistral NeMo 12B", "Mistral NeMo", "12B", "Apache-2.0", "multilingualer Allrounder", "https://ollama.com/library/mistral-nemo"),
    CatalogModel("dolphin-mistral:7b", "Dolphin Mistral 7B", "Dolphin/Mistral", "7B", "Apache-2.0", "steuerbarer Companion-/Coding-Finetune", "https://ollama.com/library/dolphin-mistral", uncensored=True, note="Ollama bezeichnet diese Modellfamilie ausdrücklich als uncensored."),
    CatalogModel("openchat:7b", "OpenChat 7B", "OpenChat", "7B", "Apache-2.0", "offener Dialog-/Allround-Finetune", "https://ollama.com/library/openchat"),
    CatalogModel("phi4-mini:3.8b", "Phi-4 Mini 3.8B", "Phi-4", "3.8B", "MIT", "leichtes multilingualeres Reasoning", "https://ollama.com/library/phi4-mini"),
    CatalogModel("phi4:14b", "Phi-4 14B", "Phi-4", "14B", "MIT", "starkes Reasoning/Allround", "https://ollama.com/library/phi4"),
    CatalogModel("phi3:3.8b", "Phi-3 Mini 3.8B", "Phi-3", "3.8B", "MIT", "leichter lokaler Fallback", "https://ollama.com/library/phi3"),
    CatalogModel("phi3:14b", "Phi-3 Medium 14B", "Phi-3", "14B", "MIT", "größerer MIT-lizenzierter Allrounder", "https://ollama.com/library/phi3"),
    CatalogModel("granite4:3b", "Granite 4 3B", "Granite 4", "3B", "Apache-2.0", "effizienter multilingualer Assistent", "https://ollama.com/library/granite4"),
    CatalogModel("granite4:7b-a1b-h", "Granite 4 7B-A1B Hybrid", "Granite 4", "7B MoE/Hybrid", "Apache-2.0", "effiziente Hybrid-Inferenz", "https://ollama.com/library/granite4"),
    CatalogModel("granite4:32b-a9b-h", "Granite 4 32B-A9B Hybrid", "Granite 4", "32B MoE/Hybrid", "Apache-2.0", "größeres Hybrid-Modell", "https://ollama.com/library/granite4"),
    CatalogModel("granite3.3:2b", "Granite 3.3 2B", "Granite 3.3", "2B", "Apache-2.0", "leichter multilingualer Assistent", "https://ollama.com/library/granite3.3"),
    CatalogModel("granite3.3:8b", "Granite 3.3 8B", "Granite 3.3", "8B", "Apache-2.0", "multilingualer Allrounder", "https://ollama.com/library/granite3.3"),
    CatalogModel("olmo2:7b", "OLMo 2 7B", "OLMo 2", "7B", "Apache-2.0", "vollständig offen dokumentierte Modellfamilie", "https://ollama.com/library/olmo2"),
    CatalogModel("olmo2:13b", "OLMo 2 13B", "OLMo 2", "13B", "Apache-2.0", "größeres vollständig offenes Modell", "https://ollama.com/library/olmo2"),
    CatalogModel("smollm2:1.7b", "SmolLM2 1.7B", "SmolLM2", "1.7B", "Apache-2.0", "kleiner On-Device-Fallback", "https://ollama.com/library/smollm2"),
)


CATALOG_BY_MODEL = {item.ollama_model.casefold(): item for item in OPEN_SOURCE_MODEL_CATALOG}


def catalog_model(name: str) -> CatalogModel | None:
    return CATALOG_BY_MODEL.get(name.strip().casefold())


def strict_open_source_models() -> tuple[CatalogModel, ...]:
    return OPEN_SOURCE_MODEL_CATALOG


def installed_catalog_models(installed: list[str]) -> tuple[CatalogModel, ...]:
    normalized = {name.strip().casefold() for name in installed}
    return tuple(item for item in OPEN_SOURCE_MODEL_CATALOG if item.ollama_model.casefold() in normalized)


ProgressCallback = Callable[[str], None]


def pull_catalog_model(
    base_url: str,
    model_name: str,
    *,
    on_progress: ProgressCallback | None = None,
    timeout: float = 1800.0,
) -> None:
    """Explicitly download one catalog model from the configured local Ollama endpoint."""

    item = catalog_model(model_name)
    if item is None:
        raise ValueError(f"Modell {model_name!r} ist nicht im geprüften Open-Source-Katalog")
    url = base_url.strip().rstrip("/")
    if not url:
        raise ValueError("Ollama/API-URL must not be blank")

    request_timeout = httpx.Timeout(connect=10.0, read=timeout, write=60.0, pool=10.0)
    try:
        with httpx.stream(
            "POST",
            f"{url}/api/pull",
            json={"name": item.ollama_model, "stream": True},
            timeout=request_timeout,
        ) as response:
            response.raise_for_status()
            last_status = ""
            for line in response.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if not isinstance(data, dict):
                    continue
                error = data.get("error")
                if isinstance(error, str) and error.strip():
                    raise RuntimeError(error.strip())
                status = str(data.get("status") or "").strip()
                completed = data.get("completed")
                total = data.get("total")
                if status and on_progress is not None:
                    text = status
                    if isinstance(completed, int) and isinstance(total, int) and total > 0:
                        percent = int((completed / total) * 100)
                        text = f"{status} · {percent}%"
                    if text != last_status:
                        on_progress(text)
                        last_status = text
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Ollama-Modell konnte nicht geladen werden: {exc}") from exc
