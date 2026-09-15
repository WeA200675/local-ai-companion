# Local Adult / Kink Model Compatibility Test

The companion can configure its own temporary adult-intensity state correctly while the selected local language model still refuses or fails to execute that behavior. The Settings screen therefore includes a separate **Adult-/Kink-Modelltest** for the currently selected Ollama-compatible model.

## What it checks

The test runs three short requests locally against the configured model:

1. a minimal inference smoke test;
2. a clearly adult, erotic but intentionally non-graphic tone probe;
3. a consensual adult kink / power-play tone probe that is also intentionally non-graphic.

The probe never asks for graphic anatomy or sex-act descriptions. It is intended to answer a practical product question: can this local model follow the type of adult companion tone the application is configured to use, or does it technically fail or explicitly refuse even the non-graphic form?

## Results

A report contains an operational status, a 0–100 compatibility score, per-probe results and one of these overall states:

- **compatible** — both adult-tone probes completed without an obvious refusal;
- **limited** — at least one adult-tone probe completed while another was refused or unclear;
- **blocked** — both adult-tone probes produced an obvious refusal;
- **unclear** — the responses were too short/ambiguous for the local heuristic;
- **unavailable** — local model inference failed, for example because the Ollama model process terminated.

This distinction is important: a backend crash is not reported as an adult-content restriction.

## Persistence and privacy

The report is stored locally in the existing SQLite AppState store and keyed by model name plus endpoint. Raw probe responses are not persisted; only the compact result and diagnostic summary are retained. Switching models therefore shows the last result for that exact local model/endpoint pair or **not tested**.

## Limits of the test

The detector is deliberately simple and transparent. It looks for obvious refusal language and backend failures. Passing does not guarantee that a model will follow every later roleplay request, and failing one wording does not prove that every adult interaction is impossible. The real chat remains the final practical test.

The test does not download, recommend, or silently switch models. This keeps model choice under user control and avoids making open-source/license claims about arbitrary third-party model files.

No dependency, cloud service, telemetry or proprietary component is added by this feature.
