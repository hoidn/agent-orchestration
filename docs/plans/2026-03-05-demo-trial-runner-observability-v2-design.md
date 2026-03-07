# Demo Trial Runner Observability v2 Design

**Goal:** Define the observability contract for a `v2` direct-vs-workflow trial runner so real trials can be monitored, interrupted, resumed, and audited without relying on ad hoc `ps`, `git status`, or manual workspace inspection.

**Architecture:** Add a runner-level state and archive contract that sits above the existing workflow engine and below the operator-facing runbook. The runner should emit durable status files, live per-arm logs, timeout/termination metadata, and partial results even when a trial does not finish cleanly. `tmux` may be used as an execution backend, but observability must come from runner-owned artifacts, not from interactive panes alone.

**Tech Stack:** Python, filesystem JSON/Markdown artifacts, subprocess or tmux-backed process execution, existing demo provisioning and evaluator scripts.

---

## Scope

This document defines observability requirements for the demo coordination layer implemented around:
- `scripts/demo/run_trial.py`
- `orchestrator/demo/trial_runner.py`

It does not redefine the workflow engine's own `.orchestrate/runs/<run_id>/` observability model. That model already covers workflow-internal state and logs. The problem here is the outer coordination path that provisions workspaces, launches both arms, waits for completion, freezes metadata, and runs the evaluator.

## Problem Statement

The current runner is operationally weak in three ways:
- it launches each arm via blocking `subprocess.run(...)`, so there is no live progress record while an arm is still running
- it only writes final metadata after both arms complete, so an interrupted or long-running trial leaves a partial archive with almost no diagnostic value
- it gives operators no stable machine-readable place to inspect current status, elapsed time, PID/session ownership, timeout state, or partial evaluation/freeze state

This forces manual process inspection and filesystem poking, which is exactly the kind of ad hoc recovery path the demo is supposed to avoid.

## Design Goals

Required goals:
- make in-flight trial state observable from disk without attaching to a child process
- preserve useful partial artifacts when a trial is interrupted, times out, or crashes
- support long-running direct or workflow arms without requiring the operator to guess whether progress is being made
- keep the contract runner-owned and backend-agnostic so subprocess and tmux backends can share one archive model
- make postmortems and grading possible even when only one arm finished

Non-goals:
- real-time UI beyond file-based status snapshots
- changing the workflow YAML or hidden evaluator contract
- introducing workflow-engine concepts into the direct arm
- claiming true parallelism; the current runner may remain serial until a separate scheduling change is made

## Core Principle

Observability must be based on runner-owned files in `archive/`, not on the child process's willingness to print useful output.

That means every meaningful runner state transition should be persisted before the next blocking operation begins.

## Required Archive Layout

`v2` should extend the existing archive layout like this:

```text
<experiment-root>/
  trial-metadata.json
  archive/
    runner-state.json
    runner-events.jsonl
    direct-command.json
    workflow-command.json
    direct-run-metadata.json
    workflow-run-metadata.json
    trial-result.json
    partial-trial-result.json
    direct/
      process.json
      heartbeat.json
      stdout.log
      stderr.log
      status.json
      freeze/
        workspace-status.txt
        workspace-head.txt
    workflow/
      process.json
      heartbeat.json
      stdout.log
      stderr.log
      status.json
      freeze/
        workspace-status.txt
        workspace-head.txt
    evaluator/
      direct-result.json
      workflow-result.json
      status.json
```

Rules:
- `runner-state.json` is the current canonical status snapshot for the whole trial
- `runner-events.jsonl` is append-only and records all state transitions in time order
- per-arm logs must be written incrementally while the arm is running, not only after exit
- `partial-trial-result.json` must exist whenever the trial has started, even if incomplete
- `trial-result.json` is written only when the runner reaches terminal state

## Runner State Model

`archive/runner-state.json` should be rewritten on every significant transition.

Minimum schema:

