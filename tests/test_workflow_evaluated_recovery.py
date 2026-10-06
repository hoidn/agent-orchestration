"""External kills of the three maintained programs at every attempt window, resumed publicly.

The census fixes, for `std/improve` (REVISE, revision, APPROVE, launch), the reviewed change
(implement, REQUEST_CHANGES, revision, APPROVE) and serial best-of-N (two isolated coders,
the judge), the ordered activation identities an uninterrupted public run reaches. Each
cell of `CELLS` kills one such run from outside at one window W0–W9 of one effect's first
attempt and resumes it through the CLI: the resumed run returns the uninterrupted value,
keeps the committed prefix, reserves ordinals and repeats dispatches exactly as §8.3
requires, and a second resume changes no byte. The launcher command repeats its ten windows
under `must_not_repeat`, and a minimal command that changes its own declared script or package
helper is killed before it fails: resume launches nothing until the original bytes return.
The harness's other branch scenarios run the same window product in
`test_workflow_evaluated_recovery_branches.py`; the tables are in `workflow_evaluated_recovery_cases`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.workflow_evaluated_consumer_sources import CANDIDATES, PROGRAMS, checked_run, compile_current, sha256
from tests.workflow_evaluated_recovery_cases import CELLS, CORE, LAUNCH, SCENARIOS, Cell, answers, scenario_inputs
from tests.workflow_evaluated_recovery_helpers import (
    WINDOWS, current_source, digest, dispatches, install_standins, kill_at, prepare, resume,
)


RETRIED = WINDOWS[2:9]  # a complete `started` survives and nothing committed: W2–W8
DISPATCHED = WINDOWS[6:]  # the first attempt's dispatch happened before the kill: W6–W9
R3 = re.compile(r"\.orchestrate/runs/[^/\s]+/effects/[0-9a-f]{64}/attempt-[0-9]+/result\.json")


@dataclass(frozen=True)
class Baseline:
    root: Path
    run_root: Path
    inputs: dict
    value: dict
    commits: list[dict]


_BASELINES: dict[tuple[str, bool], Baseline] = {}


def _commits(snapshot) -> list[dict]:
    return [entry.data for entry in sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)]


def _standins(tmp_path: Path, monkeypatch, scenario: str) -> None:
    install_standins(tmp_path / "bin", monkeypatch, answers(scenario), list(CANDIDATES))


def _baseline(factory, scenario: str, must_not_repeat: bool = False) -> Baseline:
    """Public compile, uninterrupted run and completed resume, once per scenario and worker."""
    key = (scenario, must_not_repeat)
    if key not in _BASELINES:
        root, inputs = factory.mktemp(f"baseline-{scenario}"), scenario_inputs(factory, scenario)
        frontend = prepare(root, SCENARIOS[scenario].program, inputs, must_not_repeat=must_not_repeat)
        compile_current(root, frontend)
        ran = _run_cli(root, *frontend, "--input-file", "inputs.json")
        assert ran.returncode == 0, ran.stderr
        authority, snapshot = checked_run(root)
        _assert_completed_resume_unchanged(root, authority.run_root.name)
        _BASELINES[key] = Baseline(root, authority.run_root, inputs, snapshot.terminal.data["value"],
                                   _commits(snapshot))
    return _BASELINES[key]


def _assert_completed_resume_unchanged(root: Path, run_id: str) -> None:
    before = _tree_bytes(root)
    completed = resume(root, run_id)
    assert completed.returncode == 0, completed.stderr
    assert _tree_bytes(root) == before


def _starts(snapshot) -> dict[str, list[int]]:
    starts: dict[str, list[int]] = {}
    for entry in snapshot.entries:
        if entry.data["record"] == "started":
            starts.setdefault(entry.data["identity"], []).append(entry.data["attempt"])
    return starts


def assert_census(factory, tmp_path: Path, monkeypatch, scenario: str) -> Baseline:
    """The baseline reaches exactly the table's identities and classes, in journal order, with the
    stand-ins' own dispatch logs agreeing, one start each and the installed 2.35 source."""
    _standins(tmp_path, monkeypatch, scenario)
    run = _baseline(factory, scenario)
    _, snapshot = checked_run(run.root)
    expected, program = SCENARIOS[scenario], SCENARIOS[scenario].program
    by_class = {kind: [(digest(identity), 1) for identity, effect in expected.effects if effect == kind]
                for kind in ("provider", "command")}
    assert {"effects": [(data["identity"], data["effect_class"]) for data in run.commits], "value": run.value,
            "starts": _starts(snapshot), "dispatches": dispatches(run.root),
            "documents": [data for data in run.commits if "document" in data["input_parts"]],
            "source": (run.root / PROGRAMS[program].source).read_bytes()} == {
        "effects": list(expected.effects), "value": expected.value,
        "starts": {identity: [1] for identity, _kind in expected.effects},
        "dispatches": by_class["provider"] + by_class["command"], "documents": [],
        "source": current_source(program)}
    return run


