# Selector Stdlib Call Contract Regression Reopen

## Goal

Repair `select-next-work-stdlib` so it calls `select-next-work` with one
`:ctx ctx` argument and then projects the typed selector result for
`std/drain`.

## Steps

1. Confirm the stale flattened selector call is the failing source path.
2. Replace the flattened `:steering`, `:target_design`, `:baseline_design`,
   `:manifest`, `:progress_ledger`, and `:run_state` call with
   `(call select-next-work :ctx ctx)`.
3. Run the focused selector adapter compile/typecheck check.
4. Run the Design Delta parent compile only as a targeted regression check if
   the selector adapter path is otherwise green.

## Boundaries

Do not update command-boundary manifests, inventories, parity outputs,
conformance summaries, completed-gap summaries, closeout artifacts, bridge
publication validation, or broad build artifacts. Do not add command glue,
report parsing, pointer reads, public path carriers, or compatibility-bundle
rereads.
