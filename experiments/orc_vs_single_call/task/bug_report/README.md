# Bug: a loop result with a path field is rejected from target 2.29

`reviewed_change.orc` compiles at `(:target-dsl "2.28")`. At `"2.29"` and later
(this copy declares `"2.32"`) the same source is rejected. From this directory:

    PYTHONPATH="$(git rev-parse --show-toplevel)" python -m orchestrator run reviewed_change.orc \
      --entry-workflow reviewed_change::reviewed-change \
      --provider-externs-file providers.json --input-file inputs.json --dry-run

    [workflow_boundary_type_invalid] Step 'reviewed_change::reviewed-change__loop':
    repeat_until.on_exhausted.outputs.result__report may only override scalar repeat_until outputs

Expected: at targets 2.29 through 2.32 the program compiles and behaves as it
does at 2.28, on every path through the loop, including exhaustion.
