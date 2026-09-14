# Conversations and Variety

Two layers add replayability without contaminating learned personality or long-term memory.

## Separate conversations

The app keeps one shared companion identity, Core Memory, adaptive memory, Character Studio profile, and learned persona. Chat transcripts are separated into conversation threads.

A conversation can be created, renamed, archived, restored, or forked. Forking copies the current transcript into a new thread and then lets both branches diverge independently. This is useful when the user wants to try two different directions from the same point without deleting either history.

The old single-chat `chat_messages` table is treated as legacy data. On first use of the conversation layer, its rows are copied into the initial `Hauptchat` conversation non-destructively. The legacy rows are not deleted during migration.

Conversation switching is blocked while a local text, media, learning, or memory worker is running so an in-flight result cannot accidentally land in another thread.

## Variety deck

The Variety Deck is a temporary creative overlay. It does not modify persona traits, Core Memory, adaptive memory, preference learning, or model weights.

Each card contains:

- a visible name and category;
- a short temporary instruction;
- optional style tags used by chat and local media planning;
- an enabled state.

Built-in cards vary pacing, dialogue density, atmosphere, visual framing, initiative, mystery, and conversational rhythm. Users can add their own local cards.

The active card is stored per conversation. Drawing a new card avoids recently used cards when enough alternatives exist. A card can be cleared at any time to return to the base context.

The Context Inspector displays the active conversation and variety card, so the temporary influence is never hidden.

## Privacy and open-source boundary

All conversation and variety state is stored inside the existing local SQLite database. It is covered by local backup/restore and the privacy-lock boundary. The feature adds no network calls and no new dependency, proprietary or otherwise.
