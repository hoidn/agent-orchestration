Implement only the approved plan for the full-design work item.

Use the consumed full design, MVP design, approved plan, check commands, and
the authoritative execution-report and progress-report target paths.
If the implementation completes, write an execution report and the structured
implementation-state bundle required by the output contract. When completed,
write the execution report at the consumed canonical target path and reference
that same path from the bundle. If blocked, write the progress report at the
consumed canonical target path and record the structured blocker class in the
bundle.

Do not use `user_decision_required` for repo-local scope, contract,
verification, target-design, gap-design, or prerequisite-design issues. Those
are recoverable design problems. Reserve `user_decision_required` for a concrete
external human authority decision that cannot be represented by revising the
target design, revising the gap architecture/plan, or selecting/drafting a
prerequisite gap.
