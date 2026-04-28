# Multi-Workspace Workflow Email Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `orchestrator monitor`, a headless multi-workspace workflow monitor that emails once when configured runs complete, fail, crash, or stall.

**Architecture:** Add a focused `orchestrator.monitor` package for config parsing, workspace scanning, event classification, notification de-duplication, message rendering, and email delivery. Reuse existing run-state and heartbeat surfaces, add a small run-local process metadata sidecar from `run`/`resume` for confirmed process-gone crash detection, and keep the monitor read-only with respect to `state.json`.

**Tech Stack:** Python stdlib (`argparse`, `dataclasses`, `email.message`, `json`, `os`, `smtplib`, `time`), existing PyYAML dependency, pytest, current orchestrator CLI/state/dashboard observability patterns.

---

## File Structure

- Create `orchestrator/monitor/__init__.py`: public monitor package exports.
- Create `orchestrator/monitor/config.py`: load and validate monitor YAML config.
- Create `orchestrator/monitor/models.py`: dataclasses and event enums.
- Create `orchestrator/monitor/scanner.py`: scan configured workspaces for run states, reusing dashboard scanner behavior where practical.
- Create `orchestrator/monitor/process.py`: write/read run process sidecar and check PID liveness.
- Create `orchestrator/monitor/classifier.py`: classify `COMPLETED`, `FAILED`, `CRASHED`, `STALLED`, or no event.
- Create `orchestrator/monitor/ledger.py`: notification de-duplication ledger outside watched repos.
- Create `orchestrator/monitor/messages.py`: deterministic subject/body rendering.
- Create `orchestrator/monitor/emailer.py`: SMTP backend and dry-run delivery.
- Create `orchestrator/cli/commands/monitor.py`: CLI command implementation.
- Modify `orchestrator/cli/main.py`: add `monitor` subcommand and dispatch.
- Modify `orchestrator/cli/commands/__init__.py`: export `monitor_workflows`.
- Modify `orchestrator/cli/commands/run.py` and `orchestrator/cli/commands/resume.py`: write process metadata sidecar once a run root exists.
- Modify `specs/observability.md`: normative monitor event/read-only/ledger semantics.
- Modify `specs/cli.md`: monitor command, flags, and exit behavior.
- Create `docs/workflow_monitoring.md`: operational setup and headless email runbook.
- Modify `docs/index.md`: add monitoring runbook entry.
- Modify `README.md`: add a short common-command pointer.
- Create tests:
  - `tests/test_monitor_config.py`
  - `tests/test_monitor_classifier.py`
  - `tests/test_monitor_ledger.py`
  - `tests/test_monitor_messages_emailer.py`
  - `tests/test_monitor_cli.py`
  - Extend `tests/test_cli_safety.py` or add targeted tests for process sidecar behavior if existing CLI tests are too broad.

## Task 1: Config Model And Validation

**Files:**
- Create: `orchestrator/monitor/__init__.py`
- Create: `orchestrator/monitor/models.py`
- Create: `orchestrator/monitor/config.py`
- Test: `tests/test_monitor_config.py`

- [ ] **Step 1: Write failing config tests**

Add tests for:

```python
def test_load_monitor_config_accepts_explicit_workspaces_and_smtp_env_names(tmp_path):
    config_path = tmp_path / "monitor.yaml"
    config_path.write_text("""
workspaces:
  - name: repo
    path: /tmp/repo
monitor:
  poll_interval_seconds: 10
  stale_after_seconds: 120
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
  smtp_port: 587
  use_starttls: true
  username_env: SMTP_USER
  password_env: SMTP_PASSWORD
""")

    cfg = load_monitor_config(config_path)

    assert cfg.workspaces[0].name == "repo"
    assert cfg.monitor.stale_after_seconds == 120
    assert cfg.email.password_env == "SMTP_PASSWORD"
```

Also test invalid config: no workspaces, non-positive poll/stale values, unsupported backend, missing `to`, and literal password fields being rejected.

- [ ] **Step 2: Run config tests and verify failure**

Run: `pytest tests/test_monitor_config.py -q`

Expected: FAIL because `orchestrator.monitor.config` does not exist.

- [ ] **Step 3: Implement dataclasses and parser**

Implement immutable dataclasses:

```python
@dataclass(frozen=True)
class MonitorWorkspace:
    name: str
    path: Path

@dataclass(frozen=True)
class MonitorTiming:
    poll_interval_seconds: int = 60
    stale_after_seconds: int = 900

@dataclass(frozen=True)
class EmailConfig:
    backend: str
    from_address: str
    to: tuple[str, ...]
    smtp_host: str
    smtp_port: int = 587
    use_starttls: bool = True
    username_env: str | None = None
    password_env: str | None = None

@dataclass(frozen=True)
class MonitorConfig:
    workspaces: tuple[MonitorWorkspace, ...]
    monitor: MonitorTiming
    email: EmailConfig
```

