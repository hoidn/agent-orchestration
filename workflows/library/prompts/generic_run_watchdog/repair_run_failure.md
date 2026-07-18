# Repair Orchestrator Run Failure

You are repairing a failed, crashed, stalled, or unknown orchestrator workflow run.

Authoritative inputs:

- The injected watch bundle records the evidence paths, target run id, and the repair result target path.

Before acting, diagnose and repair the target run's durable workflow mechanics on your own, without waiting for repeated prompting. Apply only fixes that are
needed to recover the target run or its durable workflow mechanics. If a
provider prompt needs a broader policy change, record that as the repair
blocker instead of changing unrelated prompt behavior.

Work carefully:

1. Read the watch bundle and the referenced run-failure bundle.
2. Identify the root cause from the target run's state, logs, or changed files.
3. Classify the issue as `TRIVIAL` or `NONTRIVIAL`.
4. If the fix is nontrivial, write an implementation plan under `docs/plans/` before changing behavior.
5. Implement the minimal principled fix or execute the plan.
6. Run relevant verification commands for the changed files.
7. As one of the final actions, either:
   - resume the target run with `python -m orchestrator resume <target_run_id>`;
   - relaunch or restart using the run's recorded command or the workflow's
     recovery policy;
   - decline recovery only when the target run cannot be recovered safely.

Do not invent workflow-specific assumptions. Prefer resume over fresh relaunch when the persisted state is usable.
A one-run workspace patch is not a fix when the same generated workflow surface
would recreate the failure. Before reporting success, repair the durable
generator when that is the root cause and run the narrow check that exercises
the repaired surface. Report `BLOCKED` only with the specific failed condition.

Do not report `FIXED_AND_RESUMED` just because the run state says `running`.
After resume, re-read the target `state.json` and verify that the resumed pid is
alive, the heartbeat advanced, no top-level step is failed, and no
`call_frames[*].state.steps` entry is failed. If any check fails, report
`BLOCKED`; keep the actual recovery action taken, such as `RESUME`.

Return a native typed `ProviderRepairResult` record with these fields:

- `repair_status`: `FIXED_AND_RESUMED`, `FIXED_AND_RELAUNCHED`, `PLAN_WRITTEN`, or `BLOCKED`;
- `fix_complexity`: `TRIVIAL` or `NONTRIVIAL`;
- `recovery_action`: `RESUME`, `RELAUNCH`, `RESTART`, or `DECLINED`;
- `repair_report_path`: the produced repair report relpath under `artifacts/work`;
- `plan_path`: the optional plan relpath, or an empty string; and
- `new_run_id`: the replacement run id, or an empty string.

Also retain the operator-facing compatibility contract: write the repair report
and write the repair-result JSON to the exact `repair_result_target_path`
recorded in the injected authoritative watch bundle, with this shape:

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
`PLAN_WRITTEN` pairs with `recovery_action: DECLINED`, since writing a plan does not resume or relaunch the run within this iteration.
