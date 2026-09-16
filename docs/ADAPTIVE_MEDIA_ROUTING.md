# Adaptive local media routing

The media service now treats a workflow catalog as a local capability graph,
not as a boolean “runnable” switch.

Each `WorkflowProfile` can declare:

- explicit checkpoint suitability for portrait, full-body, detail, and environment;
- image/GIF/video kinds, quality ladder, motion frame/FPS ceilings;
- optional minimum/preferred VRAM and reference-image mapping;
- local quarantine threshold and the existing explicit checkpoint-license flag.

`WorkflowRouter` scores every technically valid candidate using technical
readiness, checkpoint suitability, requested focus, character continuity and
reference support, hardware/VRAM budget, explicit feedback, local health, and a
workflow-plus-framing anti-repetition penalty. It returns the full ordered
fallback chain and a human-readable explanation.

`WorkflowHealthRepository` stores only local success/failure counters in the
existing SQLite app-state store. Repeated confirmed failures quarantine a
profile. A successful explicit workflow probe clears quarantine automatically;
ambiguous queue, history, output-download, and timeout failures are not counted
as confirmed workflow failures and are never automatically re-queued.

Generation walks each candidate's `draft → balanced → high` ladder downward from
the requested quality. Confirmed VRAM/render failures may retry the same profile
at the next lower quality, then continue through the prioritized profile chain.
Every attempt, downgrade, selected fallback, hardware rationale, and routing
explanation is persisted with the local media-history event.

The media-kind selector keeps image, GIF, and video routes separate, respects
validated local capabilities and motion budgets, and prefers a still image on a
CPU/low-VRAM budget unless the user explicitly requests motion. No checkpoint is
downloaded, and no license is inferred from a filename.
