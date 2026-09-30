"""`scripts/watch_workflow_usage_limit.sh` retries a resume refused by the workspace lock.

Contract: the script's usage text (RESUME_LOCK_WAIT_SECONDS) and specs/cli.md
"Workspace execution ownership". The script runs for real against a private
tmux server whose target pane shows a usage-limit message. `python -m
orchestrator` in that pane is a stand-in package (the script prepends
AGENT_ORCHESTRATION to PYTHONPATH) that logs each call and answers from a list
of outcomes: `refuse` and `guard` print the workspace lock's two refusals and exit 2, `fail`
prints another error and exits 1, `run` keeps running as an admitted resume. `late` refuses
after two and a half polls; `noisy` refuses and leaves a process that prints 400 lines after
the exit, which pushes the exit line out of the script's usual pane capture.
The Claude readiness probe and conda are stand-ins too.
"""

from __future__ import annotations

import os
import json
import subprocess
import time
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "watch_workflow_usage_limit.sh"
POLL_SECONDS = 2

STAND_IN_ORCHESTRATOR = f"""import json, subprocess, sys, time
from pathlib import Path
here = Path(__file__).parent
calls = here / "calls"
with calls.open("a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
outcomes = (here / "outcomes").read_text(encoding="utf-8").split()
attempt = len(calls.read_text(encoding="utf-8").splitlines())
outcome = outcomes[min(attempt, len(outcomes)) - 1]
if outcome == "late":
    time.sleep({2.5 * POLL_SECONDS})
    outcome = "refuse"
if outcome == "noisy":
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.2); [print('noise') for _ in range(400)]"])
    outcome = "refuse"
if outcome == "run_limit":
    run_root = Path.cwd() / ".orchestrate" / "runs" / "fresh-run"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(json.dumps({{
        "run_id": "fresh-run", "status": "running", "workflow_file": sys.argv[2],
    }}), encoding="utf-8")
    print("usage limit reached")
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
    start.workspace = tmp_path / "workspace"
    # The pane shows these lines above every prompt, so they are there again after the script clears it.
    start.prompt = lambda *lines: tmux("send-keys", "-t", "target:0.0", "PS1='" + "\\n".join([*lines, "$ "]) + "'", "Enter")
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


def test_a_refusal_printed_after_two_polls_is_retried(watcher) -> None:
    process = watcher("late run")

    _wait_for_calls(watcher, 2)
    time.sleep(3 * POLL_SECONDS)

    assert (watcher.calls(), process.poll()) == (["resume target-run --stream-output"] * 2, None)


def test_an_old_refusal_in_the_pane_is_not_the_result_of_a_new_attempt(watcher) -> None:
    # With no time to wait for the lock, a refusal taken for this attempt's result ends the watchdog.
    watcher.prompt("Error: workspace_run_already_active: run old-run is active", "orchestrator-exit=2")
    process = watcher("run", RESUME_LOCK_WAIT_SECONDS="0")

    _wait_for_calls(watcher, 1)
    time.sleep(3 * POLL_SECONDS)

    assert (watcher.calls(), process.poll()) == (["resume target-run --stream-output"], None)


def test_an_old_exit_line_in_the_pane_is_not_the_exit_of_a_new_attempt(watcher) -> None:
    watcher.prompt("orchestrator-exit=0")
    process = watcher("refuse run")

    _wait_for_calls(watcher, 2)
    time.sleep(3 * POLL_SECONDS)

    assert (watcher.calls(), process.poll()) == (["resume target-run --stream-output"] * 2, None)


def test_an_exit_line_pushed_out_of_the_usual_capture_is_still_found(watcher) -> None:
    process = watcher("noisy run")

    _wait_for_calls(watcher, 2)
    time.sleep(3 * POLL_SECONDS)

    assert (watcher.calls(), process.poll()) == (["resume target-run --stream-output"] * 2, None)


@pytest.mark.xfail(
    reason="F50: a late refusal followed by an admitted fresh run leaves the watchdog on the completed run",
    strict=True,
    raises=AssertionError,
)
def test_a_late_refusal_of_a_fresh_run_retries_with_the_fresh_run_id(watcher) -> None:
    workspace = watcher.workspace
    source_run = workspace / ".orchestrate" / "runs" / "target-run"
    source_run.mkdir(parents=True)
    manifest = workspace / "tranche-manifest.json"
    manifest.write_text(
        '{"tranches":[{"tranche_id":"t-1","status":"blocked",'
        '"last_item_outcome":"SKIPPED_AFTER_IMPLEMENTATION",'
        '"last_execution_report_path":"failed.md"}]}',
        encoding="utf-8",
    )
    (workspace / "failed.md").write_text("failed before producing a report", encoding="utf-8")
    (source_run / "state.json").write_text(
        '{"run_id":"target-run","status":"completed","workflow_file":"workflow.orc",'
        '"workflow_outputs":{"drain_status":"BLOCKED",'
        '"tranche_manifest_path":"tranche-manifest.json",'
        '"message":"provider usage limit reached"}}',
        encoding="utf-8",
    )

    process = watcher("late run_limit run")
    _wait_for_calls(watcher, 3)

    calls = watcher.calls()
    if calls[:2] != [
        "run workflow.orc --stream-output",
        "run workflow.orc --stream-output",
    ]:
        pytest.fail(f"fresh-run admission setup sent unexpected commands: {calls}")
    fresh_state = json.loads(
        (workspace / ".orchestrate" / "runs" / "fresh-run" / "state.json").read_text(encoding="utf-8")
    )
    if fresh_state["run_id"] != "fresh-run" or fresh_state["status"] != "running":
        pytest.fail(f"fresh run was not admitted: {fresh_state}")
    if process.poll() is not None:
        pytest.fail("watchdog exited before following the admitted fresh run")

    assert calls[2:] == ["resume fresh-run --stream-output"]
