"""Every place E1 opens, crossed with every shape of effect: it runs, or it is refused by name.

Contract: docs/design/workflow_lisp_surface_coherence.md §4 (rule 1) and the frontend
specification §16.3. A cell runs through the public CLI with stand-in commands that log
their argument (`tests/test_workflow_lisp_effect_placement.py`); it must give the expected
value with each effect once, in written order, or be refused with the code `REFUSED` names.
A `compiler_defect` fails its cell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_workflow_lisp_effect_placement import E, M, calls, run, value, write

CHILD = "(defworkflow child ((t Int)) -> Int t)"
BOX_ARMS = "((RECT r) (+ r.w r.k)) ((NONE z) 0)"

# An `Int` expression holding effects: (expression, its value with n = 1, the ordered command log).
SHAPES = {
    "bare": (E(1), 1, ["1"]),
    "if": (f"(if (> n 0) {E(1)} {E(2)})", 1, ["1"]),
    "cond": (f"(cond ((> n 5) {E(2)}) (else {E(1)}))", 1, ["1"]),
    "match": (f"(match (variant Shape CIRCLE :r n) ((CIRCLE c) {E(1)}) ((SQUARE q) {E(2)}))", 1, ["1"]),
    "and": (f"(if (and (> n 0) (> {E(1)} 0)) 1 0)", 1, ["1"]),
    "or": (f"(if (or (> n 5) (> {E(1)} 0)) 1 0)", 1, ["1"]),
    # `and` and `or` stop at the operand that decides: the effect after it does not run.
    "and-skips": (f"(if (and (> n 5) (> {E(1)} 0)) 0 1)", 1, []),
    "or-skips": (f"(if (or (> n 0) (> {E(1)} 0)) 1 0)", 1, []),
    "let": (f"(let* ((y {E(1)})) y)", 1, ["1"]),
    "loop": (f"(loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (done {E(1)})))", 1, ["1"]),
    "nested-map": (f"(list/length (list/map-effect ((x (list 1))) :max 1 {E(1)}))", 1, ["1"]),
    "two-effects": (f"(+ {E(1)} {E(2)})", 3, ["1", "2"]),
    # An effect beside a pure field, in a variant that is a `match` subject.
    "beside-match": (f"(match (variant Box RECT :w {E(1)} :h 0 :k {M}) {BOX_ARMS})", 2, ["1"]),
    "beside-cond": (f"(match (variant Box RECT :w {E(1)} :h 0 :k (cond ((> n 5) 0) (else 1))) {BOX_ARMS})", 2, ["1"]),
    "beside-map": (
        f"(match (variant Box RECT :w {E(1)} :h 0 :k (list/length (list/map ((x (list 1 2))) x))) {BOX_ARMS})",
        3, ["1"]),
}

PAR = f'(list/map-effect ((x {{source}})) :max 1 :parallel 1 :workspace "ws/w" {E(5)})'
ONE_ROUND = "(loop/recur :max 1 :state {seed} :on-exhausted s (fn (s) (if (= n 7) (done s) (continue {v}))))"

# A place E1 opens: (returns, template over `{v}`, expected value from the shape's value, log after the shape's, declarations).
POSITIONS = {
    "record-field": ("Pair", "(record Pair :a {v} :b 9)", lambda v: {"a": v, "b": 9}, [], ""),
    "variant-field": ("Shape", "(variant Shape CIRCLE :r {v})", lambda v: {"r": v, "variant": "CIRCLE"}, [], ""),
    "list-element": ("List[Int]", "(list {v} 9)", lambda v: [v, 9], [], ""),
    "nested-constructor": (
        "Nest", "(record Nest :xs (list 0) :p (record Pair :a {v} :b 9))",
        lambda v: {"xs": [0], "p": {"a": v, "b": 9}}, [], ""),
    "record-update-field": ("Pair", "(record-update (record Pair :a 0 :b 9) :a {v})", lambda v: {"a": v, "b": 9}, [], ""),
    "match-subject": ("Int", "(match (variant Shape CIRCLE :r {v}) ((CIRCLE c) c.r) ((SQUARE q) 0))", lambda v: v, [], ""),
    "procedure-argument": ("Int", "(add {v} 100)", lambda v: v + 100, [], ""),
    "workflow-argument": ("Int", "(call child :t {v})", lambda v: v, [], CHILD),
    "argv-item": (
        "Int", '(command-result e :argv ("python" "{probe}" {v}) :returns Int)', lambda v: v, ["{v}"], ""),
    "loop-state": ("Int", "(loop/recur :max 1 :state {v} :on-exhausted s (fn (s) (done s)))", lambda v: v, [], ""),
    "done": ("Int", "(loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (done {v})))", lambda v: v, [], ""),
    "continue": ("Int", ONE_ROUND.replace("{seed}", "0"), lambda v: v, [], ""),
    "continue-record": (
        "Pair", ONE_ROUND.replace("{seed}", "(record Pair :a 0 :b 0)").replace("{v}", "(record Pair :a {v} :b 9)"),
        lambda v: {"a": v, "b": 9}, [], ""),
    "on-exhausted": (
        "Int", "(loop/recur :max 1 :state 0 :on-exhausted {v} (fn (s) (if (= n 7) (done s) (continue s))))",
        lambda v: v, [], ""),
    "map-source": ("List[Int]", "(list/map ((x (list {v} 9))) (+ x 1))", lambda v: [v + 1, 10], [], ""),
    "serial-map-source": ("List[Int]", f"(list/map-effect ((x (list {{v}}))) :max 1 {E(5)})", lambda v: [5], ["5"], ""),
    "parallel-map-source": (
        "List[Int]", f'(list/map-effect ((x (list {{v}}))) :max 1 :parallel 1 :workspace "ws/w" {E(5)})',
        lambda v: [5], ["5"], ""),
    "parallel-map-in-continue": (
        "Int", ONE_ROUND.replace("{seed}", "0").replace("{v}", f"(list/length {PAR.replace('{source}', '(list {v})')})"),
        lambda v: 1, ["5"], ""),
    "parallel-map-in-done": (
        "Int", f"(loop/recur :max 1 :state 0 :on-exhausted s (fn (s) (done (list/length {PAR.replace('{source}', '(list {v})')}))))",
        lambda v: 1, ["5"], ""),
    # The effect's own place has a pure sibling.
    "record-field-beside-match": ("Tri", f"(record Tri :a {{v}} :b 9 :c {M})", lambda v: {"a": v, "b": 9, "c": 1}, [], ""),
    "list-element-beside-cond": ("List[Int]", "(list {v} (cond ((> n 5) 0) (else 1)))", lambda v: [v, 1], [], ""),
    "variant-field-beside-map": (
        "Box", "(variant Box RECT :w {v} :h 0 :k (list/length (list/map ((x (list 1 2))) x)))",
        lambda v: {"w": v, "h": 0, "k": 2, "variant": "RECT"}, [], ""),
    # The effect decides the whole source.
    "map-source-whole": ("List[Int]", "(list/map ((x (if (> {v} 0) (list 4) (list 6)))) (+ x 1))", lambda v: [5], [], ""),
    "serial-map-source-whole": (
        "List[Int]", f"(list/map-effect ((x (if (> {{v}} 0) (list 4) (list 6)))) :max 1 {E(5)})", lambda v: [5], ["5"], ""),
    "parallel-map-source-whole": (
        "List[Int]", PAR.replace("{source}", "(if (> {v} 0) (list 4) (list 6))"), lambda v: [5], ["5"], ""),
    "loop-max": (
        "Int", "(loop/recur :max {v} :state 0 :on-exhausted s (fn (s) (if (= n 7) (done s) (continue (+ s 1)))))",
        lambda v: v, [], ""),
    "operator-operand": ("Int", "(+ {v} 100)", lambda v: v + 100, [], ""),
    "if-condition": ("Int", "(if (> {v} 0) 7 8)", lambda v: 7, [], ""),
    "cond-condition": ("Int", "(cond ((> {v} 0) 7) (else 8))", lambda v: 7, [], ""),
}

# Cells refused at compile time, with their code. Every other cell runs. A `continue` value that holds an
# effect under control below its top, outside a constructor, list, path child or map source, cannot lower.
REFUSED: dict[tuple[str, str], str] = {
    ("continue", "and"): "effect_not_permitted",
    ("continue", "or"): "effect_not_permitted",
    ("continue", "and-skips"): "effect_not_permitted",
    ("continue", "or-skips"): "effect_not_permitted",
    ("continue", "nested-map"): "effect_not_permitted",
}


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("position", POSITIONS)
def test_effect_shape_in_a_value_position_runs_or_is_refused_by_name(tmp_path: Path, position: str, shape: str) -> None:
    returns, template, expected, after, decls = POSITIONS[position]
    expression, shape_value, log = SHAPES[shape]
    (tmp_path / "ws" / "w").mkdir(parents=True)
    write(tmp_path, returns, template.replace("{v}", expression), decls)

    result = run(tmp_path)

    assert "[compiler_defect]" not in result.stderr, result.stderr
    if (position, shape) in REFUSED:
        assert (result.returncode, f"[{REFUSED[position, shape]}]" in result.stderr) == (2, True), result.stderr
        return
    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (
        expected(shape_value), log + [entry.replace("{v}", str(shape_value)) for entry in after])
