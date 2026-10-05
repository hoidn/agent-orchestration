"""Behavioral contract for the production dynamic Workflow Lisp evaluator."""

from __future__ import annotations

import math
import traceback

import pytest

from orchestrator.workflow_lisp.dynamic.program import schema_reference
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.workflow_dynamic_helpers import BOOL, INT, _artifact, _definition, _read


FLOAT = {"kind": "primitive", "name": "Float"}
STRING = {"kind": "primitive", "name": "String"}
VALUE = {"kind": "primitive", "name": "Value"}
SCHEMAS = {
    "Int": INT,
    "Bool": BOOL,
    "Float": FLOAT,
    "String": STRING,
    "Value": VALUE,
}


def lit(value):
    return {"k": "lit", "v": value}


def name(value):
    return {"k": "name", "n": value}


def op(operator, *args):
    return {"k": "op", "name": operator, "args": list(args)}


def call(callee, *args):
    return {"k": "call", "callee": callee, "args": list(args)}


def fn(code, *captures):
    return {"k": "fn", "code": code, "captures": list(captures)}


def record(**fields):
    return {"k": "record", "fields": [[key, value] for key, value in fields.items()]}


def definition(body, params=(), captures=(), *, module="demo", boundary=None):
    return _definition(
        body,
        params=params,
        captures=captures,
        owner_module=module,
        boundary=boundary,
    )


def program(body, *, params=(("n", "Int"),), defaults=None, result="Int", definitions=None, schemas=None, budget=100):
    return _read(
        _artifact(
            body,
            definitions=definitions,
            schemas=SCHEMAS if schemas is None else schemas,
            defaults=defaults,
            result=result,
            params=params,
            budget=budget,
        )
    )


def run(body, inputs=None, **kwargs):
    from orchestrator.workflow.dynamic.evaluator import evaluate

    return evaluate(program(body, **kwargs), {} if inputs is None else inputs)


def failure(action, expected):
    with pytest.raises(ValueError) as caught:
        action()
    assert getattr(caught.value, "code", None) == expected
    return caught.value


def test_UC03_append_refuses_nonlists_and_wrong_arity():
    for operands in ((lit(1), lit(2)), (record(x=lit(1)), lit(2))):
        error = failure(lambda: run(op("list/append", *operands)), "dynamic_operand_type")
        assert error.metadata["steps"] > 0
    for operands in (({"k": "list", "items": []},),
                     ({"k": "list", "items": []}, lit(1), lit(2))):
        failure(lambda: program(op("list/append", *operands)), "dynamic_program_invalid")


def test_UC04_length_returns_checked_int_and_refuses_nonlists_and_wrong_arity():
    for items in ([], [lit(1), lit("two"), lit(True)]):
        value = run(op("list/length", {"k": "list", "items": items})).value
        assert type(value) is int and value == len(items)
    for operands in ((lit(1),), (record(x=lit(1)),)):
        assert failure(lambda: run(op("list/length", *operands)), "dynamic_operand_type").metadata["steps"] > 0
    for operands in ((), ({"k": "list", "items": []}, {"k": "list", "items": []})):
        failure(lambda: program(op("list/length", *operands)), "dynamic_program_invalid")


def test_UC06_all_update_keys_are_checked_before_any_replacement_runs():
    update = {"k": "record-update", "base": record(x=lit(1)), "fields": [
        ["x", {"k": "fail", "reason": "replacement_ran"}], ["missing", lit(2)]]}
    error = failure(lambda: run(call(fn("demo::update")),
        definitions={"demo::update": definition(update)}), "dynamic_field_missing")
    assert error.metadata["steps"] > 0 and error.metadata["call_stack"]
    assert "replacement_ran" not in str(error)
    failure(lambda: run({"k": "record-update", "base": lit(7), "fields": [
        ["x", {"k": "fail", "reason": "replacement_ran"}]]}), "dynamic_operand_type")


def test_original_pure_behavior_case_B02_required_bool_boundary():
    assert run(name("flag"), {"flag": True}, params=(("flag", "Bool"),), result="Bool").value is True
    for values in ({}, {"flag": "true"}, {"flag": True, "extra": 1}):
        failure(lambda: run(name("flag"), values, params=(("flag", "Bool"),), result="Bool"),
            "dynamic_boundary_invalid")


