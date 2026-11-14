"""Every place E1 opens, crossed with every shape of effect: it runs, or it is refused by name.

Contract: docs/design/workflow_lisp_surface_coherence.md §4 (rule 1) and the frontend
specification §16.3. A place E1 opened takes an effect only in a simple value: the simple
shapes run there, with the expected value and each effect once in written order, and every
other shape is refused with the code the place gave before E1. A cell runs through the public
CLI with stand-in commands that log their argument (`tests/test_workflow_lisp_effect_placement.py`).
A `compiler_defect` fails its cell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_workflow_lisp_effect_placement import E, ITEM, M, calls, run, value, write

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

# The shapes that are simple values (frontend specification 16.3): calls and operators over them, no branch.
SIMPLE = ("bare", "two-effects")
# A variant holding an effect beside a field that is not simple: refused wherever it is written.
BESIDE = ("beside-match", "beside-cond", "beside-map")

# A map's item logs the element it is given and returns it, so the shape's value reaches the result.
PAR = f'(list/map-effect ((x {{source}})) :max 1 :parallel 1 :workspace "ws/w" {ITEM})'
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
    "serial-map-source": ("List[Int]", f"(list/map-effect ((x (list {{v}}))) :max 1 {ITEM})", lambda v: [v], ["{v}"], ""),
    "parallel-map-source": ("List[Int]", PAR.replace("{source}", "(list {v})"), lambda v: [v], ["{v}"], ""),
    "parallel-map-in-continue": (
        "List[Int]", ONE_ROUND.replace("{seed}", "(list 0)").replace("{v}", PAR.replace("{source}", "(list {v})")),
        lambda v: [v], ["{v}"], ""),
    "parallel-map-in-done": (
        "List[Int]", f"(loop/recur :max 1 :state (list 0) :on-exhausted s (fn (s) (done {PAR.replace('{source}', '(list {v})')})))",
        lambda v: [v], ["{v}"], ""),
    # The effect's own place has a pure sibling.
    "record-field-beside-match": ("Tri", f"(record Tri :a {{v}} :b 9 :c {M})", lambda v: {"a": v, "b": 9, "c": 1}, [], ""),
    "list-element-beside-cond": ("List[Int]", "(list {v} (cond ((> n 5) 0) (else 1)))", lambda v: [v, 1], [], ""),
    "variant-field-beside-map": (
        "Box", "(variant Box RECT :w {v} :h 0 :k (list/length (list/map ((x (list 1 2))) x)))",
        lambda v: {"w": v, "h": 0, "k": 2, "variant": "RECT"}, [], ""),
    # The effect decides the whole source, under a conditional.
    "map-source-whole": ("List[Int]", "(list/map ((x (if (> {v} 0) (list 4) (list 6)))) (+ x 1))", lambda v: [5], [], ""),
    "serial-map-source-whole": (
        "List[Int]", f"(list/map-effect ((x (if (> {{v}} 0) (list 4) (list 6)))) :max 1 {ITEM})", lambda v: [4], ["4"], ""),
    "parallel-map-source-whole": (
        "List[Int]", PAR.replace("{source}", "(if (> {v} 0) (list 4) (list 6))"), lambda v: [4], ["4"], ""),
    "loop-max": (
        "Int", "(loop/recur :max {v} :state 0 :on-exhausted s (fn (s) (if (= n 7) (done s) (continue (+ s 1)))))",
        lambda v: v, [], ""),
    "operator-operand": ("Int", "(+ {v} 100)", lambda v: v + 100, [], ""),
    "if-condition": ("Int", "(if (> {v} 0) 7 8)", lambda v: 7, [], ""),
    "cond-condition": ("Int", "(cond ((> {v} 0) 7) (else 8))", lambda v: 7, [], ""),
}

# The places E1 opened, each with the code it gave while it took no effect (for a map source written as
# a list, the list element's code): an effect stands there only in a simple value.
OPENED = {
    "record-field": "effect_not_permitted", "variant-field": "effect_not_permitted",
    "list-element": "effect_not_permitted", "nested-constructor": "effect_not_permitted",
    "match-subject": "effect_not_permitted", "continue-record": "effect_not_permitted",
    "on-exhausted": "loop_recur_contract_invalid", "map-source": "effect_not_permitted",
    "serial-map-source": "effect_not_permitted", "parallel-map-source": "effect_not_permitted",
    "parallel-map-in-continue": "effect_not_permitted", "parallel-map-in-done": "effect_not_permitted",
}
# Opened places written with a part that is not simple, whatever the shape: refused for every shape.
NOT_SIMPLE = {
    "record-field-beside-match": "effect_not_permitted", "list-element-beside-cond": "effect_not_permitted",
    "variant-field-beside-map": "effect_not_permitted", "map-source-whole": "list_map_body_effect_forbidden",
    "serial-map-source-whole": "list_map_effect_body_unsupported",
    "parallel-map-source-whole": "list_map_effect_body_unsupported",
}
# A `continue` value with a conditional or a map below its top cannot be evaluated in place.
CONTINUE_REFUSED = ("and", "or", "and-skips", "or-skips", "nested-map")


def refusal(position: str, shape: str) -> str | None:
    """The code a cell is refused with at compile time, or None for a cell that runs."""

    if shape in BESIDE:
        return "effect_not_permitted"
    if position in NOT_SIMPLE:
        return NOT_SIMPLE[position]
    if position in OPENED and shape not in SIMPLE:
        return OPENED[position]
    if position == "continue" and shape in CONTINUE_REFUSED:
        return "effect_not_permitted"
    return None


def test_grid_runs_151_cells_and_refuses_284() -> None:
    codes = [refusal(position, shape) for position in POSITIONS for shape in SHAPES]

    assert (len(codes), codes.count(None)) == (435, 151)


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("position", POSITIONS)
def test_effect_shape_in_a_value_position_runs_or_is_refused_by_name(tmp_path: Path, position: str, shape: str) -> None:
    returns, template, expected, after, decls = POSITIONS[position]
    expression, shape_value, log = SHAPES[shape]
    (tmp_path / "ws" / "w").mkdir(parents=True)
    write(tmp_path, returns, template.replace("{v}", expression), decls)

    result = run(tmp_path)

    assert ("[compiler_defect]" in result.stderr, "Traceback" in result.stderr) == (False, False), result.stderr
    code = refusal(position, shape)
    if code is not None:
        assert (result.returncode, f"[{code}]" in result.stderr, calls(tmp_path)) == (2, True, []), result.stderr
        return
    assert result.returncode == 0, result.stderr
    assert (value(result), calls(tmp_path)) == (
        expected(shape_value), log + [entry.replace("{v}", str(shape_value)) for entry in after])
