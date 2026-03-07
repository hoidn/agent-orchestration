# Demo Trial Streaming Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make both direct mode and workflow mode stream agent/process output to the operator console while preserving the existing archive log files and trial-result artifacts.

**Architecture:** Extend the demo trial runner to tee each arm's `stdout` and `stderr` to two sinks at once: live console output with arm-prefixed lines, and the existing on-disk `archive/<arm>/stdout.log` and `archive/<arm>/stderr.log` files. Implement this first at the runner level with `subprocess.Popen` pipe readers; only if workflow provider output is still buffered after that should we add a second pass inside orchestrator/provider execution.

**Tech Stack:** Python, `subprocess.Popen`, `threading`, `queue`, filesystem log artifacts, pytest with test doubles.

---

## Preconditions

- Work from the current runner implementation in `orchestrator/demo/trial_runner.py`.
- Read these files before implementing:
  - `docs/plans/2026-03-05-demo-trial-runner-observability-v2-design.md`
  - `orchestrator/demo/trial_runner.py`
  - `scripts/e2e/run_real_agent_test.py`
  - `tests/test_demo_trial_runner.py`
  - `tests/test_demo_trial_runner_observability.py`
- Do not redesign scheduling or make the runner parallel in this task.
- Do not change workflow YAML or evaluator behavior in this task.

## Task 1: Add Failing Tests For Console Tee Streaming

**Files:**
- Modify: `tests/test_demo_trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`
- Reference: `orchestrator/demo/trial_runner.py`

**Step 1: Write a failing direct-arm streaming test**

Add a test that patches `sys.stdout` and expects a direct-arm line to be printed while still being written to `archive/direct/stdout.log`.

Example assertion shape:

```python
captured = fake_stdout.getvalue()
assert "[direct][stdout] direct ok" in captured
assert "direct ok" in (archive_dir / "direct" / "stdout.log").read_text()
```

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner.py::test_run_trial_streams_direct_output_to_console -v
```

Expected: FAIL because the current runner only writes final log files and does not print child output live.

**Step 3: Write a failing workflow-arm streaming test**

Add a second test that expects workflow-arm output with a distinct prefix, for example:
- `[workflow][stdout] ...`
- `[workflow][stderr] ...`

**Step 4: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner.py::test_run_trial_streams_workflow_output_to_console -v
```

Expected: FAIL.

**Step 5: Commit after implementation passes**

```bash
git add tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py orchestrator/demo/trial_runner.py
git commit -m "test: add trial runner streaming output coverage"
```

## Task 2: Add Tee Readers For `stdout` And `stderr`

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `tests/test_demo_trial_runner.py`

**Step 1: Write helper-level failing tests first**

Add tests for a helper that reads lines from a pipe and writes them to:
- console
- `archive/<arm>/stdout.log` or `stderr.log`

The helper should preserve line ordering within each stream.

**Step 2: Run helper tests to verify they fail**

Run:
```bash
pytest tests/test_demo_trial_runner.py -k "stream_output or tee_output" -v
```

Expected: FAIL because no tee helper exists.

**Step 3: Implement minimal tee helpers**

In `orchestrator/demo/trial_runner.py`, add a small helper set:
- one reader per pipe (`stdout`, `stderr`)
- each reader writes each line immediately to the corresponding log file
- each reader prints the same line immediately to console with an arm/stream prefix
- flush console output after each printed line

Recommended console prefix format:
- `[direct][stdout] ...`
- `[direct][stderr] ...`
- `[workflow][stdout] ...`
- `[workflow][stderr] ...`

Keep the prefix contract simple and explicit so tests are deterministic.

**Step 4: Run targeted tests to verify they pass**

Run:
```bash
pytest tests/test_demo_trial_runner.py -k "stream_output or tee_output" -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner.py
git commit -m "feat: tee runner output to console and logs"
```

## Task 3: Replace `communicate()` With Polling + Reader Threads

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `tests/test_demo_trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`

**Step 1: Write a failing in-flight log-growth test**

Add a test using a fake long-running `Popen` or a tiny helper script that emits multiple lines over time. Assert that:
- console output appears before process completion
- `archive/<arm>/stdout.log` grows before process completion
- the final execution result still captures full stdout/stderr content

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_streaming_logs_grow_before_process_exit -v
```

Expected: FAIL because `communicate()` buffers until completion.

**Step 3: Implement the minimal poll loop**

In `_run_command(...)`:
- start reader threads for `process.stdout` and `process.stderr`
- let those threads append to log files and print to console
- use `process.poll()` / `wait()` instead of one-shot `communicate()`
- join reader threads after child exit
- reconstruct final `stdout` / `stderr` from collected line buffers

Do not add parallel arm execution. Keep the existing direct-then-workflow order.

**Step 4: Run targeted tests**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -k "stream or process metadata or heartbeat" -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "feat: stream trial runner child output live"
```