@pytest.mark.parametrize("scenario", CORE)
def test_public_program_census_matches_reached_effects(tmp_path_factory, tmp_path, monkeypatch, scenario):
    run = assert_census(tmp_path_factory, tmp_path, monkeypatch, scenario)

    assert len(run.commits) == {"improve": 4, "reviewed_change": 4, "best_of_n": 3}[scenario]


# Held window: what the parent observes before it kills -----------------------------------------


def _listing(directory: Path) -> list[str] | None:
    return sorted(path.name for path in directory.iterdir()) if directory.is_dir() else None


def _result_state(result: Path, expected: bytes) -> str | None:
    if not result.is_file():
        return None
    raw = result.read_bytes()
    return "complete" if raw == expected else f"partial:{len(raw)}"


def _held(root: Path, cell: Cell, result: bytes) -> dict:
    """The memo, attempt directory and dispatch log of the target while the run is held."""
    authority, snapshot = checked_run(root)
    attempt = authority.run_root / f"effects/{digest(cell.identity)}/attempt-1"
    last = snapshot.entries[-1].data if snapshot.entries else {}
    return {"terminal": snapshot.terminal, "commits": [data["identity"] for data in _commits(snapshot)],
            "starts": _starts(snapshot).get(cell.identity, []), "pending": cell.identity in snapshot.pending_starts,
            "tail": len(snapshot.tail), "last": (last.get("record"), last.get("identity")),
            "directory": _listing(attempt), "result": _result_state(attempt / "result.json", result),
            "sent": [ordinal for name, ordinal in dispatches(root) if name == digest(cell.identity)]}


def _expected_held(run: Baseline, cell: Cell, marker: dict) -> dict:
    """§8.3 per window: W0/W1 leave no complete `started`, W2–W8 a pending one, W9 its commit;
    the directory appears at W4, the dispatch at W6, half a result at W7, a valid one at W8."""
    window = WINDOWS.index(cell.window)
    prior = [data["identity"] for data in run.commits[: cell.ordinal - 1]]
    previous = ("committed", prior[-1]) if prior else (None, None)
    launched = ["prompt.txt"] if cell.effect_class == "provider" else []  # a command's streams wait for its exit
    finished = _listing((run.run_root / run.commits[cell.ordinal - 1]["result_path"]).parent)
    directories = [None] * 4 + [[], [], launched, sorted([*launched, "result.json"]), finished, finished]
    return {"terminal": None, "commits": prior + [cell.identity] * (window == 9),
            "starts": [1] * (window >= 2), "pending": 2 <= window <= 8,
            "tail": marker["written"] if window == 1 else 0,
            "last": previous if window < 2 else ("committed" if window == 9 else "started", cell.identity),
            "directory": directories[window],
            "result": ([None] * 7 + [f"partial:{marker.get('written')}", "complete", "complete"])[window],
            "sent": [1] * (window >= 6), "publisher": "stand-in" if window in (6, 7) else "cli"}


