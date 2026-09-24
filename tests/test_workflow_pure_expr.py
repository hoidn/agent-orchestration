from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "pure_expr"
GOLDEN_VECTORS_PATH = FIXTURES / "golden_vectors.json"
JUSTIFICATION_REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "pure_expr_operator_justification.json"
)
EXPECTED_OPERATOR_ROWS = {
    "=",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "and",
    "or",
    "not",
    "+",
    "-",
    "*",
    "min",
    "max",
    "string/concat",
    "string/empty?",
    "symbol/name",
    "some?",
    "or-else",
    "record-update",
    "list/empty?",
    "list/head",
    "list/rest",
    "list/append",
    "list/length",
}


def _module():
    return importlib.import_module("orchestrator.workflow.pure_expr")


def _golden_vectors() -> list[dict[str, object]]:
    return json.loads(GOLDEN_VECTORS_PATH.read_text(encoding="utf-8"))


def test_golden_vectors_cover_every_required_operator_group() -> None:
    vectors = _golden_vectors()
    observed = {
        str(row["operator"])
        for row in vectors
        if isinstance(row, dict) and "operator" in row
    }
    assert observed == EXPECTED_OPERATOR_ROWS


@pytest.mark.parametrize(
    (
        "evaluation_lane",
        "row_name",
        "payload",
        "resolved_bindings",
        "expected_value",
        "expected_error_code",
    ),
    [
        (
            evaluation_lane,
            row["name"],
            row["payload"],
            row.get("resolved_bindings"),
            row.get("expected_value"),
            row.get("expected_error_code"),
        )
        for evaluation_lane in ("runtime", "compile_time_folding")
        for row in _golden_vectors()
    ],
    ids=[
        f"{evaluation_lane}-{row['name']}"
        for evaluation_lane in ("runtime", "compile_time_folding")
        for row in _golden_vectors()
    ],
)
def test_evaluate_pure_expr_matches_golden_vectors(
    evaluation_lane: str,
    row_name: str,
    payload: dict[str, object],
    resolved_bindings: dict[str, object] | None,
    expected_value: object | None,
    expected_error_code: str | None,
) -> None:
    pure_expr = _module()
    if evaluation_lane == "runtime":
        evaluator = pure_expr.evaluate_pure_expr
    else:
        pure_projection = importlib.import_module(
            "orchestrator.workflow_lisp.lowering.pure_projection"
        )
        # The compiler fold entry point imports this exact evaluator seam.
        assert pure_projection.evaluate_pure_expr is pure_expr.evaluate_pure_expr
        evaluator = pure_projection.evaluate_pure_expr

    if expected_error_code is not None:
        with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
            evaluator(
                payload,
                resolved_bindings=resolved_bindings,
            )
        assert excinfo.value.code == expected_error_code, row_name
        return

    assert evaluator(
        payload,
        resolved_bindings=resolved_bindings,
    ) == expected_value


def test_evaluate_pure_expr_rejects_unsupported_schema_version() -> None:
    pure_expr = _module()
    payload = {
        "pure_expr_schema_version": 999,
        "result_type": {"kind": "primitive", "name": "Int"},
        "bindings": {},
        "expr": {
            "kind": "literal",
            "type": {"kind": "primitive", "name": "Int"},
            "value": 1,
        },
    }

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_evaluate_pure_expr_rejects_payload_larger_than_default_bound() -> None:
    pure_expr = _module()
    expr: dict[str, object] = {
        "kind": "literal",
        "type": {"kind": "primitive", "name": "Int"},
        "value": 0,
    }
    for _ in range(256):
        expr = {
            "kind": "op",
            "operator": "+",
            "args": [
                expr,
                {
                    "kind": "literal",
                    "type": {"kind": "primitive", "name": "Int"},
                    "value": 1,
                },
            ],
        }

    payload = {
        "pure_expr_schema_version": 1,
        "result_type": {"kind": "primitive", "name": "Int"},
        "bindings": {},
        "expr": expr,
    }

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_payload_too_large"


def test_record_update_preserves_field_order_after_replacement() -> None:
    pure_expr = _module()
    row = next(
        candidate
        for candidate in _golden_vectors()
        if candidate["name"] == "record_update_replace"
    )

    result = pure_expr.evaluate_pure_expr(
        row["payload"],
        resolved_bindings=row.get("resolved_bindings"),
    )

    assert list(result.keys()) == ["count", "label", "enabled"]
    assert result == {"count": 2, "label": "updated", "enabled": True}


def test_canonical_json_is_deterministic_for_equal_results() -> None:
    pure_expr = _module()

    first = pure_expr.canonical_json_for_pure_value({"b": 2, "a": 1})
    second = pure_expr.canonical_json_for_pure_value({"a": 1, "b": 2})

    assert first == second
    assert first == '{"a":1,"b":2}'


