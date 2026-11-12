"""`--max-cost-usd`: a provider call starts only while the run's priced usage is under the cap."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from tests.test_workflow_evaluated_provider_usage import _attempts, _env, _memo, _orchestrator, _workspace

# One stand-in Claude call reports 0.25 USD (above its highest-tier price); a cap of 5e-6 is reached after one call.
BELOW_ONE_CALL = "0.000005"

TWO_CALLS = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> Result
    (let* ((first (provider-result providers.review :prompt prompts.base
                    :inputs (message) :model "claude-haiku-5-5" :effort "high" :returns Result))
           (built (command-result build :argv ("python" "command.py" message) :returns String))
           (second (provider-result providers.review :prompt prompts.base
                     :inputs (message built) :model "claude-haiku-5-5" :effort "high" :returns Result)))
      second)))'''

PARALLEL = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule main) (export run)
  (defrecord Result (ok Bool))
  (defworkflow run ((message String)) -> List[Result]
    (list/map-effect ((item (list "a" "b" "c"))) :max 3 :parallel 2 :workspace (string/concat item "/work")
      (provider-result providers.review :prompt prompts.base
        :inputs (item) :model "claude-haiku-5-5" :effort "high" :returns Result))))'''

COMMAND = '''import json, os
from pathlib import Path
with open("commands.jsonl", "a", encoding="utf-8") as log:
    log.write("{}\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("built"), encoding="utf-8")
'''

# Holds each call until `STANDIN_BARRIER` calls have started, so parallel siblings are in flight together.
BARRIER = '''import os, time
from pathlib import Path
if os.environ.get("STANDIN_BARRIER"):
    started = Path(os.environ["STANDIN_BARRIER_FILE"])
    with started.open("a") as log:
        log.write("x")
    deadline = time.monotonic() + 20
    while len(started.read_text()) < int(os.environ["STANDIN_BARRIER"]) and time.monotonic() < deadline:
        time.sleep(0.02)
'''


def _capped(tmp_path: Path, template: str = "claude_metered", source: str = TWO_CALLS) -> Path:
    root = _workspace(tmp_path / "w", template)
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "command.py").write_text(COMMAND, encoding="utf-8")
    (root / "commands.json").write_text(json.dumps(
        {"build": {"stable_command": ["python", "command.py"], "closure": ["command.py"]}}), encoding="utf-8")
    for tool in ("claude", "codex"):
        path = root / "bin" / tool
        text = path.read_text(encoding="utf-8")
        head, body = text.split("\n", 1)
        path.write_text(head + "\n" + BARRIER + body, encoding="utf-8")
    return root


def _run(root: Path, *extra: str, **standin):
    return _orchestrator(root, "run", "main.orc", "--source-root", ".", "--provider-externs-file", "providers.json",
                         "--prompt-externs-file", "prompts.json", "--command-boundaries-file", "commands.json",
                         "--input", "message=hi", *extra, **standin)


def _calls(root: Path) -> int:
    """Stand-in launches, wherever they ran (parallel items run in their own workspaces)."""
    return sum(len(path.read_text().splitlines()) for path in root.rglob("argv.jsonl"))


def _run_id(root: Path) -> str:
    (run,) = (root / ".orchestrate" / "runs").iterdir()
    return run.name


def test_cap_stops_before_the_next_provider_call_and_a_higher_cap_resumes(tmp_path):
    root = _capped(tmp_path)
    stopped = _run(root, "--max-cost-usd", BELOW_ONE_CALL)
    assert (stopped.returncode, _calls(root), [row["record"] for row in _memo(root)]) == (
        1, 1, ["started", "committed", "started", "committed"]), stopped.stderr
    assert "[spend_cap_reached]" in stopped.stderr
    suggested = stopped.stderr.split(f"resume {_run_id(root)} --max-cost-usd ")[1].split()[0]
    assert float(suggested) > float(BELOW_ONE_CALL)
    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "1")
    assert (resumed.returncode, _calls(root), _memo(root)[-1]["outcome"]) == (0, 2, "completed"), resumed.stderr


def test_cap_refuses_a_plain_template_before_its_first_call(tmp_path):
    root = _capped(tmp_path, template="claude")
    stopped = _run(root, "--max-cost-usd", "1")
    assert (stopped.returncode, _calls(root), _memo(root), "[spend_cap_unmetered]" in stopped.stderr) == (
        1, 0, [], True), stopped.stderr
    assert ("claude_metered" in stopped.stderr,      # the refusal names the metered template to bind
            "cause template_unmetered" in stopped.stderr) == (True, True), stopped.stderr


@pytest.mark.parametrize("template, model", [
    ("codex_metered", ':model "gpt-5.5"'), ("claude_metered", ':model "haiku"'),
    ("claude_haiku_summary_metered", ""),             # the template's default model is the alias `haiku`
    ("claude_unrestricted_workspace_metered", ""),    # no model at all
], ids=["unpriced", "alias", "default-alias", "missing"])
def test_cap_refuses_an_unpriced_model_before_its_call(tmp_path, template, model):
    root = _capped(tmp_path, template=template, source=TWO_CALLS.replace(':model "claude-haiku-5-5"', model))
    stopped = _run(root, "--max-cost-usd", "1")
    assert (stopped.returncode, _calls(root), "[spend_cap_unmetered]" in stopped.stderr,
            "cause model_unpriced" in stopped.stderr) == (1, 0, True, True), stopped.stderr


def test_cap_refuses_every_unmeterable_parallel_item(tmp_path):
    root = _capped(tmp_path, template="claude", source=PARALLEL)
    for item in "abc":
        (root / item / "work").mkdir(parents=True)
    stopped = _run(root, "--max-cost-usd", "1")
    assert (stopped.returncode, _calls(root), "[spend_cap_unmetered]" in stopped.stderr) == (1, 0, True), stopped.stderr


def _shift_last_start(root: Path, seconds: float) -> None:
    """Move the cut-off call's `started` row in time: the cap must not read the clock to tell it from a live call."""
    (memo,) = root.glob(".orchestrate/runs/*/memo.jsonl")
    rows = [json.loads(line) for line in memo.read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["record"] == "started"
    rows[-1]["time"] = time.time() + seconds
    memo.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.mark.parametrize("shift", [0, 3600, -3600], ids=["as-recorded", "future", "past"])
def test_killed_call_stops_its_own_retry_under_a_cap(tmp_path, shift):
    root = _capped(tmp_path)
    process = subprocess.Popen([sys.executable, "-m", "orchestrator", "run", "main.orc", "--source-root", ".",
                                "--provider-externs-file", "providers.json", "--prompt-externs-file", "prompts.json",
                                "--command-boundaries-file", "commands.json", "--input", "message=hi"],
                               cwd=root, env=_env(root, mode="hang"), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        deadline = time.monotonic() + 60
        while _calls(root) < 1 and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    assert _calls(root) == 1
    _shift_last_start(root, shift)
    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "1")
    assert (resumed.returncode, _calls(root), "[spend_cap_unmetered]" in resumed.stderr,
            "cause attempt_unmetered" in resumed.stderr) == (1, 1, True, True), resumed.stderr


def test_cap_of_zero_never_suggests_the_same_cap(tmp_path):
    root = _capped(tmp_path)
    stopped = _run(root, "--max-cost-usd", "0")
    assert ("[spend_cap_reached]" in stopped.stderr, "--max-cost-usd 0" in stopped.stderr,
            f"resume {_run_id(root)}" in stopped.stderr) == (True, False, True), stopped.stderr


def test_commands_run_under_a_reached_cap(tmp_path):
    root = _capped(tmp_path)
    _run(root, "--max-cost-usd", BELOW_ONE_CALL)
    assert len((root / "commands.jsonl").read_text().splitlines()) == 1


def test_parallel_batch_overshoots_only_by_calls_already_started(tmp_path):
    root = _capped(tmp_path, source=PARALLEL)
    for item in "abc":
        (root / item / "work").mkdir(parents=True)
    stopped = _run(root, "--max-cost-usd", BELOW_ONE_CALL, barrier="2", barrier_file=str(root / "started.log"))
    records = [row["record"] for row in _memo(root)]
    assert (stopped.returncode, _calls(root), records.count("started"), records.count("committed"),
            "[spend_cap_reached]" in stopped.stderr) == (1, 2, 2, 2, True), stopped.stderr


def test_run_without_cap_ignores_unknown_usage(tmp_path):
    root = _capped(tmp_path, template="claude")
    result = _run(root)
    assert (result.returncode, _calls(root)) == (0, 2), result.stderr
    assert all(json.loads((attempt / "usage.json").read_text())["status"] == "unknown" for attempt in _attempts(root))


def test_cap_counts_a_run_recorded_before_metering_as_unmetered(tmp_path):
    root = _capped(tmp_path)
    stopped = _run(root, "--max-cost-usd", BELOW_ONE_CALL)
    assert stopped.returncode == 1
    (_attempts(root)[0] / "usage.json").unlink()
    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "1")
    assert (resumed.returncode, _calls(root), "[spend_cap_unmetered]" in resumed.stderr) == (1, 1, True)


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_cap_reads_a_usage_file_that_is_not_regular_as_unmetered(tmp_path, kind):
    root = _capped(tmp_path)
    assert _run(root, "--max-cost-usd", BELOW_ONE_CALL).returncode == 1
    usage = _attempts(root)[0] / "usage.json"
    usage.unlink()
    usage.mkdir() if kind == "directory" else os.mkfifo(usage)
    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "1")
    assert (resumed.returncode, _calls(root), "cause attempt_unmetered" in resumed.stderr,
            "Traceback" in resumed.stderr) == (1, 1, True, False), resumed.stderr


