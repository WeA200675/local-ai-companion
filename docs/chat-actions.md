# Chat message actions

The desktop chat supports two local response actions in addition to streaming and Stop.

## Neu generieren

`Neu generieren` removes only the latest persisted assistant reply and sends the preceding user message through the current persona, memory context, and chat tuning again. The user message is never deleted by this action.

The replacement reply is streamed normally and becomes the new persisted assistant reply. Media generation, adaptive-memory analysis, and persona feedback are only started after the replacement reply finishes successfully.

## Fortsetzen

When a streamed reply is stopped or interrupted after text has already arrived, the partial assistant reply is kept locally and `Fortsetzen` becomes available for the current app session.

Continuation uses the partial reply as context and asks the local model to continue without repeating it. Once the continuation completes, the persisted history is collapsed back into one assistant message so a later app restart sees a normal user/assistant exchange rather than a synthetic continuation instruction.

If a continuation is stopped again, its new partial text is joined to the existing partial reply and can be continued again.

## Safety of local state

Incomplete replies do not trigger media generation, adaptive-memory extraction, or persona feedback learning. Regeneration and continuation are disabled while a conflicting local background job is still active.