def test_closures_can_be_created_captured_passed_stored_and_selected():
    maker = definition(fn("demo::reader", name("saved")), params=("saved",))
    reader = definition(name("saved"), captures=("saved",))
    identity = definition(name("item"), params=("item",))
    body = {
        "k": "let",
        "bindings": [
            ["make", call(fn("demo::make"), name("n"))],
            ["picked", {"k": "at", "base": {"k": "list", "items": [fn("demo::identity")]}, "index": lit(0)}],
        ],
        "body": call(name("picked"), call(name("make"))),
    }
    result = run(
        body,
        {"n": 7},
        definitions={"demo::make": maker, "demo::reader": reader, "demo::identity": identity},
    )
    assert result.value == 7


def test_input_and_captured_records_are_frozen_from_caller_aliases():
    reader = definition(name("saved"), captures=("saved",))
    body = {
        "k": "let",
        "bindings": [["read", fn("demo::reader", name("n"))], ["n", {"k": "record", "fields": [["field", lit("shadow")]]}]],
        "body": call(name("read")),
    }
    original = {"field": "captured"}
    result = run(
        body,
        {"n": original},
        params=(("n", "Value"),),
        defaults={},
        result="Value",
        definitions={"demo::reader": reader},
    )
    original["field"] = "changed"
    assert result.json_value() == {"field": "captured"}


def test_call_evaluates_all_arguments_left_to_right_before_callable_check():
    body = call(
        lit(0),
        op("+", lit(1), lit(2)),
        op("+", lit(3), lit(4)),
    )
    error = failure(
        lambda: run(body, params=(), defaults={}, result="Value", budget=8),
        "dynamic_not_callable",
    )
    assert error.metadata["steps"] == 8
    exhausted = failure(
        lambda: run(body, params=(), defaults={}, result="Value", budget=6),
        "dynamic_budget_exhausted",
    )
    assert exhausted.location.endswith("/args/1/args/0")


def test_budget_counts_each_entered_node_once_and_refuses_the_next_entry():
    body = op("+", lit(2), lit(3))
    exact = run(body, budget=3)
    assert (exact.value, exact.steps) == (5, 3)
    error = failure(lambda: run(body, budget=2), "dynamic_budget_exhausted")
    assert error.location.endswith("/args/1")
    assert error.metadata["steps"] == 2


def test_primitive_operands_keep_strict_numeric_kinds():
    failure(lambda: run(op("+", lit(True), lit(1))), "dynamic_operand_type")
    failure(lambda: run(op("+", lit(1), lit(2.0))), "dynamic_operand_type")
    assert run(op("+", lit(1.5), lit(2.0)), result="Float").value == 3.5


def test_primitive_error_traceback_does_not_expose_captured_values():
    captured = 8123456789123456789
    helper = definition(
        op("+", name("saved"), lit(1234567891234567890)),
        captures=("saved",),
        module="library",
    )
    error = failure(
        lambda: run(
            call(fn("library::overflow", name("n"))),
            {"n": captured},
            definitions={"library::overflow": helper},
        ),
        "pure_expr_overflow",
    )
    assert error.metadata["module"] == "library"
    assert str(captured) not in "".join(traceback.format_exception(error))


def test_untyped_helper_calls_remain_untyped_and_runtime_arity_is_checked():
    apply = definition(call(name("function"), name("value")), params=("function", "value"))
    identity = definition(name("value"), params=("value",))
    assert run(
        call(fn("demo::apply"), fn("demo::identity"), lit(13)),
        params=(),
        defaults={},
        definitions={"demo::apply": apply, "demo::identity": identity},
    ).value == 13

    missing = call(fn("demo::identity"))
    failure(
        lambda: run(missing, params=(), defaults={}, definitions={"demo::identity": identity}),
        "dynamic_call_arity",
    )


def test_entry_defaults_are_applied_before_strict_input_validation():
    assert run(name("n")).value == 3
    assert run(name("n"), {"n": 8}).value == 8
    failure(lambda: run(name("n"), {"n": True}), "dynamic_boundary_invalid")
    failure(lambda: run(name("n"), {"n": 8, "extra": 1}), "dynamic_boundary_invalid")
    failure(
        lambda: run(name("n"), {"n": "true"}, params=(("n", "Bool"),), defaults={}, result="Bool"),
        "dynamic_boundary_invalid",
    )
    failure(
        lambda: run(name("n"), {}, params=(("n", "Bool"),), defaults={}, result="Bool"),
        "dynamic_boundary_invalid",
    )


