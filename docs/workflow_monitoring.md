# Workflow Monitoring

`orchestrator monitor` watches one or more configured workspaces and sends
headless email notifications when workflow runs complete, fail, crash, or stall.
It is an external observer: it does not mutate run state, resume workflows, kill
processes, or depend on workflow-authored finalization steps.

## Configuration

Create a monitor config outside the repository, for example:

```yaml
workspaces:
  - name: agent-orchestration
    path: /home/ollie/Documents/agent-orchestration
  - name: EasySpin
    path: /home/ollie/Documents/EasySpin
  - name: PtychoPINN
    path: /home/ollie/Documents/PtychoPINN

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

Secrets belong in environment variables, not in the config file:

```bash
export WORKFLOW_MONITOR_SMTP_USER='workflow-monitor@example.com'
export WORKFLOW_MONITOR_SMTP_PASSWORD='app-password-or-token'
```

## Dry Run

Verify scan and message content without sending email:

```bash
python -m orchestrator monitor \
  --config ~/.config/orchestrator/monitor.yaml \
  --once \
  --dry-run
```

By default, dry runs do not mark notifications as sent. To rehearse duplicate
suppression intentionally:

```bash
python -m orchestrator monitor \
  --config ~/.config/orchestrator/monitor.yaml \
  --once \
  --dry-run \
  --dry-run-mark-sent
```

## Headless Operation

Run under tmux:

```bash
tmux new-session -s orchestrator-monitor \
  'python -m orchestrator monitor --config ~/.config/orchestrator/monitor.yaml'
```

A systemd user service can run the same command if the service environment
provides the SMTP credential variables.

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
