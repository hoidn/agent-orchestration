You are classifying a blocked implementation attempt.

Read the target design, baseline design, implementation architecture or work
item context if present, approved plan if present, implementation state, and
progress report.

Choose `GAP_DESIGN_REVISION_REQUIRED` when the target design is coherent but the
selected gap's implementation architecture, decomposition, dependencies, or
approved implementation slice no longer matches what the attempt proved: it may
be missing needed scope, or it may require a route, mechanism, or behavior that
is stale, absent from the current checkout, or in conflict with the target
design. Name the causal gap assumption in `summary` and say whether it is
missing scope or a stale requirement.

Choose `TARGET_DESIGN_REVISION_REQUIRED` only when the blocker shows that the
durable target design itself is under-specified, internally inconsistent, or
missing a contract needed to implement the selected design gap.

Choose `PREREQUISITE_GAP_REQUIRED` when the blocker shows that this selected
gap cannot be implemented until another bounded prerequisite gap is completed,
whether that prerequisite already exists or must first be drafted.

Choose `TERMINAL_BLOCKED` / `user_decision_required` only when the blocker
falls into one of these terminal categories: a major unresolvable ambiguity in
intention that cannot be resolved by target-design or gap-design revision; an
environment, access, credential, resource, or local setup failure that requires
user intervention; or true external authority outside repo-local workflow,
design, code, prompt, or contract repair.

Do not choose `TERMINAL_BLOCKED` merely because the approved slice exposed
repo-local work outside the current implementation plan, failed adjacent tests,
or needs scope clarification. Use `GAP_DESIGN_REVISION_REQUIRED` when the gap
architecture/plan is missing needed scope or carries a stale requirement,
`TARGET_DESIGN_REVISION_REQUIRED` when the
target design needs to authorize or sequence the work, and
`PREREQUISITE_GAP_REQUIRED` when another bounded prerequisite gap should be
completed first, including when that prerequisite must be drafted before it can
be selected.

Write one JSON bundle at the required output path:

```json
{
  "blocked_recovery_route": "GAP_DESIGN_REVISION_REQUIRED | TARGET_DESIGN_REVISION_REQUIRED | PREREQUISITE_GAP_REQUIRED | TERMINAL_BLOCKED",
  "reason": "implementation_architecture_under_scoped | target_design_contract_gap | prerequisite_gap_required | true_external_dependency | user_decision_required | unsupported_blocker",
  "summary": "",
  "waiting_on_work_id": "<existing prerequisite id when known, else omit>",
  "waiting_on_work_source": "DESIGN_GAP | BACKLOG_ITEM (required only with waiting_on_work_id)",
  "proposed_prerequisite": {
    "id": "<stable proposed gap id when drafting is required>",
    "title": "",
    "scope": "",
    "reason": ""
  }
}
```

For `PREREQUISITE_GAP_REQUIRED`, include either `waiting_on_work_id` /
`waiting_on_work_source` for an existing prerequisite or `proposed_prerequisite`
for a prerequisite gap that must be drafted. If neither can be identified, use
`TERMINAL_BLOCKED` with reason: unsupported_blocker.
