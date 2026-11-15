from __future__ import annotations

import importlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.expressions import FunctionCallExpr, ProcedureCallExpr, ListMapExpr, NameExpr, PureOpExpr, elaborate_expression
from orchestrator.workflow_lisp.loops import ensure_loop_projectable_type
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode, build_syntax_module
from orchestrator.workflow_lisp.type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PrimitiveTypeRef,
    TypeParamRef,
)
from tests.agent_session_shims import closed_path
from tests.workflow_lisp_closed_program_helpers import build, build_outcome


_LIST_TRAVERSAL_AUTHORED_HEADS = (
    "list",
    "list/map",
    "list/map-effect",
    "path/join-under",
    "list/empty?",
    "list/head",
    "list/rest",
    "list/append",
    "list/length",
    "list/take",
    "list/all",
    "list/any",
)


_RUNTIME_CARDINALITY_PROVIDER_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "list_map_effect_runtime_cardinality_provider.orc"
)
_RUNTIME_CARDINALITY_WORKFLOW = (
    "list_map_effect_runtime_cardinality_provider::orchestrate"
)
_PATH_JOIN_MAP_CHILD_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "judgment_views"
    / "path_join_map_child_argument.orc"
)
_PROMPT_BINDING_MAP_CHILD_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "judgment_views"
    / "prompt_binding_map_child.orc"
)


def _module_source(target_dsl: str) -> str:
    return "\n".join(
        (
            "(workflow-lisp",
            '  (:language "0.1")',
            f'  (:target-dsl "{target_dsl}")',
            "  (defmodule old_only_projection)",
            "  (export orchestrate)",
            "  (defworkflow orchestrate",
            "    ((value Int))",
            "    -> Int",
            "    (+ value 1)))",
        )
    )


def _int_literal_payload(schema_version: object) -> dict[str, object]:
    descriptor = {"kind": "primitive", "name": "Int"}
    return {
        "pure_expr_schema_version": schema_version,
        "result_type": descriptor,
        "bindings": {},
        "expr": {
            "kind": "literal",
            "type": descriptor,
            "value": 1,
        },
    }


def _future_list_payload(schema_version: int) -> dict[str, object]:
    item_descriptor = {"kind": "primitive", "name": "Int"}
    return {
        "pure_expr_schema_version": schema_version,
        "result_type": {"kind": "list", "item": item_descriptor},
        "bindings": {},
        "expr": {
            "kind": "list",
            "element_type": item_descriptor,
            "items": [],
        },
    }


























def _expression_syntax(source: str) -> SyntaxNode:
    parse_tree = read_sexpr_text(
        source,
        source_path="inline_list_traversal_compatibility.orc",
    )
    assert len(parse_tree.items) == 1
    datum = parse_tree.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="inline_list_traversal_compatibility.orc",
        form_path=("workflow-lisp", "list-traversal-compatibility"),
    )






def test_current_target_accepts_list_traversal_source() -> None:
    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.40"),
            source_path="current_list_traversal.orc",
        )
    )
    assert module.target_dsl_version == "2.40"




def test_unknown_target_versions_still_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(
            read_sexpr_text(
                _module_source("99.99"),
                source_path="target_9999_list_traversal.orc",
            )
        )
    assert excinfo.value.diagnostics[0].code == "target_dsl_unsupported"



def test_pure_runtime_accepts_existing_nodes_in_schema_2() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    payload = _int_literal_payload(2)

    assert pure_expr.validate_pure_expr_payload(payload) is payload
    assert pure_expr.evaluate_pure_expr(payload) == 1


@pytest.mark.parametrize("schema_version", (0, 4, True, 2.0, "2"))
def test_unknown_or_non_integer_pure_schema_versions_fail_closed(
    schema_version: object,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _int_literal_payload(schema_version)
        )

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_schema_1_rejects_schema_2_list_node() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _future_list_payload(1)
        )

    assert excinfo.value.code == "pure_expr_schema_mismatch"






_BOOL = {"kind": "primitive", "name": "Bool"}
_INT = {"kind": "primitive", "name": "Int"}
_STRING = {"kind": "primitive", "name": "String"}
_LIST_INT = {"kind": "list", "item": _INT}


def _literal(descriptor: dict[str, object], value: object) -> dict[str, object]:
    return {"kind": "literal", "type": descriptor, "value": value}


def _list_node(*items: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "list",
        "element_type": _INT,
        "items": list(items),
    }


def _pure_payload(
    expr: dict[str, object],
    *,
    result_type: dict[str, object],
    schema_version: int = 2,
    bindings: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "pure_expr_schema_version": schema_version,
        "result_type": result_type,
        "bindings": bindings or {},
        "expr": expr,
    }


def _list_map_node(
    *,
    source: dict[str, object],
    binder_name: str = "item",
    binder_type: dict[str, object] = _INT,
    body: dict[str, object] | None = None,
    result_element_type: dict[str, object] = _INT,
) -> dict[str, object]:
    return {
        "kind": "list_map",
        "source": source,
        "binder": {"name": binder_name, "type": binder_type},
        "body": (
            body
            if body is not None
            else {"kind": "binding", "name": binder_name}
        ),
        "result_element_type": result_element_type,
    }


def _path_descriptor(
    *,
    name: str = "Path.state-root",
    under: object = "state",
    must_exist_target: object = False,
) -> dict[str, object]:
    return {
        "kind": "path",
        "name": name,
        "under": under,
        "must_exist_target": must_exist_target,
    }


def _path_join_node(
    child: object,
    *,
    path_type: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "kind": "path_join_under",
        "path_type": (
            path_type
            if path_type is not None
            else _path_descriptor()
        ),
        "child": _literal(_STRING, child),
    }


