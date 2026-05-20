---
priority: 0
plan_path: docs/plans/NEURIPS-HYBRID-RESNET-2026/backlog/2026-05-09-roadmap-gate-empty-active-gap/execution_plan.md
check_commands:
  - pytest tests/test_neurips_backlog_roadmap_gate.py -q
  - python -m json.tool docs/backlog/roadmap_gate.json
prerequisites: []
related_roadmap_phases:
  - phase-1-dsl-v214-runtime
signals_for_selection:
  - Roadmap-driven backlog drains should not report DONE merely because active backlog is empty.
  - Fixes gap-drafter reachability for roadmap gates that intentionally allow autonomous item drafting.
blocking_signals:
  - Do not change queue movement semantics outside the roadmap gate reconciliation script and tests.
  - Do not make gap drafting default for gates that explicitly use gap_policy=block.
---

# Backlog Item: Roadmap Gate Empty Active Gap Handling

## Objective

- Fix the NeurIPS backlog roadmap gate so an empty `docs/backlog/active/`
  directory can produce `BACKLOG_GAP` when the gate policy allows gap drafting,
  instead of always reporting `DONE`.

## Problem

The current roadmap gate is queue-centric: when the active backlog directory is
empty, `reconcile_neurips_backlog_roadmap_gate.py` returns `DONE`. That is wrong
for roadmap-driven drains where the roadmap and gate may imply that a backlog
item is missing. In that mode, an empty active queue should be treated as a gap
or block depending on `gap_policy`, not as proof that roadmap scope is complete.

## Scope

- Update `workflows/library/scripts/reconcile_neurips_backlog_roadmap_gate.py`
  so gate routing is based on eligible/current-phase/gap policy rather than
  treating `total_active_count == 0` as terminal by itself.
- Add or update tests in `tests/test_neurips_backlog_roadmap_gate.py` for:
  - empty active backlog plus `gap_policy: draft_backlog_item` returns
    `BACKLOG_GAP` and emits a useful `gap_request`;
  - empty active backlog plus `gap_policy: block` returns `BLOCKED`;
  - existing eligible item behavior remains unchanged;
  - invalid current-phase item behavior remains unchanged.
- Preserve the existing `DONE` behavior only for an explicit roadmap/progress
  completion signal if such a signal already exists; otherwise do not infer
  done from an empty queue.

## Non-Goals

- Do not change the gap drafter prompt or validator unless the new gap request
  shape exposes a concrete missing field.
- Do not change selector provider behavior.
- Do not move backlog items between queue directories.
- Do not make `draft_backlog_item` the default for existing gates.

## Required Evidence

- `pytest tests/test_neurips_backlog_roadmap_gate.py -q` passes.
- A deterministic fixture or test proves empty-active plus `draft_backlog_item`
  reaches `BACKLOG_GAP`.
- A deterministic fixture or test proves empty-active plus `block` reaches
  `BLOCKED`.
- `python -m json.tool docs/backlog/roadmap_gate.json` passes.

## Notes

- This is a workflow-routing correctness fix. It should be small and should not
  be bundled with the broader v2.14 runtime semantics implementation.
