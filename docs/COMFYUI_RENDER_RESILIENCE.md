# ComfyUI render resilience

The normal desktop runtime uses a conservative resilience layer around the local ComfyUI API.

The goal is to survive short local transport/backend interruptions without accidentally submitting the same expensive render more than once.

## Safe automatic retries

The client may retry idempotent local operations up to three times with short backoff:

- reading `/history/<prompt_id>` after a render has a known prompt id
- downloading the finished output through `/view`
- uploading a Character reference through `/upload/image`, because the existing upload uses the same local filename with `overwrite=true`

Owned HTTP connections are recreated before a retry so a restarted local ComfyUI process is contacted through a fresh socket.

## Queue POST is never replayed blindly

`POST /prompt` is intentionally not retried automatically. A connection can fail after ComfyUI accepted the render but before the response reaches the app. Replaying that request could create two large jobs while the app only knows about one.

A queue failure therefore surfaces immediately with a diagnostic explaining why it was not replayed.

## Execution failures

Once a prompt id exists, the client examines ComfyUI history status messages. Execution errors such as a failing node or local GPU out-of-memory condition are surfaced immediately with available node/message context instead of waiting for the full render timeout.

## Timeout cleanup

If a known prompt id does not finish before the configured timeout, the client makes a best-effort targeted `/queue` deletion for exactly that prompt id. It deliberately does not send a global `/interrupt`, because a shared local ComfyUI endpoint may be running unrelated work.

## Runtime scope

The normal Windows launcher (`run_windows.cmd` through `app.runtime_launcher`) injects this resilient client into the desktop app. Setup/calibration tools remain isolated and can continue to report their direct backend failures independently.

No render is sent to a cloud service. No checkpoint, model, LoRA or custom node is downloaded. No new dependency, telemetry or proprietary component is introduced.