def test_declared_workflow_calls_apply_defaults_and_validate_each_boundary():
    boundary = {
        "params": [["x", "Int"], ["y", "Int"]],
        "defaults": {"y": 7},
        "result": "Int",
    }
    add = definition(
        op("+", name("x"), name("y")),
        params=("x", "y"),
        module="lib",
        boundary=boundary,
    )
    body = call(fn("lib::add"), lit(2))
    assert run(body, params=(), defaults={}, definitions={"lib::add": add}).value == 9

    bad_input = call(fn("lib::add"), lit(True))
    error = failure(
        lambda: run(bad_input, params=(), defaults={}, definitions={"lib::add": add}),
        "dynamic_boundary_invalid",
    )
    assert error.location.endswith("/boundary/params/0")

    bad_result = definition(
        lit("wrong"),
        params=("x", "y"),
        module="lib",
        boundary=boundary,
    )
    result_error = failure(
        lambda: run(body, params=(), defaults={}, definitions={"lib::add": bad_result}),
        "dynamic_boundary_invalid",
    )
    assert result_error.location.endswith("/boundary/result")


def test_declared_workflow_calls_require_defaults_for_every_omitted_suffix():
    boundary = {
        "params": [["x", "Int"], ["y", "Int"]],
        "defaults": {},
        "result": "Int",
    }
    workflow = definition(
        name("x"), params=("x", "y"), module="lib", boundary=boundary
    )
    failure(
        lambda: run(call(fn("lib::work"), lit(1)), params=(), defaults={}, definitions={"lib::work": workflow}),
        "dynamic_call_arity",
    )
    failure(
        lambda: run(call(fn("lib::work"), lit(1), lit(2), lit(3)), params=(), defaults={}, definitions={"lib::work": workflow}),
        "dynamic_call_arity",
    )


def test_condition_is_strict_bool_and_only_selected_arm_runs():
    lazy = {"k": "if", "cond": lit(True), "then": lit(1), "else": {"k": "field", "base": record(), "name": "missing"}}
    assert run(lazy).value == 1
    error = failure(
        lambda: run({"k": "if", "cond": lit(1), "then": lit(1), "else": lit(2)}),
        "dynamic_condition_type",
    )
    assert "Int" in str(error)


def test_record_list_access_and_functional_update_preserve_values():
    initial = record(a=lit(1), b=lit(2))
    updated = {
        "k": "record-update",
        "base": initial,
        "fields": [["a", lit(9)]],
    }
    body = {"k": "field", "base": updated, "name": "a"}
    assert run(body).value == 9

    missing = failure(
        lambda: run({"k": "field", "base": record(), "name": "missing"}),
        "dynamic_field_missing",
    )
    assert missing.location.endswith("/definitions/demo::main/body")
    failure(
        lambda: run({"k": "at", "base": {"k": "list", "items": [lit(1)]}, "index": lit(1)}),
        "dynamic_index_invalid",
    )


def test_nested_record_union_boundary_reuses_shared_strict_validator():
    choice = {
        "kind": "union",
        "name": "Choice",
        "variants": [
            {"name": "text", "fields": [{"name": "text", "type": STRING}]},
            {"name": "count", "fields": [{"name": "count", "type": INT}]},
        ],
    }
    payload = {
        "kind": "record",
        "name": "Payload",
        "fields": [{"name": "items", "type": {"kind": "list", "item": choice}}],
    }
    schemas = {**SCHEMAS, "Choice": choice, "Payload": payload}
    data = {"items": [{"variant": "text", "text": "ok"}, {"variant": "count", "count": 3}]}
    result = run(
        name("n"),
        {"n": data},
        params=(("n", "Payload"),),
        defaults={},
        result="Payload",
        schemas=schemas,
    )
    assert result.json_value() == data


def test_record_boundary_rejects_missing_extra_and_inactive_fields():
    row = {"kind": "record", "name": "Row", "fields": [{"name": "x", "type": INT}]}
    schemas = {**SCHEMAS, "Row": row}
    kwargs = {"params": (("n", "Row"),), "defaults": {}, "result": "Row", "schemas": schemas}
    failure(lambda: run(name("n"), {"n": {}}, **kwargs), "dynamic_boundary_invalid")
    failure(lambda: run(name("n"), {"n": {"x": 1, "extra": 2}}, **kwargs), "dynamic_boundary_invalid")

    choice = {
        "kind": "union",
        "name": "Choice",
        "variants": [{"name": "one", "fields": [{"name": "x", "type": INT}]}, {"name": "two", "fields": [{"name": "y", "type": INT}]}],
    }
    union_schemas = {**SCHEMAS, "Choice": choice}
    failure(
        lambda: run(name("n"), {"n": {"variant": "one", "x": 1, "y": 2}}, params=(("n", "Choice"),), defaults={}, result="Choice", schemas=union_schemas),
        "dynamic_boundary_invalid",
    )