def test_operator_justification_registry_matches_runtime_catalog() -> None:
    pure_expr = _module()
    registry = json.loads(JUSTIFICATION_REGISTRY_PATH.read_text(encoding="utf-8"))

    implemented = set(pure_expr.PURE_EXPR_OPERATOR_CATALOG)
    documented = {row["operator"] for row in registry}

    assert documented == implemented
    for row in registry:
        fixture_path = row.get("fixture_path")
        assert isinstance(fixture_path, str) and fixture_path
        assert (Path(__file__).resolve().parent.parent / fixture_path).is_file()


def test_enum_equality_golden_vector_keeps_existing_operator_and_schema_contract() -> None:
    row = next(candidate for candidate in _golden_vectors() if candidate["name"] == "eq_enum_member")

    assert row["operator"] == "="
    assert row["payload"]["pure_expr_schema_version"] == 1
    args = row["payload"]["expr"]["args"]
    assert [arg["type"]["kind"] for arg in args] == ["enum", "enum"]
    assert [arg["value"] for arg in args] == ["missing_resource", "missing_resource"]


def test_evaluate_kind_if_untaken_branch_is_not_evaluated() -> None:
    pure_expr = _module()
    payload = {
        "pure_expr_schema_version": 1,
        "result_type": {"kind": "primitive", "name": "String"},
        "bindings": {
            "gone": {"type": {"kind": "primitive", "name": "String"}},
        },
        "expr": {
            "kind": "if",
            "condition": {
                "kind": "literal",
                "type": {"kind": "primitive", "name": "Bool"},
                "value": True,
            },
            "then": {
                "kind": "literal",
                "type": {"kind": "primitive", "name": "String"},
                "value": "selected",
            },
            "else": {"kind": "binding", "name": "gone"},
        },
    }

    # The untaken `else` branch references a binding with no runtime value;
    # evaluating it would raise pure_expr_binding_missing. Selection must
    # return the `then` value without touching the untaken branch.
    assert pure_expr.evaluate_pure_expr(payload) == "selected"


INT_TYPE = {"kind": "primitive", "name": "Int"}
STRING_TYPE = {"kind": "primitive", "name": "String"}
PATH_TYPE = {
    "kind": "path",
    "name": "WorkspacePath",
    "under": "workspace",
    "must_exist_target": False,
}


def _literal(value: object, descriptor: dict[str, object]) -> dict[str, object]:
    return {"kind": "literal", "type": descriptor, "value": value}


def _fallible_path_value() -> dict[str, object]:
    return {
        "kind": "path_join_under",
        "path_type": PATH_TYPE,
        "child": _literal("../escape", STRING_TYPE),
    }


def _schema_3_payload(expr: dict[str, object], result_type: dict[str, object]) -> dict[str, object]:
    return {
        "pure_expr_schema_version": 3,
        "result_type": result_type,
        "bindings": {"x": {"type": INT_TYPE}},
        "expr": expr,
    }


@pytest.mark.parametrize("schema_version", [1, 2])
def test_let_is_rejected_by_schema_versions_before_three(schema_version: int) -> None:
    pure_expr = _module()
    payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {
                    "name": "captured",
                    "type": INT_TYPE,
                    "value": _literal(1, INT_TYPE),
                }
            ],
            "body": {"kind": "binding", "name": "captured"},
        },
        INT_TYPE,
    )
    payload["pure_expr_schema_version"] = schema_version

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_schema_three_let_evaluates_ordered_hygienic_bindings_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pure_expr = _module()
    first_argument = {
        "kind": "op",
        "operator": "+",
        "args": [
            {"kind": "binding", "name": "x"},
            _literal(1, INT_TYPE),
        ],
    }
    second_argument = {"kind": "binding", "name": "x"}
    payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {"name": "__arg0", "type": INT_TYPE, "value": first_argument},
                {
                    "name": "__arg1",
                    "type": INT_TYPE,
                    "value": second_argument,
                },
                {
                    "name": "formal_x",
                    "type": INT_TYPE,
                    "value": {"kind": "binding", "name": "__arg0"},
                },
                {
                    "name": "formal_y",
                    "type": INT_TYPE,
                    "value": {"kind": "binding", "name": "__arg1"},
                },
            ],
            "body": {
                "kind": "op",
                "operator": "+",
                "args": [
                    {"kind": "binding", "name": "formal_y"},
                    {"kind": "binding", "name": "formal_y"},
                ],
            },
        },
        INT_TYPE,
    )
    original = pure_expr._evaluate_expr
    evaluated_arguments: list[object] = []

    def tracked_evaluate(node: object, **kwargs: object) -> object:
        if node is first_argument or node is second_argument:
            evaluated_arguments.append(node)
        return original(node, **kwargs)

    monkeypatch.setattr(pure_expr, "_evaluate_expr", tracked_evaluate)

    assert pure_expr.evaluate_pure_expr(payload, resolved_bindings={"x": 9}) == 18
    assert evaluated_arguments == [first_argument, second_argument]


