"""Behavioral and admission contract for the isolated dynamic-core experiment."""

from __future__ import annotations

import json
import math

import pytest


BOOL = {"kind": "primitive", "name": "Bool"}
INT = {"kind": "primitive", "name": "Int"}
FLOAT = {"kind": "primitive", "name": "Float"}
STRING = {"kind": "primitive", "name": "String"}
VALUE = {"kind": "primitive", "name": "Value"}
OPTIONAL_STRING = {"kind": "optional", "item": STRING}
BASE_SCHEMAS = {
    "bool": BOOL,
    "int": INT,
    "float": FLOAT,
    "string": STRING,
    "value": VALUE,
    "nullable": OPTIONAL_STRING,
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


def definition(body, params=(), captures=()):
    return {"params": list(params), "captures": list(captures), "body": body}


def artifact(body, *, inputs=(), schemas=None, result="value", definitions=None, budget=100):
    rows = [list(row) for row in inputs]
    params = [row[0] for row in rows]
    defs = {"entry": definition(body, params)}
    defs.update(definitions or {})
    return {
        "schema": "workflow-lisp/dynamic-spike/1",
        "entry": "entry",
        "budget": budget,
        "schemas": dict(BASE_SCHEMAS if schemas is None else schemas),
        "inputs": rows,
        "result": result,
        "definitions": defs,
    }


def text(value):
    return json.dumps(value, allow_nan=True, separators=(",", ":"))


def read(value):
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    return DynamicProgram.from_artifact(value if isinstance(value, str) else text(value))


def run(value, inputs=None):
    from experiments.dynamic_core_evaluation.evaluator import evaluate

    return evaluate(read(value), {} if inputs is None else inputs)


def failure(action, expected):
    with pytest.raises(ValueError) as caught:
        action()
    assert getattr(caught.value, "code", None) == expected
    return caught.value


CASE_IDS = (
    *(f"P{i:02}" for i in range(1, 13)),
    *(f"B{i:02}" for i in range(1, 13)),
    *(f"A{i:02}" for i in range(1, 19)),
    *(f"D{i:02}" for i in range(1, 7)),
)


@pytest.mark.parametrize("case_id", CASE_IDS, ids=CASE_IDS)
def test_dynamic_core_contract(case_id):
    if case_id == "P01":
        program = artifact(
            call(fn("identity"), name("x")),
            inputs=(("x", "value"),),
            definitions={"identity": definition(name("item"), ("item",))},
        )
        assert run(program, {"x": 9}).value == 9
        assert run(program, {"x": {"field": "kept"}}).json_value() == {"field": "kept"}
    elif case_id == "P02":
        maker = definition(fn("read", name("saved")), ("saved",))
        reader = definition(name("saved"), captures=("saved",))
        program = artifact(
            call(call(fn("make"), name("x"))),
            inputs=(("x", "int"),),
            definitions={"make": maker, "read": reader},
        )
        assert run(program, {"x": 7}).value == 7
    elif case_id == "P03":
        program = artifact(
            call({"k": "at", "base": {"k": "list", "items": [fn("identity")]}, "index": lit(0)}, lit(12)),
            result="int",
            definitions={"identity": definition(name("item"), ("item",))},
        )
        assert run(program).value == 12
    elif case_id == "P04":
        apply = definition(call(name("function"), name("value")), ("function", "value"))
        identity = definition(name("value"), ("value",))
        program = artifact(call(fn("apply"), fn("identity"), lit(13)), result="int", definitions={"apply": apply, "identity": identity})
        assert run(program).value == 13
    elif case_id == "P05":
        reader = definition(name("saved"), captures=("saved",))
        body = {
            "k": "let",
            "bindings": [["read", fn("reader", name("x"))], ["x", lit(99)]],
            "body": call(name("read")),
        }
        program = artifact(body, inputs=(("x", "value"),), result="value", definitions={"reader": reader})
        source = {"field": "captured"}
        result = run(program, {"x": source})
        source["field"] = "caller mutation"
        assert result.json_value() == {"field": "captured"}
    elif case_id == "P06":
        body = {"k": "if", "cond": lit(True), "then": lit(1), "else": {"k": "field", "base": {"k": "record", "fields": []}, "name": "missing"}}
        assert run(artifact(body, result="int")).value == 1
    elif case_id == "P07":
        failure(lambda: run(artifact(call(lit(1)), result="value")), "dynamic_not_callable")
    elif case_id == "P08":
        program = artifact(call(fn("identity")), result="int", definitions={"identity": definition(name("x"), ("x",))})
        failure(lambda: run(program), "dynamic_call_arity")
    elif case_id == "P09":
        failure(lambda: run(artifact({"k": "if", "cond": lit(1), "then": lit(1), "else": lit(2)}, result="int")), "dynamic_condition_type")
    elif case_id == "P10":
        failure(lambda: run(artifact({"k": "field", "base": {"k": "record", "fields": []}, "name": "missing"})), "dynamic_field_missing")
    elif case_id == "P11":
        failure(lambda: run(artifact({"k": "at", "base": {"k": "list", "items": [lit(1)]}, "index": lit(1)}, result="value")), "dynamic_index_invalid")
    elif case_id == "P12":
        failure(lambda: run(artifact(op("+", lit(True), lit(1)), result="value")), "dynamic_operand_type")
    elif case_id == "B01":
        tagged = {"kind": "union", "name": "Choice", "variants": [{"name": "text", "fields": [{"name": "text", "type": STRING}]}, {"name": "count", "fields": [{"name": "count", "type": INT}]}]}
        nested = {"kind": "record", "name": "Payload", "fields": [{"name": "items", "type": {"kind": "list", "item": tagged}}]}
        payload = {"items": [{"variant": "text", "text": "ok"}, {"variant": "count", "count": 3}]}
        program = artifact(name("x"), inputs=(("x", "payload"),), schemas={**BASE_SCHEMAS, "payload": nested}, result="payload")
        assert run(program, {"x": payload}).json_value() == payload
    elif case_id == "B02":
        program = artifact(name("x"), inputs=(("x", "bool"),), result="bool")
        failure(lambda: run(program, {"x": "true"}), "dynamic_boundary_invalid")
        failure(lambda: run(program, {}), "dynamic_boundary_invalid")
        failure(lambda: run(program, {"x": True, "extra": False}), "dynamic_boundary_invalid")
    elif case_id == "B03":
        record = {"kind": "record", "name": "R", "fields": [{"name": "x", "type": INT}]}
        program = artifact(name("x"), inputs=(("x", "r"),), schemas={**BASE_SCHEMAS, "r": record}, result="r")
        failure(lambda: run(program, {"x": {}}), "dynamic_boundary_invalid")
    elif case_id == "B04":
        record = {"kind": "record", "name": "R", "fields": [{"name": "x", "type": INT}]}
        program = artifact(name("x"), inputs=(("x", "r"),), schemas={**BASE_SCHEMAS, "r": record}, result="r")
        failure(lambda: run(program, {"x": {"x": 1, "extra": 2}}), "dynamic_boundary_invalid")
    elif case_id == "B05":
        union = {"kind": "union", "name": "Choice", "variants": [{"name": "one", "fields": [{"name": "x", "type": INT}]}, {"name": "two", "fields": [{"name": "y", "type": INT}]}]}
        program = artifact(name("x"), inputs=(("x", "choice"),), schemas={**BASE_SCHEMAS, "choice": union}, result="choice")
        failure(lambda: run(program, {"x": {"variant": "one", "x": 1, "y": 2}}), "dynamic_boundary_invalid")
    elif case_id == "B06":
        item = {"kind": "record", "name": "Item", "fields": [{"name": "review notes", "type": INT}]}
        rec = {"kind": "record", "name": "R", "fields": [{"name": "rows", "type": {"kind": "list", "item": item}}]}
        program = artifact(name("x"), inputs=(("x", "r"),), schemas={**BASE_SCHEMAS, "r": rec}, result="r")
        error = failure(lambda: run(program, {"x": {"rows": [{"review notes": "secret"}]}}), "dynamic_boundary_invalid")
        assert error.metadata["validator_error"].startswith("$/rows/0/review notes")
        assert "secret" not in str(error) + error.metadata["validator_error"]
        nested = {"kind": "record", "name": "Review", "fields": [{"name": "x", "type": INT}]}
        spaced = {"kind": "record", "name": "R", "fields": [{"name": "review has notes", "type": nested}]}
        spaced_program = artifact(name("x"), inputs=(("x", "r"),), schemas={**BASE_SCHEMAS, "r": spaced}, result="r")
        spaced_error = failure(lambda: run(spaced_program, {"x": {"review has notes": {}}}), "dynamic_boundary_invalid")
        assert spaced_error.metadata["validator_error"].startswith("$/review has notes record fields")
        union_named_record = {"kind": "record", "name": "R", "fields": [{"name": "review union", "type": nested}]}
        union_named_program = artifact(name("x"), inputs=(("x", "r"),), schemas={**BASE_SCHEMAS, "r": union_named_record}, result="r")
        union_named_error = failure(lambda: run(union_named_program, {"x": {"review union": {}}}), "dynamic_boundary_invalid")
        assert union_named_error.metadata["validator_error"].startswith("$/review union record fields")
        union = {"kind": "union", "name": "Choice", "variants": [{"name": "one", "fields": [{"name": "x", "type": INT}]}]}
        union_record = {"kind": "record", "name": "R", "fields": [{"name": "review", "type": union}]}
        union_program = artifact(name("x"), inputs=(("x", "r"),), schemas={**BASE_SCHEMAS, "r": union_record}, result="r")
        union_error = failure(lambda: run(union_program, {"x": {"review": {"variant": "one"}}}), "dynamic_boundary_invalid")
        assert union_error.metadata["validator_error"].startswith("$/review union record fields")
    elif case_id == "B07":
        program = artifact(name("x"), inputs=(("x", "float"),), result="float")
        failure(lambda: run(program, {"x": math.inf}), "dynamic_boundary_invalid")
    elif case_id == "B08":
        program = artifact(fn("identity"), result="value", definitions={"identity": definition(lit(1))})
        failure(lambda: run(program), "dynamic_boundary_invalid")
    elif case_id == "B09":
        program = artifact(name("x"), inputs=(("x", "value"),), result="value")
        cyclic = []
        cyclic.append(cyclic)
        failure(lambda: run(program, {"x": cyclic}), "dynamic_boundary_invalid")
    elif case_id == "B10":
        program = artifact(name("x"), inputs=(("x", "value"),), result="value")
        failure(lambda: run(program, {"x": object()}), "dynamic_boundary_invalid")
    elif case_id == "B11":
        value = 2**63
        float_program = artifact(name("x"), inputs=(("x", "float"),), result="float")
        assert run(float_program, {"x": value}).value == float(value)
        for schema in ("int", "value"):
            bad = artifact(name("x"), inputs=(("x", schema),), result=schema)
            failure(lambda bad=bad: run(bad, {"x": value}), "dynamic_boundary_invalid")
        nested = artifact(name("x"), inputs=(("x", "value"),), result="value")
        error = failure(lambda: run(nested, {"x": {"nested": [value]}}), "dynamic_boundary_invalid")
        assert error.metadata["field_path"] == "$/nested/0"
        assert run(artifact(lit(1), result="float")).value == 1.0
    elif case_id == "B12":
        nullable = artifact(name("x"), inputs=(("x", "nullable"),), result="nullable")
        assert run(nullable, {"x": None}).value is None
        boolean = artifact(name("x"), inputs=(("x", "bool"),), result="bool")
        failure(lambda: run(boolean, {"x": None}), "dynamic_boundary_invalid")
    elif case_id == "A01":
        data = artifact(lit(1), result="int")
        first = read(data)
        reordered = json.dumps(data, sort_keys=True, indent=2)
        second = read(reordered)
        assert first.digest == second.digest
        assert read(first.artifact()).digest == first.digest
        with pytest.raises(TypeError):
            first.tree["entry"] = "changed"
        with pytest.raises(TypeError):
            first.tree["definitions"]["entry"]["body"]["v"] = 2
    elif case_id == "A02":
        data = artifact(lit(1), result="int")
        data["schema"] = "workflow-lisp/other/1"
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A03":
        data = artifact(lit(1), result="int")
        data["extra"] = True
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A04":
        data = artifact(lit(1), result="int", definitions={"unused": definition(name("missing"))})
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A05":
        data = artifact(fn("forged"), result="value")
        failure(lambda: read(data), "dynamic_spike_invalid")
        malformed_target = artifact(fn("bad"), result="value", definitions={"bad": {}})
        failure(lambda: read(malformed_target), "dynamic_spike_invalid")
    elif case_id == "A06":
        target = definition(name("captured"), captures=("captured",))
        data = artifact(fn("target"), result="value", definitions={"target": target})
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A07":
        data = artifact(name("x"), inputs=(("x", "missing"),), result="int")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A08":
        data = artifact(lit(1), result="int")
        data["schemas"]["bad"] = {"kind": "list", "item": {"kind": "what"}}
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A09":
        data = artifact(lit(1), result="int")
        data["schemas"]["path"] = {"kind": "path", "name": "Path", "under": "root", "must_exist_target": False}
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A10":
        data = artifact({"k": "perform", "effect": "x"}, result="int")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A11":
        data = artifact({"k": "host_call", "name": "x"}, result="int")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A12":
        data = artifact({"k": "import", "path": "x"}, result="int")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A13":
        data = artifact(op("unknown", lit(1)), result="int")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A14":
        data = artifact(lit(1), result="int", definitions={"duplicate": definition(lit(0), ("x", "x"))})
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A15":
        from experiments.dynamic_core_evaluation.program import DynamicProgram

        failure(lambda: DynamicProgram.from_artifact("{"), "dynamic_spike_invalid")
        duplicate = '{"schema":"workflow-lisp/dynamic-spike/1","schema":"workflow-lisp/dynamic-spike/1"}'
        failure(lambda: DynamicProgram.from_artifact(duplicate), "dynamic_spike_invalid")
        surrogate = artifact(lit("\ud800"), result="string")
        failure(lambda: read(json.dumps(surrogate, ensure_ascii=True)), "dynamic_spike_invalid")
    elif case_id == "A16":
        data = artifact({"k": "lit", "v": 1, "extra": True}, result="int")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A17":
        data = artifact(name("x"), inputs=(("x", "int"),), result="int")
        data["definitions"]["entry"]["params"] = []
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "A18":
        data = artifact({"k": "record", "fields": [["x", lit(1)], ["x", lit(2)]]}, result="value")
        failure(lambda: read(data), "dynamic_spike_invalid")
    elif case_id == "D01":
        data = artifact(op("+", lit(2), lit(3)), result="int", budget=3)
        assert run(data).value == 5
    elif case_id == "D02":
        data = artifact(op("+", lit(2), lit(3)), result="int", budget=2)
        error = failure(lambda: run(data), "dynamic_budget_exhausted")
        assert error.location.endswith("/args/1")
    elif case_id == "D03":
        recursive = definition(call(name("again"), name("again")), ("again",))
        body = {"k": "let", "bindings": [["self", fn("loop")]], "body": call(name("self"), name("self"))}
        data = artifact(body, result="int", definitions={"loop": recursive}, budget=6000)
        error = failure(lambda: run(data), "dynamic_budget_exhausted")
        assert len(error.metadata["call_context"]) > 1
        assert error.metadata["call_context"][-1][2] == "loop"
        assert error.location.startswith("/definitions/loop/body/")
        assert error.metadata["steps"] == 6000
    elif case_id == "D04":
        helper = definition(op("+", name("x"), lit(1)), ("x",))
        data = artifact(call(fn("helper"), lit(4)), result="int", definitions={"helper": helper}, budget=10)
        first, second = run(data), run(data)
        assert (first.value, first.steps, first.call_trace) == (second.value, second.steps, second.call_trace)
    elif case_id == "D05":
        const = definition(name("captured"), captures=("captured",))
        body = call(fn("const", lit(5)))
        data = artifact(body, result="int", definitions={"const": const}, budget=3)
        error = failure(lambda: run(data), "dynamic_budget_exhausted")
        assert error.location.endswith("/definitions/const/body")
    elif case_id == "D06":
        data = artifact(call(lit(0), op("+", lit(1), lit(2)), op("+", lit(3), lit(4))), result="value", budget=6)
        error = failure(lambda: run(data), "dynamic_budget_exhausted")
        assert error.location.endswith("/args/1/args/0")
        complete = artifact(call(lit(0), op("+", lit(1), lit(2)), op("+", lit(3), lit(4))), result="value", budget=8)
        final = failure(lambda: run(complete), "dynamic_not_callable")
        assert final.metadata["steps"] == 8