def test_boundary_errors_keep_safe_validator_path_without_rejected_values():
    item = {"kind": "record", "name": "Item", "fields": [{"name": "review notes", "type": INT}]}
    row = {"kind": "record", "name": "Row", "fields": [{"name": "rows", "type": {"kind": "list", "item": item}}]}
    error = failure(
        lambda: run(
            name("n"),
            {"n": {"rows": [{"review notes": "secret"}]}},
            params=(("n", "Row"),),
            defaults={},
            result="Row",
            schemas={**SCHEMAS, "Item": item, "Row": row},
        ),
        "dynamic_boundary_invalid",
    )
    assert error.metadata["validator_error"].startswith("$/rows/0/review notes")
    assert error.metadata["field_path"] == "$/rows/0/review notes"
    assert "secret" not in str(error) + error.metadata["validator_error"]
    nested = {"kind": "record", "name": "Review", "fields": [{"name": "x", "type": INT}]}
    choice = {"kind": "union", "name": "Choice", "variants": [
        {"name": "one", "fields": [{"name": "x", "type": INT}]}]}
    for field_name, field_type, bad_value in (
        ("review has notes", nested, {}), ("review union", nested, {}),
        ("review", choice, {"variant": "one"}),
    ):
        row = {"kind": "record", "name": "Row", "fields": [{"name": field_name, "type": field_type}]}
        error = failure(lambda: run(name("n"), {"n": {field_name: bad_value}},
            params=(("n", "Row"),), defaults={}, result="Row",
            schemas={**SCHEMAS, "Review": nested, "Choice": choice, "Row": row}), "dynamic_boundary_invalid")
        assert error.metadata["field_path"].startswith("$/" + field_name)
        assert "secret" not in str(error) + error.metadata["validator_error"]


def test_nested_map_boundary_redacts_runtime_keys_and_values():
    mapping = {
        "kind": "map",
        "key": STRING,
        "value": INT,
    }
    payload = {
        "kind": "record",
        "name": "Payload",
        "fields": [{"name": "labels", "type": mapping}],
    }
    error = failure(
        lambda: run(
            name("n"),
            {"n": {"labels": {"SECRET_MAP_KEY/~": "SECRET_MAP_VALUE"}}},
            params=(("n", "Payload"),),
            defaults={},
            result="Payload",
            schemas={**SCHEMAS, "Payload": payload},
        ),
        "dynamic_boundary_invalid",
    )
    assert error.metadata["field_path"] == "$/labels/*"
    assert error.metadata["validator_error"] == "$/labels/* is not an Int"
    assert "SECRET_MAP_KEY" not in repr(error.metadata)
    assert "SECRET_MAP_VALUE" not in repr(error.metadata)


def test_nested_value_boundary_redacts_runtime_keys_and_preserves_list_indices():
    payload = {
        "kind": "record",
        "name": "Payload",
        "fields": [{"name": "contents", "type": VALUE}],
    }
    error = failure(
        lambda: run(
            name("n"),
            {"n": {"contents": {"SECRET_VALUE_KEY/~": ["SECRET_VALUE", 1 << 63]}}},
            params=(("n", "Payload"),),
            defaults={},
            result="Payload",
            schemas={**SCHEMAS, "Payload": payload},
        ),
        "dynamic_boundary_invalid",
    )
    assert error.metadata["field_path"] == "$/contents/*/1"
    assert error.metadata["validator_error"] == "$/contents/*/1 is outside signed 64-bit Int bounds"
    assert "SECRET_VALUE_KEY" not in repr(error.metadata)
    assert "SECRET_VALUE" not in repr(error.metadata)


def test_boundary_rejects_host_cycles_nonfinite_and_normalizes_float_inputs():
    cyclical = []
    cyclical.append(cyclical)
    kwargs = {"params": (("n", "Value"),), "defaults": {}, "result": "Value"}
    failure(lambda: run(name("n"), {"n": cyclical}, **kwargs), "dynamic_boundary_invalid")
    failure(lambda: run(name("n"), {"n": object()}, **kwargs), "dynamic_boundary_invalid")
    failure(
        lambda: run(name("n"), {"n": math.inf}, params=(("n", "Float"),), defaults={}, result="Float"),
        "dynamic_boundary_invalid",
    )
    assert run(name("n"), {"n": 2**63}, params=(("n", "Float"),), defaults={}, result="Float").value == float(2**63)
    for schema in ("Int", "Value"):
        failure(
            lambda schema=schema: run(name("n"), {"n": 2**63}, params=(("n", schema),), defaults={}, result=schema),
            "dynamic_boundary_invalid",
        )
    nested = failure(
        lambda: run(name("n"), {"n": {"nested": [2**63]}}, **kwargs),
        "dynamic_boundary_invalid",
    )
    assert nested.metadata["field_path"] == "$/*/0"