def _nonempty_head_node(source: dict[str, object]) -> dict[str, object]:
    return {
        "kind": "list_nonempty_head",
        "source": source,
        "element_type": _INT,
        "compiler_owned": True,
        "invariant_diagnostic": "list_nonempty_invariant_broken",
    }


@pytest.mark.parametrize(
    ("expr", "result_type"),
    (
        (_list_node(), _LIST_INT),
        (
            _list_map_node(source=_list_node(_literal(_INT, 1))),
            _LIST_INT,
        ),
        (_path_join_node("run.json"), _path_descriptor()),
        (
            _nonempty_head_node(_list_node(_literal(_INT, 1))),
            _INT,
        ),
    ),
    ids=("list", "list-map", "path-join-under", "list-nonempty-head"),
)
def test_schema_1_rejects_every_schema_2_node(
    expr: dict[str, object],
    result_type: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _pure_payload(
                expr,
                result_type=result_type,
                schema_version=1,
            )
        )

    assert excinfo.value.code == "pure_expr_schema_mismatch"


@pytest.mark.parametrize(
    ("operator", "args", "result_type"),
    (
        ("list/empty?", [_list_node()], _BOOL),
        ("list/head", [_list_node()], {"kind": "optional", "item": _INT}),
        ("list/rest", [_list_node()], _LIST_INT),
        ("list/append", [_list_node(), _literal(_INT, 1)], _LIST_INT),
        ("list/length", [_list_node()], _INT),
    ),
)
def test_schema_1_rejects_every_schema_2_list_operator(
    operator: str,
    args: list[dict[str, object]],
    result_type: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        {"kind": "op", "operator": operator, "args": args},
        result_type=result_type,
        schema_version=1,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_schema_mismatch"


def test_schema_2_node_count_includes_every_list_item_and_map_body_node() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    expr = _list_map_node(
        source=_list_node(
            _literal(_INT, 1),
            _literal(_INT, 2),
        ),
        body={
            "kind": "op",
            "operator": "+",
            "args": [
                {"kind": "binding", "name": "item"},
                _literal(_INT, 1),
            ],
        },
    )
    payload = _pure_payload(expr, result_type=_LIST_INT)

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload, max_nodes=6)

    assert excinfo.value.code == "pure_expr_payload_too_large"
    assert pure_expr.validate_pure_expr_payload(payload, max_nodes=7) is payload


def test_list_constructor_rejects_element_descriptor_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_node(_literal(_STRING, "wrong")),
        result_type=_LIST_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


@pytest.mark.parametrize(
    "expr",
    (
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_type=_STRING,
            result_element_type=_STRING,
        ),
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            result_element_type=_STRING,
        ),
    ),
    ids=("source-binder", "body-result"),
)
def test_list_map_rejects_descriptor_mismatch(
    expr: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        expr,
        result_type={"kind": "list", "item": _STRING},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


@pytest.mark.parametrize(
    ("binder_name", "bindings"),
    (
        (
            "item",
            {"item": {"type": _INT, "value": 99}},
        ),
        ("__compiler_item", {}),
    ),
    ids=("top-level-collision", "reserved-name"),
)
def test_list_map_rejects_binder_collisions_and_reserved_names(
    binder_name: str,
    bindings: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_name=binder_name,
        ),
        result_type=_LIST_INT,
        bindings=bindings,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "list_map_binder_invalid"


def test_nested_list_map_rejects_duplicate_lexical_binder() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    nested = _list_map_node(
        source=_list_node(_literal(_INT, 2)),
        binder_name="item",
    )
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_name="item",
            body=nested,
            result_element_type=_LIST_INT,
        ),
        result_type={"kind": "list", "item": _LIST_INT},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "list_map_binder_invalid"


def test_list_map_rejects_out_of_scope_binding_reference() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            body={"kind": "binding", "name": "not_in_scope"},
        ),
        result_type=_LIST_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_list_map_binder_is_evaluator_local_and_source_is_evaluated_once() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    class CountingList(list[int]):
        def __init__(self, values: list[int]) -> None:
            super().__init__(values)
            self.iterations = 0

        def __iter__(self):
            self.iterations += 1
            return super().__iter__()

    source = CountingList([3, 1, 2])
    payload = _pure_payload(
        _list_map_node(
            source={"kind": "binding", "name": "source"},
            body={
                "kind": "op",
                "operator": "+",
                "args": [
                    {"kind": "binding", "name": "item"},
                    {"kind": "binding", "name": "offset"},
                ],
            },
        ),
        result_type=_LIST_INT,
        bindings={
            "source": {"type": _LIST_INT},
            "offset": {"type": _INT},
        },
    )

    result = pure_expr.evaluate_pure_expr(
        payload,
        resolved_bindings={"source": source, "offset": 10},
    )

    assert result == [13, 11, 12]
    assert source.iterations == 1
    assert result is not source

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(
            payload,
            resolved_bindings={"source": source, "offset": 10, "item": 99},
        )
    assert excinfo.value.code == "pure_expr_binding_unexpected"


def test_list_append_returns_fresh_array_without_mutating_input() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    source = [1, 2]
    payload = _pure_payload(
        {
            "kind": "op",
            "operator": "list/append",
            "args": [
                {"kind": "binding", "name": "source"},
                _literal(_INT, 3),
            ],
        },
        result_type=_LIST_INT,
        bindings={"source": {"type": _LIST_INT}},
    )

    result = pure_expr.evaluate_pure_expr(
        payload,
        resolved_bindings={"source": source},
    )

    assert source == [1, 2]
    assert result == [1, 2, 3]
    assert result is not source


