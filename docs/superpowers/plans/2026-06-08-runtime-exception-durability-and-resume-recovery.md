# Runtime Exception Durability And Resume Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make workflow crashes and unexpected executor exceptions persist actionable failure evidence, avoid `failed` runs with empty errors and stale running loop state, and allow resume/report tooling to recover or explain interrupted `.orc` review/fix runs.

**Architecture:** Keep the fix in the runtime failure boundary, not in the review/revise workflow. Replace bare `update_status('failed')` exception paths with structured `fail_run(...)` records that include exception type, message, traceback, current step/frame context, and resume hints. Add a narrow resume/report recovery layer that treats already-validated provider/fix bundles as durable evidence instead of losing them when a nested call exits before the parent loop advances.

**Tech Stack:** Python runtime executor, `StateManager`, CLI `run`/`resume`/`report`, pytest, local `.orc` workflow fixtures.

---

## Root Cause Summary

The failed `review_revise_design_docs.orc` run had valid review and fix result bundles on disk, but `state.json` ended as:

- top-level `status: failed`;
- top-level `error: null`;
- no useful `current_step`;
- a nested/loop step still marked `running`; and
- no persisted traceback identifying the exception that killed the executor.

That points to the executor/CLI exception boundary, not the provider structured-output path. The provider bundle path fix worked: the review decision bundle and fix revision bundle were produced. The workflow failed later because an unexpected runtime exception caused the run to be marked failed without durable diagnostic context and without reconciling the in-progress loop/nested-step state.

The principled fix is:

1. persist structured executor exceptions with traceback and current execution context;
2. make stale current-step/loop state internally consistent on run-level failure;
3. make resume able to use already-persisted valid result bundles where the state update was interrupted after the child provider completed; and
4. make `orchestrator report --run-id` useful for `.orc` runs that failed this way.

## File Structure

- Modify `orchestrator/workflow/executor.py`
  - Add a helper for structured executor exception records.
  - Use `StateManager.fail_run(...)` instead of bare `update_status('failed')` in top-level executor exception paths.
  - Preserve current step identity, node id, step index, call-frame/loop context, and traceback.
  - Add a narrow post-provider-bundle reconciliation hook only if the existing state/bundle APIs already expose enough evidence.

- Modify `orchestrator/state.py`
  - Extend failure persistence only if needed. Prefer the existing `fail_run(...)` API.
  - Do not redesign state schema unless tests prove existing fields cannot express the failure evidence.

- Modify `orchestrator/cli/commands/run.py`
  - On unexpected CLI exceptions after `StateManager` creation, persist a structured failure record before returning nonzero.
  - Keep logger traceback output, but do not rely on terminal stderr as the only evidence.

- Modify `orchestrator/cli/commands/resume.py`
  - On unexpected resume exceptions, persist structured failure records instead of bare status changes.
  - If feasible, add a targeted resume reconciliation for interrupted provider/fix bundle completion.

- Modify `orchestrator/cli/commands/report.py`
  - Fix report loading for `.orc` run state so users can inspect failed `.orc` runs without a YAML-only workflow-load error.

- Test `tests/test_runtime_failure_persistence.py`
  - New focused unit/integration tests for executor exception persistence.

- Test `tests/test_resume_command.py`
  - Add or extend a resume test for interrupted nested/provider result state if a stable fixture can reproduce it narrowly.

- Test `tests/test_cli_observability_config.py` or `tests/test_cli_report.py`
  - Add report-command coverage for `.orc` run state if no existing report test module is better.

## Dirty Worktree Guard

Before implementation, run:

```bash
git status --short
```

Known unrelated dirty files may exist:

- `orchestrator/contracts/output_contract.py`
- `tests/test_output_contract.py`
- `tests/test_cli_observability_config.py`
- `orchestrator/cli/commands/resume.py`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- untracked backlog/design-gap docs

If a required file is already dirty, inspect it before editing and preserve user changes. Stage only files touched for this fix.

## Task 1: Add Executor Exception Persistence Test

**Files:**
- Create: `tests/test_runtime_failure_persistence.py`
- Modify after red: `orchestrator/workflow/executor.py`

- [ ] **Step 1: Write a failing test for unexpected executor exceptions**

