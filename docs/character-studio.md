# Character Studio

The Character Studio keeps long-term visual identity under explicit user control while the companion remains free to choose scene, mood, styling, and a suitable local media workflow.

Each continuity key has its own persistent character profile containing a stable seed, an editable appearance description, an appearance revision counter, generation/feedback counts, and an optional pinned reference image.

## Visual identity

The **Visuelle Identität** field is appended to later local image prompts whenever that continuity key is used. It is intended for stable, non-scene-specific traits such as face, hair, body proportions, recurring accessories, and general identity cues. The app does not automatically rewrite this field from chat or learning feedback; edits remain user-controlled.

All media planning still treats depicted people as clearly adult and keeps automatic visual generation in the app's non-graphic adult/suggestive lane.

## Seed

**Neuen Seed erzeugen** rotates the persistent generation seed while keeping the appearance description and pinned reference intact. This is useful when a character has drifted into an undesirable base composition, but it can visibly change future generations, so the UI asks for confirmation first.

## Reference images

Pinned references are still managed from the Media tab. The Character Studio displays the current reference id/path and whether the local file still exists. When reference-image continuity is enabled, that pinned image remains the highest-priority identity reference.

## Multiple characters

The Continuity-Key field can load any local character profile. Changing the main Continuity-Key in Settings also switches the Character Studio to that profile. All profile data is stored only in the local SQLite state and is included in the existing local backup/restore flow.