@pytest.mark.parametrize(
    "under",
    ("", ".", "/state", "state/", "state//runs", "state/./runs", "state/../runs"),
)
def test_path_join_under_rejects_malformed_selected_root(under: str) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    descriptor = _path_descriptor(under=under)
    payload = _pure_payload(
        _path_join_node("run.json", path_type=descriptor),
        result_type=descriptor,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_root_invalid"


@pytest.mark.parametrize("child", ("", ".", "reports/", "reports//one.md", "reports/./one.md"))
def test_path_join_under_rejects_empty_or_malformed_child(child: str) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _path_join_node(child),
        result_type=_path_descriptor(),
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_child_invalid"


@pytest.mark.parametrize("child", ("/absolute.md", "../escape.md", "safe/../../escape.md"))
def test_path_join_under_rejects_absolute_or_escaping_child(child: str) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _path_join_node(child),
        result_type=_path_descriptor(),
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(payload)

    assert excinfo.value.code == "path_join_under_escape"


def test_path_join_under_requires_exact_path_descriptor_and_string_child() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    invalid_type_payload = _pure_payload(
        _path_join_node(
            "run.json",
            path_type={"kind": "primitive", "name": "String"},
        ),
        result_type=_STRING,
    )
    invalid_child_payload = _pure_payload(
        {
            "kind": "path_join_under",
            "path_type": _path_descriptor(),
            "child": _literal(_INT, 1),
        },
        result_type=_path_descriptor(),
    )
    unresolved_type_payload = _pure_payload(
        {
            "kind": "path_join_under",
            "path_type": {},
            "child": _literal(_STRING, "run.json"),
        },
        result_type=_STRING,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as type_excinfo:
        pure_expr.evaluate_pure_expr(invalid_type_payload)
    assert type_excinfo.value.code == "path_join_under_type_invalid"

    with pytest.raises(pure_expr.PureExprEvaluationError) as child_excinfo:
        pure_expr.evaluate_pure_expr(invalid_child_payload)
    assert child_excinfo.value.code == "pure_expr_operand_type_mismatch"

    with pytest.raises(pure_expr.PureExprEvaluationError) as unresolved_excinfo:
        pure_expr.evaluate_pure_expr(unresolved_type_payload)
    assert unresolved_excinfo.value.code == "path_join_under_type_invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("compiler_owned", None),
        ("compiler_owned", False),
        ("invariant_diagnostic", None),
        ("invariant_diagnostic", "some_other_code"),
    ),
)
def test_list_nonempty_head_rejects_missing_compiler_contract(
    field: str,
    value: object,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    expr = _nonempty_head_node(_list_node(_literal(_INT, 1)))
    if value is None:
        del expr[field]
    else:
        expr[field] = value
    payload = _pure_payload(expr, result_type=_INT)

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_list_nonempty_head_enforces_compiler_nonempty_invariant() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    empty_payload = _pure_payload(
        _nonempty_head_node(_list_node()),
        result_type=_INT,
    )
    present_payload = _pure_payload(
        _nonempty_head_node(_list_node(_literal(_INT, 7))),
        result_type=_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.evaluate_pure_expr(empty_payload)
    assert excinfo.value.code == "list_nonempty_invariant_broken"

    assert pure_expr.evaluate_pure_expr(present_payload) == 7


def test_validate_rejects_list_map_body_descriptor_mismatch_for_empty_source() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(),
            result_element_type=_STRING,
        ),
        result_type={"kind": "list", "item": _STRING},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_nonempty_head_source_vs_element_descriptor() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    expr = _nonempty_head_node(_list_node(_literal(_INT, 1)))
    expr["element_type"] = _STRING
    payload = _pure_payload(expr, result_type=_STRING)

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_root_expr_vs_payload_result_descriptor() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _literal(_INT, 1),
        result_type=_STRING,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


@pytest.mark.parametrize(
    ("declared_name", "canonical_name"),
    (
        ("ConsumerPath", "example/types::ConsumerPath"),
        ("one/types::ConsumerPath", "two/types::ConsumerPath"),
    ),
)
def test_validate_accepts_canonical_path_name_for_same_declared_path(
    declared_name: str,
    canonical_name: str,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    declared_path = _path_descriptor(name=declared_name)
    canonical_path = _path_descriptor(name=canonical_name)
    record_type = {
        "kind": "record",
        "name": "PathEnvelope",
        "fields": [{"name": "path", "type": declared_path}],
    }
    payload = _pure_payload(
        {
            "kind": "record",
            "type": record_type,
            "fields": [
                {
                    "name": "path",
                    "value": {"kind": "binding", "name": "path"},
                }
            ],
        },
        result_type=record_type,
        bindings={"path": {"type": canonical_path, "value": "state/run.json"}},
    )

    assert pure_expr.validate_pure_expr_payload(payload) is payload


@pytest.mark.parametrize(
    ("declared_path", "observed_path"),
    (
        (
            _path_descriptor(name="one/types::ConsumerPath"),
            _path_descriptor(name="two/types::OtherPath"),
        ),
        (
            _path_descriptor(name="ConsumerPath"),
            _path_descriptor(
                name="example/types::ConsumerPath",
                under="artifacts",
            ),
        ),
        (
            _path_descriptor(name="ConsumerPath"),
            _path_descriptor(
                name="example/types::ConsumerPath",
                must_exist_target=True,
            ),
        ),
    ),
)
def test_validate_rejects_different_path_identity_or_contract(
    declared_path: dict[str, object],
    observed_path: dict[str, object],
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    record_type = {
        "kind": "record",
        "name": "PathEnvelope",
        "fields": [{"name": "path", "type": declared_path}],
    }
    payload = _pure_payload(
        {
            "kind": "record",
            "type": record_type,
            "fields": [
                {
                    "name": "path",
                    "value": {"kind": "binding", "name": "path"},
                }
            ],
        },
        result_type=record_type,
        bindings={"path": {"type": observed_path, "value": "state/run.json"}},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_accepts_nested_container_path_alias() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    declared_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(name="ConsumerPath"),
        },
    }
    canonical_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(name="example/types::ConsumerPath"),
        },
    }
    payload = _pure_payload(
        {"kind": "binding", "name": "paths"},
        result_type=declared_type,
        bindings={
            "paths": {
                "type": canonical_type,
                "value": [None, "state/run.json"],
            }
        },
    )

    assert pure_expr.validate_pure_expr_payload(payload) is payload