Create a small workflow, monkeypatch the executor so a step raises after `start_step(...)`, then assert `state.json` has a structured error and current-step context.

```python
def test_executor_unexpected_exception_persists_error_and_current_step_context(temp_workspace):
    workflow_path = temp_workspace / "crash.yaml"
    workflow_path.write_text(
        """
version: "2.0"
steps:
  Crash:
    kind: command
    command: "echo should-not-matter"
""",
        encoding="utf-8",
    )

    loader = WorkflowLoader(temp_workspace)
    workflow = loader.load(workflow_path)
    manager = StateManager(temp_workspace)
    manager.initialize("crash.yaml")
    executor = WorkflowExecutor(workflow, temp_workspace, manager)

    def raise_runtime(*args, **kwargs):
        raise RuntimeError("synthetic executor crash")

    executor._run_top_level_step = raise_runtime

    with pytest.raises(RuntimeError, match="synthetic executor crash"):
        executor.execute(on_error="stop")

    persisted = json.loads((manager.run_root / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["error"]["type"] == "executor_unhandled_exception"
    assert persisted["error"]["exception_type"] == "RuntimeError"
    assert "synthetic executor crash" in persisted["error"]["message"]
    assert "traceback" in persisted["error"]
    assert persisted["error"]["context"]["step_name"] == "Crash"
    assert persisted["error"]["context"]["step_id"]
    assert persisted["current_step"]["status"] == "failed"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_runtime_failure_persistence.py::test_executor_unexpected_exception_persists_error_and_current_step_context -q
```

Expected: FAIL because the current executor exception path only calls `update_status('failed')`, leaving `error` empty and current-step status stale.

- [ ] **Step 3: Implement minimal executor failure helper**

In `orchestrator/workflow/executor.py`, import `traceback` if not already imported and add a helper near `execute(...)`:

```python
def _executor_exception_error(
    self,
    exc: BaseException,
    *,
    step_name: str | None = None,
    step_id: str | None = None,
    step_index: int | None = None,
    node_id: str | None = None,
    visit_count: int | None = None,
) -> dict[str, Any]:
    context = {
        "step_name": step_name,
        "step_id": step_id,
        "step_index": step_index,
        "node_id": node_id,
        "visit_count": visit_count,
    }
    return {
        "type": "executor_unhandled_exception",
        "message": str(exc),
        "exception_type": type(exc).__name__,
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        "context": {key: value for key, value in context.items() if value is not None},
    }
```

When the top-level step loop catches an unexpected exception, call:

```python
self.state_manager.fail_run(
    self._executor_exception_error(
        exc,
        step_name=step_name,
        step_id=step_id,
        step_index=step_index,
        node_id=current_node_id,
        visit_count=visit_count if isinstance(visit_count, int) else None,
    ),
)
```

Then re-raise to preserve CLI exit behavior.

- [ ] **Step 4: Mark current step failed instead of leaving it running**

Use existing `StateManager` APIs if available. If no helper exists, update `fail_run(...)` to mark the matching `current_step.status` as `failed` when `clear_current_step=False`.

Keep this conservative:

```python
if isinstance(self.state.current_step, dict):
    self.state.current_step["status"] = "failed"
    self.state.current_step["failed_at"] = datetime.now(timezone.utc).isoformat()
```

Do not clear `current_step`; preserving the failed frame is better for diagnosis than deleting it.

- [ ] **Step 5: Run the focused test**

Run:

```bash
pytest tests/test_runtime_failure_persistence.py::test_executor_unexpected_exception_persists_error_and_current_step_context -q
```

Expected: PASS.

## Task 2: Persist CLI Run/Resume Unexpected Exceptions

**Files:**
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Test: `tests/test_runtime_failure_persistence.py` or `tests/test_cli_observability_config.py`

- [ ] **Step 1: Write a failing CLI run exception test**

Patch `WorkflowExecutor.execute` to raise after `StateManager` is initialized. Assert the run command returns nonzero and persisted `state.json` includes the exception details.

