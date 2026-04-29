# Active Runtime Observability Design

## Problem

Workflow operators need to know how much time a workflow has actually spent executing across `run` and `resume` invocations. The current top-level `started_at` and `updated_at` timestamps are wall-clock lifecycle markers, so they include long gaps after a process exits or is interrupted and before a later resume starts.

That is the wrong number for operational questions like "how much executor time has this workflow consumed?" A run that executes for 20 minutes, sits overnight, then resumes for 5 minutes should report about 25 minutes of active runtime, not 12 hours and 25 minutes.

## Goals

1. Record active executor runtime across the lifetime of one run id.
2. Exclude suspended gaps between one executor process ending or crashing and a later resume process starting.
3. Surface the metric in `orchestrator report`, JSON status snapshots, and monitoring/dashboard projections.
4. Keep the feature observability-only: no timeout, deadline, routing, retry, or prompt behavior changes.
5. Preserve compatibility with existing `state.json` files that do not yet contain runtime-session data.

## Non-Goals

- No workflow-level `max_runtime`, budget, deadline, or kill behavior.
- No DSL control-flow condition based on elapsed runtime.
- No provider timeout changes. Step `timeout_sec` remains provider/command scoped.
- No prompt contract changes.
- No attempt to include idle time while no orchestrator executor process exists.
- No accumulation across `resume --force-restart`, because that creates a new run id.

## Core Model

Add run-level executor-session accounting to `state.json`. A session is one live invocation of the orchestrator executor for a run id: initial `run`, normal `resume`, or forced restart's new run.

The total active runtime is:

```text
sum(closed executor_session.duration_ms)
+ age(open executor_session) when the recorded process identity is still live
```

Suspended time is excluded because there is no open live executor session during the gap.

## State Shape

Add an additive top-level state field:

```json
{
  "runtime_observability": {
    "schema_version": 1,
    "executor_sessions": [
      {
        "session_id": "exec-0001",
        "entrypoint": "run",
        "pid": 12345,
        "process_start_time": "987654321",
        "started_at": "2026-04-29T10:00:00+00:00",
        "ended_at": "2026-04-29T10:20:00+00:00",
        "status": "completed",
        "duration_ms": 1200000
      },
      {
        "session_id": "exec-0002",
        "entrypoint": "resume",
        "pid": 12501,
        "process_start_time": "987664444",
        "started_at": "2026-04-29T22:15:00+00:00",
        "ended_at": null,
        "status": "running",
        "duration_ms": null
      }
    ]
  }
}
```

Session fields:

| Field | Meaning |
| --- | --- |
| `session_id` | Run-local monotonic id such as `exec-0003`. |
| `entrypoint` | `run` or `resume`; `resume-force-restart` starts a new run and records `run` on that new run. |
| `pid` | Process id for liveness checks. |
| `process_start_time` | Platform process-start token when available, matching `monitor_process.json`. |
| `started_at` | UTC timestamp when this executor process began owning the run. |
| `ended_at` | UTC timestamp when this executor process stopped owning the run. |
| `status` | `running`, `completed`, `failed`, `interrupted`, or `abandoned`. |
| `duration_ms` | Persisted duration for closed sessions only. |

This is an additive field under state schema `2.1`; no schema bump is required.

## Runtime Lifecycle

### Start

`orchestrator run` and `orchestrator resume` open an executor session after the run state is initialized or loaded, and before `WorkflowExecutor.execute(...)` starts.

Before opening a new session on an existing run, the runtime reconciles any previous open session:

- If the previous process identity is still live, opening a second owner fails.
- If the previous process identity is not live, close the previous session as `abandoned`.
- If identity cannot be proven, close it at the last trusted heartbeat or `state.updated_at`, whichever is available, and mark it `abandoned`.

### End

The CLI command closes the active session in a `finally` block:

- `completed` when the executor returns completed.
- `failed` when the executor returns failed or raises an exception after state loading.
- `interrupted` on `KeyboardInterrupt`.

The close operation is idempotent by `session_id`.

