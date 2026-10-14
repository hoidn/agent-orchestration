from __future__ import annotations

from dataclasses import dataclass
import importlib
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.expressions import FunctionCallExpr, LiteralExpr, ProcedureCallExpr, ListMapExpr, NameExpr, PureOpExpr, elaborate_expression
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
)


@dataclass(frozen=True)
class _UnsupportedListMapEffectBody:
    span: object
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()


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






def test_target_218_is_accepted_and_owns_one_list_traversal_gate() -> None:
    syntax = importlib.import_module("orchestrator.workflow_lisp.syntax")

    module = build_syntax_module(
        read_sexpr_text(
            _module_source("2.18"),
            source_path="target_218_list_traversal.orc",
        )
    )

    assert module.target_dsl_version == "2.18"
    assert syntax.LIST_TRAVERSAL_MIN_TARGET_DSL_VERSION == "2.18"




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


def test_validate_rejects_list_item_vs_element_descriptor_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_node(_literal(_STRING, "wrong")),
        result_type=_LIST_INT,
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


def test_validate_rejects_list_map_source_vs_binder_descriptor_mismatch() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    payload = _pure_payload(
        _list_map_node(
            source=_list_node(_literal(_INT, 1)),
            binder_type=_STRING,
            result_element_type=_STRING,
        ),
        result_type={"kind": "list", "item": _STRING},
    )

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(payload)

    assert excinfo.value.code == "pure_expr_operand_type_mismatch"


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
          (:target-dsl "2.18")
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






























def test_list_map_effect_pre_scan_surfaces_unknown_traversal_nodes() -> None:
    from orchestrator.workflow_lisp.effects import EMPTY_EFFECT_SUMMARY
    from orchestrator.workflow_lisp.expressions import ListMapEffectExpr
    from orchestrator.workflow_lisp.typecheck_context import TypedExpr
    from orchestrator.workflow_lisp.typecheck_structural_values import (
        typecheck_structural_value_expr,
    )

    datum = read_sexpr_text('"item"', source_path="unsupported_map_body.orc").items[0]
    source_expr = LiteralExpr(
        "item",
        "string",
        datum.span,
        ("workflow-lisp", "list-map-effect"),
    )
    unsupported_body = _UnsupportedListMapEffectBody(
        span=datum.span,
        form_path=("workflow-lisp", "list-map-effect", "body"),
    )
    expr = ListMapEffectExpr(
        binder_name="item",
        source_expr=source_expr,
        max_iterations=1,
        body_expr=unsupported_body,
        source_item_type_ref=None,
        result_item_type_ref=None,
        span=datum.span,
        form_path=("workflow-lisp", "list-map-effect"),
    )

    def recurse(candidate, **_kwargs):
        assert candidate is source_expr
        return TypedExpr(
            expr=source_expr,
            type_ref=ListTypeRef(
                "List[String]",
                PrimitiveTypeRef("String"),
            ),
            span=source_expr.span,
            form_path=source_expr.form_path,
            effect_summary=EMPTY_EFFECT_SUMMARY,
        )

    with pytest.raises(TypeError):
        typecheck_structural_value_expr(
            expr,
            context=SimpleNamespace(type_env=None, value_env={}),
            recurse=recurse,
            typed_factory=lambda **kwargs: kwargs,
            expected_type=None,
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
          (:target-dsl "2.23")
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
            lowering_route="wcc_m4",
        )

    assert excinfo.value.diagnostics[0].code == expected_code
















































def test_list_traversal_authored_head_inventory_is_exact() -> None:
    registry = importlib.import_module(
        "orchestrator.workflow_lisp.form_registry"
    )

    assert registry.list_traversal_authored_heads() == frozenset(
        _LIST_TRAVERSAL_AUTHORED_HEADS
    )


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
@pytest.mark.parametrize("callable_lane", ("function", "procedure", "bound"))
def test_target_217_list_traversal_heads_defer_to_same_named_callable(
    head: str,
    callable_lane: str,
) -> None:
    expression = elaborate_expression(
        _expression_syntax(f"({head} 1)"),
        target_dsl_version="2.17",
        function_names=(
            frozenset({head})
            if callable_lane == "function"
            else frozenset()
        ),
        procedure_names=(
            frozenset({head})
            if callable_lane == "procedure"
            else frozenset()
        ),
        bound_names=(
            frozenset({head})
            if callable_lane == "bound"
            else frozenset()
        ),
    )

    expected_type = (
        FunctionCallExpr
        if callable_lane == "function"
        else ProcedureCallExpr
    )
    assert isinstance(expression, expected_type)
    assert expression.callee_name == head


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
          (:target-dsl "2.18")
          (defmodule helpers/list-map-macros)
          (export map-plus-one)
          (defmacro map-plus-one (values)
            (list/map ((item values))
              (+ item 1))))
        """.strip()
        + "\n",
        encoding="utf-8",
    )


def test_target_218_local_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    expression = _compile_hygiene_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
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


def test_target_218_imported_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    _write_list_map_template_macro(tmp_path)

    expression = _compile_hygiene_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
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


def test_target_217_user_macro_list_map_head_keeps_generic_hygiene(
    tmp_path: Path,
) -> None:
    expression = _compile_hygiene_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy_list_map_hygiene)
          (export orchestrate)
          (defmacro list/map (bindings body) body)
          (defmacro use-legacy-map (values)
            (list/map ((item values))
              (+ item 1)))
          (defworkflow orchestrate
            ((values List[Int]) (item Int))
            -> Int
            (use-legacy-map values)))
        """,
    )

    assert isinstance(expression, PureOpExpr)
    assert expression.operator == "+"
    assert isinstance(expression.args[0], NameExpr)
    assert expression.args[0].name == "item"
