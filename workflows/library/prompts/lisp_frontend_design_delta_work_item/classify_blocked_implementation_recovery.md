You are classifying a blocked implementation attempt.

Read the target design, baseline design, implementation architecture or work
item context if present, approved plan if present, implementation state, and
progress report.

Choose `GAP_DESIGN_REVISION_REQUIRED` when the target design is coherent but the
selected gap's implementation architecture, decomposition, dependencies, or
approved implementation slice is under-scoped.

Choose `TARGET_DESIGN_REVISION_REQUIRED` only when the blocker shows that the
durable target design itself is under-specified, internally inconsistent, or
missing a contract needed to implement the selected design gap.

Choose `PREREQUISITE_GAP_REQUIRED` when the blocker shows that a different
missing prerequisite capability or design gap must be completed before this
selected gap can be implemented.

Choose `TERMINAL_BLOCKED` / `user_decision_required` only when the evidence
shows one of these terminal categories: a major unresolvable ambiguity in
intention that cannot be resolved by target-design or gap-design revision; an
environment, access, credential, resource, or local setup failure that requires
user intervention; or true external authority outside repo-local workflow,
design, code, prompt, or contract repair.

Do not choose `TERMINAL_BLOCKED` merely because the approved slice exposed
repo-local work outside the current implementation plan, failed adjacent tests,
or needs scope clarification. Use `GAP_DESIGN_REVISION_REQUIRED` when the gap
architecture/plan is under-scoped, `TARGET_DESIGN_REVISION_REQUIRED` when the
target design needs to authorize or sequence the work, and
`PREREQUISITE_GAP_REQUIRED` when another bounded prerequisite gap should be
selected or drafted first.

Treat this classification as a proposed recovery route. Do not choose
`PREREQUISITE_GAP_REQUIRED`, `TARGET_DESIGN_REVISION_REQUIRED`, or
`GAP_DESIGN_REVISION_REQUIRED` for stale evidence, duplicate bookkeeping, or a
selected unit whose scope should be replaced from the higher-level contract.

Write one JSON bundle at the required output path:

```json
{
  "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | PREREQUISITE_GAP_REQUIRED | TERMINAL_BLOCKED",
  "reason": "implementation_architecture_under_scoped | target_design_contract_gap | prerequisite_gap_required | true_external_dependency | user_decision_required | unsupported_blocker",
  "summary": ""
}
```

When `blocked_recovery_route` is `PREREQUISITE_GAP_REQUIRED`, include only
`waiting_on_work_id` and `waiting_on_work_source` for the prerequisite work that
must complete before retrying the blocked item. If no safe prerequisite can be
identified, use `TERMINAL_BLOCKED` with `reason: unsupported_blocker`.

```json
{
  "waiting_on_work_id": "<prerequisite-gap-or-item-id>",
  "waiting_on_work_source": "DESIGN_GAP | BACKLOG_ITEM"
}
```
