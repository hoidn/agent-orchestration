"""Public CLI variants of the D2 item cwd clauses (Phase 5 Task 3).

Every case runs a 2.37 two-item parallel map through `orchestrator run`, changes the
filesystem the way its D2 clause names, and resumes through `orchestrator resume`. The
outer workspace and each item directory hold different same-name scripts and data, so the
`tag` and `data` of a result say which bytes ran. Each script appends the logical root it
saw to `ran.log` in its cwd: an item's log is its dispatch count.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.closure_evidence import command_evidence_key
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_parallel_cwd_cli import ADAPTER_SOURCE, _write_adapter_fixture
from tests.workflow_evaluated_recovery_helpers import ROOT, resume


ITEMS = ("alpha", "beta")
SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule run) (export run)
  (defrecord Seen (item String) (tag String) (data String))
  (defworkflow run ((base String)) -> List[Seen]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace (string/concat base repo "/work")
      (command-result fetch :argv ("python" SCRIPT DATA repo) :returns Seen))))
'''
WORKER = '''import json, os, sys
from pathlib import Path
TAG = "@TAG@"
with open("ran.log", "a", encoding="utf-8") as log:
    log.write(os.environ.get("ORCHESTRATOR_WORKSPACE_ROOT", "<none>") + "\\n")
if Path("fail").exists():
    raise SystemExit(3)
data = Path(sys.argv[1])
if Path("mutate").exists():
    with data.open("a", encoding="utf-8") as stream:
        stream.write("changed by its own attempt")
seen = data.read_text() if data.is_file() else ("dir" if data.exists() else "absent")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(
    json.dumps({"item": sys.argv[2], "tag": TAG, "data": seen}))
'''
DECOY = "raise SystemExit(55)\n"


class Case:
    """One workspace with outer decoys and per-item scripts and data."""

    def __init__(self, root: Path, *, script="worker.py", data="data.txt", items_root=None,
                 source=SOURCE, boundaries=None):
        self.ws = root / "ws"
        self.items_root = items_root or self.ws
        self.script, self.data = script, data
        self.ws.mkdir(parents=True)
        source = source.replace("SCRIPT", json.dumps(script)).replace("DATA", json.dumps(data))
        (self.ws / "run.orc").write_text(source)
        (self.ws / "commands.json").write_text(json.dumps(
            {"fetch": {"stable_command": ["python", script, data], "closure": []}, **(boundaries or {})}))
        (self.ws / "worker.py").write_text(DECOY)
        (self.ws / "data.txt").write_text("outer data")
        for item in ITEMS:
            self.item(item).mkdir(parents=True)
            (self.item(item) / "worker.py").write_text(WORKER.replace("@TAG@", f"{item}-item"))
            (self.item(item) / "data.txt").write_text(f"{item} data")

    def item(self, name: str) -> Path:
        return self.items_root / name / "work"

    def run(self, *extra: str):
        base = "./" if self.items_root == self.ws else f"{self.items_root}/"
        return _run_cli(self.ws, "run.orc", "--input", f"base={base}",
                        "--command-boundaries-file", "commands.json", *extra)

    def run_failing(self, *failing: str, state_dir: str | None = None) -> str:
        """Run with `failing` items failing their first attempt; return the run id."""
        for name in failing:
            (self.item(name) / "fail").write_text("")
        extra = ("--state-dir", state_dir) if state_dir else ()
        result = self.run(*extra)
        assert result.returncode != 0 if failing else result.returncode == 0, result.stderr
        for name in failing:
            (self.item(name) / "fail").unlink()
        return self.run_root(state_dir).name

    def run_root(self, state_dir: str | None = None) -> Path:
        (root,) = (self.ws / (state_dir or ".orchestrate/runs")).iterdir()
        return root

    def snapshot(self, state_dir: str | None = None):
        authority = load_run_authority(self.run_root(state_dir))
        return read_memo(authority.memo_path, site_classes(authority.program))

    def memo_bytes(self, state_dir: str | None = None) -> bytes:
        return (self.run_root(state_dir) / "memo.jsonl").read_bytes()

    def dispatches(self, name: str) -> list[str]:
        log = self.item(name) / "ran.log"
        return log.read_text().splitlines() if log.exists() else []


def _seen(item: str, tag: str | None = None, data: str | None = None) -> dict:
    return {"item": item, "tag": tag or f"{item}-item", "data": data or f"{item} data"}


def _rows(snapshot, record: str, index: int | None = None) -> list[dict]:
    return [entry.data for entry in snapshot.entries if entry.data["record"] == record
            and (index is None or f"par-map:repo[{index}]" in entry.data["identity"])]


def _refused(result, code: str, *details: str) -> None:
    output = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert all(text in output for text in (f"[{code}]", *details)), output


def _completed(case: Case, expected: list[dict], *, state_dir: str | None = None) -> None:
    snapshot = case.snapshot(state_dir)
    assert snapshot.terminal.data["outcome"] == "completed"
    assert snapshot.terminal.data["value"] == expected
    for commit in _rows(snapshot, "committed"):
        assert commit["input_parts"]["argv"] == canonical_sha256(
            ["python", case.script, case.data, commit["value"]["item"]])


def _refused_without_rows(case: Case, run_id: str, item: str, detail: str) -> None:
    """Resume refuses `item`'s identity as diverged, naming `detail`, and writes nothing."""
    before = case.memo_bytes()
    _refused(resume(case.ws, run_id), "effect_input_diverged",
             f"par-map:repo[{ITEMS.index(item)}]", detail)
    assert case.memo_bytes() == before


