"""The I3 parent (experiments/orc_structural_search/three_arm/python/direct.py) run with a scripted `codex`.

The scripted executable (orc_structural_search_support.SCRIPTED) writes its result to the prompt's `- path:` file
or exits with a status; only `codex` is on the scripted PATH, so a call through another adapter fails. No provider
is called and no sandbox is needed.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.experiments.orc_structural_search_support import SCRIPTED, script

REPO = Path(__file__).resolve().parents[2]
PARENT = REPO / "experiments" / "orc_structural_search" / "three_arm" / "python"
# `python -c` programs that run the parent with run() replaced by a stub (argv: the candidate root, inputs.json)
STUB_HEAD = "import sys\nsys.path.insert(0, sys.argv.pop(1))\nimport direct\n\n"
STUB_TAIL = "\ndirect.run = run\nsys.exit(direct.main(sys.argv[1:]))\n"
NINE_CALLS = STUB_HEAD + """def run(task, intent, repo):
    for _ in range(9):
        direct.provider_result(direct.PROVIDERS["coder"], "x", model="m", effort="e", timeout_sec=30,
                               result=direct.Change)
    return direct.DONE(summary="unreachable")
""" + STUB_TAIL
RAISES = STUB_HEAD + """def run(task, intent, repo):
    return {}["missing"]
""" + STUB_TAIL


@pytest.fixture
def world(tmp_path):
    candidate, workspace, fakebin = tmp_path / "candidate", tmp_path / "workspace", tmp_path / "fakebin"
    shutil.copytree(PARENT, candidate, ignore=shutil.ignore_patterns("__pycache__"))
    workspace.mkdir()
    fakebin.mkdir()
    (fakebin / "codex").write_text(SCRIPTED)
    (fakebin / "codex").chmod(0o755)
    inputs = tmp_path / "inputs.json"
    inputs.write_text(json.dumps({"task": "Set VALUE to 2.\n", "intent": "VALUE is 2.\n", "repo": str(workspace)}))
    return SimpleNamespace(candidate=candidate, workspace=workspace, fakebin=fakebin, inputs=inputs,
                           results=tmp_path / "results.json")


def run_parent(world, *argv):
    """Run the parent (or `argv`, given) in the workspace; return its exit status and terminal.json."""
    argv = argv or (str(world.candidate / "direct.py"),)
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "PYTHONPATH": str(REPO),
           "SCRIPTED_RESULTS_FILE": str(world.results)}
    done = subprocess.run([sys.executable, *argv, str(world.inputs)], cwd=world.workspace, env=env,
                          capture_output=True, text=True)
    (terminal,) = world.workspace.glob(".orchestrate/runs/*/terminal.json")
    return done.returncode, json.loads(terminal.read_text())


def test_the_python_parent_completes_and_writes_a_terminal_with_one_call(world):
    script(world, [{"match": "Set VALUE to 2.", "result": {"summary": "s", "account": "a"}}])
    status, terminal = run_parent(world)
    assert (status, terminal["outcome"], terminal["value"], terminal["failure"], terminal["calls"]) == (
        0, "completed", {"variant": "DONE", "summary": "s"}, None, 1)


def test_a_provider_failure_is_a_failed_terminal_not_an_exception(world):
    script(world, [{"match": "", "exit": 1}])
    status, terminal = run_parent(world)
    assert (status, terminal["outcome"], terminal["value"], terminal["failure"]["code"]) == (
        1, "failed", None, "provider_exit_nonzero")


def test_a_result_with_an_undeclared_field_completes_as_in_the_runtime(world):
    script(world, [{"match": "", "result": {"summary": "s", "account": "a", "extra": 1}}])
    status, terminal = run_parent(world)
    assert (status, terminal["outcome"], terminal["value"]) == (0, "completed", {"variant": "DONE", "summary": "s"})


def test_an_exception_in_run_is_a_failed_terminal_with_workflow_error(world):
    status, terminal = run_parent(world, "-c", RAISES, str(world.candidate))
    assert (status, terminal["outcome"], terminal["failure"]) == (
        1, "failed", {"code": "workflow_error", "message": "KeyError: 'missing'"})


def test_the_call_budget_refuses_the_ninth_provider_call(world):
    script(world, [{"match": "", "result": {"summary": "s", "account": "a"}}])
    status, terminal = run_parent(world, "-c", NINE_CALLS, str(world.candidate))
    assert (status, terminal["failure"]["code"], terminal["calls"]) == (1, "call_budget_exceeded", 8)


def test_pyright_passes_on_the_python_parent():
    if shutil.which("pyright") is None:
        pytest.skip("pyright is not on PATH")
    # from the repository root, so `orchestrator` resolves; no network version check
    done = subprocess.run(["pyright", "--outputjson", str(PARENT / "direct.py")], cwd=REPO, capture_output=True,
                          text=True, env={**os.environ, "PYRIGHT_PYTHON_IGNORE_WARNINGS": "1"})
    assert json.loads(done.stdout)["summary"]["errorCount"] == 0, done.stdout
