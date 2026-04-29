# Active Runtime Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add observability-only active executor runtime reporting that accumulates live run/resume session time while excluding gaps between executor processes.

**Architecture:** Store additive executor-session records in `state.json` under `runtime_observability`, manage them through a small pure helper module, and surface computed active runtime through the existing report/status path. `run` and `resume` own session lifecycle; reports compute display values without changing workflow control flow.

**Tech Stack:** Python dataclasses/dicts, existing `StateManager`, existing CLI `run`/`resume` commands, existing process metadata helpers, pytest.

---

## Reference Design

Implement against [2026-04-29-active-runtime-observability-design.md](2026-04-29-active-runtime-observability-design.md).

This plan intentionally does not add DSL runtime limits, provider timeouts, prompt changes, or workflow routing behavior.

## File Structure

- Create `orchestrator/runtime_observability.py`
  - Own session id allocation, open/close/reconcile helpers, runtime computation, formatting.
- Create `tests/test_runtime_observability.py`
  - Unit-test helper behavior with injected clocks and fake liveness.
- Modify `orchestrator/state.py`
  - Add `RunState.runtime_observability`.
  - Preserve loading of old states where the field is absent.
- Modify `orchestrator/cli/commands/run.py`
  - Open a `run` session after state initialization.
  - Close it in a `finally` block.
- Modify `orchestrator/cli/commands/resume.py`
  - Reconcile old open sessions before execution.
  - Open a `resume` session and close it in `finally`.
- Modify `orchestrator/observability/report.py`
  - Add active runtime fields to `build_status_snapshot`.
  - Render active runtime in markdown.
- Modify `orchestrator/monitor/process.py`
  - Optionally accept and persist `executor_session_id` in `monitor_process.json`.
- Modify `tests/test_observability_report.py`
  - Assert JSON snapshot and markdown include active runtime.
- Modify `tests/test_cli_safety.py` or create a focused CLI test file if needed
  - Assert `run_workflow` closes sessions around executor results with mocks.
- Modify `tests/test_resume_command.py`
  - Assert resume creates an additional session and excludes the gap.
- Modify `specs/state.md`, `specs/observability.md`, `specs/cli.md`
  - Document state and report semantics.

### Task 1: Pure Session Accounting

**Files:**
- Create: `orchestrator/runtime_observability.py`
- Create: `tests/test_runtime_observability.py`

- [ ] **Step 1: Write failing unit tests for closed and open sessions**

Add tests that construct raw state dictionaries and call pure helpers with fixed `now`.

```python
from datetime import datetime, timezone

from orchestrator.runtime_observability import compute_active_runtime


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_compute_active_runtime_sums_closed_sessions():
    state = {
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": "2026-04-29T10:20:00Z",
                    "status": "completed",
                    "duration_ms": 1_200_000,
                }
            ],
        }
    }
    snapshot = compute_active_runtime(state, now=dt("2026-04-29T12:00:00Z"))
    assert snapshot["active_runtime_ms"] == 1_200_000
    assert snapshot["executor_session_count"] == 1


def test_compute_active_runtime_excludes_gap_between_sessions():
    state = {
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": "2026-04-29T10:20:00Z",
                    "status": "failed",
                    "duration_ms": 1_200_000,
                },
                {
                    "session_id": "exec-0002",
                    "started_at": "2026-04-29T22:15:00Z",
                    "ended_at": None,
                    "status": "running",
                    "duration_ms": None,
                    "pid": 123,
                },
            ],
        }
    }
    snapshot = compute_active_runtime(
        state,
        now=dt("2026-04-29T22:20:00Z"),
        process_is_live=lambda session: True,
    )
    assert snapshot["active_runtime_ms"] == 1_500_000
    assert snapshot["excluded_suspended_ms"] == 42_900_000
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: FAIL because `orchestrator.runtime_observability` does not exist.

- [ ] **Step 3: Implement minimal helper module**

Implement:

```python
def compute_active_runtime(state, *, now=None, process_is_live=None) -> dict:
    ...

def format_duration(ms: int | None) -> str | None:
    ...
```

Rules:

- Closed sessions contribute `duration_ms`.
- Live open session contributes `now - started_at`.
- Non-live open session contributes nothing until reconciliation adds a closed duration.
- Missing field returns `{"active_runtime_ms": None, "executor_session_count": 0}`.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/runtime_observability.py tests/test_runtime_observability.py
git commit -m "feat(observability): add active runtime accounting helpers"
```

### Task 2: State Persistence