```json
{
  "trial_id": "20260305-abcdef",
  "started_at": "2026-03-05T21:26:25Z",
  "updated_at": "2026-03-05T21:30:12Z",
  "status": "running",
  "mode": "serial",
  "start_commit": "50baf80cf2f62531f8fb0a7759ce5931ea324f64",
  "seed_repo": "/abs/path/to/seed-repo",
  "task_file": "/abs/path/to/task.md",
  "current_phase": "direct_execution",
  "direct": {
    "status": "running",
    "started_at": "...",
    "finished_at": null,
    "exit_code": null,
    "timed_out": false,
    "workspace": "/abs/path/to/direct-run",
    "stdout_log": "archive/direct/stdout.log",
    "stderr_log": "archive/direct/stderr.log",
    "heartbeat": "archive/direct/heartbeat.json",
    "process": "archive/direct/process.json"
  },
  "workflow": {
    "status": "pending",
    "started_at": null,
    "finished_at": null,
    "exit_code": null,
    "timed_out": false,
    "workspace": "/abs/path/to/workflow-run"
  },
  "evaluation": {
    "status": "pending",
    "direct_verdict": null,
    "workflow_verdict": null
  }
}
```

Allowed top-level `status` values:
- `provisioning`
- `running`
- `freezing`
- `evaluating`
- `completed`
- `failed`
- `terminated`
- `timed_out`

Per-arm status values:
- `pending`
- `running`
- `succeeded`
- `failed`
- `terminated`
- `timed_out`
- `skipped`

## Event Stream

`archive/runner-events.jsonl` should record one JSON object per event.

Minimum event types:
- `trial_started`
- `provisioning_completed`
- `arm_started`
- `arm_heartbeat`
- `arm_stdout_spill` or `arm_log_rotated` if relevant later
- `arm_completed`
- `arm_timeout`
- `arm_terminated`
- `freeze_started`
- `freeze_completed`
- `evaluation_started`
- `evaluation_completed`
- `trial_completed`
- `trial_failed`

Why both snapshot and event log:
- snapshot is easy for operators and future report commands
- event log preserves history and makes postmortem sequencing unambiguous

## Per-Arm Process Contract

Each arm should write `archive/<arm>/process.json` before waiting for completion.

Minimum fields:
- command argv
- cwd
- PID
- parent PID if known
- launcher backend: `subprocess` or `tmux`
- start time
- timeout seconds
- backend-specific IDs if applicable

If the backend is `tmux`, add:
- session name
- window name
- pane ID

This is where tmux belongs. It is useful as a backend identity and control surface, but not as the primary source of truth.

## Heartbeats

Each arm should rewrite `archive/<arm>/heartbeat.json` on a fixed interval while that arm is active.

Minimum fields:
- wall-clock timestamp
- elapsed seconds
- process still alive: boolean
- bytes currently written to stdout/stderr logs
- latest known workspace git status check timestamp, if collected
- optional note such as `"phase": "waiting_on_child"`

Heartbeat rules:
- target interval: 5 to 15 seconds
- missing heartbeat beyond `2 * interval + grace` should be treated as runner-health degradation
- heartbeat emission must not depend on child output; it is owned by the runner

## Logs

The runner must stream child output to on-disk log files while the child is running.

Required files per arm:
- `archive/<arm>/stdout.log`
- `archive/<arm>/stderr.log`

Rules:
- logs are append-only for the lifetime of one trial
- logs must be available even if the child is later killed or times out
- final `status.json` may include a tail summary, but the full logs remain authoritative
- the runner may still capture summarized stdout/stderr into `trial-result.json`, but that is secondary

## Timeouts and Termination

`v2` must make timeout behavior explicit.

Required config surface:
- `--direct-timeout-sec`
- `--workflow-timeout-sec`
- optional `--evaluation-timeout-sec`

Rules:
- timeout expiry must update per-arm status and event log before termination is attempted
- termination path must record whether the process exited cleanly after signal escalation
- timeout or forced termination of one arm must still produce partial freeze metadata for that arm
- a timed-out direct arm must not prevent writing workflow `pending` or `skipped` status into archive artifacts

## Freeze Semantics

The current runbook promises freeze behavior that the current runner does not actually implement. `v2` needs a smaller but real contract.

