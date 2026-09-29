"""`scripts/watch_workflow_usage_limit.sh` retries a resume refused by the workspace lock.

Contract: the script's usage text (RESUME_LOCK_WAIT_SECONDS) and specs/cli.md
"Workspace execution ownership". The script runs for real against a private
tmux server whose target pane shows a usage-limit message. `python -m
orchestrator` in that pane is a stand-in package (the script prepends
AGENT_ORCHESTRATION to PYTHONPATH) that logs each call and answers from a list
of outcomes: `refuse` and `guard` print the workspace lock's two refusals and exit 2, `fail`
prints another error and exits 1, `run` keeps running as an admitted resume.
The Claude readiness probe and conda are stand-ins too.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_workflow_usage_limit.sh"
POLL_SECONDS = 2

STAND_IN_ORCHESTRATOR = """import sys, time
from pathlib import Path
here = Path(__file__).parent
calls = here / "calls"
with calls.open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
outcomes = (here / "outcomes").read_text(encoding="utf-8").split()
attempt = len(calls.read_text(encoding="utf-8").splitlines())
outcome = outcomes[min(attempt, len(outcomes)) - 1]
if outcome == "refuse":
    print("Error: workspace_run_already_active: run other-run is active in /workspace", file=sys.stderr)
    sys.exit(2)
if outcome == "guard":
    print("Error: workspace_run_already_active: another run is starting in /workspace: .orchestrate/workspace.guard is held", file=sys.stderr)
    sys.exit(2)
if outcome == "fail":
    sys.exit("Error: some other failure")
time.sleep(60)
"""


@pytest.fixture
def watcher(tmp_path: Path):
    """Start the script against a fresh tmux server; yield a function that starts it with outcomes."""

    orchestrator = tmp_path / "stand-ins" / "orchestrator"
    orchestrator.mkdir(parents=True)
    (orchestrator / "__init__.py").write_text("", encoding="utf-8")
    (orchestrator / "__main__.py").write_text(STAND_IN_ORCHESTRATOR, encoding="utf-8")
    claude = tmp_path / "stand-ins" / "claude"
    claude.write_text("#!/bin/sh\necho OK\n", encoding="utf-8")
    claude.chmod(0o755)
    conda = tmp_path / "stand-ins" / "conda.sh"
    conda.write_text("conda() { :; }\n", encoding="utf-8")
    (tmp_path / "tmux").mkdir()
    (tmp_path / "workspace").mkdir()
    env = {key: value for key, value in os.environ.items() if key != "TMUX"}
    env.update(
        TMUX_TMPDIR=str(tmp_path / "tmux"), TARGET="target:0.0", RUN_ID="target-run",
        WORKSPACE=str(tmp_path / "workspace"), LOG=str(tmp_path / "watch.log"), POLL_SECONDS=str(POLL_SECONDS),
        RESUME_LOCK_WAIT_SECONDS="60", CONDA_SH=str(conda), CONDA_ENV="none",
        AGENT_ORCHESTRATION=str(orchestrator.parent), PROVIDER_SHIM_PATH=str(tmp_path / "stand-ins"),
        CLAUDE_BIN=str(claude), PROBE_RETRY_SECONDS="1",
    )

    def tmux(*args: str) -> None:
        subprocess.run(["tmux", *args], env=env, check=True, capture_output=True)

    tmux("-f", "/dev/null", "new-session", "-d", "-s", "target", "-x", "200", "-y", "50", "bash --norc --noprofile")
    tmux("send-keys", "-t", "target:0.0", "echo 'usage limit reached'", "Enter")
    started: list[subprocess.Popen] = []

    def start(outcomes: str, **overrides: str) -> subprocess.Popen:
        (orchestrator / "outcomes").write_text(outcomes, encoding="utf-8")
        process = subprocess.Popen(
            ["bash", str(SCRIPT)], env={**env, **overrides}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        started.append(process)
        return process

    start.calls = lambda: (orchestrator / "calls").read_text(encoding="utf-8").splitlines() if (orchestrator / "calls").exists() else []
    yield start
    for process in started:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
    subprocess.run(["tmux", "kill-server"], env=env, check=False, capture_output=True)


def _wait_for_calls(watcher, count: int, *, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while len(watcher.calls()) < count:
        if time.monotonic() > deadline:
            pytest.fail(f"stand-in orchestrator saw {watcher.calls()}")
        time.sleep(0.2)


@pytest.mark.parametrize(
    ("outcomes", "calls"),
    [("refuse refuse run", 3), ("guard run", 2), ("fail", 1)],
    ids=["refused-twice-then-admitted", "guard-held-then-admitted", "another-failure"],
)
def test_only_a_refusal_by_the_workspace_lock_is_retried(watcher, outcomes: str, calls: int) -> None:
    process = watcher(outcomes)

    _wait_for_calls(watcher, calls)
    time.sleep(3 * POLL_SECONDS)

    assert (watcher.calls(), process.poll()) == (["resume target-run --stream-output"] * calls, None)


def test_the_watchdog_exits_1_when_the_workspace_stays_busy_past_the_bound(watcher) -> None:
    process = watcher("refuse", RESUME_LOCK_WAIT_SECONDS=str(2 * POLL_SECONDS))

    exit_code = process.wait(timeout=90)

    assert (exit_code, len(watcher.calls())) == (1, 3)