**Files:**
- Modify: `orchestrator/state.py`
- Modify: `tests/test_runtime_observability.py`

- [ ] **Step 1: Write failing state round-trip tests**

Add tests that initialize `StateManager`, assign `runtime_observability`, write state, reload, and verify the payload survives. Also load a minimal old state without the field and verify `runtime_observability is None`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: FAIL because `RunState` does not expose or persist the new field.

- [ ] **Step 3: Add `runtime_observability` to `RunState`**

In `orchestrator/state.py`:

- Add `runtime_observability: Optional[Dict[str, Any]] = None` to `RunState`.
- Include it in `to_dict()` only when not `None`.
- Load it in `from_dict()` using `data.get("runtime_observability")`.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/state.py tests/test_runtime_observability.py
git commit -m "feat(state): persist runtime observability sessions"
```

### Task 3: Session Lifecycle Helpers

**Files:**
- Modify: `orchestrator/runtime_observability.py`
- Modify: `tests/test_runtime_observability.py`

- [ ] **Step 1: Write failing lifecycle tests**

Cover:

- `open_executor_session(state, entrypoint="run", ...)` creates `exec-0001`.
- second open after a closed session creates `exec-0002`.
- `close_executor_session(..., session_id="exec-0001", status="completed")` stores `ended_at` and `duration_ms`.
- closing twice preserves the original duration.
- opening a new session reconciles an old dead open session as `abandoned`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: FAIL because lifecycle helpers are missing.

- [ ] **Step 3: Implement lifecycle helpers**

Add:

```python
def open_executor_session(state, *, entrypoint, pid=None, process_start_time=None, now=None, process_is_live=None) -> str:
    ...

def close_executor_session(state, *, session_id, status, now=None) -> None:
    ...

def reconcile_open_sessions(state, *, now=None, process_is_live=None, trusted_end_at=None) -> None:
    ...
```

Use the previous session's `started_at` plus `trusted_end_at` or `now` to compute abandoned duration only when a trusted endpoint exists. Prefer `state.updated_at` as the default trusted endpoint during reconciliation.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/runtime_observability.py tests/test_runtime_observability.py
git commit -m "feat(observability): manage executor runtime sessions"
```

### Task 4: Wire `run`

**Files:**
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `tests/test_cli_safety.py` or create `tests/test_runtime_observability_cli.py`

- [ ] **Step 1: Write failing CLI test**

Patch `WorkflowExecutor.execute` to return `{"status": "completed"}` and run `run_workflow(...)` against a tiny workflow. Assert the resulting `state.json` contains one closed `run` session with status `completed` and positive `duration_ms`.

- [ ] **Step 2: Run focused test**

Run:

```bash
pytest tests/test_runtime_observability_cli.py -v
```

Expected: FAIL because `run_workflow` does not open or close sessions.

- [ ] **Step 3: Wire session lifecycle around executor execution**

In `run_workflow`:

- After `state_manager.initialize(...)`, call `open_executor_session(...)`.
- Pass the session id into `write_process_metadata(..., executor_session_id=session_id)` if Task 6 adds that parameter; otherwise write normal metadata.
- Wrap `executor.execute(...)` and archive handling in `try/finally`.
- Close the session with `completed` or `failed` based on executor result.
- On exception, close with `failed` before returning.

- [ ] **Step 4: Run focused test**

Run:

```bash
pytest tests/test_runtime_observability_cli.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/cli/commands/run.py tests/test_runtime_observability_cli.py
git commit -m "feat(cli): record active runtime for workflow run"
```

### Task 5: Wire `resume`

**Files:**
- Modify: `orchestrator/cli/commands/resume.py`
- Modify: `tests/test_resume_command.py` or `tests/test_runtime_observability_cli.py`

- [ ] **Step 1: Write failing resume test**

Create an existing run state with one closed session and an old `updated_at`, invoke `resume_workflow(...)` with executor patched to complete, and assert a second session is added while the suspended gap is not counted.

- [ ] **Step 2: Run focused test**

Run:

```bash
pytest tests/test_runtime_observability_cli.py tests/test_resume_command.py -k runtime_observability -v
```

Expected: FAIL because `resume_workflow` does not create session records.

- [ ] **Step 3: Wire resume session lifecycle**

In `resume_workflow`:

- After state load/checksum validation and before executor execution, reconcile open sessions.
- Open an `entrypoint="resume"` session.
- Close with `completed`, `failed`, or `interrupted` in a `finally` block.
- Preserve existing exit codes, especially `130` for `KeyboardInterrupt`.