```python
def test_run_command_persists_unexpected_executor_exception(temp_workspace):
    workflow_path = temp_workspace / "crash.yaml"
    workflow_path.write_text(...)
    args = _base_run_args(workflow_path)

    with patch("orchestrator.cli.commands.run.WorkflowExecutor.execute") as execute:
        execute.side_effect = RuntimeError("cli executor crash")
        exit_code = run_workflow(args)

    assert exit_code == 1
    run_dirs = sorted((temp_workspace / ".orchestrate" / "runs").iterdir())
    persisted = json.loads((run_dirs[-1] / "state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["error"]["type"] == "cli_unhandled_exception"
    assert persisted["error"]["exception_type"] == "RuntimeError"
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_runtime_failure_persistence.py::test_run_command_persists_unexpected_executor_exception -q
```

Expected: FAIL because CLI `run.py` logs the traceback but does not persist it.

- [ ] **Step 3: Implement a small CLI error helper**

In `orchestrator/cli/commands/run.py`, keep `logger.error(..., exc_info=True)` but also call `state_manager.fail_run(...)` when a `StateManager` exists.

Use a small local helper:

```python
def _cli_exception_error(exc: BaseException) -> dict[str, Any]:
    return {
        "type": "cli_unhandled_exception",
        "message": str(exc),
        "exception_type": type(exc).__name__,
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
```

Do the same for `resume.py` if its exception path still calls `update_status('failed')`.

- [ ] **Step 4: Run focused CLI tests**

Run:

```bash
pytest tests/test_runtime_failure_persistence.py::test_run_command_persists_unexpected_executor_exception -q
pytest tests/test_cli_observability_config.py -q
```

Expected: PASS, preserving current CLI behavior.

## Task 3: Make `.orc` Failed Runs Reportable

**Files:**
- Modify: `orchestrator/cli/commands/report.py`
- Test: add to existing report tests or create `tests/test_cli_report.py`

- [ ] **Step 1: Write a failing report test for `.orc` run state**

Create a run directory with `state.json` whose workflow path ends in `.orc`, then run `report_workflow(...)`.

Expected behavior:

- report should not fail with `Workflow must be a YAML object/dictionary`;
- report should print run id, persisted status, error summary, and current step if present;
- if loading the workflow is impossible, report should degrade to state-only output.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/test_cli_report.py::test_report_handles_orc_run_state_without_yaml_loader_error -q
```

Expected: FAIL with the current YAML-loader error.

- [ ] **Step 3: Implement state-only fallback**

In `orchestrator/cli/commands/report.py`, when workflow loading fails because the workflow path is `.orc` or cannot be parsed as YAML:

- do not abort the report;
- use the persisted `state.json`;
- print a clear note like `Workflow definition could not be loaded for report projection; showing state-only report`;
- include top-level `status`, `error`, `current_step`, and output fields.

Keep the fallback generic enough for malformed/missing workflow definitions, but do not hide state-file JSON errors.

- [ ] **Step 4: Run report tests**

Run:

```bash
pytest tests/test_cli_report.py::test_report_handles_orc_run_state_without_yaml_loader_error -q
```

Expected: PASS.

## Task 4: Add Interrupted Provider/Fix Bundle Resume Guard

**Files:**
- Modify: `orchestrator/workflow/executor.py`
- Possibly modify: `orchestrator/workflow/resume_planner.py`
- Test: `tests/test_resume_command.py`

- [ ] **Step 1: Inspect existing provider bundle resume behavior**

Run:

```bash
rg -n "result_bundle|missing_bundle|provider.*resume|resume_current_step|provider_session" orchestrator/workflow orchestrator/providers tests/test_resume_command.py
```

Record whether existing provider output validation persists enough state to skip/reconcile a completed provider child step.

- [ ] **Step 2: Write the narrowest failing resume test**

Simulate the observed state:

- parent repeat loop/current step remains running;
- a child provider/fix result bundle exists and validates;
- the child step result is missing or not fully linked into the parent state;
- resume should either reconcile the completed child result or fail with a structured `resume_state_integrity_error`, not rerun blindly or produce empty failure.

Name the test around the behavior:

```python
def test_resume_reconciles_interrupted_provider_bundle_before_loop_advance(...):
    ...
