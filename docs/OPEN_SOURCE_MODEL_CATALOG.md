# Strict Open-Source Model Catalog

The Windows model tool now contains a curated catalog of Ollama model variants whose published model metadata documents a permissive Apache-2.0 or MIT license (or a permissive MIT fine-tune on an Apache-2.0 base).

The catalog is intentionally stricter than the broad terms `open`, `open-weight` or `community model`. A model is not included merely because it can be downloaded from Ollama.

## Windows usage

Open the graphical catalog:

```powershell
.\model_scout_windows.cmd
```

The GUI shows installation status, family, parameter size, license metadata, intended local use and the cached Adult-/Kink compatibility result. It can explicitly download a selected catalog model, run the existing local non-graphic compatibility probe, and save an already installed model as the app's chat model.

Nothing is downloaded automatically and selecting a model never happens silently.

CLI examples remain available:

```powershell
.\model_scout_windows.cmd --catalog
.\model_scout_windows.cmd --install qwen3:8b
.\model_scout_windows.cmd --select qwen3:8b
.\model_scout_windows.cmd --catalog --compare
```

## Curated families

The built-in catalog includes practical variants from Qwen3, the Apache-2.0 Qwen2.5 sizes, DeepSeek-R1 Qwen-derived variants, Mistral NeMo, Dolphin Mistral, OpenChat, Microsoft Phi-3/Phi-4, IBM Granite, OLMo 2 and SmolLM2.

The exact list is defined in `app/ai/model_catalog.py` so it is deterministic, testable and reviewable.

## `(unzensiert)` label

The UI does not infer or rank models by an `uncensored` property. The label is displayed only when the published Ollama model description explicitly uses that wording and the same catalog entry also passes the strict permissive-license rule.

At the time this catalog snapshot was researched, `dolphin-mistral:7b` met both conditions: Ollama describes the Dolphin Mistral family as `uncensored`, while its published model metadata carries Apache-2.0. The app therefore displays `Dolphin Mistral 7B (unzensiert)` as source metadata, not as a behavioral guarantee.

Llama-based `uncensored` entries such as `llama2-uncensored`, `wizard-vicuna-uncensored` and `wizardlm-uncensored` are deliberately excluded from this strict catalog because their underlying Llama community licenses are not Apache-2.0/MIT.

## Other deliberate exclusions

Qwen2.5 3B and 72B are not included because Ollama's Qwen2.5 documentation states that those two sizes use the Qwen license while the other listed Qwen2.5 sizes use Apache-2.0.

Models under custom, non-commercial, research-only, OpenRAIL or community licenses are also excluded from the strict catalog even when they are technically usable with Ollama.

## Source references

Catalog source URLs are stored with every model entry and shown as tooltips in the GUI. The main references used for this snapshot are the corresponding Ollama library pages for Qwen3, Qwen2.5, DeepSeek-R1, Mistral NeMo, Dolphin Mistral, OpenChat, Phi, Granite, OLMo 2 and SmolLM2, plus the upstream Qwen3 model cards confirming Apache-2.0.

Licenses can change between upstream revisions. The catalog is a reviewed metadata snapshot, not legal advice. Before bundling or redistributing model weights, re-check the exact model/tag and its current upstream license.
