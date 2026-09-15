# Session Moments & Twist Deck

This feature adds two local, conversation-scoped ways to create more continuity and more variation without modifying the learned persona, Core Memory, adaptive memory, or stable Character identity.

## Session Moments

A Session Moment is deliberately saved by the user from the latest complete user/assistant exchange. Each moment stores:

- a user-chosen title
- an optional re-entry note
- a compact excerpt of the user message
- a compact excerpt of the companion reply
- creation time and source conversation

A moment can be activated as temporary re-entry context. This is useful when returning to a favorite atmosphere, composition, conversational beat, or unfinished direction. The current user message always overrides the saved cue.

Session Moments are not Core Memory and are not automatically promoted into long-term memory. They remain visible, removable, and scoped to the conversation where they were captured.

## Twist Deck

Twists are one-shot creative suggestions for the next completed response. Built-in cards cover small changes such as:

- lighting shifts
- camera reframing
- a new prop or material detail
- movement within the established setting
- weather or exterior ambience
- a temporary dialogue-rhythm change
- a reflection or silhouette clue
- a compact optional choice

The active Twist also reaches local media planning through temporary style tags and prompt context. After the response that used it has completed, the Twist is automatically consumed.

## Optional automatic Twists

Automatic Twists are disabled by default and configured per conversation. The user can choose a minimum interval from 2 to 20 completed assistant responses. When the interval is reached, the app prepares a Twist for a later response. Recently used cards are avoided when possible.

The automation never changes persona traits, memories, Character identity, model weights, or creative locks. A current user request always takes priority over a Twist.

## Transparency

The Context Inspector exposes:

- the active Session Moment and its temporary re-entry context
- the Twist prepared for the next response
- whether automatic Twists are enabled
- the configured Twist interval
- the effective prompt text and style tags that include these temporary layers

## Privacy and open-source boundary

Session Moments and Twists are stored in the existing local application state. They add no network service, telemetry, dependency, proprietary SDK, or cloud requirement. The repository's open-source-only CI audit remains authoritative.
