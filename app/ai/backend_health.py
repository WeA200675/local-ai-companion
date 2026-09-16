from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class OllamaFailure:
    code: str
    summary: str
    next_step: str
    technical_detail: str = ""

    def message(self) -> str:
        parts = [self.summary]
        if self.technical_detail:
            parts.append(self.technical_detail)
        if self.next_step:
            parts.append(f"Nächster Schritt: {self.next_step}")
        return " ".join(parts)


def _clean_text(value: object, limit: int = 320) -> str:
    clean = " ".join(str(value or "").split())
    if len(clean) > limit:
        return clean[: limit - 1].rstrip() + "…"
    return clean


def response_error_text(response: httpx.Response | None) -> str:
    if response is None:
        return ""
    try:
        payload = response.json()
    except (ValueError, httpx.ResponseNotRead):
        try:
            return _clean_text(response.text)
        except httpx.ResponseNotRead:
            return ""
    if isinstance(payload, dict):
        for key in ("error", "message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _clean_text(value)
    try:
        return _clean_text(response.text)
    except httpx.ResponseNotRead:
        return ""


def classify_ollama_failure(
    error: BaseException,
    *,
    model_name: str,
    timeout_seconds: float | None = None,
) -> OllamaFailure:
    """Turn local Ollama transport/backend failures into actionable user guidance.

    Classification is deliberately based only on the local HTTP failure. It does
    not guess a GPU vendor or claim a hardware root cause that Ollama did not
    report.
    """

    if isinstance(error, httpx.TimeoutException):
        timeout_text = (
            f" nach {timeout_seconds:g} s" if timeout_seconds is not None else ""
        )
        return OllamaFailure(
            code="timeout",
            summary=f"Ollama wurde erreicht, aber die Modell-Inferenz antwortete{timeout_text} nicht rechtzeitig.",
            next_step=(
                f"Prüfe `ollama ps` und teste anschließend `ollama run {model_name} \"Hallo\"`. "
                "Bei sehr langsamer lokaler Hardware kann ein kleineres Modell sinnvoll sein."
            ),
        )

    if isinstance(error, httpx.ConnectError):
        return OllamaFailure(
            code="unreachable",
            summary="Der lokale Ollama/API-Endpunkt ist nicht erreichbar.",
            next_step="Starte Ollama und prüfe die konfigurierte Ollama/API-URL.",
            technical_detail=_clean_text(error),
        )

    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        status = response.status_code
        body = response_error_text(response)
        body_folded = body.casefold()
        if status == 404 or (
            "model" in body_folded
            and any(token in body_folded for token in ("not found", "does not exist", "pull model"))
        ):
            return OllamaFailure(
                code="model_missing",
                summary=f"Ollama läuft, aber das Modell {model_name!r} ist nicht verfügbar.",
                next_step=f"Prüfe `ollama list` und installiere/auswähle das gewünschte lokale Modell {model_name!r}.",
                technical_detail=body,
            )
        native_crash_tokens = (
            "0xc0000005",
            "access violation",
            "llama-server process has terminated",
            "segmentation fault",
            "signal: aborted",
        )
        if status >= 500 and any(token in body_folded for token in native_crash_tokens):
            return OllamaFailure(
                code="backend_failure",
                summary=(
                    f"Ollama ist erreichbar, aber der native Modellprozess ist mit HTTP {status} fehlgeschlagen und der Modellprozess für {model_name!r} ist abgestürzt."
                ),
                next_step=(
                    "Nutze in der Ersteinrichtung „Funktionierendes Ersatzmodell suchen“. "
                    f"Teste zur Abgrenzung außerdem `ollama run {model_name} \"Hallo\"`; "
                    "wenn auch das abstürzt, prüfe Ollama-Version, Grafiktreiber und verfügbaren RAM/VRAM."
                ),
                technical_detail=body,
            )
        if status >= 500:
            return OllamaFailure(
                code="backend_failure",
                summary=(
                    f"Ollama ist erreichbar, aber das lokale Inferenz-Backend ist mit HTTP {status} fehlgeschlagen."
                ),
                next_step=(
                    f"Teste zuerst direkt `ollama run {model_name} \"Hallo\"`. "
                    "Wenn auch das fehlschlägt, liegt der Fehler unterhalb der Companion-App; prüfe Ollama-Log, RAM/VRAM und Backend/Driver-Konfiguration."
                ),
                technical_detail=body,
            )
        return OllamaFailure(
            code="http_error",
            summary=f"Ollama hat die lokale Modellanfrage mit HTTP {status} abgelehnt.",
            next_step=f"Teste `ollama run {model_name} \"Hallo\"` und prüfe die Ollama-Ausgabe.",
            technical_detail=body,
        )

    if isinstance(error, httpx.HTTPError):
        return OllamaFailure(
            code="transport_error",
            summary="Die lokale Verbindung zu Ollama ist während der Anfrage fehlgeschlagen.",
            next_step="Prüfe, ob Ollama weiterläuft und der konfigurierte lokale Endpoint erreichbar ist.",
            technical_detail=_clean_text(error),
        )

    return OllamaFailure(
        code="unknown",
        summary="Die lokale Modellanfrage ist unerwartet fehlgeschlagen.",
        next_step=f"Teste `ollama run {model_name} \"Hallo\"` und vergleiche die Fehlermeldung.",
        technical_detail=_clean_text(error),
    )
