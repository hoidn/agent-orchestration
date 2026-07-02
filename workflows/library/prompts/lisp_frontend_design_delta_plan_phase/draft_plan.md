Draft an execution-ready plan for the selected target-design work item.

Use the consumed target design, baseline design, gap architecture, and
work-item context. The plan must be self-contained enough that implementation
can execute from the approved plan without rediscovering scope.

If the plan changes shared behavior, keep the fix generic rather than
selected-case-specific.

When planning a fix for observed broken behavior, identify the causal failure
before choosing implementation steps.

Put source or runtime behavior repair before evidence refresh. Do not plan
manifest, conformance, parity, summary, inventory, or status-label work as a
blocking implementation task unless that artifact is a direct runtime input or
proves the current behavior is wrong.

Write the plan to the relpath recorded in `plan_path.txt`.
