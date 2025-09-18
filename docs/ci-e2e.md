# CI: E2E Test Job (Non‑Normative)

This repository separates deterministic unit/integration tests from environment‑dependent E2E tests. E2E tests are non‑normative but act as a release gate to confirm real CLI integration (Claude Code, Codex CLI).

Policy
- Default CI runs the main suite only: `pytest -m "not e2e" -v`.
- A separate, opt‑in job runs E2E: `pytest -v -m e2e`.
- E2E tests must skip gracefully when CLIs or secrets are unavailable (e.g., when `ORCHESTRATE_E2E` is not set, or `shutil.which("claude"/"codex")` is None).

GitHub Actions example

```yaml
name: CI

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Run unit+integration (non-E2E)
        run: pytest -m "not e2e" -v

  e2e:
    # Optional: trigger only on workflow_dispatch or when env is prepared
    if: github.event_name == 'workflow_dispatch' || contains(github.ref, 'main')
    runs-on: ubuntu-latest
    env:
      ORCHESTRATE_E2E: '1'  # Gate to enable E2E tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Install provider CLIs (example)
        run: |
          echo "Install and configure claude/codex CLIs here"
          echo "Ensure auth/secrets are available via repo or org secrets"
      - name: Run E2E suite
        run: pytest -v -m e2e
```

Notes
- Adjust the `if:` condition to your release cadence (e.g., nightly cron).
- Provider CLI installation is environment‑specific; place it in the indicated step and supply credentials via GitHub Secrets.
- Keep E2E assertions minimal and robust (exit codes and artifact presence), avoiding content‑specific expectations.

References
- Acceptance (supplemental): `specs/acceptance/index.md` → “E2E-01…E2E-03”.
- Primary acceptance (normative): same file, canonical list.

