use receiving-code-review to address the feedback

Apply the consumed review to `docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md`.
Read the review from the injected `review` artifact content, edit the ADR in place, and leave it ready for another review pass.

Do not ask the prompt to provide or rewrite a provider session id. The orchestrator binds the session handle at runtime and does not inject it into prompt text.
