# Workflow Monitoring

`orchestrator monitor` watches one or more configured workspaces and sends
headless email notifications when workflow runs complete, fail, crash, or stall.
It is an external observer: it does not mutate run state, resume workflows, kill
processes, or depend on workflow-authored finalization steps.

## Provider Observation And Peer Messaging Are Different Surfaces

Runtime provider observation panes are ephemeral, process-local execution
views. Ordinary provider invocations attempt them by default and degrade
safely if observation is unavailable. A target-2.16
`with-live-providers` group instead requires both initial panes through
directive selection because the supervisor's observation edge is part of that
node's control contract.

Neither kind of pane is monitor, result, checkpoint, or resume authority.
Pane bytes and transcripts do not replace provider transport or validated
output bundles, and live tmux targets do not enter persisted workflow state.
Use `orchestrator report` and `state.json` for workflow truth. Do not use raw
tmux `send-keys` to steer provider panes.

A target-2.17 `with-live-provider-peers` group uses separate
runtime-owned interactive client panes and an attempt-bound local endpoint.
Those resources exist only to implement natural turn-boundary
`peer-ready`/`peer-send`/`peer-ack`/`peer-finish`; they are not monitor
targets, and an operator must not inject raw pane input. The endpoint and
opaque member credentials are ephemeral and never enter persisted workflow
values, checkpoints, or reusable evidence.

While a peer group is active, `state.json` identifies the running cursor with
`current_step.type: provider_peer_group`. A normally completed or reportable
failed group stores a small `debug.provider_peer_group` record containing:

- `terminal_evidence_path`;
- `terminal_evidence_schema_version`, with value
  `provider_peer_group_terminal_evidence.v1`; and
- `outcome: completed|failed`.

`orchestrator report` preserves that typed step kind and debug pointer,
including when it must build a state-only report. The referenced group
evidence records the exact visit, terminal member attempts and lifecycles,
receiver-ledger digests/counts, frozen-bundle digests, available
natural-shutdown or failed-cleanup proofs, endpoint
drain/close/worker-join proof, and settlement digest or structured failure.
Per-member run-owned paths retain:

```text
provider-peer-group/<node>/visits/<visit>/members/<member>/attempt-<ordinal>/
  prompt-dependencies.json
  injected-messages.jsonl
  evidence.json
  provisional-result.json
```

The message ledger distinguishes `recorded`, `offered`, `offer_failed`, and
`receiver_acknowledged`. These names are deliberately narrow: none asserts
that a model saw, understood, or acted on content. The settled step result
remains the workflow value; ledgers, panes, transcripts, and provisional
member bundles are evidence only.

Fail-closed launch cleanup that cannot prove a complete boundary before a
member handle exists deliberately publishes no terminal group evidence; do
not infer a successful or complete peer lifecycle from an ordinary failed
step record in that case.

If a process crash leaves a running peer-group visit, ordinary resume
quarantines that whole visit before any new provider launch. The quarantine
is sticky and messages are never retargeted to replacement attempts. Use the
persisted failure/report evidence to decide whether an explicit force restart
or a new run is appropriate.

## Configuration

Create a monitor config outside the repository, for example:

```json
{
  "workspaces": [
    {
      "name": "agent-orchestration",
      "path": "/home/ollie/Documents/agent-orchestration"
    },
    {
      "name": "EasySpin",
      "path": "/home/ollie/Documents/EasySpin"
    },
    {
      "name": "PtychoPINN",
      "path": "/home/ollie/Documents/PtychoPINN"
    }
  ],
  "monitor": {
    "poll_interval_seconds": 60,
    "stale_after_seconds": 900
  },
  "email": {
    "backend": "smtp",
    "from": "workflow-monitor@example.com",
    "to": [
      "user@example.com"
    ],
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "use_starttls": true,
    "username_env": "WORKFLOW_MONITOR_SMTP_USER",
    "password_env": "WORKFLOW_MONITOR_SMTP_PASSWORD"
  }
}
```

Secrets belong in environment variables, not in the config file:

```bash
export WORKFLOW_MONITOR_SMTP_USER='workflow-monitor@example.com'
export WORKFLOW_MONITOR_SMTP_PASSWORD='app-password-or-token'
```

For Gmail on a headless machine, see
[`gmail_app_password_headless_monitor.md`](gmail_app_password_headless_monitor.md).

## Dry Run

Verify scan and message content without sending email:

```bash
python -m orchestrator monitor \
  --config ~/.config/orchestrator/monitor.json \
  --once \
  --dry-run
```

By default, dry runs do not mark notifications as sent. To rehearse duplicate
suppression intentionally:

```bash
python -m orchestrator monitor \
  --config ~/.config/orchestrator/monitor.json \
  --once \
  --dry-run \
  --dry-run-mark-sent
```

## Headless Operation

Run under tmux. If credentials live in an env file, source it in the tmux
command so the monitor process receives the SMTP variables without putting
secrets in the repository:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock new -d -s orchestrator-monitor \
  'cd /home/ollie/Documents/agent-orchestration && source ~/.config/orchestrator/monitor.env && python -m orchestrator monitor --config ~/.config/orchestrator/monitor.json'
```

A systemd user service can run the same command if the service environment
provides the SMTP credential variables.

Inspect the tmux monitor process:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t orchestrator-monitor:0.0 -S -100
```

## Event Meanings

- `COMPLETED`: the persisted run status is `completed`.
- `FAILED`: the persisted run status is `failed`.
- `CRASHED`: the run still says `running`, but process metadata confirms the
  original workflow process is gone.
- `STALLED`: the run still says `running`, and the active execution cursor
  heartbeat, or fallback `state.updated_at`, is older than the configured stale
  threshold.

For call-based workflows, stale detection follows the active execution cursor
into running call frames before falling back to root `updated_at`.

## After An Email

Use the suggested commands in the message:

```bash
cd <workspace>
python -m orchestrator report --run-id <run_id>
python -m orchestrator resume <run_id>
```

Inspect `.orchestrate/runs/<run_id>/state.json` and run-local logs if the email
reports `FAILED`, `CRASHED`, or `STALLED`.
