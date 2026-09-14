# Session Modes

Session Modes are temporary persona overlays for a single style of interaction. They let the app feel different for a while without rewriting the learned base personality.

A mode can add or subtract up to 0.50 from the active values of dominance, strictness, teasing, initiative, persistence, creativity, and autonomy. The effective value is still clamped to the user's configured trait bounds. Traits that are locked in Persona Lab are not overridden by a Session Mode.

Modes can also add temporary style tags. Those tags are passed to the chat prompt and local media planner only while the mode is active.

## Non-destructive behavior

The overlay is applied to an in-memory copy of the base PersonaState at prompt time. The stored persona, learning revision, trait bounds, learning rates, snapshots, and feedback-learning target stay unchanged. Positive/negative response feedback continues to train the base persona rather than baking the temporary mode into long-term learning.

## Included starting modes

On first use the app creates three local examples: **Streng & fokussiert**, **Verspielt & neckisch**, and **Kreativ & atmosphärisch**. They are ordinary editable records, not hard-coded behavior rules. You can modify them, delete them, or create new modes.

**Basis verwenden** immediately disables the overlay and returns the chat to the learned persona.

## Persistence and backup

Mode definitions plus the currently active mode are stored in the existing local SQLite app-state table. They are therefore covered by the app's local backup/restore system and never require a cloud service.
