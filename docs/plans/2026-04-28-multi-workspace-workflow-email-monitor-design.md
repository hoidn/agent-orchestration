# Multi-Workspace Workflow Email Monitor Design

## Goal

Provide headless email notifications when orchestrator workflows across multiple
repositories complete, fail, crash, or appear stalled. The monitor should work
for concurrent runs in different workspaces and should remain useful when a
workflow process dies before it can run any workflow-authored cleanup or final
notification step.

## Context

The authoritative run record is still each workspace's
`.orchestrate/runs/<run_id>/state.json`. That state already records persisted
run status, workflow file, timestamps, `current_step`, step results, run-level
errors, and step-level errors. Long-running steps already refresh
`current_step.last_heartbeat_at`, and dashboard projection code already derives
read-only stale-running display status from heartbeat age.

This feature should reuse those observability surfaces. It should not make
workflow YAML responsible for crash detection, and it should not mutate
`state.json` while monitoring.

## Proposed Shape

Add a central monitor command that watches an explicit list of workspaces:

```bash
python -m orchestrator monitor --config ~/.config/orchestrator/monitor.yaml
```

The config lists workspaces and headless email settings:

```yaml
workspaces:
  - name: agent-orchestration
    path: /home/ollie/Documents/agent-orchestration
  - name: EasySpin
    path: /home/ollie/Documents/EasySpin
  - name: PtychoPINN
    path: /home/ollie/Documents/PtychoPINN
  - name: ptychopinnpaper2
    path: /home/ollie/Documents/ptychopinnpaper2

monitor:
  poll_interval_seconds: 60
  stale_after_seconds: 900

email:
  backend: smtp
  from: workflow-monitor@example.com
  to:
    - user@example.com
  smtp_host: smtp.example.com
  smtp_port: 587
  use_starttls: true
  username_env: WORKFLOW_MONITOR_SMTP_USER
  password_env: WORKFLOW_MONITOR_SMTP_PASSWORD
```

The first version should require explicit workspace config. Auto-discovery under
`/home/ollie/Documents` can be added later as an opt-in convenience, but it
should not be the default because stale scratch runs and copied run directories
would create unpredictable email noise.

## Event Model

For each configured workspace, the monitor scans
`.orchestrate/runs/*/state.json` and classifies each run:

- `COMPLETED`: persisted `state.status` is `completed`.
- `FAILED`: persisted `state.status` is `failed`.
- `CRASHED`: persisted `state.status` is `running`, but the launcher process,
  recorded process, or known tmux session is confirmed gone. A bare live PID is
  not enough to suppress crash/stalled detection; process identity should use a
  platform start token where available to avoid PID-reuse false negatives.
- `STALLED`: persisted `state.status` is `running` and the current step
  heartbeat or state update is older than `stale_after_seconds`.

When an active execution cursor exposes `last_heartbeat_at`, stale detection
should prefer the deepest active heartbeat over `state.updated_at`, including
heartbeats inside running reusable call frames. Falling back to
`state.updated_at` is acceptable only when no active cursor heartbeat exists.

The monitor should label process absence and stale heartbeat differently. A
missing process is a stronger crash signal; stale heartbeat while a process may
still exist should be reported as stalled or suspect, not as a confirmed crash.

## Notification Ledger

The monitor keeps its own small ledger outside the watched repositories, for
example:

```text
~/.orchestrator-monitor/notifications.json
```

The ledger records `(workspace path, run directory id, event kind)` entries that
have already been sent. This prevents duplicate emails across monitor restarts.
By default, send one terminal notification per run. A later extension can add
repeat reminders for long-running stalled states, but v1 should avoid repeated
email loops.

## Email Content

Each email should include enough context to decide what to do without opening
the repository immediately:

- workspace name and path
- run id and run directory
- workflow file
- event kind and persisted run status
- started, updated, heartbeat, and duration fields when available
- current step or failed step
- run-level or step-level error type and message
- capped stdout and stderr previews from run-local step logs when available
- workflow outputs and high-value artifact paths when present
- suggested local commands, such as `python -m orchestrator report --run-id ...`
  and `python -m orchestrator resume ...`

