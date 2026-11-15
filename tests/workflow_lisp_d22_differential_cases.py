"""Programs around defect D22 (a `done` or `continue` where a value is expected), for the differential corpus
`tests/test_workflow_lisp_d22_differential.py`: each is the body of module `m` at target 2.40, entry `run`, built
beside the stand-in command `c`, the provider extern `providers.review` and the prompt `prompts.base`.

`CASES` maps an id to `(run, definitions)`. Families:
- `pos-`: a loop exit form in one value position (`POSITIONS`), as the loop body itself (`bare`), as the value of
  the loop's `done` (`done`), as a binding's value whose body is `done` (`bound`) or, for an `Int` position, as
  the value of a `continue` (`continue`), in the binder loop form and in the `fn` loop form;
- `two-`: the same with the exit two positions deep;
- `tail-`: controls, exits in tail position (in `if`, `cond`, `match` and `let*` bodies) and value positions
  inside an exit's value: they build on `main`.

`d22_differential_main.json` under `tests/fixtures/workflow_lisp/` (every case's build on `main` before the fix)
is written by this module's `__main__`, never by hand, from an export of `main` at `c24fb97d`:

    git archive c24fb97d | tar -x -C EXPORT
    cd EXPORT && PYTHONPATH=EXPORT python -B TREE/tests/workflow_lisp_d22_differential_cases.py \\
        TREE/tests/fixtures/workflow_lisp/d22_differential_main.json
"""

from __future__ import annotations

import json
from pathlib import Path

DEFINITIONS = (
    "(defunion U (A (n Int)) (B (why String)))",
    "(defrecord R (k Int))",
    "(defrecord RL (xs List[Int]))",
    '(defpath P :kind relpath :under "artifacts/work" :must-exist false)',
    "(defproc inc ((x Int)) -> Int (+ x 1))",
    "(defun dbl ((x Int)) -> Int (* x 2))",
    "(defworkflow w ((n Int)) -> Int (+ n 1))",
    "(defworkflow wl ((xs List[Int])) -> Int (list/length xs))",
)
CMD = '(command-result c :argv ("python" "c.py" "m" "1") :returns Int)'
DEFAULTS = {"Int": "0", "Bool": "false", "String": '"a"', "List[Int]": "(list 0)", "R": "(record R :k 0)",
            "RL": "(record RL :xs (list 0))", "U": "(variant U A :n 0)", "P": '(path/join-under P "a")'}

# name: (template with the hole X, the hole's type, the template's type)
POSITIONS = {
    "list-first": ("(list X)", "Int", "List[Int]"),
    "list-second": ("(list 0 X)", "Int", "List[Int]"),
    "list-first-of-two": ("(list X 0)", "Int", "List[Int]"),
    "list-both": ("(list X X)", "Int", "List[Int]"),
    "typed-list": ("(list :of Int X)", "Int", "List[Int]"),
    "record-field": ("(record R :k X)", "Int", "R"),
    "record-list-field": ("(record RL :xs X)", "List[Int]", "RL"),
    "variant-field": ("(variant U A :n X)", "Int", "U"),
    "join-under-child": ("(path/join-under P X)", "String", "P"),
    "op-left": ("(+ X 1)", "Int", "Int"),
    "op-right": ("(+ 1 X)", "Int", "Int"),
    "compare": ("(> X 1)", "Int", "Bool"),
    "not": ("(not X)", "Bool", "Bool"),
    "and": ("(and true X)", "Bool", "Bool"),
    "length": ("(list/length X)", "List[Int]", "Int"),
    "proc-arg": ("(inc X)", "Int", "Int"),
    "defun-arg": ("(dbl X)", "Int", "Int"),
    "workflow-arg": ("(call w :n X)", "Int", "Int"),
    "workflow-list-arg": ("(call wl :xs X)", "List[Int]", "Int"),
    "map-body": ("(list/map ((x (list 1))) X)", "Int", "List[Int]"),
    "map-body-let": ("(list/map ((x (list 1))) (let* ((y x)) X))", "Int", "List[Int]"),
    "map-effect-body": ("(list/map-effect ((x (list 1))) :max 2 X)", "Int", "List[Int]"),
    "map-effect-parallel-body": ('(list/map-effect ((x (list "a"))) :max 2 :parallel 1 :workspace x X)', "Int",
                                 "List[Int]"),
    "map-source": ("(list/map ((x X)) (+ x 1))", "List[Int]", "List[Int]"),
    "map-effect-source": (f"(list/map-effect ((x X)) :max 2 {CMD})", "List[Int]", "List[Int]"),
    "map-effect-max": (f"(list/map-effect ((x (list 1))) :max X {CMD})", "Int", "List[Int]"),
    "loop-max": ("(loop/recur ((t 0)) :max X :on-exhausted 0 (done t))", "Int", "Int"),
    "loop-seed": ("(loop/recur ((t X)) :max 1 :on-exhausted 0 (done t))", "Int", "Int"),
    "loop-on-exhausted": ("(loop/recur ((t 0)) :max 1 :on-exhausted X (if (> t 0) (done t) (continue (+ t 1))))",
                          "Int", "Int"),
    "match-subject": ("(match X ((A a) a.n) ((B b) 0))", "U", "Int"),
    "if-condition": ("(if X 1 2)", "Bool", "Int"),
    "let-value": ("(let* ((y X)) y)", "Int", "Int"),
}

