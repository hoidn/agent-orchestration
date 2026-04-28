"""Workflow monitor command implementation."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orchestrator.monitor.classifier import classify_run
from orchestrator.monitor.config import load_monitor_config
from orchestrator.monitor.emailer import SmtpEmailSender
from orchestrator.monitor.ledger import NotificationLedger
from orchestrator.monitor.messages import render_event_email
from orchestrator.monitor.scanner import scan_monitor_runs


def monitor_workflows(
    config: str,
    once: bool = False,
    dry_run: bool = False,
    dry_run_mark_sent: bool = False,
    ledger: str | None = None,
    **_: Any,
) -> int:
    """Monitor configured workspaces and notify on terminal/suspect events."""

    if dry_run_mark_sent and not dry_run:
        print("Error: --dry-run-mark-sent requires --dry-run", file=sys.stderr)
        return 1
    try:
        monitor_config = load_monitor_config(config)
        ledger_path = Path(ledger).expanduser() if ledger else Path("~/.orchestrator-monitor/notifications.json").expanduser()
        notification_ledger = NotificationLedger.load(ledger_path)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    sender = SmtpEmailSender(monitor_config.email)
    try:
        while True:
            handled = _scan_and_notify(
                monitor_config,
                notification_ledger,
                sender,
                dry_run=dry_run,
                mark_dry_run_sent=dry_run_mark_sent,
            )
            if once:
                if handled == 0:
                    print("No monitor notifications")
                return 0
            time.sleep(monitor_config.monitor.poll_interval_seconds)
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _scan_and_notify(
    monitor_config,
    notification_ledger: NotificationLedger,
    sender: SmtpEmailSender,
    *,
    dry_run: bool,
    mark_dry_run_sent: bool,
) -> int:
    handled = 0
    now = datetime.now(timezone.utc)
    for run in scan_monitor_runs(monitor_config):
        event = classify_run(
            run,
            now=now,
            stale_after_seconds=monitor_config.monitor.stale_after_seconds,
        )
        if event is None or notification_ledger.has_sent(event):
            continue
        message = render_event_email(event, monitor_config)
        result = sender.send(message, dry_run=dry_run)
        if dry_run:
            print(result.preview.rstrip())
        if result.sent or mark_dry_run_sent:
            notification_ledger.mark_sent(event, sent_at=now.isoformat())
            notification_ledger.save()
        handled += 1
    return handled
