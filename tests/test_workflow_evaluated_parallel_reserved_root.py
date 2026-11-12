"""The reserved `ORCHESTRATOR_WORKSPACE_ROOT` never reaches a launch from the ambient environment.

Each case poisons the variable in the environment of the public CLI. Parallel launches
must see their own run's logical root; every other launch must see none. Authored and
overlay values are refused at launcher level (`tests/test_logical_workspace_coordinates.py`):
evaluated `.orc` has no authored environment for commands or providers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests.test_workflow_evaluated_cli import _run_cli
from tests.workflow_evaluated_recovery_helpers import ROOT


POISON = "/ambient/poison"
ROOT_PROBE = '''import os
from pathlib import Path
with open("seen.log", "a", encoding="utf-8") as log:
    log.write(os.environ.get("ORCHESTRATOR_WORKSPACE_ROOT", "<none>") + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("1")
'''
NESTED = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule nested) (export run)
  (defworkflow run () -> List[Int]
    (let* ((serial (command-result probe :argv ("python" "probe.py") :returns Int)))
      (list/map-effect ((place (list "inner"))) :max 1 :parallel 1 :workspace place
        (command-result probe :argv ("python" "probe.py") :returns Int)))))
'''
NEST = '''import os, subprocess, sys
from pathlib import Path
child = subprocess.run([sys.executable, "-m", "orchestrator", "run", "nested.orc",
    "--command-boundaries-file", "commands.json"], capture_output=True, text=True)
Path("nested.log").write_text(child.stdout + child.stderr)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(str(child.returncode))
'''
OUTER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule outer) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((place (list "item"))) :max 1 :parallel 1 :workspace place
      (command-result nest :argv ("python" "nest.py") :returns Int))))
'''
CHILD_LAUNCH_LOG = '''import json, os, sys
from orchestrator.workflow.run_ref import runtime
real_run = runtime.subprocess.run

def run(argv, **kwargs):
    if any("orchestrator.workflow.run_ref.child" in str(token) for token in argv):
        with open(os.environ["CHILD_LAUNCH_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps(kwargs["env"].get("ORCHESTRATOR_WORKSPACE_ROOT", "<none>")) + "\\n")
    return real_run(argv, **kwargs)

runtime.subprocess.run = run
from orchestrator.cli import main
sys.argv = ["orchestrator", *sys.argv[1:]]
raise SystemExit(main())
'''


def _seen_roots(directory: Path) -> list[str]:
    return (directory / "seen.log").read_text().splitlines()


def _nested_orchestrator(tmp_path):
    """A command in a parallel item runs a nested 2.37 orchestrator from its cwd."""
    ws = tmp_path / "ws"
    item = ws / "item"
    (item / "inner").mkdir(parents=True)
    (ws / "outer.orc").write_text(OUTER)
    (ws / "commands.json").write_text(json.dumps({"nest": {"stable_command": ["python", "nest.py"], "closure": []}}))
    (item / "nest.py").write_text(NEST)
    (item / "nested.orc").write_text(NESTED)
    (item / "commands.json").write_text(json.dumps({"probe": {"stable_command": ["python", "probe.py"], "closure": []}}))
    for directory in (item, item / "inner"):
        (directory / "probe.py").write_text(ROOT_PROBE)
    result = _run_cli(ws, "outer.orc", "--command-boundaries-file", "commands.json")
    assert result.returncode == 0, result.stderr
    assert (item / "nested.log").exists() and _seen_roots(item) == ["<none>"], (item / "nested.log").read_text()
    assert _seen_roots(item / "inner") == [str(item)]


def _serial_provider(tmp_path):
    from tests.test_workflow_evaluated_providers import SOURCE, _cli, _fixture
    tmp_path.mkdir(exist_ok=True)
    fixture = _fixture(tmp_path, SOURCE)
    binary = tmp_path / "bin" / "codex"
    binary.write_text(f"#!{sys.executable}\n" + ROOT_PROBE.replace('write_text("1")', """write_text('{"ok": true}')"""))
    result = _cli(tmp_path, fixture)
    assert result.returncode == 0, result.stderr
    assert _seen_roots(tmp_path) == ["<none>"]


def _run_ref_child(tmp_path):
    """A parallel item's run reference launches its child with the coordinate removed."""
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    body = lambda call: f'''(let* ((batch (list/map-effect ((place (list "item"))) :max 1 :parallel 1
        :workspace place {call}))) true)'''
    parent, source, refs = _public_fixture(tmp_path, parent_target="2.37", body=body)
    (parent / "item").mkdir()
    (parent / "launch.py").write_text(CHILD_LAUNCH_LOG)
    log = tmp_path / "child-launch.log"
    result = subprocess.run([sys.executable, "launch.py", "run", str(source), "--run-ref-root", str(refs)],
        cwd=parent, env={**os.environ, "PYTHONPATH": str(ROOT), "CHILD_LAUNCH_LOG": str(log)},
        capture_output=True, text=True, check=False, timeout=120)
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == [json.dumps("<none>")]


def _parallel_provider(tmp_path):
    """Two parallel provider items each see their own run's workspace, never the poison."""
    from tests.test_workflow_evaluated_parallel_cwd_cli import _assert_provider_run, _provider_cli_fixture
    tmp_path.mkdir(exist_ok=True)
    _assert_provider_run(tmp_path, _provider_cli_fixture(tmp_path))
    for item in ("alpha", "beta"):
        assert json.loads((tmp_path / item / "provider-location.json").read_text())["root"] == str(tmp_path)


LAUNCHES = {"nested_orchestrator": _nested_orchestrator, "serial_provider": _serial_provider,
            "run_ref_child": _run_ref_child, "parallel_provider": _parallel_provider}


@pytest.mark.parametrize("launch", list(LAUNCHES))
def test_reserved_workspace_root_is_never_inherited(tmp_path, monkeypatch, launch):
    monkeypatch.setenv("ORCHESTRATOR_WORKSPACE_ROOT", POISON)
    LAUNCHES[launch](tmp_path)
