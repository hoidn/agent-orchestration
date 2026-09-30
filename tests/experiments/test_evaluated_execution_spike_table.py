"""Spike of evaluated execution, iteration 2, item F: the closed program as a tree or as a table of definitions.

Throwaway. The tree form attaches a callee body at every call path (P4 as the plan
states it); the table form (design section 6) stores each body once and names the
call site of each activation. The evaluator runs both. These tests measure, for the
owner's choice between them: (a) size, (b) whether the two name the same effects in
the same order, (c) which identities move when a procedure's body gains an effect,
under the ordinal rule of the spike (only effectful unnamed binders are counted) and
under the other one (every unnamed binder is counted).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from experiments.evaluated_execution_spike.census import census, count_nodes
from experiments.evaluated_execution_spike.evaluator import evaluate
from experiments.evaluated_execution_spike.table import resite, to_table
from tests.experiments.test_evaluated_execution_spike import (
    PROGRAMS,
    _cell,
    _refused_by_typecheck,
    build,
    calls,
    install,
    records,
    run_root,
    spike,
)
from tests.workflow_lisp_totality_matrix_sources import RULES, SKIPPED, cells

FIXTURES = Path(__file__).parent / "fixtures" / "evaluated_execution_spike"


def identities(root: Path, sources: dict, program, inputs=None) -> list[str]:
    install(root, sources)
    evaluate(program, inputs=inputs or {}, workspace=root, run_root=run_root(root))
    return [r["identity"] for r in records(root)]


def _programs() -> list:
    matrix = [pytest.param(*_cell(*c)[:2], id="/".join(c)) for c in cells()
              if c not in SKIPPED and c not in RULES and not _refused_by_typecheck(c)]
    return [*matrix, *(pytest.param(case[0], case[1], id=name) for name, case in PROGRAMS.items())]


@pytest.mark.parametrize(("sources", "inputs"), _programs())
def test_the_tree_and_the_table_name_the_same_effects_in_the_same_order(tmp_path: Path, sources, inputs) -> None:
    closed, _ = spike(tmp_path / "tree", sources, inputs=inputs)
    table = to_table(closed)

    assert identities(tmp_path / "table", sources, table, inputs) == [r["identity"] for r in records(tmp_path / "tree")]
    # at most one node for the table and one per definition more than the tree; less when a body repeats
    assert count_nodes(table.tree) <= count_nodes(closed.tree) + 1 + len(table.tree["definitions"])


def _tree_source(depth: int) -> dict[str, str]:
    """The reviewer's synthetic program: each level calls the next three times."""

    definitions = []
    for level in range(depth - 1, -1, -1):
        body = ('(command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box)' if level == depth - 1
                else f"(let* ((a (p{level + 1} n)) (b (p{level + 1} n)) (c (p{level + 1} n))) c)")
        definitions.append(f"  (defproc p{level} ((n Int)) -> Box :effects ((uses-command fetch)) :lowering inline {body})")
    text = ('(workflow-lisp (:language "0.1") (:target-dsl "2.33") (defmodule spk/tree) (export run)\n'
            "  (defrecord Box (n Int))\n" + "\n".join(definitions) + "\n  (defworkflow run () -> Box (p0 1)))\n")
    return {"spk/tree.orc": text}


def test_the_table_grows_with_the_definitions_and_the_tree_with_the_call_paths(tmp_path: Path) -> None:
    sizes = []
    for depth in (1, 2, 3, 4):
        closed = build(tmp_path / str(depth), _tree_source(depth))
        table = to_table(closed)
        sizes.append((count_nodes(closed.tree), len(closed.sites), count_nodes(table.tree), len(table.sites)))

    assert [sites for _, sites, _, _ in sizes] == [1, 3, 9, 27]
    assert [sites for *_, sites in sizes] == [1, 1, 1, 1]
    table_growth = {sizes[i + 1][2] - sizes[i][2] for i in range(1, 3)}
    assert len(table_growth) == 1  # one more definition per level, of one size
    assert sizes[3][0] > 8 * sizes[1][0] - 50  # the tree: about three times per level


def test_the_largest_shipped_workflow_builds_and_its_table_is_smaller(tmp_path: Path) -> None:
    rows = {(r["file"], r["workflow"]): r for r in census(Path.cwd(), tmp_path)}

    task_loop = rows[("workflows/experiments/repository_task_pilot/task_loop.orc", "run-task")]
    assert "not_built" not in task_loop, task_loop
    assert task_loop["table_nodes"] < task_loop["nodes"] and task_loop["table_sites"] < task_loop["sites"]


# (c) What moves when a procedure's body gains an effect ---------------------------------------

