# Demo Trial Runner Observability v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the demo trial runner so real direct-vs-workflow trials emit durable in-flight status, live logs, timeout metadata, partial results, and freeze artifacts even when a trial does not complete cleanly.

**Architecture:** Keep the current serial runner model for now, but replace blocking one-shot execution with a runner-owned state machine that persists status snapshots and events before and during each arm. Implement the new archive contract with `subprocess.Popen` first, stream logs into `archive/<arm>/`, add heartbeats and timeouts, then freeze and evaluate using the new partial/final result files.

**Tech Stack:** Python, JSON/JSONL files, filesystem archive artifacts, `subprocess.Popen`, existing `provision_trial()` and evaluator scripts, targeted pytest integration tests.

---

## Preconditions

- Work from a clean or isolated worktree before implementing. The current main workspace is dirty with unrelated tracked and untracked changes.
- Read these docs first:
  - `docs/plans/2026-03-05-demo-trial-runner-observability-v2-design.md`
  - `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
  - `tests/README.md`
- Keep the first implementation backend to plain `subprocess`; do not add `tmux` support in the same pass.
- Do not change workflow YAML or evaluator semantics in this plan.

## Task 1: Add Test Coverage For Runner-Owned State Files

**Files:**
- Modify: `tests/test_demo_trial_runner.py`
- Create: `tests/test_demo_trial_runner_observability.py`
- Reference: `orchestrator/demo/trial_runner.py`

**Step 1: Write the failing snapshot test**

Add a test that expects `run_trial()` to create `archive/runner-state.json` and `archive/partial-trial-result.json` before the whole trial completes.

Example test shape:

```python
def test_run_trial_writes_runner_state_and_partial_result(...):
    ...
    assert (archive_dir / "runner-state.json").is_file()
    assert (archive_dir / "partial-trial-result.json").is_file()
```

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_run_trial_writes_runner_state_and_partial_result -v
```

Expected: FAIL because the current runner only writes final command records and `trial-result.json` at the end.

**Step 3: Write the failing event-log test**

Add a test that expects `archive/runner-events.jsonl` with at least:
- `trial_started`
- `provisioning_completed`
- `arm_started`
- `arm_completed`

**Step 4: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_run_trial_emits_event_log -v
```

Expected: FAIL because no event log exists yet.

**Step 5: Commit after implementation passes**

```bash
git add tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py orchestrator/demo/trial_runner.py
git commit -m "test: add runner observability coverage"
```

## Task 2: Introduce Runner Snapshot/Event Helpers

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Test: `tests/test_demo_trial_runner_observability.py`

**Step 1: Add minimal state helper tests first**

Add tests for helpers like:
- `_write_runner_state(...)`
- `_append_runner_event(...)`
- `_write_partial_result(...)`

Example assertions:

```python
payload = json.loads((archive_dir / "runner-state.json").read_text())
assert payload["status"] == "running"
```

**Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py -k "runner_state or event_log or partial_result" -v
```

Expected: FAIL with missing helpers or missing files.

**Step 3: Implement the minimal helpers**

In `orchestrator/demo/trial_runner.py`, add helper functions to:
- build the archive subdirectories
- write `archive/runner-state.json`
- append JSON lines to `archive/runner-events.jsonl`
- write `archive/partial-trial-result.json`

Keep the first version small:
- snapshot fields only need current phase, per-arm status, timestamps, workspace paths, and known log/process paths
- partial result only needs known command/execution/evaluation fields so far

**Step 4: Run targeted tests to verify they pass**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py -k "runner_state or event_log or partial_result" -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "feat: add runner state and event artifacts"
```

## Task 3: Replace Blocking `subprocess.run` With Streamed `Popen`

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `tests/test_demo_trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`

**Step 1: Write the failing live-log test**

Add a test that simulates a long-running child process and expects:
- `archive/direct/stdout.log`
- `archive/direct/stderr.log`
- `archive/direct/process.json`

before the process has fully exited.

Use a fake `Popen` double or a small local helper process rather than a real Codex run.

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_arm_logs_and_process_metadata_exist_while_running -v
```

