# Workflow Monitoring

`orchestrator monitor` watches one or more configured workspaces and sends
headless email notifications when workflow runs complete, fail, crash, or stall.
It is an external observer: it does not mutate run state, resume workflows, kill
processes, or depend on workflow-authored finalization steps.

## Monitoring And Recovery Tools

`orchestrator monitor` is read-only observation. The
[generic run watchdog](../workflows/library/generic_run_watchdog/watchdog.orc)
is a retired launch surface kept as historical source; it does not inspect or
repair runs. The separate
[`watch_workflow_usage_limit.sh`](../scripts/watch_workflow_usage_limit.sh)
script watches a tmux pane and may send resume or run commands. It has a known
F50 edge: after a late refusal, an admitted fresh run can leave the watcher
following the old completed run. Check the fresh run ID manually; the behavior
is captured by strict-xfail test
[`test_a_late_refusal_of_a_fresh_run_retries_with_the_fresh_run_id`](../tests/test_watch_workflow_usage_limit.py).

## Provider Observation And Peer Messaging Are Different Surfaces

Runtime provider observation panes are ephemeral, process-local execution
views. The evaluated runtime opens them only for a program with target-2.38
agent sessions, best-effort, and degrades safely if observation is
unavailable; in a program without agent sessions no pane is opened. The target-2.16
`with-live-providers` and target-2.17 `with-live-provider-peers` groups are
retired with no evaluated port ([status](capability_status_matrix.md)); their
panes, endpoints, member ledgers and `provider_peer_group` state records
occur only in historical flat-route runs.

No pane is monitor, result, checkpoint, or resume authority.
Pane bytes and transcripts do not replace provider transport or validated
output bundles, and live tmux targets do not enter persisted workflow state.
Use `orchestrator report` and the run's derived `state.json` view for workflow
state. Do not use raw tmux `send-keys` to steer provider panes.

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
- `CRASHED`: for an evaluated run, the derived view reports `interrupted` (no
  writer holds `run.lock` and no terminal is recorded); for a historical
  flat-route run, the run still says `running`, but process metadata confirms
  the original workflow process is gone.
- `STALLED`: a historical flat-route run still says `running`, and the active
  execution cursor heartbeat, or fallback `state.updated_at`, is older than the
  configured stale threshold. Evaluated runs are never classified stalled;
  `stale_after_seconds` does not apply to them.

For historical flat-route call-based workflows, stale detection follows the
active execution cursor into running call frames before falling back to root
`updated_at`.

## After An Email

Use the suggested commands in the message:

```bash
cd <workspace>
python -m orchestrator report --run-id <run_id>
python -m orchestrator resume <run_id>
```

Inspect `.orchestrate/runs/<run_id>/state.json` and run-local logs if the email
reports `FAILED`, `CRASHED`, or `STALLED`.
