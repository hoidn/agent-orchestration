# CLI Stream Output Flag Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dedicated CLI flag that streams provider stdout/stderr live during `run` and `resume` without enabling full debug-mode side effects.

**Architecture:** Thread a new `stream_output` runtime option from the CLI parser through `run_workflow` and `resume_workflow` into `WorkflowExecutor`, then use that option when invoking provider commands. Keep `--debug` semantics unchanged so prompt audits, debug logging, and state backups remain opt-in and independent from console streaming.

**Tech Stack:** Python CLI (`argparse`), workflow executor/provider executor, normative docs in `specs/`, informative docs in `docs/`, and pytest unit tests.

---

### Task 1: Add parser and command-level coverage for a dedicated stream flag

**Files:**
- Modify: `tests/test_cli_observability_config.py`
- Modify: `tests/test_cli_safety.py`

**Step 1: Write failing parser coverage**

Add a test proving `create_parser()` accepts `--stream-output` on `run` and `resume`, with the parsed value defaulting to `False` and flipping to `True` when present.

**Step 2: Write failing command wiring coverage**

Add tests proving:
- `run_workflow()` passes `stream_output=True` into `WorkflowExecutor` when the CLI flag is set.
- `resume_workflow()` passes `stream_output=True` into `WorkflowExecutor` when the CLI flag is set.
- Existing `debug=False` calls do not implicitly set `stream_output=True`.

**Step 3: Run the targeted tests to verify red**

Run:
```bash
pytest tests/test_cli_observability_config.py tests/test_cli_safety.py -k "stream_output" -v
```

Expected: parser/command tests fail because the CLI and executor do not yet expose the flag.

### Task 2: Thread stream output through the runtime

**Files:**
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `orchestrator/workflow/executor.py`

**Step 1: Add the CLI flag**

Add `--stream-output` to both `run` and `resume`. Keep the help text explicit that this streams provider stdout/stderr live and is separate from `--debug`.

**Step 2: Pass the runtime option into the executor**

Update `run_workflow()` and `resume_workflow()` to pass a boolean `stream_output` into `WorkflowExecutor`.

**Step 3: Use the runtime option for provider execution**

Extend `WorkflowExecutor` with a `stream_output` setting and make `_execute_provider_invocation()` pass `stream_output=(self.debug or self.stream_output)` to the provider executor. This preserves existing debug behavior while allowing standalone live console streaming.

**Step 4: Run the targeted tests to verify green**

Run:
```bash
pytest tests/test_cli_observability_config.py tests/test_cli_safety.py -k "stream_output" -v
```

Expected: new parser and wiring tests pass.

### Task 3: Document the new CLI behavior and verify the narrow regression surface

**Files:**
- Modify: `specs/cli.md`
- Modify: `specs/observability.md`
- Modify: `docs/runtime_execution_lifecycle.md`

**Step 1: Update the normative CLI and observability docs**

Document `--stream-output` as a runtime observability/output flag that live-streams provider stdout/stderr without implying prompt audit or debug backups.

**Step 2: Update the runtime lifecycle guide**

Add a short note explaining that live provider console streaming is controlled by `--stream-output` or `--debug`.

**Step 3: Run the relevant regression checks**

Run:
```bash
pytest tests/test_cli_observability_config.py tests/test_cli_safety.py -v
pytest tests/test_provider_execution.py -k stream_output -v
```

**Step 4: Run a workflow smoke check**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/dsl_review_first_fix_loop.yaml --dry-run --stream-output
```

Expected: validation succeeds and the CLI accepts the new flag.