def _assert_held(root: Path, run: Baseline, cell: Cell, marker: dict) -> None:
    """The marker names this run's cell, and the run stands exactly at the window's boundary."""
    named = marker["identity"] if "identity" in marker else marker["digest"]
    assert (marker["window"], marker["run"], marker["attempt"], named) == (
        cell.window, checked_run(root)[0].run_root.name, 1,
        cell.identity if "identity" in marker else digest(cell.identity))
    base = run.commits[cell.ordinal - 1]
    held = _held(root, cell, (run.run_root / base["result_path"]).read_bytes())
    held["publisher"] = "cli" if marker["pid"] == marker["runner_pid"] else "stand-in"
    assert held == _expected_held(run, cell, marker)
    if cell.window == "W7":
        with pytest.raises(json.JSONDecodeError):
            json.loads(checked_run(root)[0].run_root.joinpath(base["result_path"]).read_bytes())


def _kill(tmp_path: Path, run: Baseline, cell: Cell, *, must_not_repeat: bool = False) -> Path:
    root, program = tmp_path / "ws", SCENARIOS[cell.scenario].program
    frontend = prepare(root, program, run.inputs, must_not_repeat=must_not_repeat)
    assert sha256((root / PROGRAMS[program].source).read_bytes()) == cell.source_hash
    kill_at(root, tmp_path / "control", ["run", *frontend, "--input-file", "inputs.json"], cell.gate(),
            lambda marker: _assert_held(root, run, cell, marker))
    return root


# Recovery: what the public resume leaves -------------------------------------------------------


def _prompt(run_root: Path, data: dict) -> str | None:
    prompt = (run_root / data["result_path"]).parent / "prompt.txt"
    if not prompt.is_file():
        return None
    assert data["input_parts"]["prompt"] == sha256(prompt.read_bytes())
    text = prompt.read_text(encoding="utf-8")
    assert len(R3.findall(text)) == 1
    return R3.sub("<R3>", text)


def _comparable(run_root: Path, data: dict) -> dict:
    """A commit apart from what is run-specific by rule: the R3 path in its prompt and the
    source-span provenance in a provider declaration; both stay fixed within the run."""
    parts = {name: value for name, value in data["input_parts"].items() if name not in ("declaration", "prompt")}
    assert data["input_digest"] == canonical_sha256(data["input_parts"])
    return {"identity": data["identity"], "class": data["effect_class"], "value": data["value"],
            "result_digest": data["result_digest"], "depends_on": data["depends_on"], "parts": parts,
            "prompt": _prompt(run_root, data)}


def _expected_dispatches(run: Baseline, cell: Cell) -> list[tuple[str, int]]:
    """Every other effect once; the target's resumed first attempt (W0/W1), its second (W2–W5),
    both (W6–W8) or only the committed first (W9)."""
    target = digest(cell.identity)
    attempts = {"W0": [1], "W1": [1], "W9": [1]}.get(cell.window, [1, 2] if cell.window in DISPATCHED else [2])
    rows = [(digest(data["identity"]), 1) for data in run.commits if data["identity"] != cell.identity]
    return sorted(rows + [(target, attempt) for attempt in attempts])


def _expected_recovery(run: Baseline, cell: Cell) -> dict:
    retried = cell.window in RETRIED
    attempts = {data["identity"]: 2 if retried and data["identity"] == cell.identity else 1 for data in run.commits}
    return {"terminal": {"record": "terminal", "outcome": "completed", "value": run.value}, "tail": b"",
            "commits": [_comparable(run.run_root, data) for data in run.commits], "attempts": attempts,
            "starts": {identity: list(range(1, attempt + 1)) for identity, attempt in attempts.items()},
            "records": Counter(started=len(run.commits) + retried, committed=len(run.commits), terminal=1),
            "dispatches": _expected_dispatches(run, cell), "prefix": True}


