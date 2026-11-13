"""A variant-only field read after a typed discriminant test lowers to a closed `case`.

The typechecker grants branch-local variant proof for `(= x.variant TAG)` in
`if`, `cond` and `and` (frontend specification, section 12). The closed program
has one narrowing construct, `case`; these tests compile through the public CLI
and run the result with stand-in commands.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

import orchestrator
from orchestrator.contracts.closed_program.check import CheckedFormError, validate

ROOT = Path(orchestrator.__file__).parents[1]
UNION = "(defunion A (OK (n Int)) (BAD (why String)))"
PROBE = """import json, os, sys
from pathlib import Path
raw = sys.argv[1]
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(raw + "\\n")
value = int(raw)
result = {"variant": "OK", "n": value} if value > 0 else {"variant": "BAD", "why": "neg"}
if len(sys.argv) > 2:
    result = value * 10
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(result))
"""


def _source(declarations: str, workflow: str) -> str:
    return (
        '(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n (defmodule m)\n (export run)\n'
        f" {declarations}\n {workflow})\n"
    )


def _cli(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONHASHSEED": "0"}
    return subprocess.run(
        [sys.executable, "-m", "orchestrator", *args, "m.orc", "--entry-workflow", "m::run",
         "--command-boundaries-file", "commands.json"],
        cwd=tmp_path, env=env, capture_output=True, text=True, check=False,
    )


def _write(tmp_path: Path, declarations: str, workflow: str) -> None:
    (tmp_path / "m.orc").write_text(_source(declarations, workflow), encoding="utf-8")
    (tmp_path / "c.py").write_text(PROBE, encoding="utf-8")
    (tmp_path / "commands.json").write_text(json.dumps(
        {"c": {"kind": "external_tool", "stable_command": ["python", "c.py"], "closure": ["c.py"]}}))


def _compile(tmp_path: Path, declarations: str, workflow: str) -> dict:
    _write(tmp_path, declarations, workflow)
    result = _cli(tmp_path, "compile")
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    tree = json.loads((Path(summary["build_root"]) / "closed_program.json").read_text())
    return {"digest": summary["program_digest"], "tree": tree.get("tree", tree)}


def _refusal(tmp_path: Path, declarations: str, workflow: str) -> str:
    _write(tmp_path, declarations, workflow)
    result = _cli(tmp_path, "compile")
    assert result.returncode == 2, result.stdout
    return result.stderr


def _run(tmp_path: Path, inputs: dict) -> object:
    shutil.rmtree(tmp_path / ".orchestrate" / "runs", ignore_errors=True)
    (tmp_path / "in.json").write_text(json.dumps(inputs))
    result = _cli(tmp_path, "run", "--input-file", "in.json")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _kinds(node) -> list[str]:
    if isinstance(node, dict):
        return [node.get("k"), *(kind for child in node.values() for kind in _kinds(child))]
    if isinstance(node, list):
        return [kind for child in node for kind in _kinds(child)]
    return []


INPUT = "(defworkflow run ((a A)) -> Int (if (= a.variant OK) a.n 0))"
OK_INPUT, BAD_INPUT = {"a": {"variant": "OK", "n": 5}}, {"a": {"variant": "BAD", "why": "x"}}


def test_field_after_discriminant_on_workflow_input_runs(tmp_path):
    _compile(tmp_path, UNION, INPUT)
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [5, 0]


def test_field_after_discriminant_on_procedure_result_runs(tmp_path):
    declarations = UNION + ' (defproc mk ((n Int)) -> A (if (> n 0) (variant A OK :n n) (variant A BAD :why "neg")))'
    _compile(tmp_path, declarations, "(defworkflow run ((n Int)) -> Int (let* ((a (mk n))) (if (= a.variant OK) a.n 0)))")
    assert [_run(tmp_path, {"n": 3}), _run(tmp_path, {"n": -1})] == [3, 0]


def test_field_after_discriminant_on_command_result_runs(tmp_path):
    workflow = ('(defworkflow run ((n Int)) -> Int (let* ((a (command-result c :argv ("python" "c.py" n) :returns A)))'
                ' (if (= a.variant OK) (+ a.n 1) 0)))')
    _compile(tmp_path, UNION, workflow)
    assert [_run(tmp_path, {"n": 4}), _run(tmp_path, {"n": -2})] == [5, 0]


def test_field_after_discriminant_in_cond_runs(tmp_path):
    _compile(tmp_path, UNION, "(defworkflow run ((a A)) -> Int (cond ((= a.variant OK) a.n) (else 0)))")
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [5, 0]


def test_exhaustive_cond_without_else_runs(tmp_path):
    workflow = "(defworkflow run ((a A)) -> Int (cond ((= a.variant OK) a.n) ((= a.variant BAD) 0)))"
    _compile(tmp_path, UNION, workflow)
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [5, 0]


def test_field_in_a_conditional_value_runs(tmp_path):
    _compile(tmp_path, UNION, "(defworkflow run ((a A)) -> Bool (if (= a.variant OK) (> a.n 3) false))")
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [True, False]


@pytest.mark.parametrize("workflow", (
    "(defworkflow run ((a A)) -> Bool (and (= a.variant OK) (> a.n 3)))",
    "(defworkflow run ((a A) (r Bool)) -> Int (if (and (= a.variant OK) r) a.n 0))",
))
def test_compound_boolean_proof_is_refused_by_the_typechecker(tmp_path, workflow):
    assert "[variant_ref_unproved]" in _refusal(tmp_path, UNION, workflow)


def test_negated_discriminant_test_runs(tmp_path):
    _compile(tmp_path, UNION, "(defworkflow run ((a A)) -> Int (if (not (= a.variant OK)) 0 a.n))")
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [5, 0]


def test_else_branch_reads_the_other_variant(tmp_path):
    _compile(tmp_path, UNION, '(defworkflow run ((a A)) -> String (if (= a.variant OK) "ok" a.why))')
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == ["ok", "x"]


def test_field_with_variant_dependent_types_runs(tmp_path):
    _compile(tmp_path, "(defunion A (OK (n Int)) (BAD (n String)))",
             '(defworkflow run ((a A)) -> String (if (= a.variant OK) "int" a.n))')
    assert _run(tmp_path, {"a": {"variant": "BAD", "n": "s"}}) == "s"


def test_field_shared_with_one_type_keeps_the_plain_conditional(tmp_path):
    built = _compile(tmp_path, "(defunion A (OK (n Int)) (BAD (n Int)))", INPUT)
    assert "case" not in _kinds(built["tree"]["body"])


def test_three_variants_with_pure_else_runs(tmp_path):
    _compile(tmp_path, "(defunion A (OK (n Int)) (BAD (why String)) (SKIP))", INPUT)
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, {"a": {"variant": "SKIP"}})] == [5, 0]


def test_nested_union_fields_after_two_discriminant_tests_run(tmp_path):
    declarations = "(defunion Inner (HIT (k Int)) (MISS)) (defunion Outer (FULL (inner Inner)) (EMPTY))"
    workflow = ("(defworkflow run ((o Outer)) -> Int (if (= o.variant FULL)"
                " (let* ((i o.inner)) (if (= i.variant HIT) i.k 0)) -1))")
    _compile(tmp_path, declarations, workflow)
    full = {"o": {"variant": "FULL", "inner": {"variant": "HIT", "k": 9}}}
    assert [_run(tmp_path, full), _run(tmp_path, {"o": {"variant": "EMPTY"}})] == [9, -1]


def test_effectful_branch_reads_the_field_in_command_argv(tmp_path):
    workflow = ('(defworkflow run ((a A)) -> Int (if (= a.variant OK)'
                ' (command-result c :argv ("python" "c.py" a.n "x") :returns Int) 0))')
    _compile(tmp_path, UNION, workflow)
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [50, 0]
    assert (tmp_path / "c.log").read_text().splitlines() == ["5"]


def test_test_on_one_value_does_not_prove_another(tmp_path):
    workflow = "(defworkflow run ((a A) (b A)) -> Int (if (= a.variant OK) b.n 0))"
    assert "[variant_ref_unproved]" in _refusal(tmp_path, UNION, workflow)


def test_unshareable_effectful_branch_is_refused_with_a_diagnostic(tmp_path):
    workflow = ('(defworkflow run ((a A)) -> Int (if (= a.variant OK) a.n'
                ' (command-result c :argv ("python" "c.py" "1" "x") :returns Int)))')
    stderr = _refusal(tmp_path, "(defunion A (OK (n Int)) (BAD (why String)) (SKIP))", workflow)
    assert "[closed_program_gap]" in stderr and "compiler_defect" not in stderr


def test_match_and_let_star_controls_run(tmp_path):
    _compile(tmp_path, UNION, "(defworkflow run ((a A)) -> Int (match a ((OK o) o.n) ((BAD b) 0)))")
    assert _run(tmp_path, OK_INPUT) == 5
    _compile(tmp_path, UNION, "(defworkflow run ((a A)) -> Int (if (= a.variant OK) (let* ((x a.n)) x) 0))")
    assert _run(tmp_path, BAD_INPUT) == 0


def test_direct_and_let_star_shapes_differ_only_by_the_authored_binding(tmp_path):
    (tmp_path / "direct").mkdir()
    (tmp_path / "bound").mkdir()
    direct = _compile(tmp_path / "direct", UNION, INPUT)
    bound = _compile(tmp_path / "bound", UNION,
                     "(defworkflow run ((a A)) -> Int (if (= a.variant OK) (let* ((x a.n)) x) 0))")
    direct_case, bound_case = (_case(_unlocated(built["tree"]["body"])) for built in (direct, bound))
    ok_direct, ok_bound = direct_case["arms"][0]["body"], bound_case["arms"][0]["body"]
    assert (ok_bound["k"], ok_bound["value"], ok_bound["body"]["value"]["n"]) == ("let", ok_direct["value"], ok_bound["name"])
    assert direct_case["arms"][1] == bound_case["arms"][1]


def _unlocated(node):
    if isinstance(node, dict):
        return {key: _unlocated(child) for key, child in node.items() if key != "@"}
    return [_unlocated(child) for child in node] if isinstance(node, list) else node


def _case(node):
    if isinstance(node, dict):
        if node.get("k") == "case":
            return node
        node = list(node.values())
    if isinstance(node, list):
        return next((found for found in map(_case, node) if found is not None), None)
    return None


def test_checker_refuses_a_stored_variant_field_read_without_case(tmp_path):
    match = "(defworkflow run ((a A)) -> Int (match a ((OK o) o.n) ((BAD b) 0)))"
    tree = deepcopy(_compile(tmp_path, UNION, match)["tree"])
    tree["body"] = {"k": "if", "cond": {"k": "lit", "v": True, "type": {"kind": "primitive", "name": "Bool"}},
                    "then": {"k": "halt", "value": {"k": "field", "base": {"k": "name", "n": "a"}, "path": ["n"]}},
                    "else": {"k": "halt", "value": {"k": "lit", "v": 0, "type": {"kind": "primitive", "name": "Int"}}}}
    with pytest.raises(CheckedFormError, match="variant-dependent"):
        validate(tree)
