# Reference-Family Completion Inventory Realignment Plan

## Goal

Close the selected completed-gap inventory mismatch without weakening the
reference-family gate.

## Steps

1. Confirm the selected production architecture file exists under
   `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/`.
2. Confirm the production architecture index names the selected gap or file.
3. Ensure the conformance helper treats missing architecture-index coverage as
   a failing `completion_inventory` condition.
4. Run the focused conformance/build checks that exercise that condition.

## Acceptance

The selected gap is complete when the selected production architecture and
index coverage are present, missing-index coverage fails closed, and focused
tests pass. Remaining broad historical inventory drift is follow-up closeout,
not a reason to keep this selected gap open.
