# Evaluated execution spike — historical source

This directory preserves the throwaway prototype used for the September 2026
[design decision](../../docs/reports/2026-09-29-evaluated-execution-spike.md).
Its frontend intercepted the flat compiler, which the selected
[executor retirement](../../docs/design/workflow_lisp_executor_retirement.md)
removes. The prototype and its old-target specimens are read-only history;
use a checkout of `23eb9c97` with its recorded environment to investigate the
original experiment. Its previous results remain historical evidence.

Current compilation and execution live in `orchestrator/workflow_lisp/closed/`
and `orchestrator/workflow/evaluated/`. Follow the
[drafting guide](../../docs/lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate)
for public usage. Current evaluator tests own compilation, input identity,
replay and recovery; the prototype is not an additional execution route.

Since 2026-11-12, `trial.py` and `closed_effects.py` import `orchestrator.workflow.trial`, which is removed; the git tag `archive/dead-executors-2026-11-11` holds it.

Since 2026-11-12, `run_ref.py` and `trial.py` import `orchestrator.workflow.executable_ir`, which is removed; the local git tag `archive/old-ir-stack-2026-11-12` holds it.