BASE = (FIXTURES / "identity_base.orc").read_text(encoding="utf-8")
EDITS = {
    "callee-gains-a-named-effect-first": ("(let* ((a (fetch n)))", "(let* ((z (fetch (+ n 5))) (a (fetch n)))"),
    "callee-gains-an-unnamed-effect-first": ("(keep a (fetch (+ n 1)))", "(keep (fetch (+ n 3)) (fetch (+ n 1)))"),
    "a-pure-callee-gains-an-effect": (
        "(defproc touch ((b Box)) -> Box :effects () :lowering inline b)",
        "(defproc touch ((b Box)) -> Box :effects ((uses-command fetch)) :lowering inline (let* ((q (fetch 99))) b))",
    ),
    "the-caller-gains-a-pure-computation-first": ("(fetch (+ y.n 5))", "(fetch (+ (+ y.n 0) 5))"),
}


def _by_command(root: Path, sources: dict, program) -> dict[str, str]:
    """Each command invocation (the probe's log line) with the identity of its effect."""

    found = identities(root, sources, program)
    return dict(zip(calls(root), found, strict=True))


def moved(tmp_path: Path, edit: str, *, count_pure: bool) -> dict[str, tuple[str, str]]:
    """The effects in both versions whose identity changed, in both forms; the forms must agree."""

    per_form = []
    for form in ("tree", "table"):
        versions = []
        for label, text in (("base", BASE), ("edited", BASE.replace(*EDITS[edit]))):
            assert text != BASE or label == "base"
            sources = {"spk/identity_base.orc": text}
            closed = resite(build(tmp_path / f"{form}-{label}-build", sources), count_pure=count_pure)
            program = to_table(closed, count_pure=count_pure) if form == "table" else closed
            versions.append(_by_command(tmp_path / f"{form}-{label}-{count_pure}", sources, program))
        base, edited = versions
        per_form.append({c: (base[c], edited[c]) for c in base if c in edited and base[c] != edited[c]})
    assert per_form[0] == per_form[1]
    return per_form[0]


def _short(identity: str) -> str:
    return re.sub(r"spk/identity_base::", "", identity)


X, Y = "run / x=step / {}=fetch / #1", "run / y=step / {}=fetch / #1"


@pytest.mark.parametrize(
    ("edit", "effectful_only", "every_unnamed"),
    [
        ("callee-gains-a-named-effect-first", {},
         {"fetch 11": (X.format("#3"), X.format("#4")), "fetch 21": (Y.format("#3"), Y.format("#4"))}),
        ("callee-gains-an-unnamed-effect-first",
         {"fetch 11": (X.format("#1"), X.format("#2")), "fetch 21": (Y.format("#1"), Y.format("#2"))},
         {"fetch 11": (X.format("#3"), X.format("#4")), "fetch 21": (Y.format("#3"), Y.format("#4"))}),
        ("a-pure-callee-gains-an-effect", {"fetch 26": ("run / #1=fetch / #1", "run / #2=fetch / #1")}, {}),
        ("the-caller-gains-a-pure-computation-first", {}, {"fetch 26": ("run / #3=fetch / #1", "run / #4=fetch / #1")}),
    ],
)
def test_what_moves_when_a_body_changes_is_the_same_in_both_forms_and_depends_on_the_ordinal_rule(
    tmp_path: Path, edit: str, effectful_only: dict, every_unnamed: dict
) -> None:
    for count_pure, expected in ((False, effectful_only), (True, every_unnamed)):
        found = moved(tmp_path / str(count_pure), edit, count_pure=count_pure)
        assert {c: (_short(a), _short(b)) for c, (a, b) in found.items()} == expected, (edit, count_pure)


def test_an_effectful_call_as_the_argument_of_an_effectful_call_typechecks_and_is_not_elaborated(tmp_path: Path) -> None:
    """Found while writing the edits above; outside the totality matrix. A criterion-9 item of iteration 2."""

    bump = ("  (defproc bump ((n Int)) -> Int :effects ((uses-command fetch)) :lowering inline\n"
            "    (let* ((q (fetch 99))) (+ n 1)))\n  (defproc step")
    nested = BASE.replace("  (defproc step", bump, 1).replace("(keep (touch x) (fetch (+ y.n 5)))", "(fetch (bump 26))")

    with pytest.raises(TypeError, match="unsupported WCC elaboration node: ProcedureCallExpr"):
        build(tmp_path, {"spk/identity_base.orc": nested})


def test_the_checked_form_refuses_a_continue_that_names_another_loop(tmp_path: Path) -> None:
    """P5: a `continue` must name the loop it is in (review finding 5)."""

    from experiments.evaluated_execution_spike.sites import CheckedFormError, validate

    closed = build(tmp_path, {"spk/loop_in_loop.orc": (FIXTURES / "loop_in_loop.orc").read_text(encoding="utf-8")})
    loops, continues = [], []

    def walk(node):
        if isinstance(node, dict):
            (loops if node.get("k") == "loop" else continues if node.get("k") == "continue" else []).append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(closed.tree)
    inner_continue = next(c for c in continues if c["loop"] == loops[1]["name"])
    inner_continue["loop"] = loops[0]["name"]

    with pytest.raises(CheckedFormError, match="does not name its enclosing target"):
        validate(closed.tree)