def _assert_recovered(root: Path, run: Baseline, cell: Cell, before: dict) -> None:
    """Uninterrupted value and commits, §8.3 ordinals and dispatches, and every earlier byte kept."""
    authority, snapshot = checked_run(root)
    commits = _commits(snapshot)
    assert {"terminal": snapshot.terminal.data, "tail": snapshot.tail,
            "commits": [_comparable(authority.run_root, data) for data in commits],
            "attempts": {data["identity"]: data["attempt"] for data in commits}, "starts": _starts(snapshot),
            "records": Counter(entry.data["record"] for entry in snapshot.entries),
            "dispatches": sorted(dispatches(root)),
            "prefix": authority.memo_path.read_bytes().startswith(before["complete"])} == _expected_recovery(run, cell)
    after = _tree_bytes(authority.run_root / "effects")
    assert {path: node for path, node in after.items() if path in before["effects"]} == before["effects"]
    if cell.window in RETRIED:
        first = next(entry.data for entry in snapshot.entries if entry.data["identity"] == cell.identity)
        (commit,) = [data for data in commits if data["identity"] == cell.identity]
        assert {**first["input_parts"], "prompt": None} == {**commit["input_parts"], "prompt": None}


def _before_resume(root: Path) -> tuple[str, dict]:
    authority, snapshot = checked_run(root)
    return authority.run_root.name, {"complete": snapshot.raw[: snapshot.complete_bytes],
                                     "effects": _tree_bytes(authority.run_root / "effects")}


def assert_window_resumes(factory, tmp_path: Path, monkeypatch, cell: Cell) -> None:
    """Kill the cell's run at its window, resume it publicly, then resume the completed run."""
    _standins(tmp_path, monkeypatch, cell.scenario)
    run = _baseline(factory, cell.scenario)
    root = _kill(tmp_path, run, cell)
    run_id, before = _before_resume(root)

    resumed = resume(root, run_id)

    assert resumed.returncode == 0, resumed.stderr
    _assert_recovered(root, run, cell, before)
    _assert_completed_resume_unchanged(root, run_id)


@pytest.mark.parametrize("cell", CELLS, ids=lambda cell: cell.id)
def test_public_program_effect_window_resumes(tmp_path_factory, tmp_path, monkeypatch, cell):
    assert_window_resumes(tmp_path_factory, tmp_path, monkeypatch, cell)


@pytest.mark.parametrize("cell", LAUNCH, ids=lambda cell: cell.id)
def test_public_must_not_repeat_command_window_controls(tmp_path_factory, tmp_path, monkeypatch, cell):
    """With `must_not_repeat` on the launcher, a complete `started` without a commit (W2–W8)
    refuses read-only even when nothing launched; W0/W1 run the first attempt; W9 reuses it."""
    _standins(tmp_path, monkeypatch, cell.scenario)
    run = _baseline(tmp_path_factory, cell.scenario, must_not_repeat=True)
    root = _kill(tmp_path, run, cell, must_not_repeat=True)
    run_id, before = _before_resume(root)
    tree = _tree_bytes(root)

    resumed = resume(root, run_id)

    if cell.window in RETRIED:
        assert (resumed.returncode, "lexical_restore_pending_effect_unsafe" in resumed.stderr) == (2, True), \
            resumed.stderr
        assert _tree_bytes(root) == tree
        return
    assert resumed.returncode == 0, resumed.stderr
    _assert_recovered(root, run, cell, before)
    _assert_completed_resume_unchanged(root, run_id)


# Closure mutation, then an external kill -------------------------------------------------------

MUTATION_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule retry) (export run)
  (defworkflow run () -> Int
    (command-result emit :argv ("python" "probe.py") :returns Int)))
'''
MUTATING_PROBE = '''import json, os, signal
from pathlib import Path
from support.normalize import value
bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
with Path("dispatches.txt").open("a", encoding="utf-8") as log:
    log.write(bundle.parent.name + "\\n")