Expected: FAIL because the current runner captures output only after child exit.

**Step 3: Implement streamed process handling**

In `orchestrator/demo/trial_runner.py`:
- replace `_run_command(...)` with a runner that uses `subprocess.Popen`
- create `archive/<arm>/stdout.log` and `archive/<arm>/stderr.log`
- write `archive/<arm>/process.json` immediately after launch
- wait on the child while logs are being written incrementally

Keep it serial for now:
- run direct arm first
- then workflow arm

Do not add concurrency between arms yet.

**Step 4: Run the targeted tests**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -k "process or stdout or stderr or build_workflow_command" -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "feat: stream runner logs and process metadata"
```

## Task 4: Add Heartbeats And Current-Phase Updates

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`

**Step 1: Write the failing heartbeat test**

Add a test that launches a fake long-running arm and expects `archive/direct/heartbeat.json` to be rewritten at least once while the child remains active.

Example assertion:

```python
heartbeat = json.loads((archive_dir / "direct" / "heartbeat.json").read_text())
assert heartbeat["alive"] is True
assert heartbeat["elapsed_sec"] >= 0
```

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_running_arm_updates_heartbeat -v
```

Expected: FAIL because no heartbeat file exists.

**Step 3: Implement heartbeat updates**

In `orchestrator/demo/trial_runner.py`:
- add a heartbeat interval constant or CLI-configurable value
- rewrite `archive/<arm>/heartbeat.json` while waiting on the child
- update `runner-state.json` `current_phase` and per-arm status on every major transition
- append `arm_heartbeat` events sparingly; do not flood the event log on every tick unless the interval is coarse

**Step 4: Run targeted tests**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py -k "heartbeat or current_phase" -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner_observability.py
git commit -m "feat: add runner heartbeats"
```

## Task 5: Add Timeout And Termination Recording

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `scripts/demo/run_trial.py`
- Modify: `tests/test_demo_trial_runner_observability.py`

**Step 1: Write the failing timeout test**

Add a test that runs a fake long child with a short timeout and expects:
- arm status becomes `timed_out`
- `runner-state.json` records timeout
- `runner-events.jsonl` includes `arm_timeout`
- `partial-trial-result.json` persists the timeout outcome

**Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py::test_arm_timeout_records_state_and_events -v
```

Expected: FAIL because the current runner has no timeout behavior.

**Step 3: Implement minimal timeout support**

Add CLI flags and plumbing for:
- `--direct-timeout-sec`
- `--workflow-timeout-sec`
- optional `--evaluation-timeout-sec`

Implement termination recording with at least:
- timeout event
- termination attempt event
- final per-arm `status.json`
- exit/termination fields in `partial-trial-result.json`

Do not over-engineer signal escalation. Start with a simple terminate/wait/kill path and record what happened.

**Step 4: Run targeted tests**

Run:
```bash
pytest tests/test_demo_trial_runner_observability.py -k timeout -v
python scripts/demo/run_trial.py --help
```

Expected: PASS for pytest, and `--help` shows the new timeout flags.

**Step 5: Commit**

```bash
git add orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner_observability.py
git commit -m "feat: add trial runner timeouts"
```

## Task 6: Add Freeze Manifests And Evaluator Status Artifacts

**Files:**
- Modify: `orchestrator/demo/trial_runner.py`
- Modify: `tests/test_demo_trial_runner.py`
- Modify: `tests/test_demo_trial_runner_observability.py`
- Modify: `tests/test_demo_trial_smoke.py`

**Step 1: Write the failing freeze-manifest test**

Add a test that expects, after an arm completes or times out:
- `archive/<arm>/freeze/workspace-status.txt`
- `archive/<arm>/freeze/workspace-head.txt`
- `archive/<arm>/freeze/tree.txt`

**Step 2: Write the failing evaluator-status test**

Add a test that expects:
- `archive/evaluator/status.json`
- `archive/evaluator/direct-result.json`
- `archive/evaluator/workflow-result.json`

when evaluation runs, even if one result is failure or invalid JSON.

**Step 3: Run tests to verify they fail**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py -k "freeze or evaluator" -v
```

