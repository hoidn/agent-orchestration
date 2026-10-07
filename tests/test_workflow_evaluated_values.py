from __future__ import annotations

from importlib import import_module
import os
from pathlib import Path

import pytest

from orchestrator.workflow.pure_expr import (
    PureExprEvaluationError,
    canonical_json_for_pure_value,
    validate_pure_expr_payload,
)
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.syntax import EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


INT = {"kind": "primitive", "name": "Int"}
FLOAT = {"kind": "primitive", "name": "Float"}
BOOL = {"kind": "primitive", "name": "Bool"}
STRING = {"kind": "primitive", "name": "String"}
MAP_STR_INT = {"kind": "map", "key": STRING, "value": INT}
VALUE = {"kind": "primitive", "name": "Value"}
PATH = {
    "kind": "path",
    "name": "sample::ArtifactPath",
    "under": "artifacts",
    "must_exist_target": True,
}
WORKSPACE_PATH = {
    "kind": "path",
    "name": "sample::WorkspacePath",
    "under": ".",
    "must_exist_target": True,
}
LIST_INT = {"kind": "list", "item": INT}
OPTIONAL_PATH = {"kind": "optional", "item": PATH}
ROW = {
    "kind": "record",
    "name": "sample::Row",
    "fields": [{"name": "path", "type": PATH}, {"name": "count", "type": INT}],
}
CHOICE = {
    "kind": "union",
    "name": "sample::Choice",
    "variants": [
        {"name": "Ready", "fields": [{"name": "path", "type": PATH}]},
        {"name": "Skipped", "fields": []},
    ],
}


def _values_api():
    return import_module("orchestrator.workflow.evaluated.values")


def test_evaluated_boundary_rejects_non_finite_float_binding() -> None:
    values = _values_api()
    with pytest.raises(PureExprEvaluationError) as excinfo:
        values.coerce_evaluated_value(float("inf"), FLOAT)

    assert excinfo.value.code == "pure_expr_float_not_finite"


@pytest.mark.parametrize(
    "value",
    ["", ".", "../outside.md", "/tmp/outside.md", "other/report.md"],
)
def test_evaluated_boundary_rejects_lexically_invalid_or_outside_paths(value: str) -> None:
    values = _values_api()

    with pytest.raises(PureExprEvaluationError) as excinfo:
        values.coerce_evaluated_value(value, PATH)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_nested_path_refinement_checks_only_active_values_without_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _values_api()
    filesystem_observations = []

    def observe(*args, **kwargs):
        filesystem_observations.append((args, kwargs))
        return False

    monkeypatch.setattr(Path, "exists", observe)
    monkeypatch.setattr(Path, "is_file", observe)
    monkeypatch.setattr(Path, "resolve", observe)
    monkeypatch.setattr(os.path, "exists", observe)
    monkeypatch.setattr(os.path, "lexists", observe)

    assert values.coerce_evaluated_value(None, OPTIONAL_PATH).value is None
    assert values.coerce_evaluated_value(
        {"variant": "Skipped", "path": "../outside.md"}, CHOICE
    ).value == {"variant": "Skipped"}
    for descriptor, invalid in (
        (ROW, {"path": "../outside.md", "count": 1}),
        (OPTIONAL_PATH, "other/report.md"),
        (CHOICE, {"variant": "Ready", "path": "/tmp/outside.md"}),
    ):
        with pytest.raises(PureExprEvaluationError):
            values.coerce_evaluated_value(invalid, descriptor)
    assert filesystem_observations == []


@pytest.mark.parametrize("raw", ["report.md", "."])
def test_workspace_root_path_preserves_dot_refinement(
    raw: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _values_api()

    def forbid_filesystem(*args, **kwargs):
        pytest.fail("pure path coercion observed the filesystem")

    with monkeypatch.context() as scope:
        for method in ("exists", "is_file", "resolve"):
            scope.setattr(Path, method, forbid_filesystem)
        for method in ("exists", "lexists"):
            scope.setattr(os.path, method, forbid_filesystem)
        result = values.coerce_evaluated_value(raw, WORKSPACE_PATH)

    assert result.value == raw
    assert result.descriptor == WORKSPACE_PATH


@pytest.mark.parametrize(
    "raw",
    [None, False, 7, 2.5, "value", [1, True], {"nested": [1, None]}],
)
def test_evaluated_value_accepts_json_values_and_retains_value_descriptor(raw: object) -> None:
    values = _values_api()

    result = values.coerce_evaluated_value(raw, VALUE)

    assert result.json_value() == raw
    assert result.descriptor == VALUE


def test_nested_evaluated_value_accepts_json_values() -> None:
    values = _values_api()
    descriptor = {
        "kind": "record",
        "name": "sample::Envelope",
        "fields": [
            {"name": "payload", "type": VALUE},
            {"name": "count", "type": INT},
        ],
    }
    raw = {"payload": {"nested": [1, True, None]}, "count": 2}

    result = values.coerce_evaluated_value(raw, descriptor)

    assert result.json_value() == raw
    assert result.descriptor["fields"][0]["type"] == VALUE


def test_built_and_read_back_list_value_payload_reaches_catalog_operator(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "cp" / "probe.orc"
    source_path.parent.mkdir()
    source_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/probe)
  (export run)
  (defworkflow run ((payload List[Value])) -> Int
    (list/length payload)))