## Task 4: Preserve Timeout Behavior Under Streaming

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`

**Step 1: Write the failing timeout-with-streaming test**

Add a test that simulates a child writing some lines and then timing out. Assert that:
- the pre-timeout lines are already printed to console
- the pre-timeout lines are preserved in `stdout.log`
- timeout state still appears in `runner-state.json`
- timeout event still appears in `runner-events.jsonl`

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_timeout_preserves_streamed_output -v
```

Expected: FAIL until the timeout path is adapted to the threaded readers.

**Step 3: Implement timeout-safe shutdown**

Update `_run_command(...)` so that on timeout:
- terminate/kill logic still runs
- reader threads are joined cleanly
- already-read lines are not lost
- final `stdout` / `stderr` in the result match the streamed output actually seen so far

**Step 4: Run targeted tests**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py -k "timeout" -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "fix: preserve streamed output on timeout"
```

## Task 5: Add A User-Facing Runner Flag For Streaming

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `scripts/demo/run_trial.py`
- Modify: `tests/test_demo_trial_runner.py`
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Write the failing CLI/config test**

Add a test that expects a new flag such as:
- `--stream-output`

and that the runner defaults are explicit.

Recommendation:
- make streaming enabled by default for real trials, but add `--no-stream-output` only if needed later
- if you want a safer rollout, invert that and require `--stream-output`

Choose one, document it, and keep tests aligned.

**Step 2: Run the parser test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner.py -k stream_output_flag -v
python scripts/demo/run_trial.py --help
```

Expected: FAIL for pytest until the flag exists.

**Step 3: Implement the flag and plumb it through**

Add the chosen CLI flag and pass it into `run_trial()` / `_run_command()`.

**Step 4: Update the runbook**

Document:
- how console streaming works
- the line prefix format
- that on-disk logs remain authoritative archives
- that the runner is still serial even though output is now live

**Step 5: Run targeted checks**

Run:
```bash
pytest tests/test_demo_trial_runner.py -k stream_output_flag -v
python scripts/demo/run_trial.py --help
```

Expected: PASS and the flag appears in help output.

**Step 6: Commit**

```bash
git add orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py docs/plans/2026-03-05-demo-scaffold-and-runbook.md
git commit -m "feat: add configurable trial output streaming"
```

## Task 6: Decide Whether Workflow-Internal Buffering Still Needs Work

**Files:**
- Verify: `orchestrator/demo/trial_runner.py`
- Inspect if needed: provider execution path under `orchestrator/providers/` and CLI run path under `orchestrator/cli/commands/run.py`
- Document if needed: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Run one real local smoke trial with streaming enabled**

Use a temporary seed and short timeouts.

Run:
```bash
python scripts/demo/run_trial.py \
  --seed-repo /tmp/demo-seed-repo \
  --experiment-root /tmp/demo-trial-streaming \
  --task-file /tmp/demo-seed-repo/docs/tasks/port_linear_classifier_to_rust.md \
  --direct-timeout-sec 60 \
  --workflow-timeout-sec 120 \
  --stream-output
```

**Step 2: Observe actual workflow-arm console behavior**

Check whether workflow provider steps emit live lines as they happen, or whether they still appear in large buffered chunks.

Expected outcomes:
- if console output is acceptably live, stop here
- if workflow output is still buffered until step completion, record that as a separate follow-on task inside orchestrator/provider execution rather than expanding this task ad hoc

**Step 3: Document the observed limitation if present**

If buffering remains, update the runbook or a follow-on note to say:
- runner-level streaming is implemented
- workflow provider internals may still buffer step output depending on provider/orchestrator behavior

**Step 4: Commit any doc-only follow-up**

```bash
git add docs/plans/2026-03-05-demo-scaffold-and-runbook.md
 git commit -m "docs: record workflow streaming limitations"
```

## Task 7: Final Verification

**Files:**
- Verify: `orchestrator/demo/trial_runner.py`
- Verify: `scripts/demo/run_trial.py`
- Verify: `tests/test_demo_trial_runner.py`
- Verify: `tests/test_demo_trial_runner_observability.py`
- Verify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Run the targeted runner suite**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py tests/test_demo_trial_smoke.py tests/test_demo_provisioning.py tests/test_demo_linear_classifier_evaluator.py -q
```

Expected: all pass.

**Step 2: Run workflow dry-run validation**

Run:
```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run
```

Expected: dry-run validation successful.

**Step 3: Run formatting sanity check**

Run:
```bash
git diff --check -- orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py docs/plans/2026-03-05-demo-scaffold-and-runbook.md
```

Expected: clean.

**Step 4: Final commit**

```bash
git add orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py docs/plans/2026-03-05-demo-scaffold-and-runbook.md
git commit -m "feat: stream demo trial output to console"
```
