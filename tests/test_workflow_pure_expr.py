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
    ("row_name", "payload", "resolved_bindings", "expected_value", "expected_error_code"),
    [
        (
            row["name"],
            row["payload"],
            row.get("resolved_bindings"),
            row.get("expected_value"),
            row.get("expected_error_code"),
        )
        for row in _golden_vectors()
    ],
    ids=[str(row["name"]) for row in _golden_vectors()],
)
def test_evaluate_pure_expr_matches_golden_vectors(
    row_name: str,
    payload: dict[str, object],
    resolved_bindings: dict[str, object] | None,
    expected_value: object | None,
    expected_error_code: str | None,
) -> None:
    pure_expr = _module()

    if expected_error_code is not None:
        with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
            pure_expr.evaluate_pure_expr(
                payload,
                resolved_bindings=resolved_bindings,
            )
        assert excinfo.value.code == expected_error_code, row_name
        return

    assert pure_expr.evaluate_pure_expr(
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