Required freeze artifacts per arm:
- `archive/<arm>/freeze/workspace-status.txt`
- `archive/<arm>/freeze/workspace-head.txt`
- `archive/<arm>/freeze/tree.txt` or equivalent manifest

Optional later enhancement:
- a tarball or zip snapshot of the workspace

Minimal requirement for `v2`:
- capture workspace git status, git head, and deterministic file manifest before evaluation starts
- do this even if the arm failed or timed out, as long as the workspace exists

## Partial Results Contract

`archive/partial-trial-result.json` should always exist once trial execution begins.

It should be rewritten after:
- direct arm completion or failure
- workflow arm completion or failure
- freeze completion for either arm
- evaluator completion for either arm

This file is the recovery-safe summary. If the runner crashes before terminal state, operators should still be able to answer:
- which arm started
- which arm finished
- with what exit code or timeout state
- whether evaluation ran
- where the logs live

## Evaluator Observability

Evaluator execution should follow the same pattern:
- `archive/evaluator/status.json`
- `archive/evaluator/direct-result.json`
- `archive/evaluator/workflow-result.json`

Rules:
- evaluator start/end timestamps must be recorded
- evaluator command must be archived
- invalid evaluator output must still produce a structured failure artifact, not just disappear into stderr

## Backend Choice: Subprocess vs tmux

Recommended design:
- keep the archive/state contract backend-agnostic
- allow two execution backends:
  - `subprocess` as the default local backend
  - `tmux` as an optional long-running interactive backend

Trade-offs:
- `subprocess` is simpler to test and reason about
- `tmux` is better for operator attachment and long-running sessions
- neither backend removes the need for runner-owned logs, heartbeats, or state files

Recommendation:
- implement observability contract first with `subprocess.Popen`
- add `tmux` backend only if operator attachment is actually needed after the archive contract exists

## Minimal CLI Additions

Suggested new flags:
- `--direct-timeout-sec`
- `--workflow-timeout-sec`
- `--heartbeat-sec`
- `--runner-backend subprocess|tmux`
- `--resume-existing-trial` only if resume is explicitly added later

Do not add resume in the same pass unless the archive/state contract is already stable.

## Acceptance Criteria

A `v2` runner is not done until these cases are verifiably true:
- when the direct arm is running for several minutes, `archive/runner-state.json` and `archive/direct/heartbeat.json` continue updating
- when a trial is interrupted mid-run, `partial-trial-result.json` still exists and points to the correct per-arm logs
- when a child times out, the archive records `timed_out: true`, termination events, and freeze artifacts
- when the workflow arm never starts because the direct arm fails first in serial mode, the archive still records workflow status as `pending` or `skipped`, not implicit absence
- when evaluation is missing or invalid, the archive contains a structured evaluator failure artifact rather than `null` with no explanation

## Testing Strategy

The implementation should be tested in layers.

Unit tests:
- state snapshot writing
- event log appends
- timeout transition handling
- partial-result rewriting
- per-arm process metadata serialization

Integration tests:
- fake long-running child updates heartbeat and logs while alive
- interrupted runner leaves partial archive
- timeout path produces freeze + status artifacts
- evaluator invalid JSON produces structured failure output

Real smoke test:
- run one real local trial against the linear-classifier seed with short but nonzero timeouts
- verify that the archive can be inspected meaningfully before completion and after termination

## Recommended Sequencing

Implementation order:
1. introduce runner state snapshot and event log
2. switch from blocking `subprocess.run` to streamed `Popen`
3. add per-arm log files and heartbeats
4. add timeout and termination recording
5. add partial result rewriting
6. add real freeze manifests
7. optionally add tmux backend after the archive contract is stable

## Bottom Line

The core defect is not just “there are no logs.” The real defect is that the coordination layer has no durable model of a trial while it is still in flight.

`v2` should fix that by making the runner observable as a state machine with append-only events, live per-arm logs, periodic heartbeats, explicit timeout behavior, and partial-result persistence. `tmux` can improve operator ergonomics, but it is not the observability contract.
