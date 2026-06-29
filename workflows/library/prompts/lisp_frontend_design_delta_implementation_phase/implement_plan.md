Implement only the approved plan for the target-design work item.
Use `superpowers:executing-plans` to execute the approved plan task by task.

Use the consumed target design, baseline design, approved plan, check commands,
and the authoritative execution-report and progress-report target paths.
Stop and report `BLOCKED` if the approved plan asks for a change that only
works for the selected case while changing code used by other tasks.
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
