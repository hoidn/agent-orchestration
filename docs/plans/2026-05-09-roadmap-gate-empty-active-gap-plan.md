# Roadmap Gate Empty Active Gap Handling Plan

## Objective

Fix the NeurIPS backlog roadmap gate so an empty active backlog is not treated
as completed roadmap work by default.

## Scope

- Modify `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py`.
- Modify `tests/test_neurips_backlog_roadmap_gate.py`.
- Keep the change limited to deterministic gate routing and emitted gap
  request diagnostics.

## Required Behavior

- If at least one eligible item exists, return `ELIGIBLE`.
- If current-phase items exist but none are eligible, return `BLOCKED`.
- If no current-phase item exists and `gap_policy` is `draft_backlog_item`,
  return `BACKLOG_GAP`, including when `docs/backlog/active/` is empty.
- If no current-phase item exists and `gap_policy` is `block`, return
  `BLOCKED`.
- Do not infer `DONE` from an empty active queue unless a separate explicit
  completion signal is introduced and tested.

## Implementation Tasks

1. Add tests for empty active backlog behavior:
   - empty active plus `draft_backlog_item` yields `BACKLOG_GAP`;
   - empty active plus `block` yields `BLOCKED`;
   - emitted `gap_request` contains the current gate id, required scope summary,
     allowed and disallowed phase prefixes, and counts.
2. Update the gate-status decision tree in
   `reconcile_neurips_backlog_roadmap_gate.py` to prioritize eligibility,
   current-phase blockage, and gap policy over `total_active_count == 0`.
3. Re-run existing roadmap-gate tests to ensure valid eligible items, invalid
   item handling, and current-phase blockage are unchanged.

## Verification

- `pytest tests/test_neurips_backlog_roadmap_gate.py -q`
- `python -m json.tool docs/backlog/roadmap_gate.json`

## Non-Goals

- Do not change the selector provider prompt.
- Do not change gap drafter behavior unless tests expose a missing field.
- Do not move backlog items or alter queue lifecycle rules.
- Do not make gap drafting the default for gates that declare
  `gap_policy: block`.