# Each variant prepares its case, runs it, changes it as its clause names, and resumes.

def _prior_gone(tmp_path, phase):
    case = Case(tmp_path)
    run_id = case.run_failing("beta")
    target = "beta" if phase == "retry" else "alpha"
    (case.item(target) / "data.txt").unlink()
    _refused_without_rows(case, run_id, target, f"{target}/work/data.txt")


def _new_item_homonym(tmp_path, phase):
    case = Case(tmp_path)
    target = "beta" if phase == "retry" else "alpha"
    (case.item(target) / "data.txt").unlink()
    run_id = case.run_failing("beta")
    (case.item(target) / "data.txt").write_text("appeared after the attempt")
    detail = f"{target}/work/data.txt" if phase == "retry" else "implementation_files"
    _refused_without_rows(case, run_id, target, detail)


def _outer_homonym_appears(tmp_path, _phase):
    case = Case(tmp_path)
    (case.ws / "worker.py").unlink()
    (case.ws / "data.txt").unlink()
    run_id = case.run_failing("beta")
    (case.ws / "worker.py").write_text(DECOY)
    (case.ws / "data.txt").write_text("outer data appeared")
    assert resume(case.ws, run_id).returncode == 0
    _completed(case, [_seen(item) for item in ITEMS])
    assert [len(case.dispatches(item)) for item in ITEMS] == [1, 2]


def _symlink_dotdot(tmp_path, _phase):
    case = Case(tmp_path, script="link/../worker.py")
    for item in ITEMS:
        elsewhere = case.ws / "elsewhere" / item
        (elsewhere / "nested").mkdir(parents=True)
        (elsewhere / "worker.py").write_text(WORKER.replace("@TAG@", f"{item}-elsewhere"))
        (case.item(item) / "worker.py").write_text(DECOY)
        (case.item(item) / "link").symlink_to(elsewhere / "nested", target_is_directory=True)
    run_id = case.run_failing("beta")
    assert resume(case.ws, run_id).returncode == 0
    _completed(case, [_seen(item, tag=f"{item}-elsewhere") for item in ITEMS])
    for commit in _rows(case.snapshot(), "committed"):
        item = commit["value"]["item"]
        row = commit["implementation_files"][
            command_evidence_key("workspace", f"{item}/work/link/../worker.py", 1)]
        assert row["target"] == f"elsewhere/{item}/worker.py"


def _outside_cwd(tmp_path, _phase):
    case = Case(tmp_path, items_root=tmp_path / "outside")
    run_id = case.run_failing("beta")
    assert resume(case.ws, run_id).returncode == 0
    _completed(case, [_seen(item) for item in ITEMS])
    for commit in _rows(case.snapshot(), "committed"):
        item = case.item(commit["value"]["item"])
        assert set(commit["implementation_files"]) == {
            command_evidence_key("absolute", str(item / "worker.py"), 1),
            command_evidence_key("absolute", str(item / "data.txt"), 2)}
        assert commit["input_parts"]["launch_cwd"] == canonical_sha256(str(item))


