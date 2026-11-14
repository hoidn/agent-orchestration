"""Differential programs around a `let-proc` local that captures a procedure reference or a `bind-proc` role.

Each program has two spellings: `local`, where the uses call a local step over the captured reference, and
`direct`, the same uses calling the reference without a local. Every spelling's outcome on `main` at `99726a3d`
is recorded in `fixtures/let_proc_capture_differential_main.json`, written by this module's `--record` entry run
in an export of that commit (`python -m tests.test_workflow_lisp_let_proc_capture_differential --record OUT`
from the export's root). The tests assert, per program:

- a spelling that builds on `main` builds here with the recorded digest;
- each spelling gives one outcome in two builds in one process;
- no spelling crashes outside the signatures of the defect record's `KNOWN`;
- a local spelling that builds runs to the value and command log of its direct spelling.

Programs are module `m` at target 2.40 with the defect record's stand-in command; inputs `k=1`.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from tests import test_workflow_lisp_defect_backlog as backlog
from tests.workflow_lisp_closed_program_helpers import build_outcome

RECORD = Path(__file__).parent / "fixtures" / "let_proc_capture_differential_main.json"
CMD = '(command-result c :argv ("python" "c.py" "add" "0") :returns Int)'
CALLEES = {
    "pure": "(defproc add ((n Int) (x Int)) -> Int (+ n x)) (defproc inc ((x Int)) -> Int (+ x 1))",
    "effect": (f"(defproc add ((n Int) (x Int)) -> Int (let* ((z {CMD})) (+ (+ n x) z))) "
               f"(defproc inc ((x Int)) -> Int (let* ((z {CMD})) (+ (+ x 1) z)))"),
}
SUPPORT = ("(defrecord R (k Int))"
           " (defproc map-each ((f ProcRef[Int -> Int]) (xs List[Int])) -> List[Int]"
           " (list/map-effect ((x xs)) :max 2 (f x)))"
           " (defproc apply1 ((f ProcRef[Int -> Int]) (v Int)) -> Int (f v))")
# The captured value, as the `let*` bindings that hold it; `role` is the captured name.
ROLES = {
    "literal": "(role (bind-proc (proc-ref add) :n 1))",
    "input": "(role (bind-proc (proc-ref add) :n k))",
    "let-value": "(v k) (role (bind-proc (proc-ref add) :n v))",
    "field": "(r (record R :k k)) (role (bind-proc (proc-ref add) :n r.k))",
    "reference": "(role (proc-ref inc))",
}
# A use of the step: the result type and the body, with CALL as a call and FN as the callable.
USES = {
    "called": ("Int", "(CALL 1)"),
    "called-twice": ("Int", "(+ (CALL 1) (CALL 2))"),
    "map-effect-body": ("List[Int]", "(list/map-effect ((x (list 1 2))) :max 2 (CALL x))"),
    "passed-to-a-mapping-procedure": ("List[Int]", "(map-each FN (list 1 2))"),
    "passed-to-apply": ("Int", "(apply1 FN 3)"),
    "in-a-loop": ("Int", "(loop/recur ((s 0)) :max 1 :on-exhausted 0 (done (CALL 1)))"),
}
# How the local is written around a use.
FORMS = {
    "typed": "(let-proc ((step ((x Int)) -> Int (role x))) USE)",
    "inferred": "(let-proc ((step (x) (role x))) USE)",
    "group": "(let-proc ((step ((x Int)) -> Int (role x)) (other ((x Int)) -> Int (+ x 0))) USE)",
}
# A binder of `k` between the role and the local; the copied role must not read it.
REBINDERS = {
    "loop-binder": "(loop/recur ((k 100)) :max 1 :on-exhausted 0 (done INNER))",
    "let-binder": "(let* ((k 100)) INNER)",
    "fn-state-binder": "(loop/recur :max 1 :state 100 :on-exhausted 0 (fn (k) (done INNER)))",
}


def _spellings(role, use, form, callee, rebinder=None):
    returns, body = USES[use]
    local = FORMS[form].replace("USE", body.replace("CALL", "step").replace("FN", "(proc-ref step)"))
    direct = body.replace("CALL", "role").replace("FN", "role")
    if rebinder is not None:
        local, direct = (REBINDERS[rebinder].replace("INNER", text) for text in (local, direct))
    run = f"((k Int)) -> {returns} (let* ({ROLES[role]}) BODY)"
    return {name: backlog.module(run.replace("BODY", text), CALLEES[callee], SUPPORT)
            for name, text in (("local", local), ("direct", direct))}


def programs() -> dict[str, dict[str, str]]:
    found = {}
    for role in ROLES:
        for use in USES:
            for form in FORMS:
                for callee in CALLEES:
                    found[f"{role}/{use}/{form}/{callee}"] = _spellings(role, use, form, callee)
    for rebinder in REBINDERS:
        for use in ("called", "map-effect-body", "passed-to-a-mapping-procedure"):
            for callee in CALLEES:
                found[f"input/{use}/typed/{callee}/{rebinder}"] = _spellings("input", use, "typed", callee, rebinder)
    return found


PROGRAMS = programs()


def _build(root: Path, source: str):
    """The outcome and digest of the public build, twice in this process."""
    root.mkdir(parents=True, exist_ok=True)
    path = backlog._install(root, {"m.orc": source})
    box = {}

    def build():
        box["digest"] = build_closed_program_bundle(FrontendBuildRequest(source_path=path, source_roots=(root,),
            entry_workflow="m::run", command_boundaries_path=root / "commands.json",
            workspace_root=root)).program.digest

    first = build_outcome(build)
    first_digest = box.pop("digest", None)
    second = build_outcome(build)
    return (list(first), first_digest), (list(second), box.get("digest")), path


def record(out: Path, scratch: Path) -> None:
    rows = {}
    for program_id, spellings in sorted(PROGRAMS.items()):
        rows[program_id] = {}
        for name, source in spellings.items():
            (outcome, digest), _, _ = _build(scratch / program_id.replace("/", "_") / name, source)
            rows[program_id][name] = {"outcome": outcome, "digest": digest}
    out.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _known_crashes() -> set[tuple]:
    return {signature for signature in backlog.KNOWN.values() if signature[0] in ("crash", "traceback")}


def test_the_record_holds_every_program():
    assert set(json.loads(RECORD.read_text(encoding="utf-8"))) == set(PROGRAMS)


def test_there_are_at_least_120_programs():
    assert len(PROGRAMS) >= 120


@pytest.mark.parametrize("program_id", sorted(PROGRAMS))
def test_capture_program(program_id, tmp_path):
    recorded = json.loads(RECORD.read_text(encoding="utf-8"))[program_id]
    observed = {}
    for name, source in PROGRAMS[program_id].items():
        (outcome, digest), (again, again_digest), path = _build(tmp_path / name, source)
        assert (outcome, digest) == (again, again_digest), f"{name}: two builds in one process differ"
        if outcome[0] in ("crash", "traceback"):
            assert tuple(outcome) in _known_crashes(), f"{name}: crash outside KNOWN: {outcome}"
        if recorded[name]["outcome"] == ["builds"]:
            assert digest == recorded[name]["digest"], f"{name}: built on main with another digest"
        observed[name] = (outcome, path)
    (local, local_path), (direct, direct_path) = observed["local"], observed["direct"]
    if local == ["builds"] and direct == ["builds"]:
        local_value, detail = backlog._run(local_path.parent, local_path, "m::run", ("k=1",))
        direct_value, direct_detail = backlog._run(direct_path.parent, direct_path, "m::run", ("k=1",))
        assert local_value == direct_value, f"{detail}\n{direct_detail}"


if __name__ == "__main__":
    if sys.argv[1:2] != ["--record"] or len(sys.argv) != 4:
        raise SystemExit("usage: python -m tests.test_workflow_lisp_let_proc_capture_differential --record OUT SCRATCH")
    record(Path(sys.argv[2]), Path(sys.argv[3]))
