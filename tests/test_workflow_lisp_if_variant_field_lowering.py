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
from tests.agent_session_shims import closed_path

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


def test_field_after_discriminant_on_procedure_parameter_runs(tmp_path):
    declarations = UNION + " (defproc get-n ((a A)) -> Int (if (= a.variant OK) a.n 0))"
    _compile(tmp_path, declarations, "(defworkflow run ((a A)) -> Int (+ (get-n a) 1))")
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT)] == [6, 1]


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


THREE = "(defunion A (OK (n Int)) (BAD (why String)) (SKIP))"
SKIP_INPUT = {"a": {"variant": "SKIP"}}
REC = UNION + " (defrecord Rec (n Int))"
APPLY = (" (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int (hook value))"
         " (defproc apply-rec ((hook ProcRef[Rec -> Int]) (value Rec)) -> Int (hook value))")
B_OK, B_BAD = {"variant": "OK", "n": 2}, {"variant": "BAD", "why": "y"}
AB = [{"a": OK_INPUT["a"], "b": B_OK}, {"a": OK_INPUT["a"], "b": B_BAD}, {"a": BAD_INPUT["a"], "b": B_OK}]
EFFECT = '(command-result c :argv ("python" "c.py" {} "x") :returns Int)'


def _workflow(body: str, params: str = "((a A))") -> str:
    return f"(defworkflow run {params} -> Int {body})"


# One program per WCC binder that can rebind the tested name inside the narrowed branch
# (closed/variant_proof.py `_SCOPED`, `_arm_children`). A read of the rebinding must not take the
# outer proof, so values must be right; a program that compiled before the variant-proof lowering
# keeps the digest it had there (main at 0af290d9), so its recorded runs still resume.
SCOPES = {
    "let": (REC, _workflow("(if (= a.variant OK) (let* ((a (record Rec :n 42))) a.n) 0)"), None, [42, 0],
            "sha256:b987a72fe8e419bc052266b682ac9e9613f59bd3908a257fb2c39ad82ec9f856"),
    "let-later-binding": (REC, _workflow("(if (= a.variant OK) (let* ((x 1) (a (record Rec :n 42)) (y a.n)) (+ x y)) 0)"),
                          None, [43, 0], "sha256:2b51aee68dd767a9b4e7082a983d1cd6b8b9f710dba656c84cdc6f32b7801173"),
    "let-own-right-side": (REC, _workflow("(if (= a.variant OK) (let* ((a (record Rec :n a.n))) a.n) 0)"),
                           None, [5, 0], None),
    "let-right-side-is-the-read": (REC, _workflow("(if (= a.variant OK) (let* ((a a.n)) " + EFFECT.format("a") + ") 0)"),
                                   None, [50, 0], None),
    "match-binder": (REC, _workflow("(if (= a.variant OK) (match b ((OK a) a.n) ((BAD x) -3)) 0)", "((a A) (b A))"),
                     AB, [2, -3, 0], "sha256:5e8cb99646815f702f084758b1fc8c6992244253c6e333078bee66cd815c47ea"),
    "join-of-if": (REC, _workflow("(if (= a.variant OK) (let* ((a (if (= b.variant OK) (let* ((v " + EFFECT.format(1)
                                  + ")) (record Rec :n v)) (record Rec :n 0)))) a.n) 0)", "((a A) (b A))"),
                   AB, [10, 0, 0], "sha256:ac9fdb5360aa008c60882edd5d767a68af2ff8bb3046a7d9b597fa71dbdbcc2f"),
    "join-of-match": (REC, _workflow("(if (= a.variant OK) (let* ((a (match b ((OK x) (let* ((v " + EFFECT.format("x.n")
                                     + ")) (record Rec :n v))) ((BAD y) (record Rec :n 0))))) a.n) 0)", "((a A) (b A))"),
                      AB, [20, 0, 0], "sha256:6e49580247caef4ea112c546d17ddec6b931a941527ed063fc78c45367283a53"),
    "loop-state-and-exhausted": (REC, _workflow(
        "(if (= a.variant OK) (loop/recur :max 5 :state (record Rec :n 1) :on-exhausted a.n"
        " (fn (a) (if (< a.n 3) (continue (record Rec :n (+ a.n 1))) (done a.n)))) 0)"), None, [3, 0], "sha256:4ba5c9ac5a01a1f7833cef1b667a302c834bb6c4b0d10bd57b9a81b0912665ce"),
    "let-proc-parameter": (REC + APPLY, _workflow(
        "(if (= a.variant OK) (let-proc ((f ((a Rec)) -> Int a.n)) (apply-rec (proc-ref f) (record Rec :n 7))) 0)"),
        None, [7, 0], "sha256:8f1c342060e1248411e6d1ad1ab0cd1f7dc630eecbb85b18be0d84e8405f5a1c"),
    "let-proc-local": (REC + APPLY, _workflow(
        "(if (= a.variant OK) (let-proc ((f ((x Int)) -> Int (let* ((a (record Rec :n x))) a.n))) (apply-int (proc-ref f) 3)) 0)"),
        None, [3, 0], "sha256:6129ad773b8480e1f08cbdc4be2070f97cb0eda2c941eb7cf857abc44ac28e1c"),
    "procedure-parameter": (REC + " (defproc getn ((a Rec)) -> Int a.n)",
                            _workflow("(if (= a.variant OK) (+ (getn (record Rec :n 4)) a.n) 0)"), None, [9, 0], None),
    "macro-binder": (REC + " (defmacro bind1 (nm v body) (let* ((nm v)) body))",
                     _workflow("(if (= a.variant OK) (bind1 a (record Rec :n 42) a.n) 0)"), None, [42, 0], "sha256:b987a72fe8e419bc052266b682ac9e9613f59bd3908a257fb2c39ad82ec9f856"),
}


