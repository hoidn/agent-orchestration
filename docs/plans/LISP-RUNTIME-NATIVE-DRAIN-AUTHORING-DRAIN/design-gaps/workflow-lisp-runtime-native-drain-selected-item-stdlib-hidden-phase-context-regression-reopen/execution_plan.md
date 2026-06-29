# Selected-Item Stdlib Hidden Phase Context Regression Reopen Plan

## Goal

Restore the selected-item stdlib route as a consumer of the canonical
mixed-caller hidden-context contract.

## Steps

1. Reproduce the selected-item `phase-ctx__work-item` admission failure.
2. Ensure `run-work-item` exposes the shared callee hidden requirement.
3. Ensure the `ItemCtx + typed payload` caller mode admits
   `run-selected-item-stdlib`.
4. Repair diagnostic ordering for invalid roots if needed.
5. Run focused compile, smoke, and boundary/build checks for the selected-item
   route.

## Acceptance

`run-selected-item-stdlib` can call `run-work-item` without authored
`phase-ctx`; private binding metadata is emitted; invalid roots fail closed; and
unrelated parent-drain failures remain contextual follow-up, not blockers for
this regression slice.
