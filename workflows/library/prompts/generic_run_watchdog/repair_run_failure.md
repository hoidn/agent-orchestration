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
   - decline recovery only when concrete evidence shows recovery is unsafe.

Do not invent workflow-specific assumptions. Prefer resume over fresh relaunch when the persisted state is usable.
A one-run workspace patch is not a fix when the same generated workflow surface
would recreate the failure. Before reporting success, repair the durable generator
and verify a regenerated surface; report `BLOCKED` only with concrete evidence.

Do not report `FIXED_AND_RESUMED` just because the run state says `running`.
After resume, re-read the target `state.json` and verify that the resumed pid is
alive, the heartbeat advanced, no top-level step is failed, and no
`call_frames[*].state.steps` entry is failed. If any check fails, report
`BLOCKED`; keep the actual recovery action taken, such as `RESUME`.

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