mutate = json.loads(os.environ.get("RECOVERY_MUTATE", "null"))
if mutate and bundle.parent.name == "attempt-1":
    with open(mutate["path"], "a", encoding="utf-8") as target:
        target.write("# changed by its own attempt\\n")
    marker = Path(mutate["marker"])
    marker.with_name("marker.tmp").write_text(json.dumps({"pid": os.getpid(), "pgid": os.getpgrp(),
                                                          "runner_pid": os.getppid(), "changed": mutate["path"]}))
    os.replace(marker.with_name("marker.tmp"), marker)
    while True:
        signal.pause()
bundle.write_text(str(value()), encoding="utf-8")
'''
MUTATED = {"script": "probe.py", "helper": "support/normalize.py"}


def _mutation_fixture(root: Path, must_not_repeat: bool) -> dict[str, bytes]:
    (root / "support").mkdir(parents=True)
    files = {"retry.orc": MUTATION_SOURCE, "probe.py": MUTATING_PROBE, "support/__init__.py": "",
             "support/normalize.py": "def value():\n    return 5\n",
             "commands.json": json.dumps({"emit": {"stable_command": ["python", "probe.py"], "must_not_repeat":
                                                   must_not_repeat, "closure": ["probe.py", "support/__init__.py",
                                                                                "support/normalize.py"]}})}
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return {name: (root / name).read_bytes() for name in files}


def _sent(root: Path) -> list[str]:
    return (root / "dispatches.txt").read_text(encoding="utf-8").splitlines()


def _assert_mutated_and_held(root: Path, original: dict[str, bytes], changed: str) -> None:
    _, snapshot = checked_run(root)
    assert {"changed": [name for name, raw in original.items() if (root / name).read_bytes() != raw],
            "records": [(entry.data["record"], entry.data["attempt"]) for entry in snapshot.entries],
            "results": list(root.glob(".orchestrate/runs/*/effects/*/attempt-*/result.json")), "sent": _sent(root)} == {
        "changed": [changed], "records": [("started", 1)], "results": [], "sent": ["attempt-1"]}


def _assert_refused(root: Path, run_id: str, code: str) -> None:
    before = _tree_bytes(root / ".orchestrate")
    refused = resume(root, run_id)
    assert (refused.returncode, code in refused.stderr) == (2, True), refused.stderr
    assert (_tree_bytes(root / ".orchestrate"), _sent(root)) == (before, ["attempt-1"])


@pytest.mark.parametrize("policy", ["retryable", "must-not-repeat"])
@pytest.mark.parametrize("changed", MUTATED)
def test_public_closure_mutation_then_external_kill_refuses_retry(tmp_path, changed, policy):
    root, control = tmp_path / "ws", tmp_path / "control"
    original = _mutation_fixture(root, policy == "must-not-repeat")
    mutate = {"RECOVERY_MUTATE": json.dumps({"path": MUTATED[changed], "marker": str(control / "marker.json")})}
    kill_at(root, control, ["run", "retry.orc", "--command-boundaries-file", "commands.json"], None,
            lambda _marker: _assert_mutated_and_held(root, original, MUTATED[changed]), env=mutate)
    authority, _ = checked_run(root)
    first = _tree_bytes(authority.run_root / "effects")

    _assert_refused(root, authority.run_root.name, "effect_input_diverged")
    (root / MUTATED[changed]).write_bytes(original[MUTATED[changed]])
    assert {name: (root / name).read_bytes() for name in original} == original

    if policy == "must-not-repeat":
        _assert_refused(root, authority.run_root.name, "lexical_restore_pending_effect_unsafe")
        return
    resumed = resume(root, authority.run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    _, snapshot = checked_run(root)
    after = _tree_bytes(authority.run_root / "effects")
    assert {"terminal": snapshot.terminal.data, "starts": list(_starts(snapshot).values()),
            "commit": [data["attempt"] for data in _commits(snapshot)], "sent": _sent(root),
            "first": {path: node for path, node in after.items() if path in first}} == {
        "terminal": {"record": "terminal", "outcome": "completed", "value": 5},
        "starts": [[1, 2]], "commit": [2], "sent": ["attempt-1", "attempt-2"],
        "first": first}
    _assert_completed_resume_unchanged(root, authority.run_root.name)
