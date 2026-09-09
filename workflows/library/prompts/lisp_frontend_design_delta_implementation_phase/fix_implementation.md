Fix the Lisp frontend implementation according to the review findings while
preserving the approved target-design plan scope and baseline-design
constraints.

Read `request.subject`: its target design, baseline design, plan at `plan_path`,
execution report, checks report, and findings at `findings_items_path`. Follow
the plan's gap-architecture reference before editing. Fix the
review findings in a way that preserves the target and gap architecture intent.
Use generated artifacts only when they are consumed inputs or required output
targets for this task.

Do not satisfy a finding by fabricating records or hard-coding generated values
in authored source; use the approved binding surface. Report a blocker only
when that surface is absent, contradictory, or would require changing the
approved contract.

Update the execution report at `request.targets.execution_report_target_path` when possible,
or keep the currently published execution-report path valid if the target was
not used in the original implementation pass. Leave the check commands runnable.
Rerun relevant checks and update the checks report at
`request.subject.checks_report`. Return `execution_report` and `checks_report`
as the actual report paths in the runtime-bound output-contract bundle.
