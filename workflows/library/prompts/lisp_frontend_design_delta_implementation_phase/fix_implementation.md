Fix the Lisp frontend implementation according to the review findings while
preserving the approved target-design plan scope and baseline-design
constraints.

Read the consumed target design, gap architecture, execution plan, execution
report, checks report, and implementation review report before editing. Fix the
review findings in a way that preserves the target and gap architecture intent.
Use generated artifacts only when they are consumed inputs or required output
targets for this task.

Do not satisfy hidden/system-owned context, generated path, checkpoint, or
boundary findings by fabricating context records or hard-coded generated paths
in authored source. First look for the approved binding surface and use it when
available. Report a blocker only when that surface is absent, contradictory, or
would require changing the approved contract.

Update the execution report at the consumed canonical target path when possible,
or keep the currently published execution-report path valid if the target was
not used in the original implementation pass. Leave the check commands runnable.