''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        source_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={},
    )
    built = build_closed_program(typed)
    read_back = ClosedProgram.from_artifact(built.artifact())
    pending = [read_back.tree["body"]]
    operator = None
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            if (
                node.get("k") == "op"
                and node["payload"]["expr"].get("operator") == "list/length"
            ):
                operator = node
                break
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    assert operator is not None

    list_type = read_back.tree["params"][0][1]
    values = _values_api()
    value = values.coerce_evaluated_value([{"score": 4}, True], list_type)
    result = values.evaluate_closed_value(
        operator, values.LexicalEnvironment({"payload": value})
    )

    assert result.value == 2
    assert result.descriptor == INT
    assert value.descriptor["item"] == VALUE


def test_built_and_read_back_value_parameter_preserves_json_carrier(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "cp" / "identity.orc"
    source_path.parent.mkdir()
    source_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}")
  (defmodule cp/identity)
  (export run)
  (defworkflow run ((payload Value)) -> Value payload))
''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        source_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={},
    )
    built = build_closed_program(typed)
    read_back = ClosedProgram.from_artifact(built.artifact())
    values = _values_api()
    descriptor = read_back.tree["params"][0][1]
    raw = {"score": 4, "tags": ["ok", True]}
    carrier = values.coerce_evaluated_value(raw, descriptor)

    result = values.evaluate_closed_value(
        read_back.tree["body"]["value"],
        values.LexicalEnvironment({"payload": carrier}),
    )

    assert result.json_value() == raw
    assert result.descriptor == descriptor


@pytest.mark.parametrize(
    ("descriptor", "raw"),
    [
        (PATH, "artifacts/run/report.md"),
        (ROW, {"path": "artifacts/run/report.md", "count": 4}),
        (LIST_INT, [1, 2, 3]),
        (MAP_STR_INT, {"count": 3}),
        (CHOICE, {"variant": "Ready", "path": "artifacts/run/report.md"}),
        (OPTIONAL_PATH, None),
        (OPTIONAL_PATH, "artifacts/run/report.md"),
    ],
)
def test_evaluated_carrier_accepts_existing_catalog_value_shapes(
    descriptor: dict, raw: object
) -> None:
    values = _values_api()
    result = values.coerce_evaluated_value(raw, descriptor)

    assert result.json_value() == raw
    assert canonical_json_for_pure_value(result.descriptor) == canonical_json_for_pure_value(
        descriptor
    )


def test_lexical_environment_and_aggregate_values_are_immutable() -> None:
    values = _values_api()
    original = {"path": "artifacts/run/report.md", "count": 4}
    typed = values.coerce_evaluated_value(original, ROW, dependencies={"producer"})
    outer = values.LexicalEnvironment({"row": typed})
    inner = outer.extend("count", values.coerce_evaluated_value(4, INT))

    original["count"] = 9
    assert outer.lookup("row").value["count"] == 4
    assert inner.lookup("row").dependencies == frozenset({"producer"})
    with pytest.raises(TypeError):
        typed.value["count"] = 9
    with pytest.raises(TypeError):
        inner.bindings["count"] = typed


def test_closed_list_over_256_values_reaches_existing_catalog_operator() -> None:
    values = _values_api()
    items = {"k": "list", "type": LIST_INT, "items": [
        {"k": "lit", "v": number, "type": INT} for number in range(300)
    ]}
    payload = {
        "pure_expr_schema_version": 2,
        "result_type": INT,
        "bindings": {"a0": {"type": LIST_INT}},
        "expr": {
            "kind": "op",
            "operator": "list/length",
            "args": [{"kind": "binding", "name": "a0"}],
        },
    }
    result = values.evaluate_closed_value(
        {"k": "op", "payload": payload, "args": [items]}, values.LexicalEnvironment()
    )

    assert result.value == 300
    assert result.descriptor == INT