def test_validate_rejects_nested_container_path_contract_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    declared_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(name="ConsumerPath"),
        },
    }
    mismatched_type = {
        "kind": "list",
        "item": {
            "kind": "optional",
            "item": _path_descriptor(
                name="example/types::ConsumerPath",
                under="artifacts",
            ),
        },
    }
    payload = _pure_payload(
        {"kind": "binding", "name": "paths"},
        result_type=declared_type,
        bindings={
            "paths": {
                "type": mismatched_type,
                "value": ["artifacts/run.json"],
            }
        },
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_payload_invalid"


def test_validate_rejects_non_string_path_child_descriptor() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        {
            "kind": "path_join_under",
            "path_type": _path_descriptor(),
            "child": _literal(_INT, 1),
        },
        result_type=_path_descriptor(),
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


@pytest.mark.parametrize(
    ("operator", "args", "result_type", "expected_code"),
    (
        (
            "list/empty?",
            [_literal(_STRING, "not-a-list")],
            _BOOL,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/head",
            [_literal(_STRING, "not-a-list")],
            {"kind": "optional", "item": _INT},
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/rest",
            [_literal(_STRING, "not-a-list")],
            _LIST_INT,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/append",
            [_list_node(), _literal(_STRING, "wrong")],
            _LIST_INT,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/length",
            [_literal(_STRING, "not-a-list")],
            _INT,
            "pure_expr_operand_type_mismatch",
        ),
        (
            "list/empty?",
            [_list_node()],
            _INT,
            "pure_expr_payload_invalid",
        ),
        (
            "list/head",
            [_list_node()],
            {"kind": "optional", "item": _STRING},
            "pure_expr_payload_invalid",
        ),
        (
            "list/rest",
            [_list_node()],
            {"kind": "list", "item": _STRING},
            "pure_expr_payload_invalid",
        ),
        (
            "list/append",
            [_list_node(), _literal(_INT, 1)],
            {"kind": "list", "item": _STRING},
            "pure_expr_payload_invalid",
        ),
        (
            "list/length",
            [_list_node()],
            _BOOL,
            "pure_expr_payload_invalid",
        ),
    ),
)
def test_validate_enforces_schema_2_list_operator_operand_and_result_types(
    operator: str,
    args: list[dict[str, object]],
    result_type: dict[str, object],
    expected_code: str,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        {"kind": "op", "operator": operator, "args": args},
        result_type=result_type,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == expected_code








def test_empty_list_uses_declared_return_context_through_match_arms(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "match_empty_context.orc"
    source_path.write_text(
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.40")
          (defmodule match_empty_context)
          (defunion Choice
            (EMPTY)
            (READY (items List[Int])))
          (defun choice-items ((choice Choice)) -> List[Int]
            (match choice
              ((EMPTY value) (list))
              ((READY value) (list 1)))))
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    definitions = importlib.import_module("orchestrator.workflow_lisp.definitions")
    functions = importlib.import_module("orchestrator.workflow_lisp.functions")
    reader = importlib.import_module("orchestrator.workflow_lisp.reader")
    syntax = importlib.import_module("orchestrator.workflow_lisp.syntax")
    type_env_module = importlib.import_module("orchestrator.workflow_lisp.type_env")
    traversal = importlib.import_module("orchestrator.workflow_lisp.expression_traversal")
    expressions = importlib.import_module("orchestrator.workflow_lisp.expressions")

    syntax_module = syntax.build_syntax_module(reader.read_sexpr_file(source_path))
    module = definitions.elaborate_definition_module(
        compiler._definition_only_syntax_module(syntax_module)
    )
    compiler._validate_definition_module(module)
    type_env = type_env_module.FrontendTypeEnvironment.from_module(module)
    function_defs = functions.elaborate_function_definitions(syntax_module)
    catalog = functions.build_function_catalog(function_defs, type_env=type_env)
    typed = functions.typecheck_function_definitions(
        function_defs,
        type_env=type_env,
        function_catalog=catalog,
    )

    list_nodes = [
        node
        for node in traversal.walk_expr(typed[0].typed_body.expr)
        if isinstance(node, expressions.ListExpr)
    ]
    assert [node.element_type_ref.name for node in list_nodes] == ["Int", "Int"]






@pytest.mark.parametrize("state_kind", ("optional", "map"))
def test_loop_recur_keeps_top_level_optional_and_map_state_unsupported(
    state_kind: str,
) -> None:
    string_type = PrimitiveTypeRef(name="String")
    state_type = (
        OptionalTypeRef(name="Optional[String]", item_type_ref=string_type)
        if state_kind == "optional"
        else MapTypeRef(
            name="Map[String,String]",
            key_type_ref=string_type,
            value_type_ref=string_type,
        )
    )
    span = _expression_syntax("1").span

    with pytest.raises(LispFrontendCompileError) as excinfo:
        ensure_loop_projectable_type(
            state_type,
            code="loop_recur_state_type_invalid",
            span=span,
            form_path=("workflow-lisp", "defworkflow", "orchestrate"),
        )

    assert excinfo.value.diagnostics[0].code == "loop_recur_state_type_invalid"


@pytest.mark.parametrize("state_kind", ("optional", "map"))
def test_loop_recur_keeps_generic_top_level_optional_and_map_state_unsupported(
    state_kind: str,
) -> None:
    type_param = TypeParamRef(name="T")
    string_type = PrimitiveTypeRef(name="String")
    state_type = (
        OptionalTypeRef(name="Optional[T]", item_type_ref=type_param)
        if state_kind == "optional"
        else MapTypeRef(
            name="Map[String,T]",
            key_type_ref=string_type,
            value_type_ref=type_param,
        )
    )
    span = _expression_syntax("1").span

    with pytest.raises(LispFrontendCompileError) as excinfo:
        ensure_loop_projectable_type(
            state_type,
            code="loop_recur_state_type_invalid",
            span=span,
            form_path=("workflow-lisp", "defworkflow", "orchestrate"),
        )

    assert excinfo.value.diagnostics[0].code == "loop_recur_state_type_invalid"


def test_loop_recur_defers_unresolved_generic_list_projection_validation() -> None:
    span = _expression_syntax("1").span

    ensure_loop_projectable_type(
        ListTypeRef(
            name="List[T]",
            item_type_ref=TypeParamRef(name="T"),
        ),
        code="loop_recur_state_type_invalid",
        span=span,
        form_path=("workflow-lisp", "defworkflow", "orchestrate"),
    )






























@pytest.mark.parametrize(
    ("module_name", "body", "expected_code"),
    (
        (
            "map_path_prompt_fill_refusal",
            """
              (defprompt worker-prompt
                (:fills (target :path :out ChildPath))
                -> Int
                "{target}")
              (defworkflow orchestrate ((children List[String])) -> List[Int]
                (list/map-effect ((child_name children)) :max 2
                  (provider-result providers.worker
                    :prompt
                      (worker-prompt
                        :target
                          (path/join-under ChildPath child_name))
                    :delivery :composed)))
            """,
            "prompt_fill_identity_unsupported",
        ),
    ),
)
def test_frontend_effect_map_path_join_under_does_not_widen_other_surfaces(
    tmp_path: Path,
    module_name: str,
    body: str,
    expected_code: str,
) -> None:
    module_path = tmp_path / f"{module_name}.orc"
    module_path.write_text(
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.40")
          (defmodule {module_name})
          (export orchestrate)
          (defpath ChildPath
            :kind relpath
            :under "artifacts/children"
            :must-exist false)
          {body})
        """.strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            module_path,
            source_roots=(tmp_path,),
            entry_workflow="orchestrate",
            provider_externs={"providers.worker": "deterministic-worker"},
            validate_shared=True,
            workspace_root=tmp_path,

        )

    assert excinfo.value.diagnostics[0].code == expected_code
















































def test_list_traversal_authored_head_inventory_is_exact() -> None:
    registry = importlib.import_module(
        "orchestrator.workflow_lisp.form_registry"
    )

    assert registry.list_traversal_authored_heads() == frozenset(
        _LIST_TRAVERSAL_AUTHORED_HEADS
    )


_REDUCTIONS_PROGRAM = """(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule reductions) (export run)
  (defun first-of ((xs List[Int]) (n Int)) -> List[Int] (list/take xs n))
  (defun all-positive ((xs List[Int])) -> Bool (list/all (list/map ((x xs)) (> x 0))))
  (defun any-large ((xs List[Int])) -> Bool (list/any (list/map ((x xs)) (> x 5))))
  (defworkflow run ((xs List[Int])) -> RESULT
    BODY))"""


@pytest.mark.parametrize(
    ("result", "body", "expected"),
    (
        ("List[Int]", "(first-of xs 2)", [1, 2]),
        ("Bool", "(all-positive xs)", True),
        ("Bool", "(any-large (first-of xs 2))", False),
        ("List[Int]", "(list/map ((x xs)) (list/length (list/take xs x)))", [1, 2, 3]),
        ("List[Bool]", "(list/map ((x xs)) (list/any (list (> x 5) (= x 1))))", [True, False, True]),
        ("Int", "(if (list/all (list/map ((x xs)) (> x 0))) (list/length (list/take xs 2)) 0)", 2),
        ("Int", "(if (list/any (list/map ((x xs)) (> x 9))) 1 0)", 0),
    ),
    ids=("defun-take", "defun-all", "defun-any", "map-body-take", "map-body-any", "condition-all",
         "condition-any"),
)
def test_reduction_operators_are_pure_everywhere(tmp_path: Path, result: str, body: str, expected) -> None:
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import EvaluatedValue
    from tests.test_workflow_evaluated_control import INT, _build_read_back

    source = _REDUCTIONS_PROGRAM.replace("RESULT", result).replace("BODY", body)
    program = _build_read_back(tmp_path, {"reductions.orc": source}, "reductions::run")
    xs = EvaluatedValue([1, 2, 9], {"kind": "list", "item": INT}, {"input:xs"})

    def no_effect(*_args):
        raise AssertionError("a pure operator performed an effect")

    assert evaluate_closed_program(program, {"xs": xs}, effect_handler=no_effect).json_value() == expected


@pytest.mark.parametrize(
    ("result", "body"),
    (
        ("List[Int]", "(list/take xs 1.5)"),
        ("List[Int]", "(list/take xs flag)"),
        ("Bool", "(list/all xs)"),
        ("Bool", "(list/any xs)"),
        ("Bool", "(list/all flag)"),
    ),
    ids=("take-float-count", "take-bool-count", "all-of-ints", "any-of-ints", "all-of-a-bool"),
)
def test_take_and_reductions_refuse_operands_of_the_wrong_type(tmp_path: Path, result: str, body: str) -> None:
    from tests.test_workflow_evaluated_control import _build_read_back

    source = (
        '(workflow-lisp (:language "0.1") (:target-dsl "2.40")\n'
        "  (defmodule refusal) (export run)\n"
        f"  (defworkflow run ((xs List[Int]) (flag Bool)) -> {result}\n    {body}))"
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_read_back(tmp_path, {"refusal.orc": source}, "refusal::run")

    assert excinfo.value.diagnostics[0].code == "pure_expr_operand_type_mismatch"




def _compile_hygiene_source(tmp_path: Path, source: str):
    module_match = re.search(r"\(defmodule\s+([^()\s]+)\)", source)
    assert module_match is not None
    path = tmp_path / (module_match.group(1) + ".orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.strip() + "\n", encoding="utf-8")
    result = compile_stage3_entrypoint(path, source_roots=(tmp_path,),
        provider_externs={}, prompt_externs={}, workspace_root=tmp_path,
        validate_shared=False)
    return result.entry_result.typed_workflows[0].typed_body.expr


def _write_list_map_template_macro(tmp_path: Path) -> None:
    module_path = tmp_path / "helpers" / "list-map-macros.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.40")
          (defmodule helpers/list-map-macros)
          (export map-plus-one)
          (defmacro map-plus-one (values)
            (list/map ((item values))
              (+ item 1))))
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def test_current_target_local_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    expression = _compile_hygiene_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.40")
          (defmodule local_list_map_hygiene)
          (export orchestrate)
          (defmacro map-plus-one (values)
            (list/map ((item values))
              (+ item 1)))
          (defworkflow orchestrate
            ((values List[Int]) (item Int))
            -> List[Int]
            (map-plus-one values)))
        """,
    )

    assert isinstance(expression, ListMapExpr)
    assert expression.binder_name == "%macro__map-plus-one__m0001__item"
    assert expression.binder_name != "item"
    assert isinstance(expression.body_expr, PureOpExpr)
    assert expression.body_expr.operator == "+"
    assert isinstance(expression.body_expr.args[0], NameExpr)
    assert expression.body_expr.args[0].name == expression.binder_name


def test_current_target_imported_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    _write_list_map_template_macro(tmp_path)

    expression = _compile_hygiene_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.40")
          (defmodule imported_list_map_hygiene)
          (import helpers/list-map-macros :only (map-plus-one))
          (export orchestrate)
          (defworkflow orchestrate
            ((values List[Int]) (item Int))
            -> List[Int]
            (map-plus-one values)))
        """,
    )

    assert isinstance(expression, ListMapExpr)
    assert expression.binder_name == "%macro__map-plus-one__m0001__item"
    assert expression.binder_name != "item"
    assert isinstance(expression.body_expr, PureOpExpr)
    assert expression.body_expr.operator == "+"
    assert isinstance(expression.body_expr.args[0], NameExpr)
    assert expression.body_expr.args[0].name == expression.binder_name


# The typed list literal `(list :of T item…)` (staged-workflow authoring, Task L).

_COMMAND_BOUNDARIES = {
    name: ExternalToolBinding(name=name, stable_command=("python", "probe.py"), closure=())
    for name in ("fetch",)
}
_FETCH_WORKFLOW = (
    "(defworkflow fetch-one ((n Int)) -> Int "
    '(command-result fetch :argv ("python" "probe.py" n) :returns Int))'
)


def _typed_list_module(body: str, *, returns: str, extra: str = "", params: str = "") -> str:
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule typed_list) (export run)
  {extra}
  (defworkflow run ({params}) -> {returns} {body}))'''


def _typed_list_program(root: Path, source: str) -> ClosedProgram:
    return ClosedProgram.from_artifact(build(root, source, boundaries=_COMMAND_BOUNDARIES).artifact())


def _typed_list_outcome(root: Path, source: str) -> tuple:
    return build_outcome(lambda: build(root, source, boundaries=_COMMAND_BOUNDARIES))


# Each case: (result type, workflow body, its value).
_TYPED_EMPTY_POSITIONS = {
    "let_binding": ("List[String]", '(let* ((xs (list :of String))) (list/append xs "a"))', ["a"]),
    "loop_state_fn_form": (
        "List[String]",
        '(loop/recur :max 3 :state (list :of String) '
        '(fn (s) (if (= (list/length s) 2) (done s) (continue (list/append s "x")))))',
        ["x", "x"],
    ),
    "loop_state_binder_form": (
        "List[String]",
        '(loop/recur ((s (list :of String))) :max 3 '
        '(if (= (list/length s) 2) (done s) (continue (list/append s "x"))))',
        ["x", "x"],
    ),
    "continue_value": (
        "Int",
        '(loop/recur ((s (list "a"))) :max 3 (if (list/empty? s) (done 7) (continue (list :of String))))',
        7,
    ),
    "done_value": ("Int", "(list/length (loop/recur ((s 0)) :max 2 (done (list :of String))))", 0),
    "on_exhausted_value": (
        "Int",
        '(list/length (loop/recur ((s 0)) :max 2 :on-exhausted (list :of String) '
        '(if (= s 9) (done (list "z")) (continue (+ s 1)))))',
        0,
    ),
    "list_append_operand": ("List[String]", '(list/append (list :of String) "a")', ["a"]),
    "map_source": ("List[Int]", "(list/map ((x (list :of String))) 1)", []),
}


@pytest.mark.parametrize("case", sorted(_TYPED_EMPTY_POSITIONS))
def test_typed_empty_list_in_every_position(tmp_path: Path, case: str) -> None:
    returns, body, value = _TYPED_EMPTY_POSITIONS[case]
    program = _typed_list_program(tmp_path, _typed_list_module(body, returns=returns))

    assert evaluate_closed_program(program, {}).json_value() == value


def test_typed_empty_list_as_an_equal_operand_meets_the_list_equality_refusal(tmp_path: Path) -> None:
    """`=` compares no lists; a typed list reaches that refusal, as two named lists do."""
    typed = _typed_list_outcome(tmp_path / "typed", _typed_list_module(
        "(= (list :of String) (list :of String))", returns="Bool"))
    named = _typed_list_outcome(tmp_path / "named", _typed_list_module(
        "(= xs ys)", returns="Bool", params="(xs List[String]) (ys List[String])"))

    assert typed == named == ("refused", "pure_expr_operand_type_mismatch")


# Each case: (result type, extra definitions, parameters, body with `{list}` where the list stands).
_CONTEXT_STATED_POSITIONS = {
    "record_field": ("R", "(defrecord R (xs List[String]))", "", "(record R :xs {list})"),
    "workflow_argument": (
        "Int", "(defworkflow count-of ((xs List[String])) -> Int (list/length xs))", "",
        "(call count-of :xs {list})",
    ),
    "if_arm": ("List[String]", "", "(c Bool) (ys List[String])", "(if c ys {list})"),
}


@pytest.mark.parametrize("case", sorted(_CONTEXT_STATED_POSITIONS))
def test_typed_list_has_the_digest_of_the_contextual_list(tmp_path: Path, case: str) -> None:
    returns, extra, params, body = _CONTEXT_STATED_POSITIONS[case]
    programs = [
        _typed_list_program(tmp_path / name, _typed_list_module(
            body.format(list=written), returns=returns, extra=extra, params=params))
        for name, written in (("untyped", "(list)"), ("typed", "(list :of String)"))
    ]

    assert (programs[1].digest, programs[1].sites) == (programs[0].digest, programs[0].sites)


def test_typed_list_with_items_has_the_digest_of_the_untyped_list(tmp_path: Path) -> None:
    programs = [
        _typed_list_program(tmp_path / name, _typed_list_module(
            f'(let* ((xs {written})) (list/append xs "c"))', returns="List[String]"))
        for name, written in (("untyped", '(list "a" "b")'), ("typed", '(list :of String "a" "b")'))
    ]

    assert programs[1].digest == programs[0].digest


_TYPED_LIST_REFUSALS = {
    "item_of_another_type": ("List[Int]", "", '(list :of Int "a")', "pure_expr_operand_type_mismatch"),
    "context_of_another_type": (
        "R", "(defrecord R (xs List[String]))", "(record R :xs (list :of Int))", "pure_expr_operand_type_mismatch",
    ),
    "unknown_type": ("Int", "", "(list/length (list :of Nope))", "type_unknown"),
    "no_type": ("Int", "", "(list/length (list :of))", "list_item_type_invalid"),
    "type_not_a_name": ("Int", "", "(list/length (list :of 3))", "list_item_type_invalid"),
    "value_name": ("Int", "", "(let* ((n 3)) (list/length (list :of n 4)))", "type_unknown"),
    "value_named_like_a_primitive_type": (
        "List[String]", "", '(let* ((Int "s")) (list :of Int "a"))', "pure_expr_operand_type_mismatch",
    ),
    "value_named_like_a_record_type": (
        "Int", "(defrecord R (v String))", "(let* ((R 1)) (list/length (list :of R 1)))",
        "pure_expr_operand_type_mismatch",
    ),
}


@pytest.mark.parametrize("case", sorted(_TYPED_LIST_REFUSALS))
def test_typed_list_checks_its_items_and_its_context(tmp_path: Path, case: str) -> None:
    returns, extra, body, code = _TYPED_LIST_REFUSALS[case]

    assert _typed_list_outcome(tmp_path, _typed_list_module(body, returns=returns, extra=extra)) == (
        "refused", code)


@pytest.mark.parametrize(
    "value", ("(list 1)", "(list :of Int)", "(list/map ((x s)) 1)"),
    ids=("untyped_items", "typed_empty", "map"),
)
def test_wrongly_typed_continue_list_keeps_the_continue_refusal(tmp_path: Path, value: str) -> None:
    body = f'(loop/recur ((s (list "a"))) :max 2 (if (list/empty? s) (done 1) (continue {value})))'

    assert _typed_list_outcome(tmp_path, _typed_list_module(body, returns="Int")) == (
        "refused", "loop_recur_continue_type_mismatch")


@pytest.mark.parametrize(
    ("returns", "extra", "body", "value"),
    (
        ("Int", "", '(loop/recur ((s (list "a"))) :max 3 (if (list/empty? s) (done 7) (continue (list))))', 7),
        ("Int", "(defun count ((xs List[String])) -> Int (list/length xs))", "(count (list))", 0),
    ),
    ids=("continue_value", "defun_argument"),
)
def test_empty_list_takes_its_type_from_continue_and_a_defun_argument(
    tmp_path: Path, returns: str, extra: str, body: str, value: object,
) -> None:
    program = _typed_list_program(tmp_path, _typed_list_module(body, returns=returns, extra=extra))

    assert evaluate_closed_program(program, {}).json_value() == value


def test_typed_list_names_a_type_parameter_of_a_generic_procedure(tmp_path: Path) -> None:
    """`T` resolves to the procedure's parameter; a `List[T]` in a generic body is then refused as
    `(list x)` with `x` of type `T` is."""
    outcomes = [
        _typed_list_outcome(tmp_path / name, _typed_list_module(
            '(list/length (wrap "a"))', returns="Int",
            extra=f"(defproc wrap :forall (T) ((x T)) -> List[T] {body})"))
        for name, body in (("typed", "(list/append (list :of T) x)"), ("untyped", "(list x)"))
    ]

    assert outcomes[0] == outcomes[1] == ("refused", "list_collection_contract_unsupported")


# Surface coherence E1: a list element takes an effect only when every part of the list is simple.
# Each case: (typed list, untyped list) in one `let*` binding.
_TYPED_LIST_EFFECT_ELEMENTS = {
    "direct_effect": ("(list :of Int (call fetch-one :n 1) 2)", "(list (call fetch-one :n 1) 2)"),
    "effect_beside_a_conditional": (
        "(list :of Int (call fetch-one :n 1) (if c 2 3))", "(list (call fetch-one :n 1) (if c 2 3))",
    ),
    "effect_in_a_conditional": (
        "(list :of Int (if c (call fetch-one :n 1) 0) 2)", "(list (if c (call fetch-one :n 1) 0) 2)",
    ),
}


@pytest.mark.parametrize("case", sorted(_TYPED_LIST_EFFECT_ELEMENTS))
def test_typed_list_admits_effect_elements_as_the_untyped_list_does(tmp_path: Path, case: str) -> None:
    outcomes = []
    for name, written in zip(("typed", "untyped"), _TYPED_LIST_EFFECT_ELEMENTS[case], strict=True):
        source = _typed_list_module(f"(let* ((xs {written})) (list/length xs))", returns="Int",
                                    extra=_FETCH_WORKFLOW, params="(c Bool)")
        outcome = _typed_list_outcome(tmp_path / name, source)
        if outcome == ("builds",):
            program = _typed_list_program(tmp_path / f"{name}-program", source)
            outcome = ("builds", program.digest, program.sites)
        outcomes.append(outcome)

    assert outcomes[0] == outcomes[1]
    assert outcomes[0][0] == ("builds" if case == "direct_effect" else "refused")


def test_typed_list_in_a_macro_template_used_twice_gives_two_values(tmp_path: Path) -> None:
    extra = (_FETCH_WORKFLOW + " (defrecord Pair (a List[Int]) (b List[Int]))"
             " (defmacro fetched (n) (list :of Int (call fetch-one :n n)))")
    program = _typed_list_program(tmp_path, _typed_list_module(
        "(let* ((a (fetched 1)) (b (fetched 1))) (record Pair :a a :b b))", returns="Pair", extra=extra))
    identities: list[str] = []

    def perform(node, _operands, identity, _owner, _reader):
        identities.append(identity)
        return coerce_evaluated_value(len(identities), node["result"], dependencies={identity},
                                      committed_result_path=f"artifacts/{len(identities)}.json")

    result = evaluate_closed_program(program, {}, effect_handler=perform)

    assert (result.json_value(), len(set(identities))) == ({"a": [1], "b": [2]}, 2)


_GROWING_LOOP = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule grow) (export run)
  (defworkflow run () -> List[String]
    (loop/recur ((notes (list :of String))) :max 4
      (if (= (list/length notes) 3) (done notes)
        (continue (list/append notes
          (command-result step :argv ("python" "step.py" (list/length notes)) :returns String)))))))
'''
_NOTE_STEP = '''import json, os, sys
from pathlib import Path
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("note-" + sys.argv[1]))
'''
# `:steps` takes a name: a fill operand is a literal, a name or a field path, and a list is none of these.
_EMPTY_FILL = '''(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule fill) (export run)
  (defrecord Feedback (findings List[String]))
  (defprompt review (:fills (steps :value List[String])) -> Feedback "Review the plan: {steps}")
  (defworkflow run () -> Int
    (let* ((none (list :of String))
           (feedback (provider-result providers.review :model "m" :effort "low" :prompt (review :steps none))))
      (list/length feedback.findings))))
'''
_REVIEW_STAND_IN = '''import os, sys
from pathlib import Path
sys.stdin.buffer.read()
with Path("calls.log").open("a") as stream:
    stream.write("launched\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text('{"findings": ["a", "b"]}')
'''


def _orchestrator_run(root: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": closed_path(root / "bin"), "PYTHONPATH": str(Path(__file__).parents[1]),
           "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run([sys.executable, "-B", "-m", "orchestrator", "run", *argv], cwd=root, env=env,
                          capture_output=True, text=True, check=False, timeout=120)


def test_loop_state_started_as_a_typed_empty_list_grows_through_the_command_line(tmp_path: Path) -> None:
    (tmp_path / "grow.orc").write_text(_GROWING_LOOP, encoding="utf-8")
    (tmp_path / "step.py").write_text(_NOTE_STEP, encoding="utf-8")
    (tmp_path / "commands.json").write_text(
        json.dumps({"step": {"stable_command": ["python", "step.py"], "closure": ["step.py"]}}), encoding="utf-8")

    ran = _orchestrator_run(tmp_path, "grow.orc")

    assert (ran.returncode, json.loads(ran.stdout.splitlines()[-1])) == (
        0, ["note-0", "note-1", "note-2"]), ran.stderr


def test_typed_empty_list_bound_by_let_fills_a_prompt_through_the_command_line(tmp_path: Path) -> None:
    (tmp_path / "fill.orc").write_text(_EMPTY_FILL, encoding="utf-8")
    (tmp_path / "providers.json").write_text(json.dumps({"providers.review": "codex"}), encoding="utf-8")
    stand_in = tmp_path / "bin" / "codex"
    stand_in.parent.mkdir()
    stand_in.write_text(f"#!{sys.executable}\n" + _REVIEW_STAND_IN, encoding="utf-8")
    stand_in.chmod(0o700)

    ran = _orchestrator_run(tmp_path, "fill.orc", "--provider-externs-file", "providers.json")

    launches = (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()
    assert (ran.returncode, ran.stdout.splitlines()[-1], len(launches)) == (0, "2", 1), ran.stderr