`load_monitor_config(path: Path) -> MonitorConfig` should use `yaml.safe_load`, validate types, expand `~` for workspace paths without requiring directories to exist at config-load time, and reject literal secret keys such as `password`.

- [ ] **Step 4: Run config tests and verify pass**

Run: `pytest tests/test_monitor_config.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/monitor/__init__.py orchestrator/monitor/models.py orchestrator/monitor/config.py tests/test_monitor_config.py
git commit -m "feat: add monitor config parsing"
```

## Task 2: Workspace Scan And Event Classification

**Files:**
- Create: `orchestrator/monitor/scanner.py`
- Create: `orchestrator/monitor/process.py`
- Create: `orchestrator/monitor/classifier.py`
- Test: `tests/test_monitor_classifier.py`

- [ ] **Step 1: Write failing scanner/classifier tests**

Cover these cases with temporary `.orchestrate/runs/<run_id>/state.json` files:

- completed state produces `COMPLETED`
- failed state produces `FAILED`
- running state with fresh `current_step.last_heartbeat_at` produces no event
- running state with stale heartbeat produces `STALLED`
- running state without heartbeat falls back to stale `updated_at`
- running state with process metadata for a dead PID produces `CRASHED`
- `current_step.last_heartbeat_at` takes precedence over stale `updated_at`
- active nested call-frame heartbeat takes precedence over stale root
  `updated_at`; use the dashboard execution cursor semantics rather than only
  checking top-level `current_step`
- missing process identity confirmation does not suppress stalled detection
- invalid/unreadable state files do not crash the monitor scan

- [ ] **Step 2: Run classifier tests and verify failure**

Run: `pytest tests/test_monitor_classifier.py -q`

Expected: FAIL because classifier modules do not exist.

- [ ] **Step 3: Implement process metadata sidecar helpers**

Use a run-local sidecar path such as:

```text
<run_root>/monitor_process.json
```

Shape:

```json
{
  "schema": "orchestrator-monitor-process/v1",
  "pid": 12345,
  "started_at": "2026-04-28T12:00:00+00:00",
  "process_start_time": "platform process start token when available",
  "argv": ["python", "-m", "orchestrator", "run", "..."],
  "tmux": "optional raw TMUX env value"
}
```

Implement:

```python
def write_process_metadata(run_root: Path, argv: Sequence[str] | None = None) -> Path: ...
def read_process_metadata(run_root: Path) -> ProcessMetadata | None: ...
def process_identity_matches(metadata: ProcessMetadata) -> bool | None: ...
```

Use a platform process identity token where available, such as Linux
`/proc/<pid>/stat` field 22. A bare live PID is not sufficient to suppress
crash or stalled notifications because PID reuse can make a dead workflow look
alive. If process identity cannot be confirmed, continue to heartbeat/stale
classification rather than treating the process as healthy. Do not fail a
workflow if the sidecar write fails; log/debug later in `run`/`resume`.

- [ ] **Step 4: Implement scanner and classifier**

`scan_monitor_runs(config) -> list[MonitorRun]` should scan configured workspace roots, ignore missing `.orchestrate/runs`, and read state JSON safely.

`classify_run(run, now, stale_after_seconds) -> MonitorEvent | None` should:

- return terminal events from persisted `state.status`
- for running states, return `CRASHED` only when sidecar metadata confirms the
  original process identity is no longer alive
- derive freshness from the active execution cursor, recursively following
  running call frames, so call-based workflows with fresh nested heartbeats do
  not false-stall
- return `STALLED` when the active cursor heartbeat or fallback updated
  timestamp exceeds threshold
- otherwise return `None`

- [ ] **Step 5: Run classifier tests and verify pass**

Run: `pytest tests/test_monitor_classifier.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/monitor/scanner.py orchestrator/monitor/process.py orchestrator/monitor/classifier.py tests/test_monitor_classifier.py
git commit -m "feat: classify workflow monitor events"
```

## Task 3: Notification Ledger

**Files:**
- Create: `orchestrator/monitor/ledger.py`
- Test: `tests/test_monitor_ledger.py`

- [ ] **Step 1: Write failing ledger tests**

Test that the ledger:

- records `(workspace path, run_dir_id, event kind)`
- suppresses duplicates across reload
- uses atomic write behavior
- survives missing file by starting empty
- rejects malformed ledger content with a clear exception

- [ ] **Step 2: Run ledger tests and verify failure**

Run: `pytest tests/test_monitor_ledger.py -q`

Expected: FAIL because `ledger.py` does not exist.

- [ ] **Step 3: Implement ledger**

Use JSON:

```json
{
  "schema": "orchestrator-monitor-ledger/v1",
  "sent": [
    {
      "workspace": "/abs/path",
      "run_dir_id": "20260428T000000Z-abc123",
      "event_kind": "FAILED",
      "sent_at": "2026-04-28T12:00:00+00:00"
    }
  ]
}
```

Implement `has_sent(event)`, `mark_sent(event, sent_at)`, and `save()` with temp-file rename.

- [ ] **Step 4: Run ledger tests and verify pass**

Run: `pytest tests/test_monitor_ledger.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/monitor/ledger.py tests/test_monitor_ledger.py
git commit -m "feat: add monitor notification ledger"
```

## Task 4: Message Rendering And SMTP Delivery

**Files:**
- Create: `orchestrator/monitor/messages.py`
- Create: `orchestrator/monitor/emailer.py`
- Test: `tests/test_monitor_messages_emailer.py`

- [ ] **Step 1: Write failing message/email tests**

Tests should assert:

- subject includes event kind, workspace name, and run id
- body includes workflow file, status, current/failed step, heartbeat/update time, error message, and report/resume commands
- capped stdout/stderr previews from run-local step log files are included when
  present and safe to read
- prompt audits, provider-session transport logs, and arbitrary artifact files
  are excluded from email bodies by default
- dry-run returns rendered message without network
- SMTP delivery reads username/password from env names
- configured secret values and common sensitive key/value patterns are not
  included in rendered body, dry-run output, or raised exception text

- [ ] **Step 2: Run message/email tests and verify failure**

Run: `pytest tests/test_monitor_messages_emailer.py -q`

Expected: FAIL because modules do not exist.

- [ ] **Step 3: Implement deterministic renderer**

Implement:

```python
def render_event_email(event: MonitorEvent, config: MonitorConfig) -> EmailMessage: ...
```

Use `email.message.EmailMessage`. Keep body local and deterministic. Do not call provider summarizers.

Log previews must be bounded and route-safe:

- read only under the run root
- include only `logs/<Step>.stdout` and `logs/<Step>.stderr`
- cap each preview, for example 4 KiB per stream and 8 KiB total
- exclude prompt audit files and provider-session transport logs unless a later
  explicit opt-in is designed
- redact configured SMTP secret values and simple secret-looking lines before
  rendering

- [ ] **Step 4: Implement SMTP backend**

Implement:

```python
class SmtpEmailSender:
    def send(self, message: EmailMessage, *, dry_run: bool = False) -> SendResult: ...
```

Use `smtplib.SMTP`, optional `starttls()`, and `login()` only when username/password env names are configured. Missing required env vars should produce a clear non-secret error.

- [ ] **Step 5: Run message/email tests and verify pass**

Run: `pytest tests/test_monitor_messages_emailer.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/monitor/messages.py orchestrator/monitor/emailer.py tests/test_monitor_messages_emailer.py
git commit -m "feat: render and send monitor emails"
```

## Task 5: CLI Command And Poll Loop

**Files:**
- Create: `orchestrator/cli/commands/monitor.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Test: `tests/test_monitor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Cover:

- `python -m orchestrator monitor --help` exposes `--config`, `--once`, `--dry-run`, `--ledger`
- `monitor --once --dry-run` scans temp workspaces and prints planned notifications without SMTP
- dry-run never marks notifications as sent by default
- duplicate events are suppressed by the ledger in normal send mode
- optional `--dry-run-mark-sent` marks dry-run events in the ledger for manual
  rehearsal of duplicate suppression
- missing config exits non-zero with a clear message

- [ ] **Step 2: Run CLI tests and verify failure**

Run: `pytest tests/test_monitor_cli.py -q`

Expected: FAIL because CLI command is absent.

- [ ] **Step 3: Add parser and command function**

Add subcommand:

```text
orchestrator monitor --config <path> [--once] [--dry-run] [--dry-run-mark-sent] [--ledger <path>]
```

Behavior:

- `--once`: single scan, send/render eligible notifications, exit
- no `--once`: poll forever until interrupted
- `--dry-run`: do not connect to SMTP; print rendered subject/body or concise summary
- `--dry-run-mark-sent`: with `--dry-run`, update the ledger after rendering so
  operators can rehearse duplicate suppression intentionally
- `--ledger`: override default `~/.orchestrator-monitor/notifications.json`

Exit behavior:

- `0`: scan completed and all eligible notifications handled
- `1`: config/load/delivery failure
- `130`: interrupted polling loop via `KeyboardInterrupt`

- [ ] **Step 4: Implement monitor loop orchestration**

In `orchestrator/cli/commands/monitor.py`, wire together config, scanner, classifier, ledger, renderer, and sender. Do not mutate watched run states.

- [ ] **Step 5: Run CLI tests and verify pass**

Run: `pytest tests/test_monitor_cli.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/cli/main.py orchestrator/cli/commands/__init__.py orchestrator/cli/commands/monitor.py tests/test_monitor_cli.py
git commit -m "feat: add workflow monitor cli"
```