def test_closed_operator_payload_over_256_nodes_uses_explicit_unbounded_catalog_route() -> None:
    values = _values_api()
    count = 300
    payload = {
        "pure_expr_schema_version": 2,
        "result_type": INT,
        "bindings": {f"a{index}": {"type": INT} for index in range(count)},
        "expr": {
            "kind": "op",
            "operator": "+",
            "args": [{"kind": "binding", "name": f"a{index}"} for index in range(count)],
        },
    }
    with pytest.raises(PureExprEvaluationError) as excinfo:
        validate_pure_expr_payload(payload)
    assert excinfo.value.code == "pure_expr_payload_too_large"

    node = {
        "k": "op",
        "payload": payload,
        "args": [{"k": "lit", "v": 1, "type": INT} for _ in range(count)],
    }
    result = values.evaluate_closed_value(node, values.LexicalEnvironment())

    assert result.value == count
    assert result.descriptor == INT


@pytest.mark.parametrize(("descriptor", "value"), [(BOOL, 1), (INT, True)])
def test_closed_operator_refuses_boolean_integer_substitution(
    descriptor: dict, value: object
) -> None:
    values = _values_api()
    node = {
        "k": "op",
        "payload": {
            "pure_expr_schema_version": 2,
            "result_type": descriptor,
            "bindings": {"a0": {"type": descriptor}},
            "expr": {"kind": "binding", "name": "a0"},
        },
        "args": [{"k": "lit", "v": value, "type": descriptor}],
    }

    with pytest.raises(PureExprEvaluationError) as excinfo:
        values.evaluate_closed_value(node, values.LexicalEnvironment())

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_operator_error_points_to_application_and_reports_actual_operands() -> None:
    values = _values_api()
    payload = {
        "pure_expr_schema_version": 2,
        "result_type": FLOAT,
        "bindings": {"a0": {"type": FLOAT}, "a1": {"type": FLOAT}},
        "expr": {
            "kind": "op",
            "operator": "/",
            "args": [{"kind": "binding", "name": "a0"}, {"kind": "binding", "name": "a1"}],
        },
    }
    node = {
        "k": "op",
        "payload": payload,
        "args": [
            {"k": "lit", "v": 8.0, "type": FLOAT},
            {"k": "lit", "v": 0.0, "type": FLOAT},
        ],
        "@": {"span": "numbers.orc:7:4"},
    }

    with pytest.raises(values.EvaluatedValueError) as excinfo:
        values.evaluate_closed_value(node, values.LexicalEnvironment())

    assert excinfo.value.code == "pure_expr_division_by_zero"
    assert excinfo.value.location == "numbers.orc:7:4"
    assert excinfo.value.operands == (8.0, 0.0)


def test_path_values_propagate_without_filesystem_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _values_api()
    filesystem_observations = []
    path_record = {
        "kind": "record",
        "name": "sample::Result",
        "fields": [{"name": "report", "type": PATH}],
    }
    typed = values.coerce_evaluated_value(
        {"report": "artifacts/run/report.md"}, path_record, dependencies={"producer"}
    )
    environment = values.LexicalEnvironment({"stored": typed})

    def observe(*args, **kwargs):
        filesystem_observations.append((args, kwargs))
        return False

    monkeypatch.setattr(Path, "exists", observe)
    monkeypatch.setattr(Path, "is_file", observe)
    monkeypatch.setattr(Path, "resolve", observe)
    monkeypatch.setattr(os.path, "exists", observe)
    monkeypatch.setattr(os.path, "lexists", observe)
    result = values.evaluate_closed_value(
        {"k": "field", "base": {"k": "name", "n": "stored"}, "path": ["report"]},
        environment,
    )

    assert result.descriptor["kind"] == "path"
    assert result.value == "artifacts/run/report.md"
    assert result.dependencies == frozenset({"producer"})
    assert filesystem_observations == []


def test_closed_path_join_and_list_map_preserve_values_and_dependencies() -> None:
    values = _values_api()
    source = values.coerce_evaluated_value([1, 2], LIST_INT, dependencies={"source"})
    environment = values.LexicalEnvironment({
        "items": source,
        "root": values.coerce_evaluated_value("artifacts/run", PATH, dependencies={"root"}),
    })
    path_value = values.evaluate_closed_value(
        {
            "k": "path_join",
            "base": {"k": "name", "n": "root"},
            "child": {"k": "lit", "v": "reports/out.md", "type": STRING},
            "type": PATH,
        },
        environment,
    )

    def evaluate_body(body: dict, local: object):
        assert body == {"k": "halt", "value": {"k": "name", "n": "item"}}
        return values.evaluate_closed_value(body["value"], local)

    mapped = values.evaluate_closed_value(
        {
            "k": "list_map",
            "binder": "item",
            "source": {"k": "name", "n": "items"},
            "body": {"k": "block", "body": {"k": "halt", "value": {"k": "name", "n": "item"}}},
            "type": LIST_INT,
        },
        environment,
        evaluate_body=evaluate_body,
    )

    assert path_value.value == "artifacts/run/reports/out.md"
    assert path_value.dependencies == frozenset({"root"})
    assert mapped.json_value() == [1, 2]
    assert mapped.dependencies == frozenset({"source"})