@pytest.mark.parametrize("binder", sorted(SCOPES))
def test_a_binder_that_rebinds_the_tested_name_hides_the_proof(tmp_path, binder):
    declarations, workflow, inputs, values, digest = SCOPES[binder]
    built = _compile(tmp_path, declarations, workflow)
    assert [_run(tmp_path, row) for row in inputs or (OK_INPUT, BAD_INPUT)] == values
    if digest is not None:
        assert built["digest"] == digest


def test_a_rebinding_branch_with_effects_keeps_its_effect_sites(tmp_path):
    workflow = ('(defworkflow run ((a A)) -> Int (if (= a.variant OK) (let* ((a (record Rec :n 42))'
                ' (x (command-result c :argv ("python" "c.py" a.n "x") :returns Int))'
                ' (y (command-result c :argv ("python" "c.py" "1" "x") :returns Int))) (+ x y)) 0))')
    built = _compile(tmp_path, REC, workflow)
    assert (built["digest"], built["tree"]["sites"]) == (
        "sha256:b37f1a9e54189f33c4f8db80040ec4bd6621e7eae892709ce870582a1f0edeb4", [["workflow:m::run", "then / x"], ["workflow:m::run", "then / y"]])


def test_cond_after_a_clause_that_excludes_a_variant_runs(tmp_path):
    _compile(tmp_path, THREE, "(defworkflow run ((a A)) -> Int (cond ((= a.variant BAD) 1) ((= a.variant OK) a.n) (else 3)))")
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT), _run(tmp_path, SKIP_INPUT)] == [5, 1, 3]


def test_both_branches_reading_under_an_excluded_variant_is_refused(tmp_path):
    declarations = "(defunion A (OK (n Int)) (BAD (why String)) (SKIP (z Int)))"
    workflow = "(defworkflow run ((a A)) -> Int (if (= a.variant BAD) 0 (if (= a.variant OK) a.n a.z)))"
    assert _refused_at(tmp_path, declarations, workflow, "a.n") == "closed_program_gap"


def test_a_cond_that_excludes_a_variant_before_two_reading_clauses_is_that_refused_shape(tmp_path):
    clauses = ('((= a.variant SKIP) 3)', '((= a.variant BAD) (if (= a.why "x") 10 11))')
    refused = f"(defworkflow run ((a A)) -> Int (cond {clauses[0]} {clauses[1]} (else a.n)))"
    assert _refused_at(tmp_path, THREE, refused, "a.why") == "closed_program_gap"
    _compile(tmp_path, THREE, f"(defworkflow run ((a A)) -> Int (cond {clauses[1]} {clauses[0]} (else a.n)))")
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT), _run(tmp_path, SKIP_INPUT)] == [5, 10, 3]


