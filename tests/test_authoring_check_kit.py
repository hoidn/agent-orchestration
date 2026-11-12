"""The authoring-check kit works end to end without any provider call.

A scripted stand-in for the agent CLI writes either a correct workflow or one
that returns a constant; the kit builds the "before" arm, launches both
sessions, checks them and reads them out. The no-provider stubs sit on PATH
behind the stand-in, so any real provider launch would fail and be logged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "experiments" / "authoring_check"
NO_PROVIDER = REPO / "experiments" / "thread_m" / "no_provider"

CORRECT = {
    "tally.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule tally) (export run)
  (defrecord Tally (lines Int) (rounds Int))
  (defworkflow run ((file String) (target Int)) -> Tally
    (loop/recur
      :max 7
      :state (record Tally :lines 0 :rounds 0)
      (fn (state)
        (let* ((lines (command-result count :argv ("sh" "count.sh" file) :returns Int)))
          (if (or (>= lines target) (>= state.rounds 6))
            (done (record Tally :lines lines :rounds state.rounds))
            (let* ((added (command-result append :argv ("sh" "append.sh" file) :returns Bool)))
              (continue (record Tally :lines lines :rounds (+ state.rounds 1))))))))))
''',
    "commands.json": json.dumps({
        "count": {"stable_command": ["sh", "count.sh"], "closure": ["count.sh", "line_count.sh"]},
        "append": {"stable_command": ["sh", "append.sh"], "closure": ["append.sh"]}}),
    "count.sh": 'sh line_count.sh "$1" > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n',
    "append.sh": 'echo more >> "$1"\necho true > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n',
}

# Right on the visible example, wrong on both hidden cases, and never calls line_count.sh.
CONSTANT = {
    "tally.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule tally) (export run)
  (defrecord Tally (lines Int) (rounds Int))
  (defworkflow run ((file String) (target Int)) -> Tally
    (record Tally :lines 5 :rounds 3)))
''',
    "commands.json": "{}",
}

# Stand-in for the agent CLI: logs its argv, writes the solution named by FAKE_AGENT_SOLUTION into its
# working directory, and prints a stream-json transcript with one orchestrator call and a result event.
FAKE_AGENT = r'''import json, os, sys
from pathlib import Path
with open(os.environ["FAKE_AGENT_ARGV_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
for name, text in json.loads(Path(os.environ["FAKE_AGENT_SOLUTION"]).read_text()).items():
    Path(name).write_text(text)
events = [
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
        "input": {"command": "orchestrator compile tally.orc --command-boundaries-file commands.json"}}]}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "is_error": True}]}},
    {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.25,
     "usage": {"input_tokens": 100, "output_tokens": 20, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
     "modelUsage": {"claude-haiku-5-5": {}}},
]
print("\n".join(json.dumps(event) for event in events))
'''


def _env(tmp: Path, **extra: str) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PATH"] = os.pathsep.join([str(tmp / "fake-bin"), str(NO_PROVIDER), os.environ["PATH"]])
    env["FAKE_AGENT_ARGV_LOG"] = str(tmp / "agent-argv.jsonl")
    return {**env, **extra}


def _launch(tmp: Path, arm_env: Path, solution: dict | None = None, **extra: str) -> subprocess.CompletedProcess[str]:
    if solution is not None:
        (tmp / "solution.json").write_text(json.dumps(solution))
    env = _env(tmp, FAKE_AGENT_SOLUTION=str(tmp / "solution.json"), **extra)
    return subprocess.run(["bash", str(KIT / "run_session.sh"), str(arm_env), str(tmp / "sessions")],
                          env=env, capture_output=True, text=True, timeout=600, check=False)


def _agent_calls(tmp: Path) -> list[list[str]]:
    log = tmp / "agent-argv.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


@pytest.fixture(scope="module")
def arm_env(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("arm") / "before"
    built = subprocess.run([sys.executable, str(KIT / "build_env.py"), "before", str(out)],
                           env=_env(out.parent), capture_output=True, text=True, timeout=600, check=False)
    assert built.returncode == 0, built.stderr
    return out


@pytest.fixture
def workspace(tmp_path) -> Path:
    fake = tmp_path / "fake-bin" / "claude"
    fake.parent.mkdir()
    fake.write_text(f"#!{sys.executable}\n" + FAKE_AGENT)
    fake.chmod(0o700)
    return tmp_path


def test_the_before_arm_installs_the_phase_base_with_the_drafting_guide(arm_env):
    facts = json.loads((arm_env / "env.json").read_text())
    assert (facts["commit"], facts["document"]) == ("22dfb97389ea7dba4c2424f187ff084e492ffdfb",
                                                    "docs/lisp_workflow_drafting_guide.md")
    assert Path(facts["orchestrator_module"]).is_relative_to(arm_env / "venv")
    assert (arm_env / "GUIDE.md").stat().st_size > 0


def test_the_launcher_refuses_without_spend_authorization(workspace, arm_env):
    refused = _launch(workspace, arm_env, CORRECT)
    assert refused.returncode == 3
    assert _agent_calls(workspace) == [] and not (workspace / "sessions").exists()


def test_the_launcher_binds_the_model_the_cap_and_no_fallback(workspace, arm_env):
    assert _launch(workspace, arm_env, CORRECT, AUTHORING_CHECK_SPEND_AUTHORIZED="yes").returncode == 0
    (argv,) = _agent_calls(workspace)
    bound = {argv[i]: argv[i + 1] for i in range(len(argv) - 1) if argv[i] in ("--model", "--max-budget-usd")}
    assert bound == {"--model": "claude-haiku-5-5", "--max-budget-usd": "2"}
    assert not any(arg.startswith("--fallback-model") or "fable" in arg.lower() for arg in argv)


def test_the_kit_passes_a_correct_session_and_fails_a_constant_one(workspace, arm_env):
    for solution in (CORRECT, CONSTANT):
        assert _launch(workspace, arm_env, solution, AUTHORING_CHECK_SPEND_AUTHORIZED="yes").returncode == 0
    read = subprocess.run([sys.executable, str(KIT / "readout.py"), str(workspace / "sessions")],
                          capture_output=True, text=True, check=True)
    sessions = {row["session"]: row for row in json.loads(read.stdout)["sessions"]}
    assert (sessions["before-1"]["passed"], sessions["before-2"]["fail_reasons"]) == (True, ["check_failed"])


def test_check_fails_the_constant_workflow_on_the_hidden_cases_only(workspace, arm_env):
    assert _launch(workspace, arm_env, CONSTANT, AUTHORING_CHECK_SPEND_AUTHORIZED="yes").returncode == 0
    check = json.loads((workspace / "sessions" / "before-1" / "check.json").read_text())
    assert {case["case"]: case["passed"] for case in check["cases"]} == {
        "visible": True, "hidden_already_satisfied": False, "hidden_bound_reached": False}


def test_the_readout_reports_counts_and_cost_per_arm(workspace, arm_env):
    assert _launch(workspace, arm_env, CORRECT, AUTHORING_CHECK_SPEND_AUTHORIZED="yes").returncode == 0
    read = subprocess.run([sys.executable, str(KIT / "readout.py"), str(workspace / "sessions")],
                          capture_output=True, text=True, check=True)
    report = json.loads(read.stdout)
    (session,) = report["sessions"]
    assert report["arms"] == {"before": {"run": 1, "passed": 1, "cost_usd": 0.25}}
    assert (session["orchestrator_invocations"], session["orchestrator_failures"]) == (1, 1)


def test_the_launcher_refuses_a_fourth_session_of_an_arm(workspace, arm_env):
    for n in (1, 2, 3):
        (workspace / "sessions" / f"before-{n}").mkdir(parents=True)
    refused = _launch(workspace, arm_env, CORRECT, AUTHORING_CHECK_SPEND_AUTHORIZED="yes")
    assert refused.returncode == 3 and _agent_calls(workspace) == []
