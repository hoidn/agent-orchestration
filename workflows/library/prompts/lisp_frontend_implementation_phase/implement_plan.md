Implement only the approved plan for the full-design work item.

Use the consumed full design, MVP design, approved plan, check commands, and
the authoritative execution-report and progress-report target paths.
Do not report `BLOCKED` solely because a broad, default, or closeout check
fails on documented pre-existing or out-of-scope drift after the current-scope
behavior and equivalent focused checks pass. Record that as follow-up drift and
write `COMPLETED` if the approved current implementation scope is delivered.
Report the conflict as observed evidence; a failing check or legacy behavior is
not by itself a preservation requirement, so do not state one as a requirement
unless you verified its consumer is live in the current checkout. If a check
can only pass by doing something the approved plan forbids, do not make that
change; report `BLOCKED` with the conflict.
Do not spend implementation effort on manifest, conformance, parity, summary,
inventory, or status-label refresh before the current source/runtime behavior
works, unless that artifact is a direct runtime input or proves current
behavior is wrong.
If the implementation completes, write an execution report and the structured
implementation-state bundle required by the output contract. When completed,
write the execution report at the consumed canonical target path and reference
that same path from the bundle. If blocked, write the progress report at the
consumed canonical target path and record the structured blocker class in the
bundle.

Do not use `user_decision_required` for repo-local scope, contract,
verification, target-design, gap-design, or prerequisite-design issues. Those
are recoverable design problems. Reserve `user_decision_required` only for a
major unresolvable ambiguity in intention that cannot be resolved by target-design
or gap-design revision, an environment/access/credential/resource/local setup
issue requiring user intervention, or a concrete external human authority
decision that cannot be represented by revising the target design, revising the
gap architecture/plan, or selecting/drafting a prerequisite gap.