def test_optional_boundary_preserves_none_and_bool_does_not_coerce():
    optional = {"kind": "optional", "item": STRING}
    reference = schema_reference(optional)
    schemas = {**SCHEMAS, reference: optional}
    assert run(
        name("n"),
        {"n": None},
        params=(("n", reference),),
        defaults={},
        result=reference,
        schemas=schemas,
    ).value is None
    failure(lambda: run(name("n"), {"n": None}, params=(("n", "Bool"),), defaults={}, result="Bool"), "dynamic_boundary_invalid")


def test_optional_path_absence_needs_no_owner_but_a_path_value_does():
    path = {
        "kind": "path",
        "name": "demo::InputPath",
        "under": "artifacts",
        "must_exist_target": False,
    }
    path_ref = schema_reference(path)
    optional = {"kind": "optional", "item": path}
    optional_ref = schema_reference(optional)
    schemas = {**SCHEMAS, path_ref: path, optional_ref: optional}
    kwargs = {
        "params": (("n", optional_ref),),
        "defaults": {},
        "result": optional_ref,
        "schemas": schemas,
    }
    assert run(name("n"), {"n": None}, **kwargs).value is None

    from orchestrator.workflow.dynamic.evaluator import evaluate

    dynamic_program = program(name("n"), **kwargs)
    error = failure(
        lambda: evaluate(dynamic_program, {"n": "artifacts/input.json"}),
        "dynamic_boundary_invalid",
    )
    assert "workspace file owner" in error.metadata["validator_error"]


def test_nested_path_boundaries_use_workspace_owner_for_confinement_and_existence(tmp_path):
    path = {
        "kind": "path",
        "name": "demo::InputPath",
        "under": "artifacts",
        "must_exist_target": True,
    }
    path_ref = schema_reference(path)
    payload = {
        "kind": "record",
        "name": "demo::Payload",
        "fields": [{"name": "path", "type": path}],
    }
    payload_ref = schema_reference(payload)
    schemas = {**SCHEMAS, path_ref: path, payload_ref: payload}
    dynamic_program = program(
        name("n"),
        params=(("n", payload_ref),),
        defaults={},
        result=payload_ref,
        schemas=schemas,
    )
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "present.txt").write_text("ok")
    files = WorkspaceFiles(tmp_path)
    try:
        from orchestrator.workflow.dynamic.evaluator import evaluate

        valid = evaluate(dynamic_program, {"n": {"path": "artifacts/present.txt"}}, workspace_files=files)
        assert valid.json_value() == {"path": "artifacts/present.txt"}
        outside = failure(
            lambda: evaluate(dynamic_program, {"n": {"path": "other/present.txt"}}, workspace_files=files),
            "dynamic_boundary_invalid",
        )
        assert "under root" in outside.metadata["validator_error"]
        missing = failure(
            lambda: evaluate(dynamic_program, {"n": {"path": "artifacts/missing.txt"}}, workspace_files=files),
            "dynamic_boundary_invalid",
        )
        assert "does not exist" in missing.metadata["validator_error"]
    finally:
        files.close()


def test_closures_cannot_cross_the_entry_data_boundary():
    helper = definition(lit(1))
    failure(
        lambda: run(fn("demo::helper"), params=(), defaults={}, result="Value", definitions={"demo::helper": helper}),
        "dynamic_boundary_invalid",
    )
    nested = {"k": "record", "fields": [["items", {"k": "list", "items": [fn("demo::helper")]}]]}
    failure(
        lambda: run(nested, params=(), defaults={}, result="Value", definitions={"demo::helper": helper}),
        "dynamic_boundary_invalid",
    )

    workflow = definition(
        name("value"),
        params=("value",),
        module="lib",
        boundary={"params": [["value", "Value"]], "defaults": {}, "result": "Value"},
    )
    closure_argument = call(fn("lib::workflow"), nested)
    failure(
        lambda: run(
            closure_argument,
            params=(),
            defaults={},
            result="Value",
            definitions={"demo::helper": helper, "lib::workflow": workflow},
        ),
        "dynamic_boundary_invalid",
    )


