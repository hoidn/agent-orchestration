"""`--max-cost-usd`: a provider call starts only while the run's priced usage is under the cap."""

from __future__ import annotations

import json
from pathlib import Path

from tests.test_workflow_evaluated_provider_usage import _attempts, _memo, _orchestrator, _workspace

# One stand-in call (11 input, 7 output, 5 cache-read, 3 cache-write tokens of claude-haiku-5-5) prices at
# 5.25e-6 USD with the packaged table; a cap of 5e-6 is reached after one call.
ONE_CALL = 5.25e-6
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
    assert "[spend_cap_reached]" in stopped.stderr and f"resume {_run_id(root)} --max-cost-usd" in stopped.stderr
    resumed = _orchestrator(root, "resume", _run_id(root), "--max-cost-usd", "1")
    assert (resumed.returncode, _calls(root), _memo(root)[-1]["outcome"]) == (0, 2, "completed"), resumed.stderr


def test_cap_reached_refusal_names_spent_and_cap(tmp_path):
    root = _capped(tmp_path)
    stopped = _run(root, "--max-cost-usd", BELOW_ONE_CALL)
    assert f"spent {ONE_CALL:.6g} USD of a {float(BELOW_ONE_CALL):.6g} USD cap" in stopped.stderr


def test_cap_with_an_unmetered_attempt_stops_before_the_next_call(tmp_path):
    root = _capped(tmp_path, template="claude")
    stopped = _run(root, "--max-cost-usd", "1")
    assert (stopped.returncode, _calls(root), "[spend_cap_unmetered]" in stopped.stderr) == (1, 1, True), stopped.stderr
    assert "_metered" in stopped.stderr       # the refusal says how a capped run gets metered usage


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
    assert (stopped.returncode, _calls(root), records.count("started"), records.count("committed")) == (
        1, 2, 2, 2), stopped.stderr


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
