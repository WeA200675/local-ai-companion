from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import random
import time
from typing import Any, TypeVar
from urllib.parse import quote

import httpx

from app.media.comfyui import ComfyUIClient, ComfyUIError, GeneratedMedia
from app.media.profiles import WorkflowProfile
from app.media.rendering import MediaRenderPlan

T = TypeVar("T")
RetryCallback = Callable[[str, int, int, str], None]


class ResilientComfyUIError(ComfyUIError):
    """ComfyUI failure with enough context for action-oriented diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        stage: str,
        prompt_id: str = "",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.prompt_id = prompt_id
        self.retryable = retryable


class ResilientComfyUIClient(ComfyUIClient):
    """ComfyUI adapter that retries only operations that are safe to replay.

    The `/prompt` queue POST is deliberately *never* replayed automatically: a
    transport failure can occur after ComfyUI accepted the job but before the
    response reached the app, and replaying could create a duplicate expensive
    render. Once a prompt id exists, history and output downloads are idempotent
    GET operations and can be retried with fresh local connections.
    """

    def __init__(
        self,
        *args: Any,
        read_retries: int = 3,
        retry_backoff_seconds: float | None = None,
        retry_callback: RetryCallback | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.read_retries = max(0, int(read_retries))
        self.retry_callback = retry_callback
        if retry_backoff_seconds is None:
            retry_backoff_seconds = 0.6 if self._owns_client else 0.0
        self.retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    @staticmethod
    def _http_retryable(exc: httpx.HTTPError) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return isinstance(exc, httpx.RequestError)

    def _reset_owned_connection(self) -> None:
        if not self._owns_client:
            return
        try:
            self._client.close()
        finally:
            self._client = httpx.Client(timeout=self.timeout)

    def _retry_delay(self, attempt: int) -> float:
        if self.retry_backoff_seconds <= 0:
            return 0.0
        return min(4.0, self.retry_backoff_seconds * (2 ** max(0, attempt - 1)))

    def _notify_retry(self, stage: str, attempt: int, error: Exception) -> None:
        if self.retry_callback is not None:
            self.retry_callback(stage, attempt, self.read_retries, str(error))

    def _safe_retry(
        self,
        stage: str,
        operation: Callable[[], T],
        *,
        prompt_id: str = "",
    ) -> T:
        retries_used = 0
        while True:
            try:
                return operation()
            except httpx.HTTPError as exc:
                if not self._http_retryable(exc) or retries_used >= self.read_retries:
                    raise ResilientComfyUIError(
                        f"ComfyUI {stage} failed: {exc}",
                        stage=stage,
                        prompt_id=prompt_id,
                        retryable=self._http_retryable(exc),
                    ) from exc
                retries_used += 1
                self._notify_retry(stage, retries_used, exc)
                self._reset_owned_connection()
                delay = self._retry_delay(retries_used)
                if delay:
                    time.sleep(delay)

    def _upload_reference(self, path: Path) -> str:
        if not path.exists() or not path.is_file():
            raise ResilientComfyUIError(
                f"Reference image does not exist: {path}",
                stage="reference_upload",
            )

        def upload() -> dict[str, Any]:
            with path.open("rb") as handle:
                response = self._client.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (path.name, handle, "application/octet-stream")},
                    data={"type": "input", "overwrite": "true"},
                )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ResilientComfyUIError(
                    "ComfyUI returned an invalid reference upload response",
                    stage="reference_upload",
                )
            return payload

        try:
            payload = self._safe_retry("reference upload", upload)
        except OSError as exc:
            raise ResilientComfyUIError(
                f"Could not read local reference image: {exc}",
                stage="reference_upload",
            ) from exc
        except ValueError as exc:
            raise ResilientComfyUIError(
                f"ComfyUI returned invalid JSON after reference upload: {exc}",
                stage="reference_upload",
            ) from exc

        name = payload.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ResilientComfyUIError(
                "ComfyUI reference upload did not return a file name",
                stage="reference_upload",
            )
        subfolder = payload.get("subfolder")
        if isinstance(subfolder, str) and subfolder.strip():
            return f"{subfolder.strip().strip('/')}/{name.strip()}"
        return name.strip()

    def _queue_workflow(self, workflow: dict[str, Any]) -> str:
        """Queue exactly once; never replay an ambiguous expensive POST."""

        try:
            response = self._client.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            note = (
                " Der Queue-Aufruf wird absichtlich nicht automatisch wiederholt, "
                "weil der Render trotz verlorener Antwort bereits angenommen worden sein koennte."
            )
            raise ResilientComfyUIError(
                f"Could not queue ComfyUI workflow: {exc}.{note}",
                stage="queue",
                retryable=False,
            ) from exc
        except ValueError as exc:
            raise ResilientComfyUIError(
                f"ComfyUI returned invalid queue JSON: {exc}",
                stage="queue",
            ) from exc

        prompt_id = payload.get("prompt_id") if isinstance(payload, dict) else None
        if not isinstance(prompt_id, str) or not prompt_id:
            raise ResilientComfyUIError(
                "ComfyUI did not return a prompt_id; the request is not replayed automatically.",
                stage="queue",
            )
        return prompt_id

    def _history(self, prompt_id: str) -> dict[str, Any]:
        def read() -> dict[str, Any]:
            response = self._client.get(f"{self.base_url}/history/{prompt_id}")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ResilientComfyUIError(
                    "ComfyUI history returned an invalid object",
                    stage="history",
                    prompt_id=prompt_id,
                )
            return payload

        try:
            return self._safe_retry("history read", read, prompt_id=prompt_id)
        except ValueError as exc:
            raise ResilientComfyUIError(
                f"ComfyUI returned invalid history JSON: {exc}",
                stage="history",
                prompt_id=prompt_id,
            ) from exc

    @staticmethod
    def _execution_error(entry: dict[str, Any]) -> str:
        status = entry.get("status")
        if not isinstance(status, dict):
            return ""
        status_str = str(status.get("status_str") or "").casefold()
        completed = status.get("completed")
        messages = status.get("messages")
        details: list[str] = []
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, (list, tuple)) or len(message) < 2:
                    continue
                kind = str(message[0] or "")
                payload = message[1]
                if "error" not in kind.casefold():
                    continue
                if isinstance(payload, dict):
                    node = payload.get("node_id") or payload.get("node_type") or "?"
                    text = (
                        payload.get("exception_message")
                        or payload.get("message")
                        or payload.get("exception_type")
                        or kind
                    )
                    details.append(f"Node {node}: {text}")
                else:
                    details.append(f"{kind}: {payload}")
        if details:
            return "; ".join(details)
        if status_str in {"error", "failed", "failure"} or completed is False and status_str == "error":
            return "ComfyUI marked the workflow as failed"
        return ""

    def cancel_queued_prompt(self, prompt_id: str) -> bool:
        """Best-effort deletion of a queued prompt; never interrupts unrelated work."""

        if not prompt_id:
            return False
        try:
            response = self._client.post(
                f"{self.base_url}/queue",
                json={"delete": [prompt_id]},
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            return False

    def _download_output(self, item: dict[str, str]) -> Path:
        filename = item["filename"]
        params = (
            f"filename={quote(filename)}&subfolder={quote(item['subfolder'])}"
            f"&type={quote(item['type'])}"
        )

        def download() -> bytes:
            response = self._client.get(f"{self.base_url}/view?{params}")
            response.raise_for_status()
            return response.content

        content = self._safe_retry("output download", download)
        stamp = int(time.time() * 1000)
        suffix = Path(filename).suffix or ".png"
        target = self.output_dir / f"generated_{stamp}{suffix}"
        target.write_bytes(content)
        return target

    def generate(
        self,
        positive: str,
        negative: str,
        *,
        seed: int | None = None,
        reference_path: str | Path | None = None,
        profile: WorkflowProfile | None = None,
        render_plan: MediaRenderPlan | None = None,
    ) -> GeneratedMedia:
        if profile is not None:
            if not self.can_run_profile(profile):
                raise ResilientComfyUIError(
                    f"Workflow profile {profile.id!r} is not available",
                    stage="prepare",
                )
        elif not self.enabled:
            raise ResilientComfyUIError(
                "ComfyUI media generation is not configured",
                stage="prepare",
            )

        actual_seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**63 - 1)
        reference_name = None
        if reference_path is not None:
            reference_node = profile.reference_node if profile is not None else self.reference_node
            reference_input = (
                profile.reference_input_key if profile is not None else self.reference_input_key
            )
            if not reference_node or not reference_input:
                raise ResilientComfyUIError(
                    "Reference continuity is enabled but no workflow node is configured",
                    stage="prepare",
                )
            reference_name = self._upload_reference(Path(reference_path))

        applied_render_parameters: list[str] = []
        workflow = self.build_workflow(
            positive,
            negative,
            seed=actual_seed,
            reference_name=reference_name,
            profile=profile,
            render_plan=render_plan,
            render_trace=applied_render_parameters,
        )
        prompt_id = self._queue_workflow(workflow)

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            history = self._history(prompt_id)
            entry = history.get(prompt_id)
            if isinstance(entry, dict):
                execution_error = self._execution_error(entry)
                if execution_error:
                    raise ResilientComfyUIError(
                        f"ComfyUI execution failed: {execution_error}",
                        stage="execution",
                        prompt_id=prompt_id,
                    )
                output = self._first_output_file(entry)
                if output is not None:
                    path = self._download_output(output)
                    return GeneratedMedia(
                        path=path,
                        kind=path.suffix.lower().lstrip(".") or "image",
                        prompt_id=prompt_id,
                        seed=actual_seed,
                        applied_render_parameters=tuple(applied_render_parameters),
                    )
            time.sleep(self.poll_interval)

        removed = self.cancel_queued_prompt(prompt_id)
        suffix = " Queued prompt was removed." if removed else " Queue cleanup could not be confirmed."
        raise ResilientComfyUIError(
            f"Timed out waiting for ComfyUI output.{suffix}",
            stage="timeout",
            prompt_id=prompt_id,
        )