def test_the_whole_tested_value_stays_the_union_in_the_narrowed_branch(tmp_path):
    declarations = UNION + " (defrecord W (x A) (k Int))"
    workflow = "(defworkflow run ((a A)) -> W (if (= a.variant OK) (record W :x a :k a.n) (record W :x a :k 0)))"
    _compile(tmp_path, declarations, workflow)
    assert _run(tmp_path, OK_INPUT) == {"x": OK_INPUT["a"], "k": 5}


def test_a_pure_match_in_a_shared_branch_runs(tmp_path):
    workflow = "(defworkflow run ((a A)) -> Int (if (= a.variant OK) a.n (match a ((OK o) o.n) ((BAD b) 1) ((SKIP s) 2))))"
    _compile(tmp_path, THREE, workflow)
    assert [_run(tmp_path, OK_INPUT), _run(tmp_path, BAD_INPUT), _run(tmp_path, SKIP_INPUT)] == [5, 1, 2]


def test_an_effect_in_a_shared_branch_is_refused_at_the_read(tmp_path):
    workflow = ('(defworkflow run ((a A)) -> Int (if (= a.variant OK) a.n'
                ' (command-result c :argv ("python" "c.py" "1" "x") :returns Int)))')
    assert _refused_at(tmp_path, THREE, workflow, "a.n") == "closed_program_gap"


def _refused_at(tmp_path: Path, declarations: str, workflow: str, read: str) -> str:
    """The diagnostic code of a refusal located at the first `read` of the workflow line."""
    stderr = _refusal(tmp_path, declarations, workflow)
    line = _source(declarations, workflow).splitlines()[4]
    location = f"m.orc:5:{line.index(read) + 1}: ["
    assert location in stderr and "compiler_defect" not in stderr, stderr
    return stderr.split(location, 1)[1].split("]", 1)[0]


PROMPT_SOURCE = """(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule m) (export run)
  (defrecord Result (ok Bool))
  (defunion A (OK (msg String)) (BAD (why String)))
  (defprompt ask (:fills (message :text)) -> Result "Say: {message}")
  (defworkflow run ((a A)) -> Result
    (if (= a.variant OK)
        (provider-result providers.review :prompt (ask :message a.msg) :model "m" :effort "low")
        (record Result :ok false))))
"""
PROVIDER = """import os, sys
from pathlib import Path
with open("calls.log", "a", encoding="utf-8") as log:
    log.write(sys.stdin.read().replace("\\n", " ") + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"ok": true}')
"""


def test_a_variant_field_in_a_prompt_fill_reaches_the_provider(tmp_path):
    (tmp_path / "m.orc").write_text(PROMPT_SOURCE, encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({"providers.review": "codex"}))
    (tmp_path / "prompts.json").write_text("{}")
    (tmp_path / "commands.json").write_text("{}")
    shim = tmp_path / "bin" / "codex"
    shim.parent.mkdir()
    shim.write_text(f"#!{sys.executable}\n" + PROVIDER, encoding="utf-8")
    shim.chmod(0o700)
    env = {**os.environ, "PATH": closed_path(tmp_path / "bin"), "PYTHONPATH": str(ROOT)}
    results = []
    for message in ("from-the-ok-variant", None):
        shutil.rmtree(tmp_path / ".orchestrate" / "runs", ignore_errors=True)
        value = {"variant": "OK", "msg": message} if message else {"variant": "BAD", "why": "x"}
        (tmp_path / "in.json").write_text(json.dumps({"a": value}))
        run = subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", "m.orc", "--entry-workflow", "m::run",
                              "--provider-externs-file", "providers.json", "--prompt-externs-file", "prompts.json",
                              "--command-boundaries-file", "commands.json", "--input-file", "in.json"],
                             cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
        assert run.returncode == 0, run.stderr
        results.append(json.loads(run.stdout.strip().splitlines()[-1]))
    calls = (tmp_path / "calls.log").read_text().splitlines()
    assert (results, len(calls), "from-the-ok-variant" in calls[0]) == ([{"ok": True}, {"ok": False}], 1, True)