Expected: FAIL because these artifacts do not exist yet.

**Step 4: Implement freeze + evaluator status**

In `orchestrator/demo/trial_runner.py`:
- add per-arm freeze helper that writes git status, git head, and a deterministic file manifest
- write evaluator status/result files outside workspaces
- ensure `partial-trial-result.json` is rewritten after each freeze/evaluation milestone
- write `trial-result.json` only at terminal completion

**Step 5: Run targeted tests**

Run:
```bash
pytest tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py tests/test_demo_trial_smoke.py -k "freeze or evaluator or snapshot" -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add orchestrator/demo/trial_runner.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py tests/test_demo_trial_smoke.py
git commit -m "feat: freeze runner state and evaluator artifacts"
```

## Task 7: Update Runbook And Testing Docs

**Files:**
- Modify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`
- Modify: `docs/plans/2026-03-05-workflow-demo-session-handoff.md`
- Modify: `tests/README.md`

**Step 1: Write the docs delta**

Update the runbook so it reflects the actual `v2` runner behavior:
- serial execution remains explicit
- in-flight archive/status files are documented
- timeout flags are documented
- partial-result behavior is documented
- freeze semantics reflect the implemented manifest contract rather than an aspirational full snapshot

Update `tests/README.md` to add the targeted runner-observability selector.

**Step 2: Run docs sanity checks**

Run:
```bash
git diff --check -- docs/plans/2026-03-05-demo-scaffold-and-runbook.md docs/plans/2026-03-05-workflow-demo-session-handoff.md tests/README.md
```

Expected: clean.

**Step 3: Commit**

```bash
git add docs/plans/2026-03-05-demo-scaffold-and-runbook.md docs/plans/2026-03-05-workflow-demo-session-handoff.md tests/README.md
git commit -m "docs: document v2 trial runner observability"
```

## Task 8: Final Verification With Real Smoke Evidence

**Files:**
- Verify: `orchestrator/demo/trial_runner.py`
- Verify: `scripts/demo/run_trial.py`
- Verify: `tests/test_demo_trial_runner.py`
- Verify: `tests/test_demo_trial_runner_observability.py`
- Verify: `tests/test_demo_trial_smoke.py`
- Verify: `docs/plans/2026-03-05-demo-scaffold-and-runbook.md`

**Step 1: Run targeted pytest coverage**

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

**Step 3: Run one real local smoke trial with short timeouts**

Use a temporary seed repo cloned from `examples/demo_task_linear_classifier_port`, then run:

```bash
python scripts/demo/run_trial.py \
  --seed-repo /tmp/demo-seed-repo \
  --experiment-root /tmp/demo-trial-v2 \
  --task-file /tmp/demo-seed-repo/docs/tasks/port_linear_classifier_to_rust.md \
  --direct-timeout-sec 60 \
  --workflow-timeout-sec 120
```

Expected:
- `archive/runner-state.json` exists during the run
- `archive/direct/heartbeat.json` updates while direct arm runs
- if timeout occurs, timeout artifacts are present instead of a silent hang
- `partial-trial-result.json` exists even if the trial does not reach a final `PASS`/`FAIL` result

**Step 4: Record evidence in docs or handoff note**

Write down:
- actual command used
- actual archive location
- whether the smoke completed, timed out, or was interrupted
- the key archive artifacts that proved observability worked

**Step 5: Final commit**

```bash
git add orchestrator/demo/trial_runner.py scripts/demo/run_trial.py tests/test_demo_trial_runner.py tests/test_demo_trial_runner_observability.py tests/test_demo_trial_smoke.py docs/plans/2026-03-05-demo-scaffold-and-runbook.md docs/plans/2026-03-05-workflow-demo-session-handoff.md tests/README.md
git commit -m "feat: add observable demo trial runner"
```