def test_run_reference_under_a_cap_stops_before_its_child(tmp_path, monkeypatch):
    from tests.agent_session_shims import closed_path
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_run_ref import _public_fixture

    monkeypatch.setenv("PATH", closed_path(tmp_path / "bin"))      # `_run_cli` inherits the environment
    parent, source, refs = _public_fixture(tmp_path)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs), "--max-cost-usd", "1")
    children = list(refs.rglob("child-request.json")) if refs.exists() else []
    assert (result.returncode, "cause step_uncapped" in result.stderr, children) == (1, True, []), result.stderr


def test_completed_pending_agent_turn_recovers_under_a_cap(tmp_path, monkeypatch):
    from tests.agent_session_shims import install_agent_shims, shim_requests
    from tests.test_workflow_evaluated_agent_turn_recovery import STOP_AFTER_RECEIPT, _stopped
    from tests.test_workflow_evaluated_agent_turns import PLAN, fixture, memo_of, turns
    from tests.test_workflow_evaluated_invalidate import _cli

    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan=PLAN)
    _stopped(tmp_path, STOP_AFTER_RECEIPT, {"STOP_AT_COMPLETION": "completed", "STOP_TURN": "/ b1"}, "run",
             *fixture(tmp_path))
    run_root, _authority, _classes, _memo_before = memo_of(tmp_path)
    resumed = _cli(tmp_path, "resume", run_root.name, "--max-cost-usd", "1000")
    _root, _authority, classes, after = memo_of(tmp_path)
    # b1 commits at its first attempt without a launch; the next turn (an unpriced model) is refused before its call.
    assert (turns(after, classes)["b1"]["attempt"], len(shim_requests(tmp_path)),
            "cause model_unpriced" in resumed.stderr) == (1, 2, True), resumed.stderr
