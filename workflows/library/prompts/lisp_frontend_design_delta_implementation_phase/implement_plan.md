Implement only the approved plan for the target-design work item.
Use `superpowers:executing-plans` to execute the approved plan task by task.

Use the consumed target design, baseline design, approved plan, check commands,
and the authoritative execution-report and progress-report target paths.
If the implementation completes, write an execution report and the structured
implementation-state bundle required by the output contract. When completed,
write the execution report at the consumed canonical target path and reference
that same path from the bundle. If blocked, write the progress report at the
consumed canonical target path and record the structured blocker class in the
bundle.
