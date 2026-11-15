"""Differential programs around a `let-proc` local that captures a procedure reference or a `bind-proc` role.

Each program has two spellings: `local`, where the uses call a local step over the captured reference, and
`direct`, the same uses calling the reference without a local. The programs cover the binder of the name the
role reads (a workflow input, a `let*` name bound to a name or to a literal, a `loop/recur` or `fn` state binder,
a `list/map-effect` binder, a procedure parameter), the role (over that name, over a field read of it, over a
literal; a plain `proc-ref`), the callee (pure, command-backed), the use (called once and twice, a `list/map`
and a `list/map-effect` body, passed by `proc-ref` to a mapping procedure and to an applying one, in a loop) and
the local (typed, in a group, with an inferred signature). A last family binds the read name again between the
role and the local (each binder kind), with the binder spelled `k` and renamed `q`.

`fixtures/let_proc_capture_differential_main.json` holds every spelling's outcome, digest and, when it builds,
the value and command log of the public `run`, on `main` at `524ed71a`. It is written by this module's own
entry, run from the root of an export of that commit (`git archive`), never by hand:

    python -m tests.test_workflow_lisp_let_proc_capture_differential --record OUT.json SCRATCH_DIR

The tests assert, per program:

- each spelling gives one outcome and digest in two builds in one process;
- no spelling crashes outside the signatures of the defect record's `KNOWN`;
- a spelling that builds on `main` builds here, never refused, with the recorded digest;
- a local spelling whose read name is bound again (`rebound-k/…`) keeps the capture parameter, so it gives
  exactly the outcome it gave on `main`;
- a local spelling that builds here, whose direct spelling builds on `main`, runs to the value and command log the
  direct spelling ran to on `main`.

Programs are module `m` at target 2.40 with the defect record's stand-in command; input `k=1`.
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
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
SUPPORT = ("(defrecord R (k Int)) (defunion U (A (n Int)) (B (why String)))"
           " (defproc map-each ((f ProcRef[Int -> Int]) (xs List[Int])) -> List[Int]"
           " (list/map-effect ((x xs)) :max 2 (f x)))"
           " (defproc apply1 ((f ProcRef[Int -> Int]) (v Int)) -> Int (f v))"
           " (defmacro bind-as (nm body) (let* ((nm 100)) body))")
# Where the name the role reads is bound: the name, and the text around the role's `let*` bindings (BIND) and
# the use (BODY). RET is the result type of BODY, EXH a value of that type.
CONTEXTS = {
    "input": ("k", "(let* (BIND) BODY)"),
    "let-name": ("v", "(let* ((v k) BIND) BODY)"),
    "let-literal": ("v", "(let* ((v 10) BIND) BODY)"),
    "loop-binder": ("s", "(loop/recur ((s k)) :max 1 :on-exhausted EXH (let* (BIND) (done BODY)))"),
    "fn-state-binder": ("s", "(loop/recur :max 1 :state k :on-exhausted EXH (fn (s) (let* (BIND) (done BODY))))"),
    "map-effect-binder": ("s", "(list/map-effect ((s (list k))) :max 1 (let* (BIND) BODY))"),
    "procedure-parameter": ("k", "(holder k)"),
}
# The role, as the `let*` bindings that hold it; NAME is the name it reads.
ROLES = {
    "name": "(role (bind-proc (proc-ref add) :n NAME))",
    "field": "(r (record R :k NAME)) (role (bind-proc (proc-ref add) :n r.k))",
    "literal": "(role (bind-proc (proc-ref add) :n 1))",
    "reference": "(role (proc-ref inc))",
}
# A use of the step: the result type and the body, with CALL as a call and FN as the callable.
USES = {
    "called": ("Int", "(CALL 1)"),
    "called-twice": ("Int", "(+ (CALL 1) (CALL 2))"),
    "map-body": ("List[Int]", "(list/map ((x (list 1 2))) (CALL x))"),
    "map-effect-body": ("List[Int]", "(list/map-effect ((x (list 1 2))) :max 2 (CALL x))"),
    "passed-to-a-mapping-procedure": ("List[Int]", "(map-each FN (list 1 2))"),
    "passed-to-apply": ("Int", "(apply1 FN 3)"),
    "in-a-loop": ("Int", "(loop/recur ((i 0)) :max 1 :on-exhausted 0 (done (CALL 1)))"),
}
# How the local is written around a use.
FORMS = {
    "typed": "(let-proc ((step ((x Int)) -> Int (role x))) USE)",
    "group": "(let-proc ((step ((x Int)) -> Int (role x)) (other ((x Int)) -> Int (+ x 0))) USE)",
    "inferred": "(let-proc ((step (x) (role x))) USE)",
}
# A binder of K between a role over `k` and the local (K is `k`, a rebinding, or `q`, a renamed binder).
REBINDERS = {
    "loop-done": "(loop/recur ((K 100)) :max 1 :on-exhausted EXH (done INNER))",
    "fn-state": "(loop/recur :max 1 :state 100 :on-exhausted EXH (fn (K) (done INNER)))",
    "let": "(let* ((K 100)) INNER)",
    "let-in-a-loop": "(loop/recur ((i 0)) :max 1 :on-exhausted EXH (let* ((K 100)) (done INNER)))",
    "match-arm": "(match (variant U A :n 100) ((A K) INNER) ((B b) EXH))",
    "macro-binder": "(bind-as K INNER)",
    "map-effect-binder": "(list/map-effect ((K (list 100))) :max 1 INNER)",
    "local-parameter": "INNER",
}


def _exhausted(returns: str) -> str:
    return "0" if returns == "Int" else "(list 0)"


def _spellings(context, role, use, form, callee, rebinder=None, binder="k"):
    name, around = CONTEXTS[context]
    returns, body = USES[use]
    local = FORMS[form].replace("USE", body.replace("CALL", "step").replace("FN", "(proc-ref step)"))
    if rebinder == "local-parameter":
        local = local.replace("((x Int)) -> Int (role x)", "((K Int)) -> Int (role K)").replace("K", binder)
    direct = body.replace("CALL", "role").replace("FN", "role")
    if rebinder is not None:
        local, direct = (REBINDERS[rebinder].replace("K", binder).replace("EXH", _exhausted(returns))
                         .replace("INNER", text) for text in (local, direct))
        returns = f"List[{returns}]" if rebinder == "map-effect-binder" else returns
    bind = ROLES[role].replace("NAME", name)
    inner_returns = returns
    if context == "map-effect-binder":
        returns = f"List[{returns}]"
    definitions = [CALLEES[callee], SUPPORT]
    if context == "procedure-parameter":
        definitions.append(f"(defproc holder ((k Int)) -> {inner_returns} (let* ({bind}) BODY))")
    run = f"((k Int)) -> {returns} " + around.replace("BIND", bind).replace("EXH", _exhausted(inner_returns))
    return {spelling: backlog.module(run.replace("BODY", text), *(d.replace("BODY", text) for d in definitions))
            for spelling, text in (("local", local), ("direct", direct))}


def programs() -> dict[str, dict[str, str]]:
    found = {}
    for callee in CALLEES:
        for use in USES:
            for context in CONTEXTS:
                for role in ("name", "field"):
                    for form in ("typed", "group") + (("inferred",) if context == "input" else ()):
                        found[f"{context}/{role}/{use}/{form}/{callee}"] = _spellings(context, role, use, form, callee)
            for role in ("literal", "reference"):
                for form in FORMS:
                    found[f"input/{role}/{use}/{form}/{callee}"] = _spellings("input", role, use, form, callee)
        for rebinder in REBINDERS:
            for use in ("called", "passed-to-a-mapping-procedure"):
                for binder in ("k", "q"):
                    found[f"rebound-{binder}/{rebinder}/{use}/{callee}"] = _spellings(
                        "input", "name", use, "typed", callee, rebinder, binder)
    return found


PROGRAMS = programs()


def _build(root: Path, source: str):
    """The outcome and digest of the public build, twice in this process; the entry file."""
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


def _record_one(program_id: str, scratch: Path) -> dict:
    row = {}
    for name, source in PROGRAMS[program_id].items():
        (outcome, digest), _, path = _build(scratch / program_id.replace("/", "_") / name, source)
        ran = list(backlog._run(path.parent, path, "m::run", ("k=1",))[0]) if outcome == ["builds"] else None
        row[name] = {"outcome": outcome, "digest": digest, "value": ran}
    return row


def record(out: Path, scratch: Path) -> None:
    """Each program in a worker process of its own (one build history per program, as in a cold build)."""
    ids = sorted(PROGRAMS)
    with ProcessPoolExecutor(max_workers=8, max_tasks_per_child=1) as pool:
        rows = dict(zip(ids, pool.map(_record_one, ids, [scratch] * len(ids)), strict=True))
    out.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _recorded() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def _known_crashes() -> set[tuple]:
    return {signature for signature in backlog.KNOWN.values() if signature[0] in ("crash", "traceback")}


def test_the_record_holds_every_program():
    assert set(_recorded()) == set(PROGRAMS)


def test_there_are_at_least_120_programs():
    assert len(PROGRAMS) >= 120


@pytest.mark.parametrize("program_id", sorted(PROGRAMS))
def test_capture_program(program_id, tmp_path):
    recorded = _recorded()[program_id]
    observed = {}
    for name, source in PROGRAMS[program_id].items():
        (outcome, digest), (again, again_digest), path = _build(tmp_path / name, source)
        assert (outcome, digest) == (again, again_digest), f"{name}: two builds in one process differ"
        if outcome[0] in ("crash", "traceback"):
            assert tuple(outcome) in _known_crashes(), f"{name}: crash outside KNOWN: {outcome}"
        if recorded[name]["outcome"] == ["builds"]:
            assert outcome == ["builds"], f"{name}: built on main, here {outcome}"
            assert digest == recorded[name]["digest"], f"{name}: built on main with another digest"
        observed[name] = (outcome, path)
    local, local_path = observed["local"]
    if program_id.startswith("rebound-k/"):
        assert local == recorded["local"]["outcome"], "a rebound read keeps the capture parameter, as on main"
    if local == ["builds"] and recorded["direct"]["value"] is not None:
        ran, detail = backlog._run(local_path.parent, local_path, "m::run", ("k=1",))
        assert list(ran) == recorded["direct"]["value"], detail


if __name__ == "__main__":
    if sys.argv[1:2] != ["--record"] or len(sys.argv) != 4:
        raise SystemExit("usage: python -m tests.test_workflow_lisp_let_proc_capture_differential --record OUT SCRATCH")
    record(Path(sys.argv[2]), Path(sys.argv[3]))
