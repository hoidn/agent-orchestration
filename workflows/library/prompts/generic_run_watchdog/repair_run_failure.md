# Repair Orchestrator Run Failure

You are repairing a failed, crashed, stalled, or unknown orchestrator workflow run.

Authoritative inputs:

- Watch bundle: `${inputs.state_root}/watch.json`
- Evidence bundle path is recorded inside that watch bundle.
- Repair result target: `${inputs.repair_result_target_path}`
- Target run id is recorded inside the watch bundle.

Work carefully:

1. Read the watch bundle and evidence bundle.
2. Identify the root cause from concrete evidence.
3. Classify the issue as `TRIVIAL` or `NONTRIVIAL`.
4. If the fix is nontrivial, write an implementation plan under `docs/plans/` before changing behavior.
5. Implement the minimal principled fix or execute the plan.
6. Run relevant verification commands for the changed files.
7. As one of the final actions, either:
   - resume the target run with `python -m orchestrator resume <target_run_id>`;
   - relaunch or restart using a command justified by the evidence or policy;
   - decline recovery and explain why it is unsafe.

Do not invent workflow-specific assumptions. Prefer resume over fresh relaunch when the persisted state is usable.

Write `${inputs.repair_result_target_path}` as JSON with this shape:

```json
{
  "repair_status": "FIXED_AND_RESUMED | FIXED_AND_RELAUNCHED | PLAN_WRITTEN | BLOCKED",
  "fix_complexity": "TRIVIAL | NONTRIVIAL",
  "recovery_action": "RESUME | RELAUNCH | RESTART | DECLINED",
  "repair_report_path": "artifacts/work/generic-run-watchdog/repair-report.md",
  "plan_path": "docs/plans/optional-plan.md",
  "new_run_id": ""
}
```

If no plan was needed, set `plan_path` to an empty string. If no new run was launched, set `new_run_id` to an empty string.
