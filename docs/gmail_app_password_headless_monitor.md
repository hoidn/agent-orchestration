# Gmail App Password For Headless Workflow Monitoring

This guide explains how to create a Gmail app password for
`orchestrator monitor` on a headless machine.

You cannot create the app password fully headlessly. Google requires an
interactive browser login to the Google Account security page. After the app
password exists, using it from the workflow monitor is headless.

## Create The App Password

1. On any machine with a browser, sign into the Gmail account that will send
   monitor emails.

2. Open Google Account security settings:

   ```text
   https://myaccount.google.com/security
   ```

3. Enable 2-Step Verification if it is not already enabled.

4. Open App Passwords:

   ```text
   https://myaccount.google.com/apppasswords
   ```

5. Create a new app password. A clear name is:

   ```text
   orchestrator-monitor
   ```

6. Copy the generated 16-character password. Google shows it once.

## Configure The Headless Machine

Set the SMTP credentials in the shell or service environment that launches the
monitor:

```bash
export WORKFLOW_MONITOR_SMTP_USER='workflow-monitor@example.com'
export WORKFLOW_MONITOR_SMTP_PASSWORD='xxxx xxxx xxxx xxxx'
```

The monitor config should reference those environment variable names:

```yaml
email:
  backend: smtp
  from: workflow-monitor@example.com
  to:
    - workflow-alerts@example.com
  smtp_host: smtp.gmail.com
  smtp_port: 587
  use_starttls: true
  username_env: WORKFLOW_MONITOR_SMTP_USER
  password_env: WORKFLOW_MONITOR_SMTP_PASSWORD
```

## Verify Without Sending

```bash
python -m orchestrator monitor \
  --config ~/.config/orchestrator/monitor.yaml \
  --once \
  --dry-run
```

## Launch In tmux

If the Gmail credentials are in `~/.config/orchestrator/monitor.env`, source
that file in the tmux command:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock new -d -s orchestrator-monitor \
  'cd /home/ollie/Documents/agent-orchestration && source ~/.config/orchestrator/monitor.env && python -m orchestrator monitor --config ~/.config/orchestrator/monitor.yaml'
```

Check output:

```bash
tmux -S /tmp/claude-tmux-sockets/claude.sock capture-pane -p -J -t orchestrator-monitor:0.0 -S -100
```

## Notes

- If the Gmail account password changes, Google may revoke app passwords.
- Keep the app password out of repository files.
- For long-term service use, put the environment variables in a user-level
  systemd environment file or another local secret store, not in the monitor
  YAML.