def _destination_overlap(tmp_path, _phase):
    case = Case(tmp_path, data="state")
    state_dir = "alpha/work/state"
    result = case.run("--state-dir", state_dir)
    _refused(result, "command_closure_unreadable")
    snapshot = case.snapshot(state_dir)
    assert _rows(snapshot, "started", 0) == []
    assert [row["value"] for row in _rows(snapshot, "committed")] == [_seen("beta", data="absent")]
    before = case.memo_bytes(state_dir)
    retried = subprocess.run([sys.executable, "-m", "orchestrator", "resume", case.run_root(state_dir).name,
        "--state-dir", state_dir], cwd=case.ws, env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, check=False, timeout=120)
    _refused(retried, "command_closure_unreadable")
    assert case.memo_bytes(state_dir) == before
    assert case.dispatches("alpha") == []


def _c4_mutation(tmp_path, _phase):
    case = Case(tmp_path)
    (case.item("alpha") / "mutate").write_text("")
    result = case.run()
    _refused(result, "command_closure_written")
    snapshot = case.snapshot()
    assert [row["code"] for row in _rows(snapshot, "failed", 0)] == ["command_closure_written"]
    assert _rows(snapshot, "committed", 0) == []
    (case.item("alpha") / "mutate").unlink()
    (case.item("alpha") / "data.txt").write_text("alpha data")
    assert resume(case.ws, case.run_root().name).returncode == 0
    _completed(case, [_seen(item) for item in ITEMS])
    assert [len(case.dispatches(item)) for item in ITEMS] == [2, 1]


def _mutation_after_commit(tmp_path, _phase):
    case = Case(tmp_path)
    run_id = case.run_failing("beta")
    (case.item("alpha") / "worker.py").write_text(WORKER.replace("@TAG@", "alpha-changed"))
    _refused_without_rows(case, run_id, "alpha", "implementation_files")
    assert case.dispatches("alpha") == [str(case.ws)]


def _relocated(tmp_path, _phase):
    case = Case(tmp_path)
    run_id = case.run_failing("beta")
    original = case.ws
    case.ws = case.items_root = tmp_path / "moved"
    original.rename(case.ws)
    assert resume(case.ws, run_id).returncode == 0
    _completed(case, [_seen(item) for item in ITEMS])
    assert case.dispatches("alpha") == [str(original)]
    assert case.dispatches("beta") == [str(original), str(case.ws)]


BRANCH_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
  (defmodule run) (export run)
  (defrecord Seen (item String) (tag String) (data String))
  (defworkflow worker ((repo String)) -> Seen
    (if (= repo "never")
        (command-result absent :argv ("./absent.py" repo) :returns Seen)
        (command-result fetch :argv ("python" SCRIPT DATA repo) :returns Seen)))
  (defworkflow run ((base String)) -> List[Seen]
    (list/map-effect ((repo (list "alpha" "beta"))) :max 2 :parallel 2
      :workspace (string/concat base repo "/work")
      (call worker :repo repo))))