```

- [ ] **Step 3: Run the test to verify it fails**

Run:

```bash
pytest tests/test_resume_command.py::test_resume_reconciles_interrupted_provider_bundle_before_loop_advance -q
```

Expected: FAIL by either rerunning, failing without error context, or ignoring the durable bundle.

- [ ] **Step 4: Implement minimal reconciliation**

Prefer a narrow helper that:

- only runs in resume mode;
- only applies when current persisted state indicates an interrupted provider/fix step;
- validates the existing declared bundle through the same output-contract path used after normal provider execution;
- persists the reconstructed step result exactly once; and
- then lets normal control-flow/loop advancement continue.

If the existing state cannot identify the interrupted child safely, fail closed:

```python
{
  "type": "resume_state_integrity_error",
  "message": "Interrupted provider result bundle exists but cannot be safely associated with a workflow step.",
  "context": {...}
}
```

Do not add broad filesystem scanning or sibling-bundle copy recovery.

- [ ] **Step 5: Run resume tests**

Run:

```bash
pytest tests/test_resume_command.py::test_resume_reconciles_interrupted_provider_bundle_before_loop_advance -q
pytest tests/test_resume_command.py -k "current_step or provider_session or looped_completion" -q
```

Expected: PASS.

## Task 5: End-To-End Regression Check For Generic Review/Revise `.orc`

**Files:**
- No production files unless the focused tests reveal a real gap.

- [ ] **Step 1: Run the narrow Workflow Lisp example test**

Run:

```bash
pytest tests/test_workflow_lisp_examples.py -k "review_revise_design_docs" -q
```

Expected: PASS.

- [ ] **Step 2: Resume the failed real run if still available**

Use the existing failed run id if present:

```bash
python -m orchestrator resume 20260608T231536Z-ig5heu --stream-output
```

Expected:

- either successful recovery from the already-produced fix bundle;
- or a structured failure with `error.type`, traceback/context, and no contradictory `failed` plus stale-running state.

If resuming the real run is no longer useful because code/state drift invalidates it, launch a fresh generic workflow only after confirming the user wants a live provider run.

- [ ] **Step 3: Check report**

Run:

```bash
python -m orchestrator report --run-id 20260608T231536Z-ig5heu
```

Expected: report displays state/error/current-step information for the `.orc` run instead of YAML-loader failure.

## Task 6: Final Verification And Commit

**Files:**
- Stage only files directly touched for this fix.

- [ ] **Step 1: Run focused verification**

Run:

```bash
pytest tests/test_runtime_failure_persistence.py -q
pytest tests/test_cli_report.py -q
pytest tests/test_cli_observability_config.py -q
pytest tests/test_resume_command.py -k "current_step or provider_session or looped_completion" -q
pytest tests/test_workflow_lisp_examples.py -k "review_revise_design_docs" -q
```

- [ ] **Step 2: Run diff hygiene**

Run:

```bash
git diff --check -- orchestrator/workflow/executor.py orchestrator/state.py orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py orchestrator/cli/commands/report.py tests/test_runtime_failure_persistence.py tests/test_cli_report.py tests/test_resume_command.py tests/test_cli_observability_config.py
```

- [ ] **Step 3: Inspect scoped diff**

Run:

```bash
git diff -- orchestrator/workflow/executor.py orchestrator/state.py orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py orchestrator/cli/commands/report.py tests/test_runtime_failure_persistence.py tests/test_cli_report.py tests/test_resume_command.py tests/test_cli_observability_config.py
```

Confirm no unrelated edits or prompt literal assertions were added.

- [ ] **Step 4: Commit**

Run:

```bash
git add orchestrator/workflow/executor.py orchestrator/state.py orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py orchestrator/cli/commands/report.py tests/test_runtime_failure_persistence.py tests/test_cli_report.py tests/test_resume_command.py tests/test_cli_observability_config.py
git commit -m "orchestrator: persist runtime failure diagnostics"
```

If some listed files were not changed, omit them from `git add`.

## Local Plan Review Checklist

Because this session did not have explicit permission to spawn a plan-review subagent, use this manual review before execution:

- Does every production change have a red test first?
- Does the plan fix the runtime failure boundary rather than the review/revise workflow?
- Does it avoid sibling-bundle copy recovery?
- Does it preserve provider structured-output validation as authority?
- Does it avoid public state-schema churn unless tests require it?
- Does it keep unrelated dirty files unstaged?
- Does it leave live provider relaunch as a separate decision unless the user asks for it?
