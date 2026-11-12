"""Run-level equivalence of the evaluated runtime's fast paths with the reference paths.

Every workload runs in process with self-checks: each continued memo reduction must equal a
fresh reduction of the same bytes (which also catches a consumer mutating a shared row), and
each published ``state.json`` must equal the bytes the reference path publishes for the same
record. A deterministic loop is also run twice, fast and with every reference path forced, and
must give the same memo rows, views, report and program.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.cli.main import main
from orchestrator.workflow.evaluated import memo_reducer, views
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import append_record
from tests.test_workflow_evaluated_command_lifecycle import _publish
from tests.test_workflow_evaluated_memo import _started
from tests.workflow_lisp_closed_program_helpers import build

TICK = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule tick)
  (export run)
  (defworkflow run ((n Int)) -> Int
    (loop/recur :max 1000 :state 0
      :on-exhausted i
      (fn (i)
        (if (>= i n)
          (done i)
          (let* ((j (command-result tick :argv ("sh" "tick.sh" i) :returns Int)))
            (continue j)))))))
'''
FANOUT = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule fanout) (export run)
  (defworkflow run () -> List[Int]
    (list/map-effect ((repo (list "a" "b" "c" "d"))) :max 4 :parallel 2
      :workspace (string/concat repo "/work")
      (command-result tick :argv ("sh" "../../tick.sh" "${loop.index}") :returns Int))))
'''
TICK_SH = 'printf "%s" "$(( $1 + 1 ))" > "$ORCHESTRATOR_OUTPUT_BUNDLE_PATH"\n'
KILL_AFTER = '''import os, sys
from orchestrator.cli.main import main
from orchestrator.workflow.evaluated import runtime
append, seen = runtime.append_record, [0]
def stop(path, record, **kwargs):
    entry = append(path, record, **kwargs)
    seen[0] += record["record"] == "committed"
    if seen[0] == int(os.environ["KILL_AFTER"]):
        os._exit(75)
    return entry
runtime.append_record = stop
sys.exit(main(sys.argv[1:]))
'''


def _workspace(root: Path, source: str) -> Path:
    root.mkdir(parents=True)
    (root / ("tick.orc" if "loop/recur" in source else "fanout.orc")).write_text(source)
    (root / "tick.sh").write_text(TICK_SH)
    for item in "abcd":
        (root / item / "work").mkdir(parents=True)
    (root / "commands.json").write_text(json.dumps({"tick": {
        "stable_command": ["sh", "tick.sh"] if "loop/recur" in source else ["sh", "../../tick.sh"],
        "closure": ["tick.sh"] if "loop/recur" in source else []}}))
    return root


def _cli(monkeypatch, root: Path, *arguments: str) -> int:
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["orchestrator", *arguments])
    return main(list(arguments))


def _run_root(root: Path) -> Path:
    (run,) = (root / ".orchestrate" / "runs").iterdir()
    return run


class _Checks:
    """Self-checks installed for one test; ``full`` counts reductions from byte 0."""

    def __init__(self, monkeypatch):
        self.full = 0
        self.continued = 0
        self.views: list[bytes] = []
        self.shortcuts = 0
        reduce = memo_reducer._Reducer.reduce
        publish = views.publish_evaluated_view

        def checked_publish(authority, entry, **kwargs):
            publish(authority, entry, **kwargs)
            published = authority.run_files.read("state.json")
            if kwargs.get("start_reached"):
                self.shortcuts += 1
                publish(authority, entry)
                assert authority.run_files.read("state.json") == published, "started view differs from replay"
            self.views.append(published)

        def checked_reduce(reducer, raw, start=0):
            snapshot = reduce(reducer, raw, start)
            if start:
                self.continued += 1
                assert snapshot == reduce(memo_reducer._Reducer(reducer.site_classes), raw), "continued fold differs"
            else:
                self.full += 1
            return snapshot

        monkeypatch.setattr(memo_reducer._Reducer, "reduce", checked_reduce)
        monkeypatch.setattr(views, "publish_evaluated_view", checked_publish)


def _assert_cached_rows_are_the_journal_bytes():
    """A consumer that mutated a shared row would leave the cached fold unequal to its bytes."""
    reducer, raw = memo_reducer._LAST
    lines = raw.splitlines()
    assert [entry.data for entry in reducer.entries] == [json.loads(line) for line in lines]


@pytest.fixture
def checks(monkeypatch):
    memo_reducer._LAST = None
    return _Checks(monkeypatch)


def test_loop_run_continues_folds_that_equal_fresh_reductions(tmp_path, monkeypatch, checks):
    root = _workspace(tmp_path / "loop", TICK)
    assert _cli(monkeypatch, root, "run", "tick.orc", "--input", "n=12") == 0
    _assert_cached_rows_are_the_journal_bytes()
    assert checks.continued > 12 * 3
    assert checks.shortcuts == 12
    small = checks.full
    memo_reducer._LAST = None
    checks.full = 0
    assert _cli(monkeypatch, _workspace(tmp_path / "loop24", TICK), "run", "tick.orc", "--input", "n=24") == 0
    assert checks.full == small, "full memo reductions grow with the number of effects"


def test_parallel_map_run_continues_folds_that_equal_fresh_reductions(tmp_path, monkeypatch, checks):
    root = _workspace(tmp_path / "fanout", FANOUT)
    assert _cli(monkeypatch, root, "run", "fanout.orc") == 0
    _assert_cached_rows_are_the_journal_bytes()
    assert checks.continued
    assert checks.shortcuts == 4


def test_killed_loop_resume_continues_folds_that_equal_fresh_reductions(tmp_path, monkeypatch, checks):
    root = _workspace(tmp_path / "killed", TICK)
    (root / "kill.py").write_text(KILL_AFTER)
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "KILL_AFTER": "5"}
    killed = subprocess.run([sys.executable, "kill.py", "run", "tick.orc", "--input", "n=10"],
                            cwd=root, env=env, capture_output=True, text=True)
    assert killed.returncode == 75, killed.stderr
    assert _cli(monkeypatch, root, "resume", _run_root(root).name) == 0
    _assert_cached_rows_are_the_journal_bytes()
    assert checks.continued
    assert checks.shortcuts == 5


BRANCH = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule branch) (export run)
  (defworkflow run ((flag Bool)) -> Int
    (if flag
      (command-result fetch :argv ("python" "probe.py") :returns Int)
      (command-result inc :argv ("python" "probe.py") :returns Int))))
'''


@pytest.mark.parametrize(("site", "detail"), [
    ("workflow:branch::run / else / #1", "memo_inconsistent: a pending start is unreachable from the evaluated program"),
    (None, "memo_inconsistent: identity does not resolve to a checked effect site: workflow:branch::run / nowhere"),
])
def test_unreachable_or_unknown_start_still_fails_at_its_own_view_publication(tmp_path, site, detail):
    (tmp_path / "probe.py").write_text("# probe\n")
    program = build(tmp_path, BRANCH)
    with _publish(tmp_path, program, inputs={"flag": True}) as authority:
        assert set(site_classes(authority.program)) == {"workflow:branch::run / then / #1", "workflow:branch::run / else / #1"}
        identity = site or "workflow:branch::run / nowhere"
        with pytest.raises(views.ViewPublicationError) as refused:
            append_record(authority.memo_path, _started(identity), run_files=authority.run_files,
                          checked_authority=authority)
    assert refused.value.code == "view_write_failed"
    assert str(refused.value) == f"derived view publication failed at memo byte {len(authority.memo_path.read_bytes())}: {detail}"
