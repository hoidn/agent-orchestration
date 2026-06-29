Draft an execution-ready plan for the selected target-design work item.

Use the consumed target design, baseline design, work-item context, and
progress ledger. The plan must be self-contained enough that implementation can
execute from the approved plan without rediscovering scope.

If the plan changes code used by other tasks too, include at least one check
that is not just the selected case.

If the selected gap involves broken behavior, use systematic debugging first:
identify the earliest causal failure and minimal reproducer before drafting the
plan.

Write the plan to the relpath recorded in `plan_path.txt`.
