"""Surface coherence E1 against the compiler before it: a fixed corpus and its recorded outcomes.

Contract: docs/design/workflow_lisp_surface_coherence.md §8 and the frontend specification §16.3.

- A program that built before E1 builds with the same program digest. E1 changes the compiler
  only, so the same digest runs the same; a sample is run and compared with its recorded run.
- A program that was refused under a named code is refused under that code, or builds; one that
  builds is listed (`admitted`) and a sample of the listed ones is run for value and call order.
- No program ends in `compiler_defect` or an exception unless it did before.

`fixtures/workflow_lisp/effect_placement_corpus/programs.json` holds 410 programs: grid cells
that built before E1 (eight of the twelve shapes that build) and probe programs of the E1 reviews
(the loop-body, macro, nested-`if` and older-defect sets whole; of the two identity sets, the
literal, `match` and `let*` operand forms and four of ten condition forms). `main_outcomes.json`
holds what `main` at `1e090cc8` gave for each, for every grid cell, and for the tracked `.orc`
files that build in process with no externs. To record it again, from a directory outside the
repository, with that `main`'s package first on `PYTHONPATH` and this repository second:
`python -m tests.test_workflow_lisp_effect_placement_corpus`.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_cli_run_output import REPO, env
from tests.test_workflow_lisp_effect_placement import PROBE, calls, cli, started, value
from tests.test_workflow_lisp_effect_placement_grid import POSITIONS, SHAPES, refusal

FIXTURE = Path(__file__).parent / "fixtures" / "workflow_lisp" / "effect_placement_corpus"
CORPUS = json.loads((FIXTURE / "programs.json").read_text(encoding="utf-8"))
PROGRAMS: dict[str, dict] = CORPUS["programs"]
MAIN = json.loads((FIXTURE / "main_outcomes.json").read_text(encoding="utf-8"))
FAMILIES = sorted({name.split("/")[0] for name in PROGRAMS})
DEFECTS = ("compiler_defect", "exception")

# Run in the suite: programs E1 admits, programs that built before it, and a value bound by `let*` or not.
ADMITTED_SAMPLE = (
    "n1probe/k2-cont-len-par-command", "n1probe/k6-cont-len-ser-command", "n1b/o4-loop-let-statement",
    "n3mine/p01-fn-two-rounds-continue-whole", "n3mine/p09-serial-whole-continue-computed-max",
    "n3mine/p27-binder-let-serial-max-then-par", "n3macro2/r7-continue-macro-par-named-binder-eff",
    "n3macro2/r11-top-macro-ser-eff-src",
)
BUILT_BEFORE_SAMPLE = (
    "grid/argv-item|two-effects", "grid/continue|match", "grid/loop-max|if", "grid/workflow-argument|nested-map",
    "m1c/v4-cond-three-clauses-pure-child", "j4b/let-op|match", "j4b/operand-ifc|proc", "j4b/wfarg-op|match",
)
BOUND_OR_NOT = (("list", "let-list"), ("record", "let-record"), ("path-child", "let-path-child"), ("serial-source", "let-serial-source"))


def write(root: Path, name: str, probe: str = "probe.py") -> Path:
    """Write the program `name` under `root` with its stand-in command, named in the source as `probe`.

    The relative default keeps a program's digest the same in every directory; a run passes the
    absolute path, since a parallel map's item runs in its own workspace.
    """

    program = PROGRAMS[name]
    root.mkdir(parents=True, exist_ok=True)
    body = f"\n  (defworkflow run ((n Int)) -> {program['returns']}\n    {program['body']}))\n"
    source = CORPUS["headers"][program["header"]] + program.get("decls", "") + body
    (root / "main.orc").write_text(source.replace("{probe}", probe), encoding="utf-8")
    (root / "probe.py").write_text(PROBE, encoding="utf-8")
    (root / "commands.json").write_text(
        json.dumps({"e": {"stable_command": ["python", probe], "closure": []}}), encoding="utf-8")
    for workspace in ("w", "q", "v", "sA", "sB", "u"):
        (root / "ws" / workspace).mkdir(parents=True, exist_ok=True)
    return root


def compiled(source: Path, workspace: Path) -> dict:
    """`{"code": None, "digest": ...}` for a program that builds, else `{"code": <its first diagnostic's>}`."""

    commands = source.with_name("commands.json")
    try:
        built = build_closed_program_bundle(FrontendBuildRequest(
            source_path=source, command_boundaries_path=commands if commands.exists() else None, workspace_root=workspace))
    except LispFrontendCompileError as exc:
        return {"code": exc.diagnostics[0].code}
    except Exception:  # an internal error the CLI would print as a traceback: recorded, never expected
        return {"code": "exception"}
    return {"code": None, "digest": built.program.digest}


def kept(before: dict, now: dict) -> bool:
    """Whether `now` keeps what `main` gave: the same build, or the same named refusal or a build."""

    if before["code"] is None:
        return now == before
    if before["code"] in DEFECTS:
        return True
    return now["code"] in (None, before["code"])


@pytest.mark.parametrize("family", FAMILIES)
def test_program_builds_as_before_or_is_refused_as_before(tmp_path: Path, family: str) -> None:
    broken, admitted = {}, set()
    for name in (name for name in PROGRAMS if name.split("/")[0] == family):
        root = write(tmp_path / str(len(admitted) + len(broken)) / hashlib.sha256(name.encode()).hexdigest()[:12], name)
        before, now = MAIN["compile"][name], compiled(root / "main.orc", root)
        if not kept(before, now):
            broken[name] = (before, now)
        if before["code"] not in (None, *DEFECTS) and now["code"] is None:
            admitted.add(name)

    assert broken == {}
    assert admitted == {name for name in PROGRAMS if name.split("/")[0] == family and PROGRAMS[name].get("admitted")}


def run_program(root: Path, name: str):
    write(root, name, probe=(root / "probe.py").as_posix())
    return cli(root, "run", "main.orc", "--input", f"n={PROGRAMS[name].get('n', 1)}")


@pytest.mark.parametrize("name", ADMITTED_SAMPLE)
def test_admitted_program_runs_with_its_value_and_call_order(tmp_path: Path, name: str) -> None:
    result = run_program(tmp_path, name)

    assert result.returncode == 0, result.stderr
    assert (PROGRAMS[name]["admitted"], value(result), calls(tmp_path)) == (True, PROGRAMS[name]["value"], PROGRAMS[name]["log"])


@pytest.mark.parametrize("name", BUILT_BEFORE_SAMPLE)
def test_program_that_built_before_runs_as_recorded(tmp_path: Path, name: str) -> None:
    result = run_program(tmp_path, name)

    assert result.returncode == 0, result.stderr
    assert {"value": value(result), "log": calls(tmp_path), "ids": started(result.stderr)} == MAIN["runs"][name]


@pytest.mark.parametrize(("written", "bound"), BOUND_OR_NOT)
def test_reviewed_value_names_its_effects_the_same_bound_or_not(tmp_path: Path, written: str, bound: str) -> None:
    names = [started(run_program(tmp_path / place, f"j5c/{place}|op|lit").stderr) for place in (written, bound)]

    assert names[0] and names[0] == names[1], names


def test_grid_expects_what_main_gave_or_a_build() -> None:
    faults = {}
    for position in POSITIONS:
        for shape in SHAPES:
            before, expected = MAIN["grid"][f"{position}|{shape}"], refusal(position, shape)
            if (before is None and expected is not None) or (
                    before not in (None, *DEFECTS) and expected not in (None, before)):
                faults[position, shape] = (before, expected)

    assert faults == {}


def test_tracked_source_that_built_before_keeps_its_digest(tmp_path: Path) -> None:
    """A source edited since the recording is not compared: its recorded digest is of another text."""

    moved, compared = {}, 0
    for index, (path, before) in enumerate(MAIN["tracked"].items()):
        source = REPO / path
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != before["source_sha256"]:
            continue
        compared += 1
        workspace = tmp_path / str(index)
        workspace.mkdir()
        now = compiled(source, workspace)
        if now != {"code": None, "digest": before["digest"]}:
            moved[path] = now

    assert (moved, compared > 0) == ({}, True)


def record() -> None:
    """Write `main_outcomes.json` from the package this process imports."""

    import orchestrator
    import tempfile

    package = str(Path(orchestrator.__file__).parents[1])
    scratch = Path(tempfile.mkdtemp(prefix="corpus-"))
    outcomes = {"compile": {}, "runs": {}, "tracked": {}, "grid": MAIN["grid"]}
    for index, name in enumerate(PROGRAMS):
        root = write(scratch / str(index), name)
        outcomes["compile"][name] = compiled(root / "main.orc", root)
    for index, name in enumerate(BUILT_BEFORE_SAMPLE):
        root = write(scratch / f"run{index}", name)
        result = subprocess.run(
            [sys.executable, "-B", "-m", "orchestrator", "run", "main.orc", "--input", f"n={PROGRAMS[name].get('n', 1)}"],
            cwd=root, env={**env(), "PYTHONPATH": package}, capture_output=True, text=True, check=True)
        outcomes["runs"][name] = {"value": value(result), "log": calls(root), "ids": started(result.stderr)}
    tracked = subprocess.run(["git", "ls-files", "*.orc"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    for index, path in enumerate(tracked):
        workspace = scratch / f"tracked{index}"
        workspace.mkdir()
        now = compiled(REPO / path, workspace)
        if now["code"] is None:
            outcomes["tracked"][path] = {
                "source_sha256": hashlib.sha256((REPO / path).read_bytes()).hexdigest(), "digest": now["digest"]}
    (FIXTURE / "main_outcomes.json").write_text(json.dumps(outcomes, indent=0, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    record()