Message composition should be deterministic and local. No provider call is
needed to summarize the run.

Email bodies must be bounded and conservative. They should read only run-local
logs, cap previews, exclude prompt audits and provider-session transport logs by
default, and redact configured SMTP secret values plus simple secret-looking
key/value lines before rendering. Larger or more sensitive artifacts should be
linked by path rather than embedded.

## Delivery

The first backend should be SMTP using environment-variable secrets. This is
compatible with headless machines and avoids browser/OAuth flows.

Required behavior:

- read username/password only from configured environment variable names
- never write secrets into state, logs, or notification ledgers
- support `--dry-run` to print or write the would-be email without sending
- keep `--dry-run` from marking notifications as sent unless an explicit
  rehearsal flag such as `--dry-run-mark-sent` is used
- fail closed when email config is missing or invalid

A local `sendmail` backend can be added later for machines that already have a
mail transfer agent configured.

## Integration Boundaries

The monitor is an external observer, not workflow control flow.

- It does not change run status.
- It does not reconcile stale running state.
- It does not resume or kill workflows.
- It does not depend on any workflow-authored finalization step.
- It may reuse pure projection helpers used by dashboard/report code, but it
  must not call mutating report paths that self-heal state.

This boundary matters because the feature is specifically meant to report
failures when workflow control is broken.

## Specification And Documentation Updates

The implementation must update the discoverable contract surfaces along with
the monitor code. The feature has both normative behavior and operational setup;
those should not be mixed into one hidden design document.

Normative updates:

- `specs/observability.md` must describe the monitor as a read-only observer,
  the event kinds (`COMPLETED`, `FAILED`, `CRASHED`, `STALLED`), heartbeat
  precedence over `state.updated_at`, notification-ledger de-duplication, and
  the requirement that monitoring does not mutate run state.
- `specs/cli.md` must document the `orchestrator monitor` command surface,
  including `--config`, `--once`, `--dry-run`, expected exit behavior, and the
  relationship between polling mode and single-scan mode.
- If implementation adds durable process or tmux-session sidecars, the owning
  spec must define their schema and lifecycle before the monitor depends on
  them for confirmed crash classification.

Operational documentation:

- Add a discoverable runbook, for example `docs/workflow_monitoring.md`, with
  setup instructions, a full config example, SMTP environment variables,
  headless operation notes, suggested tmux or systemd launch commands, dry-run
  verification, and guidance for interpreting completion, failure, crashed, and
  stalled emails.
- Update `docs/index.md` so operators can find the monitoring runbook from the
  documentation hub.
- Add a short pointer from `README.md` or another existing quick-start surface
  to the monitoring command and runbook.

The config file format is operational configuration, not a workflow DSL
extension. Its behavior should be documented in the runbook and CLI docs, while
the event semantics and read-only guarantees belong in the specs.

## Testing Strategy

Unit tests should cover:

- scanning multiple workspace roots
- ignoring workspaces without `.orchestrate/runs`
- event classification for completed, failed, crashed, and stalled runs
- heartbeat preference over `state.updated_at`
- notification ledger de-duplication
- SMTP backend dry-run behavior without network access
- redaction of configured secret values from logs and rendered messages
- documentation coverage for the CLI/spec/runbook/index surfaces, without
  asserting exact prompt or prose phrasing

Integration or CLI smoke tests should create temporary workspace roots with
sample run states and run the monitor in `--once --dry-run` mode.

## Open Follow-Ups

- Whether launch commands should persist process metadata in run state or a
  run-local sidecar to make process-gone detection more precise.
- Whether tmux-launched workflows should write a session identifier sidecar at
  launch time.
- Whether dashboard and monitor should share a single read-only run projection
  module for stale-running classification.
- Whether users want optional repeat reminders for stalled runs after v1 proves
  useful.
