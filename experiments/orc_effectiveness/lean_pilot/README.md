# Lean Pilot: Frozen Inputs

The July 2026 lean-pilot apparatus was removed on 2026-10-14, on branch
`feat/compare-harness`, in the commit that adds this notice. Its ORC
treatment, `workflows/experiments/repository_task_pilot/task_loop.orc`, is
target 2.20, which the compiler refuses with
`workflow_execution_target_retired`. Removed with it: `orchestrator/experiments/`,
`scripts/experiments/lean_pilot.py`,
`scripts/experiments/conventional_coordinator.py`,
`workflows/experiments/repository_task_pilot/`,
`tests/experiments/test_lean_pilot_*.py` and
`tests/experiments/fixtures/lean_pilot/`. The decision is D1 of the
[comparison harness design](../../../docs/design/orc_effectiveness_comparison_harness.md).

The code is recoverable from git history at the parent of that commit:

```bash
git log --diff-filter=A --format=%H -- experiments/orc_effectiveness/lean_pilot/README.md
git show <that-commit>^:orchestrator/experiments/contracts.py
```

## Evidence

- Deterministic report:
  [`docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md`](../../../docs/reports/2026-07-26-orc-effectiveness-lean-pilot.md)
- Forensics report:
  [`docs/reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md`](../../../docs/reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md)
- Owner-decision record:
  [`docs/reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md`](../../../docs/reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md)
- Run evidence outside the repository:
  `/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/`
- Frozen inputs in this directory: `pilot-lock.json`,
  `apparatus-source-map.json`, `calibration/`, `control/`, `evaluation/`,
  `reviewers/`, `tasks/` and `treatments/`. They are kept unchanged; paths in
  them that name removed files refer to the tree before the removal.