# name: an exit form, with D the loop's result value and H a value of the hole's type
EXITS = {
    "done": "(done D)",
    "continue": "(continue (+ s 1))",
    "if-all": "(if (> n 0) (done D) (continue (+ s 1)))",
    "cond-all": "(cond ((> n 0) (done D)) (else (continue (+ s 1))))",
    "match-all": "(match u ((A a) (done D)) ((B b) (continue (+ s 1))))",
    "let-tail": "(let* ((y 1)) (done D))",
    "if-one": "(if (> n 0) (done D) H)",
}

# Inner positions of the two-deep family: the ones that crash on `main` and a few that do not.
INNER = ("list-first", "map-body", "map-effect-body", "op-left", "proc-arg")
TWO_EXITS = ("done", "continue", "if-all")

TAILS = {
    "done": "(done 1)",
    "if": "(if (> s 0) (done s) (continue (+ s 1)))",
    "cond": "(cond ((> s 0) (done s)) (else (continue (+ s 1))))",
    "match": "(match u ((A a) (done a.n)) ((B b) (continue (+ s 1))))",
    "let": "(let* ((y (+ s 1))) (done y))",
    "let-if": "(let* ((y 1)) (if (> s 0) (done y) (continue (+ s y))))",
    "if-let": "(if (> s 0) (let* ((y s)) (done y)) (let* ((z (+ s 1))) (continue z)))",
    "match-let": "(match u ((A a) (let* ((y a.n)) (done y))) ((B b) (continue (+ s 1))))",
    "cond-if": "(cond ((> n 0) (if (> s 0) (done s) (continue (+ s 1)))) (else (done 1)))",
    "let-match-cond": "(let* ((y 1)) (match u ((A a) (cond ((> s 0) (done a.n)) (else (continue (+ s y))))) "
                      "((B b) (done 0))))",
    "done-list": "(done (list/length (list s 1)))",
    "done-map": "(done (list/length (list/map ((x (list 1 2))) (+ x s))))",
    "done-record": "(let* ((r (record R :k s))) (done r.k))",
    "continue-call": "(if (> s 0) (done s) (continue (inc (dbl s))))",
    "bound-map-effect": f"(let* ((k (list/length (list/map-effect ((x (list 1))) :max 2 {CMD})))) "
                        "(if (> s 0) (done k) (continue (+ s k))))",
}


def _loop(form: str, on_exhausted: str, body: str) -> str:
    if form == "binder":
        return f"(loop/recur ((s 0)) :max 2 :on-exhausted {on_exhausted} {body})"
    return f"(loop/recur :max 2 :state 0 :on-exhausted {on_exhausted} (fn (s) {body}))"


def _exit(name: str, result_type: str, hole_type: str) -> str:
    return EXITS[name].replace("D", DEFAULTS[result_type]).replace("H", DEFAULTS[hole_type])


def _contexts(value: str, type_: str):
    """(name, workflow result type, loop body) of each place the valued expression `value` takes in a loop body."""
    yield "bare", "Int", value
    yield "done", type_, f"(done {value})"
    yield "bound", type_, f"(let* ((v {value})) (done v))"
    if type_ == "Int":
        yield "continue", "Int", f"(if (> s 0) (done s) (continue {value}))"


def _run(result_type: str, loop: str) -> str:
    return f"((n Int) (u U)) -> {result_type} {loop}"


def _cases() -> dict[str, tuple[str, tuple[str, ...]]]:
    cases = {}
    for form in ("binder", "fn"):
        for position, (template, hole, type_) in POSITIONS.items():
            for context, result_type, body in _contexts(template, type_):
                for exit_name in EXITS:
                    value = body.replace("X", _exit(exit_name, result_type, hole))
                    cases[f"pos-{form}-{position}-{context}-{exit_name}"] = (
                        _run(result_type, _loop(form, DEFAULTS[result_type], value)), DEFINITIONS)
        for inner in INNER:
            inner_template, inner_hole, inner_type = POSITIONS[inner]
            for outer, (template, hole, type_) in POSITIONS.items():
                if hole != inner_type or outer == inner:
                    continue
                for exit_name in TWO_EXITS:
                    value = template.replace("X", inner_template).replace("X", _exit(exit_name, type_, inner_hole))
                    cases[f"two-{form}-{inner}-in-{outer}-{exit_name}"] = (
                        _run(type_, _loop(form, DEFAULTS[type_], f"(done {value})")), DEFINITIONS)
        for name, body in TAILS.items():
            cases[f"tail-{form}-{name}"] = (_run("Int", _loop(form, "0", body)), DEFINITIONS)
    return cases


CASES: dict[str, tuple[str, tuple[str, ...]]] = _cases()


def observe(case_id: str, root: Path) -> list:
    """The public build of the case in `root`, which it creates: `["builds", digest]`, `["refused", codes...]`,
    `["crash", class, place]` or `["traceback", class, place]`."""
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
    from tests.workflow_lisp_closed_program_helpers import build_outcome
    from tests.workflow_lisp_td21_differential_cases import _install

    run, definitions = CASES[case_id]
    _install(root, run, definitions)
    built = []
    outcome = build_outcome(lambda: built.append(build_closed_program_bundle(FrontendBuildRequest(
        source_path=root / "m.orc", source_roots=(root,), entry_workflow="m::run",
        command_boundaries_path=root / "commands.json", workspace_root=root,
        provider_externs_path=root / "providers.json", prompt_externs_path=root / "prompts.json"))))
    return ["builds", built[0].program.digest] if built else list(outcome)


if __name__ == "__main__":
    # With PYTHONPATH the tree to observe: OUT.json, every case's build.
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as scratch:
        result = {case_id: observe(case_id, Path(scratch) / str(index)) for index, case_id in enumerate(CASES)}
    Path(sys.argv[1]).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