'''


def _unchosen_branch(tmp_path, _phase):
    """The arm no item takes names a missing slashed argv[0] and a missing declared closure file."""
    case = Case(tmp_path, source=BRANCH_SOURCE, boundaries={
        "absent": {"stable_command": ["./absent.py"], "closure": ["absent-closure.txt"]}})
    run_id = case.run_failing("beta")
    assert resume(case.ws, run_id).returncode == 0
    _completed(case, [_seen(item) for item in ITEMS])
    assert not any((case.ws / name).exists() for name in ("absent.py", "absent-closure.txt"))


def _changed_alias(tmp_path, phase):
    """Each item cwd is a symlink; retargeting one to identical bytes elsewhere diverges it."""
    case = Case(tmp_path)
    for item in ITEMS:
        first, second = case.item(item).with_name("first"), case.item(item).with_name("second")
        case.item(item).rename(first)
        shutil.copytree(first, second)
        case.item(item).symlink_to(first, target_is_directory=True)
    run_id = case.run_failing("beta")
    target = "beta" if phase == "retry" else "alpha"
    case.item(target).unlink()
    case.item(target).symlink_to(case.item(target).with_name("second"), target_is_directory=True)
    _refused_without_rows(case, run_id, target, "launch_cwd")


def _adapter_case(tmp_path):
    ws = tmp_path / "ws"
    source = ws / "parallel" / "adapter-cli.orc"
    source.parent.mkdir(parents=True)
    source.write_text(ADAPTER_SOURCE)
    _write_adapter_fixture(ws)
    return ws, source


def _adapter_run(ws, source):
    return _run_cli(ws, str(source), "--input", "items=artifacts/work/carrier.json")


def _adapter_values(ws):
    (run_root,) = (ws / ".orchestrate" / "runs").iterdir()
    authority = load_run_authority(run_root)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program))
    return run_root.name, snapshot


ADAPTER_VALUE = {"schema_version": "ReviewFindings.v1", "items_path": "artifacts/work/findings.json"}


def _package_shadow(tmp_path, _phase):
    ws, source = _adapter_case(tmp_path)
    shadow = ws / "alpha" / "work" / "orchestrator"
    shadow.mkdir()
    (shadow / "__init__.py").write_text("raise SystemExit(55)\n")
    _refused(_adapter_run(ws, source), "command_module_origin_mismatch")
    run_id, snapshot = _adapter_values(ws)
    assert [row["code"] for row in _rows(snapshot, "failed", 0)] == ["command_module_origin_mismatch"]
    assert [row["value"] for row in _rows(snapshot, "committed")] == [ADAPTER_VALUE]
    shutil.rmtree(shadow)
    assert resume(ws, run_id).returncode == 0
    assert _adapter_values(ws)[1].terminal.data["value"] == [ADAPTER_VALUE] * 2


def _unsafe_carrier(tmp_path, phase):
    ws, source = _adapter_case(tmp_path)
    artifacts = ws / "artifacts" / "work"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "findings.json").write_text('{"items": []}')
    unsafe = {"absolute": str(outside / "findings.json"),
              "dotdot": "artifacts/work/../../outside/findings.json",
              "symlink": "artifacts/work/escape/findings.json"}[phase]
    if phase == "symlink":
        (artifacts / "escape").symlink_to(outside, target_is_directory=True)
    carrier = artifacts / "carrier.json"
    safe = carrier.read_text()
    carrier.write_text(json.dumps({**ADAPTER_VALUE, "items_path": unsafe}))
    _refused(_adapter_run(ws, source), "command_exit_nonzero")
    run_id, snapshot = _adapter_values(ws)
    assert _rows(snapshot, "committed") == []
    assert [row["code"] for row in _rows(snapshot, "failed")] == ["command_exit_nonzero"] * 2
    outputs = list((ws / ".orchestrate" / "runs" / run_id / "effects").glob("*/attempt-1/stdout.txt"))
    assert len(outputs) == 2
    assert all("review_findings_path_unsafe" in path.read_text() for path in outputs)
    carrier.write_text(safe)
    assert resume(ws, run_id).returncode == 0
    assert _adapter_values(ws)[1].terminal.data["value"] == [ADAPTER_VALUE] * 2


VARIANTS = {
    "prior_gone": (_prior_gone, ("retry", "committed")),
    "new_item_homonym": (_new_item_homonym, ("retry", "committed")),
    "outer_homonym_appears": (_outer_homonym_appears, (None,)),
    "symlink_dotdot": (_symlink_dotdot, (None,)),
    "outside_cwd": (_outside_cwd, (None,)),
    "destination_overlap": (_destination_overlap, (None,)),
    "c4_mutation": (_c4_mutation, (None,)),
    "mutation_after_commit": (_mutation_after_commit, (None,)),
    "package_shadow": (_package_shadow, (None,)),
    "unsafe_carrier": (_unsafe_carrier, ("absolute", "dotdot", "symlink")),
    "relocated": (_relocated, (None,)),
    "unchosen_branch": (_unchosen_branch, (None,)),
    "changed_alias": (_changed_alias, ("retry", "committed")),
}


@pytest.mark.parametrize("variant,phase", [
    pytest.param(name, phase, id=name if phase is None else f"{name}-{phase}")
    for name, (_check, phases) in VARIANTS.items() for phase in phases
])
def test_parallel_item_cwd_variant_follows_d2(tmp_path, variant, phase):
    check, _phases = VARIANTS[variant]
    check(tmp_path, phase)