## Task 6: Process Sidecar From Run And Resume

**Files:**
- Modify: `orchestrator/cli/commands/run.py`
- Modify: `orchestrator/cli/commands/resume.py`
- Test: add focused tests to `tests/test_monitor_cli.py` or `tests/test_cli_safety.py`

- [ ] **Step 1: Write failing process-sidecar tests**

Use monkeypatch/temp run roots to verify that:

- a normal `run` writes `monitor_process.json` under the run root
- `resume` refreshes the sidecar for the resumed process
- sidecar write failures are non-fatal and do not mask workflow execution errors

- [ ] **Step 2: Run sidecar tests and verify failure**

Run the selected tests, for example:

```bash
pytest tests/test_monitor_cli.py -k process_sidecar -q
```

Expected: FAIL because `run`/`resume` do not write the sidecar.

- [ ] **Step 3: Integrate sidecar writes**

After the run root is known and before long-running execution begins, call:

```python
write_process_metadata(run_root, argv=sys.argv)
```

For `resume`, write the sidecar after loading the run root and before executing resumed steps. Catch/log sidecar write exceptions.

- [ ] **Step 4: Run sidecar tests and verify pass**

Run:

```bash
pytest tests/test_monitor_cli.py -k process_sidecar -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/cli/commands/run.py orchestrator/cli/commands/resume.py tests/test_monitor_cli.py
git commit -m "feat: record workflow monitor process metadata"
```

## Task 7: Specs, Runbook, Index, README

**Files:**
- Modify: `specs/observability.md`
- Modify: `specs/cli.md`
- Create: `docs/workflow_monitoring.md`
- Modify: `docs/index.md`
- Modify: `README.md`
- Test: documentation checks in `tests/test_monitor_cli.py` or a new `tests/test_monitor_docs.py`

- [ ] **Step 1: Write failing docs coverage test**

Add a lightweight test that checks for discoverable references, not exact prose:

```python
def test_monitor_docs_are_discoverable():
    assert "orchestrator monitor" in Path("specs/cli.md").read_text()
    assert "workflow_monitoring.md" in Path("docs/index.md").read_text()
    assert "COMPLETED" in Path("specs/observability.md").read_text()
```

- [ ] **Step 2: Run docs test and verify failure**

Run: `pytest tests/test_monitor_docs.py -q`

Expected: FAIL until docs are updated.

- [ ] **Step 3: Update normative specs**

In `specs/observability.md`, add monitor semantics:

- read-only observer
- event kinds
- heartbeat precedence
- ledger de-duplication
- no mutation of `state.json`

In `specs/cli.md`, add command syntax, flags, and exit codes.

- [ ] **Step 4: Add operational runbook and links**

Create `docs/workflow_monitoring.md` with:

- config example
- SMTP env setup
- `--once --dry-run`
- tmux/systemd examples for headless operation
- interpreting event kinds
- recovery commands after email

Update `docs/index.md` and `README.md` with concise pointers.

- [ ] **Step 5: Run docs tests and verify pass**

Run: `pytest tests/test_monitor_docs.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add specs/observability.md specs/cli.md docs/workflow_monitoring.md docs/index.md README.md tests/test_monitor_docs.py
git commit -m "docs: document workflow email monitoring"
```

## Task 8: Final Verification

**Files:**
- All monitor implementation, specs, docs, and tests above.

- [ ] **Step 1: Run monitor-focused test suite**

Run:

```bash
pytest \
  tests/test_monitor_config.py \
  tests/test_monitor_classifier.py \
  tests/test_monitor_ledger.py \
  tests/test_monitor_messages_emailer.py \
  tests/test_monitor_cli.py \
  tests/test_monitor_docs.py \
  -q
```

Expected: PASS.

- [ ] **Step 2: Run related observability/dashboard tests**

Run:

```bash
pytest tests/test_observability_report.py tests/test_dashboard_projection.py tests/test_dashboard_scanner.py -q
```

Expected: PASS.

- [ ] **Step 3: Run CLI smoke checks**

Run:

```bash
python -m orchestrator monitor --help
python -m orchestrator monitor --config /tmp/nonexistent-monitor.yaml --once --dry-run
```

Expected:

- help exits `0`
- missing config exits non-zero with a clear non-secret message

- [ ] **Step 4: Run full non-e2e suite if time allows**

Run:

```bash
pytest -m "not e2e" -q
```

Expected: PASS or report unrelated existing failures explicitly.

- [ ] **Step 5: Final commit if any cleanup remains**

```bash
git status --short
git add <remaining monitor files only>
git commit -m "test: verify workflow email monitor"
```

Only commit if there are remaining monitor-related changes from cleanup. Do not stage unrelated dirty files already present in the checkout.
