# Reference-image continuity

The local media pipeline can optionally reuse a generated image as a visual reference for the recurring companion character.

## Reference priority

The app uses a simple priority order:

1. If you explicitly pin an image in **Medien** with **Als Charakter-Referenz**, that image becomes the stable anchor for its continuity key.
2. If no usable anchor is pinned, the newest positively rated image for the same continuity key is used automatically.
3. If neither exists locally, generation continues without a reference image.

Only still-existing image files such as PNG, JPEG, WebP, or BMP are eligible. GIF/video history entries are never sent as identity reference images.

## How it works

Character continuity must be enabled and the media intent must use the configured continuity key. The selected local reference file is uploaded to the configured local ComfyUI endpoint as an input image. The exported API workflow receives the uploaded image name in a user-configured node/input pair.

The rest of the workflow remains fully user-owned. It can route that image through IP-Adapter, ControlNet, reference-only conditioning, face/identity nodes, or another local consistency method. The application does not assume a specific custom node or model family.

## Configuration

In Settings, enable **Referenzbild-Continuity** and configure **Referenzbild-Node** plus **Referenzbild-Input**. The input is commonly `image` for a LoadImage-style node.

Run **Lokale Verbindungen testen** after changing the workflow. Diagnostics verify that the configured node and input exist before generation is attempted.

In the **Medien** tab, select a generated image with a continuity key and use **Als Charakter-Referenz** to pin it. The pinned entry gets a 📌 marker. **Referenz lösen** removes the explicit anchor and returns the character to automatic liked-image fallback.

## Privacy and failure behavior

Reference files come from local media history and are sent only to the configured ComfyUI endpoint. They are never committed to Git by the application.

If a pinned file is later deleted, the pipeline falls back to the newest usable positively rated image. If ComfyUI rejects an upload or the configured reference node is invalid, that media generation is skipped rather than taking down the chat.
