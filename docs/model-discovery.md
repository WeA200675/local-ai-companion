# Local model discovery

The Settings tab can query the configured local Ollama-compatible endpoint and populate the model field with the models already installed there.

Use **Modelle laden** next to the editable model selector. Discovery runs in a worker thread so the UI stays responsive, and it only calls the configured local `/api/tags` endpoint. No cloud service is involved.

The selector remains editable even after discovery, so custom Ollama-compatible backends or model aliases that do not appear in `/api/tags` can still be entered manually. Selecting a model does not download or install anything; it only changes which already-available model the app will use after settings are saved.