- [ ] **Step 4: Run focused test**

Run:

```bash
pytest tests/test_runtime_observability_cli.py tests/test_resume_command.py -k runtime_observability -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/cli/commands/resume.py tests/test_runtime_observability_cli.py tests/test_resume_command.py
git commit -m "feat(cli): record active runtime for workflow resume"
```

### Task 6: Reuse Process Identity Metadata

**Files:**
- Modify: `orchestrator/monitor/process.py`
- Modify: `tests/test_runtime_observability.py`

- [ ] **Step 1: Write failing process metadata test**

Assert `write_process_metadata(run_root, executor_session_id="exec-0001")` writes the session id and `read_process_metadata(...)` can expose it if the model supports extra fields. If `ProcessMetadata` is intentionally strict, assert the raw JSON includes the session id and callers tolerate its absence.

- [ ] **Step 2: Run focused tests**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: FAIL if the new argument is not accepted.

- [ ] **Step 3: Add optional session id**

Add optional `executor_session_id: str | None = None` to `write_process_metadata`. Persist it as `"executor_session_id"` when provided.

- [ ] **Step 4: Run tests**

Run:

```bash
pytest tests/test_runtime_observability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/monitor/process.py tests/test_runtime_observability.py
git commit -m "feat(monitor): tag process metadata with executor session"
```

### Task 7: Report Active Runtime

**Files:**
- Modify: `orchestrator/observability/report.py`
- Modify: `tests/test_observability_report.py`

- [ ] **Step 1: Write failing report tests**

Add tests that build a status snapshot with runtime sessions and assert:

- `snapshot["run"]["active_runtime_ms"]` is present.
- `snapshot["run"]["active_runtime"]` is human-readable.
- rendered markdown includes `active_runtime`.
- missing runtime state does not break reporting.

- [ ] **Step 2: Run focused tests**

Run:

```bash
pytest tests/test_observability_report.py -k runtime -v
```

Expected: FAIL because report snapshots do not include active runtime.

- [ ] **Step 3: Add snapshot and markdown fields**

In `build_status_snapshot(...)`, call `compute_active_runtime(...)` and merge the returned fields into `run_payload`.

In `render_status_markdown(...)`, render:

```markdown
- active_runtime: `...`
- executor_sessions: `...`
- suspended_gap_excluded: `...`
```

Only render values that are not `None`.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/test_observability_report.py -k runtime -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/observability/report.py tests/test_observability_report.py
git commit -m "feat(report): show active workflow runtime"
```

### Task 8: Spec and CLI Documentation

**Files:**
- Modify: `specs/state.md`
- Modify: `specs/observability.md`
- Modify: `specs/cli.md`

- [ ] **Step 1: Document state field**

In `specs/state.md`, add `runtime_observability` to the state schema list and describe executor-session records.

- [ ] **Step 2: Document observability semantics**

In `specs/observability.md`, document:

- active runtime excludes gaps between executor sessions.
- dashboards and reports may expose it.
- it does not drive workflow control.

- [ ] **Step 3: Document CLI report output**

In `specs/cli.md`, note that `report --format json` may include `run.active_runtime_ms`, `run.active_runtime`, `run.executor_session_count`, and `run.excluded_suspended_ms`.

- [ ] **Step 4: Run docs-adjacent focused tests**

Run:

```bash
pytest tests/test_observability_report.py tests/test_runtime_observability.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add specs/state.md specs/observability.md specs/cli.md
git commit -m "docs(spec): define active runtime observability"
```

### Task 9: End-to-End Smoke Check

**Files:**
- Modify only if failures reveal missing coverage.

- [ ] **Step 1: Run unit suite for touched areas**

Run:

```bash
pytest tests/test_runtime_observability.py tests/test_observability_report.py tests/test_runtime_observability_cli.py -v
```

Expected: PASS.

- [ ] **Step 2: Run a minimal orchestrator workflow**

Run an existing tiny example workflow, then report it:

```bash
python -m orchestrator run workflows/examples/hello.yaml
python -m orchestrator report --format json
```

Expected:

- run exits 0.
- report JSON includes non-null `run.active_runtime_ms`.
- no workflow YAML changes are required.

- [ ] **Step 3: Simulate resume gap**

Use a test or fixture state with one closed session, then resume. Confirm the reported active runtime excludes the artificial gap.

- [ ] **Step 4: Final status**

Record exact commands and outputs in the implementation summary. Do not claim completion unless the smoke check and focused tests pass.
