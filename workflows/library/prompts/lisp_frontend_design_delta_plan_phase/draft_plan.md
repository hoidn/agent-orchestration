Draft an execution-ready plan for the selected target-design work item.

Use the consumed target design, baseline design, work-item context, and
progress ledger. The plan must be self-contained enough that implementation can
execute from the approved plan without rediscovering scope.

If the plan changes a file that is used outside the selected gap's files,
include a check for one of those outside uses.

If the selected gap involves broken behavior, use systematic debugging first:
identify the earliest causal failure and minimal reproducer before drafting the
plan.
Put source or runtime behavior repair before evidence refresh. Do not plan
manifest, conformance, parity, summary, inventory, or status-label work as a
blocking implementation task unless that artifact is a direct runtime input or
proves the current behavior is wrong.
If a broad/default check is useful but known to fail on unrelated existing
drift, make its pass criterion explicit and keep current-scope proof on focused
checks. Do not make unrelated drift a blocking implementation gate.

Write the plan to the relpath recorded in `plan_path.txt`.