### Hard Crash

If the process is killed with `SIGKILL`, loses power, or otherwise cannot run cleanup, its session remains `running` in state. Reports must not count that open session until "now" forever.

For an open session, report logic checks process identity:

- If process identity matches and is live, include `now - started_at`.
- If process identity is definitively dead, count only until the latest trusted heartbeat, then display the session as `abandoned`.
- If identity cannot be confirmed, prefer the deepest active execution cursor heartbeat used by monitor stale detection; if stale, cap at that heartbeat rather than at report time.

This preserves the central invariant: once the executor process is no longer known to be alive, later wall-clock gap time is not counted as active runtime.

## Reporting Surface

`build_status_snapshot(...)` adds:

```json
{
  "run": {
    "active_runtime_ms": 1500000,
    "active_runtime": "25m 0s",
    "executor_session_count": 2,
    "current_executor_session": {
      "session_id": "exec-0002",
      "entrypoint": "resume",
      "status": "running",
      "started_at": "2026-04-29T22:15:00+00:00",
      "active_ms": 300000
    },
    "excluded_suspended_ms": 42900000
  }
}
```

Markdown reports add the active runtime under the run section:

```markdown
- active_runtime: `25m 0s`
- executor_sessions: `2`
- suspended_gap_excluded: `11h 55m`
```

`excluded_suspended_ms` is informational. It is computed from gaps between adjacent sessions and never drives control flow.

## DSL Boundary

This feature is runtime observability, not workflow authoring semantics.

Do not add a top-level DSL field such as:

```yaml
runtime:
  max_total: 6h
```

Do not expose runtime elapsed values to `when`, `assert`, `goto`, or provider prompts in the initial implementation. If a future feature needs read-only variables like `${run.active_runtime_ms}`, it should be designed separately and must state that those variables are advisory unless a later control-flow spec explicitly says otherwise.

## File Responsibilities

| File | Responsibility |
| --- | --- |
| `orchestrator/runtime_observability.py` | Pure session accounting helpers: open, close, reconcile, compute active runtime. |
| `orchestrator/state.py` | Persist and round-trip `runtime_observability` without changing older state loading. |
| `orchestrator/cli/commands/run.py` | Open and close a session around initial executor invocation. |
| `orchestrator/cli/commands/resume.py` | Reconcile old open session, then open and close a resume session. |
| `orchestrator/observability/report.py` | Add active runtime fields to status snapshots and markdown. |
| `orchestrator/monitor/process.py` | Reuse process identity helpers; optionally include session id in `monitor_process.json`. |
| `specs/state.md` | Document the additive state field. |
| `specs/observability.md` | Document report/status fields and the no-control-flow guarantee. |
| `specs/cli.md` | Document `report` output semantics. |

## Invariants

1. Active runtime is never greater than wall-clock time from `started_at` to report time.
2. Time between a closed session and the next session is excluded.
3. Closing a session twice does not double-count time.
4. A new resume never silently leaves two live owner sessions for one run id.
5. Missing `runtime_observability` is treated as unknown/unavailable, not as zero.
6. The metric is advisory and read-only.

## Test Strategy

Unit tests should use an injectable clock and fake process-identity checker.

Required cases:

1. One closed session reports its duration.
2. Closed session plus live open session reports closed duration plus current age.
3. Gap between two sessions is excluded.
4. Reopening after an orphaned session caps the orphan at trusted heartbeat and marks it abandoned.
5. Closing the same session twice is idempotent.
6. Existing states without `runtime_observability` still load and report successfully.
7. `run` and `resume` open and close sessions around executor execution.
8. `report --format json` includes `run.active_runtime_ms`.
9. Markdown report renders active runtime without implying a timeout or limit.

## Rollout

Implement this as an additive runtime/reporting change:

1. Add pure accounting helpers and tests.
2. Persist the new state field.
3. Wire CLI `run` and `resume`.
4. Wire reports.
5. Update specs.
6. Run focused unit tests and a minimal orchestrator smoke check.

No workflow YAML migration is required.