def test_schema_three_let_eagerly_evaluates_unused_fallible_binding() -> None:
    pure_expr = _module()
    payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {
                    "name": "unused",
                    "type": PATH_TYPE,
                    "value": _fallible_path_value(),
                }
            ],
            "body": _literal(1, INT_TYPE),
        },
        INT_TYPE,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_escape"


def test_schema_three_let_in_untaken_if_branch_is_not_evaluated() -> None:
    pure_expr = _module()
    payload = _schema_3_payload(
        {
            "kind": "if",
            "condition": _literal(True, {"kind": "primitive", "name": "Bool"}),
            "then": _literal(1, INT_TYPE),
            "else": {
                "kind": "let",
                "bindings": [
                    {
                        "name": "unused",
                        "type": PATH_TYPE,
                        "value": _fallible_path_value(),
                    }
                ],
                "body": _literal(2, INT_TYPE),
            },
        },
        INT_TYPE,
    )

    assert pure_expr.evaluate_pure_expr(payload) == 1


def test_schema_three_let_in_empty_list_map_body_is_not_evaluated() -> None:
    pure_expr = _module()
    payload = _schema_3_payload(
        {
            "kind": "list_map",
            "source": {"kind": "list", "element_type": INT_TYPE, "items": []},
            "binder": {"name": "item", "type": INT_TYPE},
            "result_element_type": INT_TYPE,
            "body": {
                "kind": "let",
                "bindings": [
                    {
                        "name": "unused",
                        "type": PATH_TYPE,
                        "value": _fallible_path_value(),
                    }
                ],
                "body": _literal(1, INT_TYPE),
            },
        },
        {"kind": "list", "item": INT_TYPE},
    )

    assert pure_expr.evaluate_pure_expr(payload) == []


def test_schema_three_let_rejects_binding_type_mismatch() -> None:
    pure_expr = _module()
    payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {
                    "name": "wrong",
                    "type": STRING_TYPE,
                    "value": _literal(1, INT_TYPE),
                }
            ],
            "body": _literal(1, INT_TYPE),
        },
        INT_TYPE,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_schema_three_let_shadows_outer_bindings_but_rejects_duplicate_locals() -> None:
    pure_expr = _module()
    shadowing_payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {
                    "name": "x",
                    "type": INT_TYPE,
                    "value": {
                        "kind": "op",
                        "operator": "+",
                        "args": [
                            {"kind": "binding", "name": "x"},
                            _literal(1, INT_TYPE),
                        ],
                    },
                }
            ],
            "body": {"kind": "binding", "name": "x"},
        },
        INT_TYPE,
    )

    assert pure_expr.evaluate_pure_expr(shadowing_payload, resolved_bindings={"x": 9}) == 10

    duplicate_payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {"name": "local", "type": INT_TYPE, "value": _literal(1, INT_TYPE)},
                {"name": "local", "type": INT_TYPE, "value": _literal(2, INT_TYPE)},
            ],
            "body": {"kind": "binding", "name": "local"},
        },
        INT_TYPE,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(duplicate_payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_schema_three_nested_let_does_not_leak_into_its_parent_scope() -> None:
    pure_expr = _module()
    record_type = {
        "kind": "record",
        "name": "ScopedValues",
        "fields": [
            {"name": "inner", "type": INT_TYPE},
            {"name": "outer", "type": INT_TYPE},
        ],
    }
    payload = _schema_3_payload(
        {
            "kind": "let",
            "bindings": [
                {"name": "local", "type": INT_TYPE, "value": _literal(9, INT_TYPE)}
            ],
            "body": {
                "kind": "record",
                "type": record_type,
                "fields": [
                    {
                        "name": "inner",
                        "value": {
                            "kind": "let",
                            "bindings": [
                                {
                                    "name": "local",
                                    "type": INT_TYPE,
                                    "value": _literal(2, INT_TYPE),
                                }
                            ],
                            "body": {"kind": "binding", "name": "local"},
                        },
                    },
                    {"name": "outer", "value": {"kind": "binding", "name": "local"}},
                ],
            },
        },
        record_type,
    )

    assert pure_expr.evaluate_pure_expr(payload) == {"inner": 2, "outer": 9}
