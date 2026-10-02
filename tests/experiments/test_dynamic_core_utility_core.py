"""DC-2a bounded-core contract, frozen as UC01–UC12."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from orchestrator.workflow.evaluated.values import EvaluatedValueError


@pytest.fixture(scope="module")
def type_env(tmp_path_factory):
    from orchestrator.workflow_lisp.compiler import (
        compile_stage1_entrypoint,
        linked_module_type_environment,
    )

    path = tmp_path_factory.mktemp("dynamic-core-utility-types") / "utility_core.orc"
    path.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.34") '
        '(defmodule utility_core) (export UtilityResult) '
        '(defrecord UtilityResult (value Int)))',
        encoding="utf-8",
    )
    return linked_module_type_environment(compile_stage1_entrypoint(path), "utility_core")


def _lit(value):
    return {"k": "lit", "v": value}


def _name(name):
    return {"k": "name", "n": name}


def _record(**fields):
    return {"k": "record", "fields": [[key, node] for key, node in fields.items()]}


def _op(name, *args):
    return {"k": "op", "name": name, "args": list(args)}


def _artifact(body, *, schema="workflow-lisp/dynamic-spike/3", budget=500,
              result="Value", inputs=(), effects=(), definitions=None,
              schemas=None):
    definitions = dict(definitions or {})
    entry = {"params": [row[0] for row in inputs], "captures": [], "body": body}
    definitions = {"entry": entry, **definitions}
    artifact = {
        "schema": schema,
        "entry": "entry",
        "budget": budget,
        "schemas": schemas or {"result": {"kind": "primitive", "name": result}},
        "inputs": [list(row) for row in inputs],
        "result": result if result in (schemas or {"result": {"kind": "primitive", "name": result}}) else "result",
        "definitions": definitions,
    }
    if schema.endswith(("/2", "/3")):
        artifact["effects"] = list(effects)
    return json.dumps(artifact)


def _evaluate(body, **options):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    return evaluate(DynamicProgram.from_artifact(_artifact(body, **options)), {})


def _source(body, *, helpers="", result="Value", effects="", budget=200):
    return (
        f'(dynamic-core (:budget {budget}) (:inputs ) (:result {result}) '
        f'(:effects {effects}) {helpers} (run {body}))'
    )


def _compile(source, type_env, path="utility.orc"):
    from experiments.dynamic_core_evaluation.source import compile_source

    return compile_source(source, source_path=path, type_env=type_env)


def _run_source(source, type_env, *, inputs=None, leaf_bridge=None, read_only=False):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    program = _compile(source, type_env)
    restored = DynamicProgram.from_artifact(program.artifact())
    return evaluate(restored, inputs or {}, leaf_bridge=leaf_bridge, read_only=read_only)


def _adapter_source(root: Path, *, mutate_output=False):
    """Build a direct compiled leaf around the maintained compact-controller adapter."""
    from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge
    from tests.experiments.test_evaluated_execution_spike_programs import compact_controller

    _sources, boundaries = compact_controller(root)
    leaf_script = root / "experiments/mlevolve_pair/leaves.py"
    original = leaf_script.read_text(encoding="utf-8")
    instrumented = original.replace(
        "    request = json.loads(raw)\n",
        "    request = json.loads(raw)\n"
        "    with Path(__file__).with_name('adapter-inputs.jsonl').open('a', encoding='utf-8') as log:\n"
        "        log.write(json.dumps({'operation': operation, 'payload': request}, separators=(',', ':')) + '\\n')\n",
        1,
    )
    assert instrumented != original
    leaf_script.write_text(instrumented, encoding="utf-8")
    if mutate_output:
        original = leaf_script.read_text(encoding="utf-8")
        corrupted = original.replace(
            'return {"a": candidate_a, "b": other_b}',
            'return {"a": True, "b": other_b}',
            1,
        )
        assert corrupted != original
        leaf_script.write_text(corrupted, encoding="utf-8")

    source_path = root / "mlevolve_pair/search_compact.orc"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.33")
          (defmodule mlevolve_pair/search_compact) (export adapter-leaf)
          (defrecord Candidate (a Int) (b Int))
          (defworkflow adapter-leaf
            ((operation String) (branch String) (candidate_a Int) (candidate_b Int)
             (other_a Int) (other_b Int) (history_size Int))
            -> Candidate
            (command-result propose-branch-candidate
              :adapter propose_candidate
              :inputs ((operation operation) (branch branch)
                       (candidate_a candidate_a) (candidate_b candidate_b)
                       (other_a other_a) (other_b other_b)
                       (history_size history_size))
              :returns Candidate)))''',
        encoding="utf-8",
    )
    bridge = LeafBridge.compile(
        source_path,
        root,
        operations={"propose": "mlevolve_pair/search_compact::adapter-leaf"},
        command_boundaries=boundaries,
    )
    return bridge, source_path, boundaries


def _adapter_inputs(operation="fuse", branch="both", *, candidate_a=1,
                    candidate_b=2, other_a=3, other_b=4, history_size=5):
    return {
        "operation": operation,
        "branch": branch,
        "candidate_a": candidate_a,
        "candidate_b": candidate_b,
        "other_a": other_a,
        "other_b": other_b,
        "history_size": history_size,
    }


def _effect(inputs):
    return {"k": "effect", "name": "propose", "inputs": _record(**{
        name: _lit(value) for name, value in inputs.items()
    })}


def _run_count(root: Path) -> int:
    return len(list((root / ".orchestrate/runs").glob("*/state.json")))


def _adapter_log(root: Path):
    path = root / "experiments/mlevolve_pair/adapter-inputs.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_UC01_v3_roundtrip_keeps_the_new_vocabulary_out_of_v1_and_v2(tmp_path, type_env):
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    program = _compile(_source("(list/append (list 1) 2" + ")"), type_env)
    path = tmp_path / "program.json"
    path.write_text(program.artifact(), encoding="utf-8")
    restored = DynamicProgram.from_artifact(path.read_text(encoding="utf-8"))
    assert restored.schema == "workflow-lisp/dynamic-spike/3"
    assert restored.digest == program.digest

    additions = [
        _op("list/append", {"k": "list", "items": []}, _lit(1)),
        _op("list/length", {"k": "list", "items": []}),
        {"k": "record-update", "base": _record(x=_lit(1)), "fields": [["x", _lit(2)]]},
        {"k": "fail", "reason": "reason"},
    ]
    for schema in ("workflow-lisp/dynamic-spike/1", "workflow-lisp/dynamic-spike/2"):
        legacy_body = _lit(7)
        legacy = DynamicProgram.from_artifact(_artifact(
            legacy_body, schema=schema, effects=(), result="Value"
        ))
        from experiments.dynamic_core_evaluation.evaluator import evaluate
        assert evaluate(legacy, {}).json_value() == 7
        for node in additions:
            with pytest.raises(EvaluatedValueError) as error:
                DynamicProgram.from_artifact(_artifact(node, schema=schema, effects=()))
            assert error.value.code == "dynamic_spike_invalid"


def test_UC02_append_preserves_order_copies_the_list_and_allows_mixed_closures(type_env):
    assert _run_source(_source(
        "(let* ((items (list 1 \"two\")) (grown (list/append items true))) "
        "(list (at grown 0) (at grown 1) (at grown 2) (list/length items)))"
    ), type_env).json_value() == [1, "two", True, 2]
    assert _run_source(_source(
        "((at (list/append (list (fn (n) (+ n 1))) "
        "(fn (n) (+ n 2))) 1) 40)"
    ), type_env).json_value() == 42
    for values, appended, expected in (([], 1, [1]), ([1, 2], 3, [1, 2, 3])):
        body = _op("list/append", {"k": "list", "items": [_lit(v) for v in values]}, _lit(appended))
        assert _evaluate(body).json_value() == expected


def test_UC03_append_refuses_nonlists_and_wrong_arity():
    cases = [
        (_op("list/append", _lit(1), _lit(2)), "dynamic_operand_type"),
        (_op("list/append", {"k": "list", "items": []}), "dynamic_operand_type"),
        (_op("list/append", {"k": "list", "items": []}, _lit(1), _lit(2)), "dynamic_operand_type"),
        (_op("list/append", _record(x=_lit(1)), _lit(2)), "dynamic_operand_type"),
    ]
    for body, code in cases:
        with pytest.raises(EvaluatedValueError) as error:
            _evaluate(body)
        assert error.value.code == code
        assert error.value.location.endswith("/body")
        assert error.value.metadata["steps"] > 0


def test_UC04_length_returns_checked_int_and_refuses_nonlists_and_wrong_arity():
    assert _evaluate(_op("list/length", {"k": "list", "items": []})).json_value() == 0
    assert _evaluate(_op("list/length", {"k": "list", "items": [_lit(1), _lit("x")] })).json_value() == 2
    empty = {"k": "list", "items": []}
    for args in ((_lit(1),), (), (empty, empty)):
        with pytest.raises(EvaluatedValueError) as error:
            _evaluate(_op("list/length", *args))
        assert error.value.code == "dynamic_operand_type"


def test_UC05_record_update_retains_fields_and_can_replace_with_a_closure(type_env):
    source = _source(
        '''(let* (
          (base (record (count 1) (keep "yes")))
          (updated (record-update base (count (fn (n) (+ n 1)))))
        )
        (list ((field updated "count") 4) (field updated "keep")))'''
    )
    assert _run_source(source, type_env).json_value() == [5, "yes"]


def test_UC06_all_update_keys_are_checked_before_any_replacement_runs():
    missing_later = {
        "k": "record-update",
        "base": _record(x=_lit(1)),
        "fields": [["x", {"k": "fail", "reason": "replacement_ran"}], ["missing", _lit(2)]],
    }
    definitions = {"helper": {"params": [], "captures": [], "body": missing_later}}
    with pytest.raises(EvaluatedValueError) as error:
        _evaluate({"k": "call", "callee": {"k": "fn", "code": "helper", "captures": []}, "args": []},
                  definitions=definitions)
    assert error.value.code == "dynamic_field_missing"
    assert error.value.metadata["field"] == "missing"
    assert error.value.metadata["steps"] > 0
    assert error.value.metadata["call_context"]

    with pytest.raises(EvaluatedValueError) as error:
        _evaluate({
            "k": "record-update", "base": _lit(7),
            "fields": [["x", {"k": "fail", "reason": "replacement_ran"}]],
        })
    assert error.value.code == "dynamic_operand_type"


def test_UC07_empty_duplicate_and_nonliteral_updates_fail_admission(type_env):
    source_cases = [
        _source('(record-update (record (x 1)))'),
        _source('(record-update (record (x 1)) (x 2) ("x" 3))'),
        _source('(record-update (record (x 1)) ((field (record) "x") 2))'),
    ]
    for source in source_cases:
        with pytest.raises(EvaluatedValueError) as error:
            _compile(source, type_env)
        assert error.value.code == "dynamic_source_invalid"

    malformed = [
        {"k": "record-update", "base": _record(x=_lit(1)), "fields": []},
        {"k": "record-update", "base": _record(x=_lit(1)), "fields": [["x", _lit(2)], ["x", _lit(3)]]},
        {"k": "record-update", "base": _record(x=_lit(1)), "fields": [[1, _lit(2)]]},
        {"k": "record-update", "base": _record(x=_lit(1)), "fields": [["x", _lit(2)]], "extra": 1},
    ]
    for body in malformed:
        with pytest.raises(EvaluatedValueError) as error:
            from experiments.dynamic_core_evaluation.program import DynamicProgram
            DynamicProgram.from_artifact(_artifact(body))
        assert error.value.code == "dynamic_spike_invalid"

    unreachable = _artifact(_lit(1), definitions={
        "unused": {"params": [], "captures": [], "body": malformed[0]},
    })
    with pytest.raises(EvaluatedValueError) as error:
        from experiments.dynamic_core_evaluation.program import DynamicProgram
        DynamicProgram.from_artifact(unreachable)
    assert error.value.code == "dynamic_spike_invalid"


def test_UC08_effect_operands_run_once_in_order_and_share_one_budget(tmp_path):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    bridge, _path, _boundaries = _adapter_source(tmp_path)
    first = _effect(_adapter_inputs(candidate_a=1, other_b=4))
    second = _effect(_adapter_inputs(candidate_a=2, other_b=5))
    body = _op("list/append", {"k": "list", "items": [first]}, second)
    result = evaluate(DynamicProgram.from_artifact(_artifact(body, effects=("propose",))), {}, leaf_bridge=bridge)
    assert result.json_value() == [
        {"return__a": 1, "return__b": 4},
        {"return__a": 2, "return__b": 5},
    ]
    assert _run_count(tmp_path) == 2
    requests = _adapter_log(tmp_path)
    assert [row["payload"]["candidate_a"] for row in requests] == [1, 2]
    assert [list(row["payload"]) for row in requests] == [
        ["operation", "branch", "candidate_a", "candidate_b", "other_a", "other_b", "history_size"]
    ] * 2

    update = {
        "k": "let",
        "bindings": [["base", _record(first=_lit(0), second=_lit(0), keep=_lit("same"))]],
        "body": {
            "k": "let",
            "bindings": [["updated", {
                "k": "record-update", "base": _name("base"),
                "fields": [
                    ["first", {"k": "field", "base": _effect(_adapter_inputs(candidate_a=10, other_b=14)), "name": "return__a"}],
                    ["second", {"k": "field", "base": _effect(_adapter_inputs(candidate_a=20, other_b=24)), "name": "return__a"}],
                ],
            }]],
            "body": {"k": "list", "items": [
                {"k": "field", "base": _name("updated"), "name": "first"},
                {"k": "field", "base": _name("updated"), "name": "second"},
                {"k": "field", "base": _name("updated"), "name": "keep"},
                {"k": "field", "base": _name("base"), "name": "first"},
                {"k": "field", "base": _name("base"), "name": "second"},
            ]},
        },
    }
    updated = evaluate(DynamicProgram.from_artifact(_artifact(update, effects=("propose",))), {}, leaf_bridge=bridge)
    assert updated.json_value() == [10, 20, "same", 0, 0]
    requests = _adapter_log(tmp_path)
    assert [row["payload"]["candidate_a"] for row in requests] == [1, 2, 10, 20]

    (tmp_path / ".orchestrate/runs").rename(tmp_path / "runs-complete")
    (tmp_path / "experiments/mlevolve_pair/adapter-inputs.jsonl").unlink()
    body_cost_through_first_leaf = 11  # operator + list + effect + record + seven input literals
    with pytest.raises(EvaluatedValueError) as error:
        evaluate(DynamicProgram.from_artifact(_artifact(
            body, effects=("propose",), budget=body_cost_through_first_leaf,
        )), {}, leaf_bridge=bridge)
    assert error.value.code == "dynamic_budget_exhausted"
    assert error.value.metadata["steps"] == body_cost_through_first_leaf
    assert _run_count(tmp_path) == 1


def test_UC09_fail_keeps_reason_context_and_skips_unselected_work(tmp_path, type_env):
    bridge, _path, _boundaries = _adapter_source(tmp_path)
    selected = _source(
        '(if true (chosen) '
        '(effect propose (record (operation "fuse") (branch "both") '
        '(candidate_a 1) (candidate_b 2) (other_a 3) (other_b 4) (history_size 5))))',
        helpers='(define (chosen) (fail "chosen_reason"))',
        effects="propose",
    )
    with pytest.raises(EvaluatedValueError) as error:
        _run_source(selected, bridge.type_env, leaf_bridge=bridge)
    assert error.value.code == "dynamic_explicit_failure"
    assert error.value.metadata["reason"] == "chosen_reason"
    assert error.value.location.endswith("/body")
    assert error.value.metadata["call_context"]
    assert error.value.metadata["steps"] > 0
    assert _run_count(tmp_path) == 0
    assert _run_source(_source('(if true 7 (fail "unselected"))'), type_env).json_value() == 7


def test_UC10_fail_requires_an_admitted_literal_reason(type_env):
    for text in (
        _source('(fail "")'),
        _source('(fail 3)'),
        _source('(let* ((reason "x")) (fail reason))'),
        _source('1', helpers='(define (hidden) (fail false))'),
    ):
        with pytest.raises(EvaluatedValueError) as error:
            _compile(text, type_env)
        assert error.value.code == "dynamic_source_invalid"
        assert "reason" in str(error.value)

    malformed = [
        {"k": "fail", "reason": ""},
        {"k": "fail", "reason": 4},
        {"k": "fail"},
        {"k": "fail", "reason": "x", "payload": _lit(1)},
    ]
    from experiments.dynamic_core_evaluation.program import DynamicProgram
    for body in malformed:
        with pytest.raises(EvaluatedValueError) as error:
            DynamicProgram.from_artifact(_artifact(body))
        assert error.value.code == "dynamic_spike_invalid"


def test_UC11_direct_certified_adapter_runs_through_the_compiler_and_executor(tmp_path):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    bridge, _path, _boundaries = _adapter_source(tmp_path)
    text = _source(
        '(let* ((raw (effect propose (record (operation "fuse") (branch "both") '
        '(candidate_a 6) (candidate_b 2) (other_a 3) (other_b 9) (history_size 5))))) '
        '(record (a (field raw "return__a")) (b (field raw "return__b"))))',
        result="Candidate", effects="propose",
    )
    program = _compile(text, bridge.type_env)
    artifact_path = tmp_path / "dynamic-program.json"
    artifact_path.write_text(program.artifact(), encoding="utf-8")
    restored = DynamicProgram.from_artifact(artifact_path.read_text(encoding="utf-8"))
    assert evaluate(restored, {}, leaf_bridge=bridge).json_value() == {"a": 6, "b": 9}
    assert _run_count(tmp_path) == 1
    assert list(_adapter_log(tmp_path)[0]["payload"]) == [
        "operation", "branch", "candidate_a", "candidate_b", "other_a", "other_b", "history_size"
    ]

    shutil.rmtree(tmp_path / ".orchestrate/runs")
    with pytest.raises(EvaluatedValueError) as error:
        evaluate(restored, {}, leaf_bridge=bridge, read_only=True)
    assert error.value.code == "dynamic_effect_forbidden"
    assert _run_count(tmp_path) == 0


def test_UC12_adapter_refusals_happen_before_dispatch_and_bad_raw_results_stay_hidden(tmp_path):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge
    from experiments.dynamic_core_evaluation.program import DynamicProgram
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    bridge, source_path, boundaries = _adapter_source(tmp_path)
    with pytest.raises(LispFrontendCompileError):
        LeafBridge.compile(source_path, tmp_path,
                           operations={"propose": "mlevolve_pair/search_compact::adapter-leaf"},
                           command_boundaries={})
    assert _run_count(tmp_path) == 0

    from dataclasses import replace
    mismatched = dict(boundaries)
    mismatched["propose_candidate"] = replace(
        boundaries["propose_candidate"], output_type_name="String"
    )
    with pytest.raises(LispFrontendCompileError) as wrong_binding:
        LeafBridge.compile(source_path, tmp_path,
                           operations={"propose": "mlevolve_pair/search_compact::adapter-leaf"},
                           command_boundaries=mismatched)
    assert "must return `String`" in str(wrong_binding.value)
    assert _run_count(tmp_path) == 0

    with pytest.raises(EvaluatedValueError) as error:
        evaluate(DynamicProgram.from_artifact(_artifact(
            _effect({**_adapter_inputs(), "candidate_a": "bad"}), effects=("propose",),
        )), {}, leaf_bridge=bridge)
    assert error.value.code == "dynamic_boundary_invalid"
    assert _run_count(tmp_path) == 0

    valid, _second_root_source, _ = _adapter_source(tmp_path / "bad-output", mutate_output=True)
    program = DynamicProgram.from_artifact(_artifact(
        _effect(_adapter_inputs()), effects=("propose",),
    ))
    with pytest.raises(EvaluatedValueError) as error:
        evaluate(program, {}, leaf_bridge=valid)
    assert error.value.code == "dynamic_effect_failed"
    assert error.value.metadata["leaf_run_id"]
    run_state = next((tmp_path / "bad-output/.orchestrate/runs").glob("*/state.json"))
    state = json.loads(run_state.read_text(encoding="utf-8"))
    assert state["status"] == "failed"
    assert "workflow_outputs" not in state or not state["workflow_outputs"]
    step = state["steps"]["mlevolve_pair/search_compact::adapter-leaf__propose-branch-candidate"]
    assert step["error"]["context"]["cause_code"] == "leaf_result_schema_invalid"