def test_self_application_uses_iterative_machine_and_one_budget():
    recursive = definition(call(name("again"), name("again")), params=("again",))
    body = {
        "k": "let",
        "bindings": [["self", fn("demo::loop")]],
        "body": call(name("self"), name("self")),
    }
    error = failure(
        lambda: run(body, params=(), defaults={}, definitions={"demo::loop": recursive}, budget=6000),
        "dynamic_budget_exhausted",
    )
    assert error.metadata["steps"] == 6000
    assert len(error.metadata["call_context"]) > 1
    assert error.metadata["call_context"][-1][2] == "demo::loop"
    assert error.location.startswith("/definitions/demo::loop/body/")


def test_call_trace_and_node_budget_are_deterministic_across_independent_runs():
    increment = definition(op("+", name("x"), lit(1)), params=("x",))
    body = call(fn("demo::increment"), lit(4))
    first = run(body, params=(), defaults={}, definitions={"demo::increment": increment}, budget=10)
    second = run(body, params=(), defaults={}, definitions={"demo::increment": increment}, budget=10)
    assert (first.value, first.steps, first.call_trace) == (second.value, second.steps, second.call_trace)
    assert first.steps == 6


def test_capture_creation_and_return_each_consume_the_shared_budget():
    const = definition(name("captured"), captures=("captured",))
    body = call(fn("demo::const", lit(5)))
    error = failure(
        lambda: run(body, params=(), defaults={}, definitions={"demo::const": const}, budget=3),
        "dynamic_budget_exhausted",
    )
    assert error.location.endswith("/definitions/demo::const/body")


def test_imported_helper_failures_use_persisted_source_map_and_named_call_frames(monkeypatch):
    broken = definition(
        {"k": "field", "base": record(), "name": "missing"},
        captures=("secret",),
        module="library",
    )
    dynamic_program = program(
        call(fn("library::broken", lit("CAPTURE_SECRET"))),
        params=(),
        defaults={},
        definitions={"library::broken": broken},
    )
    from orchestrator.workflow.dynamic.evaluator import evaluate

    monkeypatch.setattr("builtins.open", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("source file read")))
    error = failure(lambda: evaluate(dynamic_program, {}), "dynamic_field_missing")
    assert error.location.endswith("/definitions/library::broken/body")
    assert error.metadata["artifact_pointer"] == error.location
    assert error.metadata["module"] == "library"
    assert error.metadata["span"]["start"]["path"] == "library/main.orc"
    assert error.metadata["call_stack"][-1]["caller"] == "demo::main"
    assert error.metadata["call_stack"][-1]["callee"] == "library::broken"
    assert "CAPTURE_SECRET" not in str(error) + repr(error.metadata)


def test_record_update_missing_field_reports_its_mapped_expression():
    update = definition(
        {"k": "record-update", "base": record(), "fields": [["authoredField", lit(1)]]},
        module="library",
    )
    error = failure(
        lambda: run(
            call(fn("library::update")),
            params=(),
            defaults={},
            result="Value",
            definitions={"library::update": update},
        ),
        "dynamic_field_missing",
    )
    assert error.location.endswith("/definitions/library::update/body")
    assert error.metadata["artifact_pointer"] == error.location
    assert error.metadata["field"] == "authoredField"
    assert error.metadata["module"] == "library"
    assert error.metadata["span"]["start"]["path"] == "library/main.orc"
    assert error.metadata["form_path"] == ("workflow-lisp", "definition", "library::update")


def test_imported_required_call_arity_failure_includes_attempted_callee_frame():
    required = definition(name("value"), params=("value",), module="library")
    error = failure(
        lambda: run(
            call(fn("library::required")),
            params=(),
            defaults={},
            result="Value",
            definitions={"library::required": required},
        ),
        "dynamic_call_arity",
    )
    assert error.metadata["call_stack"] == (
        {
            "caller": "demo::main",
            "caller_module": "demo",
            "callee": "library::required",
            "callee_module": "library",
            "call_site": "/definitions/demo::main/body",
        },
    )


def test_explicit_failure_is_runtime_error_at_its_source_mapped_node():
    error = failure(
        lambda: run({"k": "fail", "reason": "stopped"}),
        "dynamic_explicit_failure",
    )
    assert error.location.endswith("/body")
    assert error.metadata["reason"] == "stopped"
