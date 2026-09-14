# Reference-image continuity

The local media pipeline can optionally reuse a positively rated generated image as a visual reference for the recurring companion character.

## How it works

1. Character continuity must already be enabled and the media intent must use the configured continuity key.
2. The app scans local media history for the newest positively rated file with that continuity key.
3. If the file still exists locally, it is uploaded to the configured local ComfyUI endpoint as an input image.
4. The exported API workflow receives the uploaded image name in a user-configured node/input pair.
5. The rest of the workflow remains fully user-owned. It can route that image through IP-Adapter, ControlNet, reference-only conditioning, face/identity nodes, or another local consistency method.

The application does not assume a specific ComfyUI custom node or model family. This keeps reference continuity compatible with different local workflows.

## Configuration

In Settings, enable **Referenzbild-Continuity** and configure:

- **Referenzbild-Node**: the node id in the exported API workflow that receives the uploaded image name.
- **Referenzbild-Input**: the input field on that node, commonly `image` for a LoadImage-style node.

Run **Lokale Verbindungen testen** after changing the workflow. Diagnostics verify that the configured node and input exist before generation is attempted.

## Privacy and failure behavior

Reference files are selected from the local media history and are sent only to the configured ComfyUI endpoint. The reference image is not committed to Git.

Only positively rated media are eligible. If no liked file exists, or the previously liked file was deleted, generation continues without a reference image. If ComfyUI rejects an upload or the configured reference node is invalid, that media generation is skipped rather than taking down the chat.
