from __future__ import annotations

import importlib
import json
from pathlib import Path
import re

import pytest

from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expressions import (
    FunctionCallExpr,
    ProcedureCallExpr,
    elaborate_expression,
)
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
    "path/join-under",
    "list/empty?",
    "list/head",
    "list/rest",
    "list/append",
    "list/length",
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


def _build_old_only_projection(tmp_path: Path, *, target_dsl: str):
    source_path = tmp_path / "old_only_projection.orc"
    source_path.write_text(_module_source(target_dsl) + "\n", encoding="utf-8")
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    return build.build_frontend_bundle(
        build.FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="orchestrate",
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )


def _projection_payload(result) -> dict[str, object]:
    projection_steps = [
        step
        for step in result.validated_bundle.surface.steps
        if step.pure_projection is not None
    ]
    assert len(projection_steps) == 1
    return projection_steps[0].pure_projection


def _build_source(
    tmp_path: Path,
    source: str,
    *,
    entry_workflow: str = "orchestrate",
    filename: str | None = None,
    source_roots: tuple[Path, ...] | None = None,
    lowering_route: str | None = None,
):
    if filename is None:
        module_match = re.search(r"\(defmodule\s+([^()\s]+)\)", source)
        assert module_match is not None
        filename = f"{module_match.group(1)}.orc"
    source_path = tmp_path / filename
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(source.strip() + "\n", encoding="utf-8")
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    return build.build_frontend_bundle(
        build.FrontendBuildRequest(
            source_path=source_path,
            source_roots=source_roots or (tmp_path,),
            entry_workflow=entry_workflow,
            provider_externs_path=None,
            prompt_externs_path=None,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
            lowering_route=lowering_route,
        )
    )


def _diagnostic_code_for_source(
    tmp_path: Path,
    source: str,
    *,
    filename: str | None = None,
) -> str:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build_source(tmp_path, source, filename=filename)
    return excinfo.value.diagnostics[0].code


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


def _write_legacy_list_traversal_macro(
    tmp_path: Path,
    *,
    head: str,
) -> None:
    module_path = tmp_path / "legacy" / "list-macros.orc"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy/list-macros)
          (export {head})
          (defmacro {head} (value) value))
        """.strip()
        + "\n",
        encoding="utf-8",
    )


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


def test_shared_mapping_validation_accepts_target_218(tmp_path: Path) -> None:
    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.18",
                "name": "target-218",
                "steps": [{"name": "Done", "command": ["echo", "done"]}],
            },
            workflow_path=tmp_path / "target-218.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert result.bundle.surface.version == "2.18"


def test_unknown_target_versions_still_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_syntax_module(
            read_sexpr_text(
                _module_source("2.19"),
                source_path="target_219_list_traversal.orc",
            )
        )
    assert excinfo.value.diagnostics[0].code == "target_dsl_unsupported"

    result = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.19",
                "name": "target-219",
                "steps": [{"name": "Done", "command": ["echo", "done"]}],
            },
            workflow_path=tmp_path / "target-219.orc",
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )
    assert result.bundle is None
    assert any("Unsupported version '2.19'" in error.message for error in result.errors)


def test_pure_runtime_accepts_existing_nodes_in_schema_2() -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    payload = _int_literal_payload(2)

    assert pure_expr.validate_pure_expr_payload(payload) is payload
    assert pure_expr.evaluate_pure_expr(payload) == 1


@pytest.mark.parametrize("schema_version", (0, 3, True, 2.0, "2"))
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


def test_old_only_target_218_projection_stays_on_schema_1(
    tmp_path: Path,
) -> None:
    target_217_projection = _projection_payload(
        _build_old_only_projection(tmp_path, target_dsl="2.17")
    )
    target_218_projection = _projection_payload(
        _build_old_only_projection(tmp_path, target_dsl="2.18")
    )

    assert target_218_projection["payload"]["pure_expr_schema_version"] == 1
    assert target_218_projection["payload"] == target_217_projection["payload"]
    assert (
        target_218_projection["payload_digest"]
        == target_217_projection["payload_digest"]
    )


def test_target_217_schema_1_projection_digest_is_frozen(
    tmp_path: Path,
) -> None:
    projection = _projection_payload(
        _build_old_only_projection(tmp_path, target_dsl="2.17")
    )

    assert projection["payload"]["pure_expr_schema_version"] == 1
    assert projection["payload_digest"] == (
        "sha256:a40fe0237ee12f03aff127afcc613dfa89daad5a0e586c0a49072289a50f0323"
    )


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


def test_frontend_list_constructor_and_total_operators_synthesize_exact_types(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_surface)
          (export orchestrate)
          (defun is-empty ((items List[Int])) -> Bool
            (list/empty? items))
          (defun first-item ((items List[Int])) -> Optional[Int]
            (list/head items))
          (defun remaining-items ((items List[Int])) -> List[Int]
            (list/rest items))
          (defun append-item ((items List[Int]) (item Int)) -> List[Int]
            (list/append items item))
          (defun item-count ((items List[Int])) -> Int
            (list/length items))
          (defworkflow orchestrate
            ((items List[Int]))
            -> List[Int]
            (append-item (list 1 2) 3)))
        """,
    )

    projection = _projection_payload(result)
    payload = projection["payload"]
    assert payload["pure_expr_schema_version"] == 2
    # Each helper body is checked against its distinct declared result above;
    # reaching a bundle proves all five operator result types synthesized.
    assert payload["expr"]["kind"] == "op"
    assert payload["expr"]["operator"] == "list/append"
    assert payload["expr"]["args"][0] == {
        "kind": "list",
        "element_type": _INT,
        "items": (
            _literal(_INT, 1),
            _literal(_INT, 2),
        ),
    }


def test_frontend_list_constructor_rejects_mixed_element_types(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule list_mismatch)
              (export orchestrate)
              (defworkflow orchestrate () -> List[Int]
                (list 1 "wrong")))
            """,
        )
        == "pure_expr_operand_type_mismatch"
    )


@pytest.mark.parametrize(
    "body",
    (
        "(list)",
        "(record Box :items (list))",
        "(variant Choice READY :items (list))",
        "(identity-list (list))",
        "(if true (list) (list 1))",
    ),
    ids=(
        "declared-return",
        "record-field",
        "union-field",
        "direct-callable-argument",
        "if-branch",
    ),
)
def test_empty_list_uses_only_enumerated_exact_expected_type_contexts(
    tmp_path: Path,
    body: str,
) -> None:
    definitions = """
      (defrecord Box (items List[Int]))
      (defunion Choice
        (EMPTY)
        (READY (items List[Int])))
      (defun identity-list ((items List[Int])) -> List[Int] items)
    """
    params = "()"
    return_type = (
        "Box"
        if body.startswith("(record")
        else "Choice"
        if body.startswith("(variant")
        else "List[Int]"
    )
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule empty_context)
          (export orchestrate)
          {definitions}
          (defworkflow orchestrate {params} -> {return_type}
            {body}))
        """,
    )

    if return_type == "List[Int]":
        payload = _projection_payload(result)["payload"]
        assert payload["pure_expr_schema_version"] == 2


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


def test_empty_list_in_loop_state_lowers_as_one_collection_field(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule empty_loop_state_context)
          (export orchestrate)
          (defworkflow orchestrate () -> Int
            (loop/recur
              :max 1
              :state (loop-state
                (items List[Int] (list)))
              (fn (state)
                (done 0)))))
        """,
    )

    repeat_step = next(
        step
        for step in result.validated_bundle.surface.steps
        if step.repeat_until is not None
    )
    state_fields = {
        name: dict(contract.definition)
        for name, contract in repeat_step.repeat_until.outputs.items()
        if name.startswith("state")
    }
    assert set(state_fields) == {"state__items"}
    assert {
        key: value
        for key, value in state_fields["state__items"].items()
        if key != "from"
    } == {
        "kind": "collection",
        "type": "list",
        "items": {"type": "integer"},
    }
    assert state_fields["state__items"]["from"]["ref"].endswith(
        ".artifacts.state__items"
    )


@pytest.mark.parametrize(
    "list_type",
    (
        "List[String]",
        "List[Path.artifact-root]",
    ),
)
def test_loop_recur_accepts_whole_list_transportable_state_and_result(
    tmp_path: Path,
    list_type: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_loop_contract)
          (export orchestrate)
          (defworkflow orchestrate ((items {list_type})) -> {list_type}
            (loop/recur
              :max 1
              :state items
              (fn (state)
                (done state)))))
        """,
    )

    repeat_step = next(
        step
        for step in result.validated_bundle.surface.steps
        if step.repeat_until is not None
    )
    assert repeat_step.repeat_until.outputs["state"].kind == "collection"
    assert repeat_step.repeat_until.outputs["state"].value_type == "list"
    assert repeat_step.repeat_until.outputs["result"].kind == "collection"
    assert repeat_step.repeat_until.outputs["result"].value_type == "list"


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


def test_generic_list_loop_revalidates_supported_concrete_specialization(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule generic_supported_list_loop)
          (export orchestrate)
          (defproc carry-list
            :forall (T)
            ((items List[T]))
            -> List[T]
            :effects ()
            :lowering inline
            (loop/recur :max 1 :state items
              (fn (state)
                (done state))))
          (defworkflow orchestrate ((items List[String])) -> List[String]
            (carry-list items)))
        """,
    )

    assert result.validated_bundle.surface.outputs["__result__"].kind == "collection"


def test_generic_list_loop_rejects_unsupported_concrete_specialization(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule generic_unsupported_list_loop)
              (export orchestrate)
              (defrecord Item
                (value Int))
              (defproc carry-list
                :forall (T)
                ((items List[T]))
                -> List[T]
                :effects ()
                :lowering inline
                (loop/recur :max 1 :state items
                  (fn (state)
                    (done state))))
              (defproc instantiate-unsupported
                ((items List[Item]))
                -> Int
                :effects ()
                :lowering inline
                (let* ((ignored (carry-list items)))
                  0))
              (defworkflow orchestrate () -> Int
                0))
            """,
        )
        == "list_collection_contract_unsupported"
    )


@pytest.mark.parametrize(
    "state_type",
    (
        "Optional[T]",
        "Map[String,T]",
    ),
)
def test_generic_optional_and_map_loops_fail_before_specialization(
    tmp_path: Path,
    state_type: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule generic_unsupported_container_loop)
              (export orchestrate)
              (defproc carry-container
                :forall (T)
                ((value {state_type}))
                -> {state_type}
                :effects ()
                :lowering inline
                (loop/recur :max 1 :state value
                  (fn (state)
                    (done state))))
              (defworkflow orchestrate () -> Int
                0))
            """,
        )
        == "loop_recur_state_type_invalid"
    )


@pytest.mark.parametrize(
    ("element_definition", "seed_expr"),
    (
        ("(defrecord Item (value Int))", "(list (record Item :value 1))"),
        (
            "(defunion Item (READY (value Int)))",
            "(list (variant Item READY :value 1))",
        ),
    ),
)
def test_loop_recur_rejects_record_and_union_collection_elements(
    tmp_path: Path,
    element_definition: str,
    seed_expr: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule unsupported_loop_list)
              (export orchestrate)
              {element_definition}
              (defworkflow orchestrate () -> Int
                (loop/recur
                  :max 1
                  :state {seed_expr}
                  (fn (state)
                    (done 0)))))
            """,
        )
        == "list_collection_contract_unsupported"
    )


@pytest.mark.parametrize(
    "body",
    (
        "(list)",
        "(let* ((items (list))) items)",
    ),
    ids=("standalone-wrong-expected-type", "unannotated-let"),
)
def test_empty_list_without_exact_list_context_fails_closed(
    tmp_path: Path,
    body: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule empty_context_required)
              (export orchestrate)
              (defworkflow orchestrate () -> Int
                {body}))
            """,
        )
        == "list_empty_type_context_required"
    )


def test_frontend_pure_map_captures_lexically_and_lowers_one_schema2_value(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule pure_map)
          (export orchestrate)
          (defworkflow orchestrate
            ((items List[Int]) (offset Int))
            -> List[Int]
            (list/map ((item items))
              (+ item offset))))
        """,
    )

    projection = _projection_payload(result)
    payload = projection["payload"]
    assert payload["pure_expr_schema_version"] == 2
    assert payload["expr"]["kind"] == "list_map"
    assert payload["expr"]["source"] == {"kind": "binding", "name": "items"}
    assert payload["expr"]["binder"] == {"name": "item", "type": _INT}
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")
    assert pure_expr.evaluate_pure_expr(
        payload,
        resolved_bindings={"items": [3, 1, 2], "offset": 10},
    ) == [13, 11, 12]


@pytest.mark.parametrize(
    "binder",
    (
        "()",
        "((item))",
        "((item xs) (other xs))",
        "((__compiler_item xs))",
    ),
)
def test_frontend_pure_map_rejects_invalid_binder_shapes(
    tmp_path: Path,
    binder: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule invalid_map_binder)
              (export orchestrate)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map {binder} 1)))
            """,
        )
        == "list_map_binder_invalid"
    )


def test_frontend_pure_map_rejects_effectful_body(
    tmp_path: Path,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            """
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule impure_map)
              (export orchestrate)
              (defworkflow child ((value Int)) -> Int value)
              (defworkflow orchestrate ((xs List[Int])) -> List[Int]
                (list/map ((item xs))
                  (call child :value item))))
            """,
        )
        == "list_map_body_effect_forbidden"
    )


@pytest.mark.parametrize(
    "element_type",
    (
        "Optional[String]",
        "Map[String,Int]",
    ),
)
def test_frontend_pure_map_accepts_whole_list_transportable_nested_shapes(
    tmp_path: Path,
    element_type: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule nested_map)
          (export orchestrate)
          (defun map-items
            ((items List[{element_type}]))
            -> List[{element_type}]
            (list/map ((item items)) item))
          (defworkflow orchestrate () -> Int 1))
        """,
    )

    assert result.validated_bundle.surface.name == "nested_map::orchestrate"


@pytest.mark.parametrize(
    "element_definition",
    (
        "(defrecord Item (value Int))",
        "(defunion Item (READY (value Int)))",
    ),
)
def test_frontend_pure_map_rejects_record_and_union_collection_elements(
    tmp_path: Path,
    element_definition: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule unsupported_map_contract)
              (export orchestrate)
              {element_definition}
              (defun map-items ((items List[Item])) -> List[Item]
                (list/map ((item items)) item))
              (defworkflow orchestrate () -> Int 1))
            """,
        )
        == "list_collection_contract_unsupported"
    )


@pytest.mark.parametrize(
    ("path_type", "expected_under"),
    (
        ("Path.state-root", "state"),
        ("Path.artifact-root", "artifacts"),
        ("LocalReport", "artifacts/reports"),
    ),
)
def test_frontend_path_join_under_resolves_exact_prelude_and_local_family(
    tmp_path: Path,
    path_type: str,
    expected_under: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule path_join)
          (export orchestrate)
          (defpath LocalReport
            :kind relpath
            :under "artifacts/reports"
            :must-exist true)
          (defworkflow orchestrate ((child String)) -> {path_type}
            (path/join-under {path_type} child)))
        """,
    )

    payload = _projection_payload(result)["payload"]
    assert payload["pure_expr_schema_version"] == 2
    assert payload["expr"]["kind"] == "path_join_under"
    assert payload["expr"]["path_type"]["under"] == expected_under
    assert payload["expr"]["path_type"]["name"].endswith(path_type)
    if path_type == "LocalReport":
        assert payload["expr"]["path_type"]["must_exist_target"] is True


def test_frontend_path_join_under_resolves_imported_family(
    tmp_path: Path,
) -> None:
    package = tmp_path / "paths"
    package.mkdir()
    (package / "types.orc").write_text(
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule paths/types)
          (export ImportedReport)
          (defpath ImportedReport
            :kind relpath
            :under "artifacts/imported"
            :must-exist false))
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule paths/entry)
          (import paths/types :only (ImportedReport))
          (export orchestrate)
          (defworkflow orchestrate ((child String)) -> ImportedReport
            (path/join-under ImportedReport child)))
        """,
        filename="paths/entry.orc",
    )

    descriptor = _projection_payload(result)["payload"]["expr"]["path_type"]
    assert descriptor["name"] == "paths/types::ImportedReport"
    assert descriptor["under"] == "artifacts/imported"


@pytest.mark.parametrize(
    ("path_type", "child", "expected_code"),
    (
        ("String", '"child.md"', "path_join_under_type_invalid"),
        ("Path.state-root", "1", "pure_expr_operand_type_mismatch"),
        ("MalformedRoot", '"child.md"', "path_join_under_root_invalid"),
        ("Path.state-root", '""', "path_join_under_child_invalid"),
        ("Path.state-root", '"/absolute.md"', "path_join_under_escape"),
        ("Path.state-root", '"../escape.md"', "path_join_under_escape"),
    ),
)
def test_frontend_path_join_under_preserves_exact_refusal_families(
    tmp_path: Path,
    path_type: str,
    child: str,
    expected_code: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule invalid_path_join)
              (export orchestrate)
              (defpath MalformedRoot
                :kind relpath
                :under "."
                :must-exist false)
              (defworkflow orchestrate () -> {path_type}
                (path/join-under {path_type} {child})))
            """,
        )
        == expected_code
    )


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


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_217_list_traversal_heads_are_macro_bindable(
    tmp_path: Path,
    head: str,
) -> None:
    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy_list_traversal_macro)
          (export orchestrate)
          (defmacro {head} (value) value)
          (defworkflow orchestrate () -> Int
            ({head} 1)))
        """,
    )

    assert (
        result.validated_bundle.surface.name
        == "legacy_list_traversal_macro::orchestrate"
    )


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_217_receiver_imports_and_expands_legacy_list_macro(
    tmp_path: Path,
    head: str,
) -> None:
    _write_legacy_list_traversal_macro(tmp_path, head=head)

    result = _build_source(
        tmp_path,
        f"""
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.17")
          (defmodule legacy_macro_receiver)
          (import legacy/list-macros :only ({head}))
          (export orchestrate)
          (defworkflow orchestrate () -> Int
            ({head} 1)))
        """,
    )

    assert (
        result.validated_bundle.surface.name
        == "legacy_macro_receiver::orchestrate"
    )


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_218_receiver_rejects_imported_legacy_list_macro(
    tmp_path: Path,
    head: str,
) -> None:
    _write_legacy_list_traversal_macro(tmp_path, head=head)

    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule current_macro_receiver)
              (import legacy/list-macros :only ({head}))
              (export orchestrate)
              (defworkflow orchestrate () -> Int
                ({head} 1)))
            """,
        )
        == "macro_reserved_name"
    )


def test_target_218_local_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    result = _build_source(
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

    expression = _projection_payload(result)["payload"]["expr"]
    binder_name = expression["binder"]["name"]
    assert binder_name == "%macro__map-plus-one__m0001__item"
    assert binder_name != "item"
    assert expression["body"]["args"][0] == {
        "kind": "binding",
        "name": binder_name,
    }


def test_target_218_imported_macro_hygienically_introduces_list_map_binder(
    tmp_path: Path,
) -> None:
    _write_list_map_template_macro(tmp_path)

    result = _build_source(
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

    expression = _projection_payload(result)["payload"]["expr"]
    binder_name = expression["binder"]["name"]
    assert binder_name == "%macro__map-plus-one__m0001__item"
    assert binder_name != "item"
    assert expression["body"]["args"][0] == {
        "kind": "binding",
        "name": binder_name,
    }


def test_target_217_user_macro_list_map_head_keeps_generic_hygiene(
    tmp_path: Path,
) -> None:
    result = _build_source(
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

    expression = _projection_payload(result)["payload"]["expr"]
    assert expression["kind"] == "op"
    assert expression["operator"] == "+"
    assert expression["args"][0] == {
        "kind": "binding",
        "name": "item",
    }


@pytest.mark.parametrize("head", _LIST_TRAVERSAL_AUTHORED_HEADS)
def test_target_218_list_traversal_heads_remain_macro_reserved(
    tmp_path: Path,
    head: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.18")
              (defmodule owned_list_traversal_macro)
              (export orchestrate)
              (defmacro {head} (value) value)
              (defworkflow orchestrate () -> Int
                ({head} 1)))
            """,
        )
        == "macro_reserved_name"
    )


@pytest.mark.parametrize(
    ("body", "params", "return_type"),
    (
        ("(list 1)", "()", "List[Int]"),
        (
            "(list/map ((item xs)) item)",
            "((xs List[Int]))",
            "List[Int]",
        ),
        (
            '(path/join-under Path.state-root "child")',
            "()",
            "Path.state-root",
        ),
        ("(list/empty? xs)", "((xs List[Int]))", "Bool"),
        ("(list/head xs)", "((xs List[Int]))", "Optional[Int]"),
        ("(list/rest xs)", "((xs List[Int]))", "List[Int]"),
        ("(list/append xs 1)", "((xs List[Int]))", "List[Int]"),
        ("(list/length xs)", "((xs List[Int]))", "Int"),
    ),
)
def test_every_new_list_surface_is_rejected_below_target_218(
    tmp_path: Path,
    body: str,
    params: str,
    return_type: str,
) -> None:
    assert (
        _diagnostic_code_for_source(
            tmp_path,
            f"""
            (workflow-lisp
              (:language "0.1")
              (:target-dsl "2.17")
              (defmodule target_gate)
              (export orchestrate)
              (defworkflow orchestrate {params} -> {return_type}
                {body}))
            """,
        )
        == "list_traversal_target_dsl_unsupported"
    )


def test_schema2_list_frontend_stays_inside_existing_ir_node_families(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_ir_shape)
          (export orchestrate)
          (defworkflow orchestrate ((xs List[Int])) -> List[Int]
            (list/map ((item xs)) (+ item 1))))
        """,
    )

    executable_ir = json.loads(
        result.artifact_paths["executable_ir"].read_text(encoding="utf-8")
    )
    core_ast = json.loads(
        result.artifact_paths["core_workflow_ast"].read_text(encoding="utf-8")
    )
    assert executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert core_ast["schema_version"] == "core_workflow_ast.v1"
    projection = _projection_payload(result)
    assert projection["payload"]["pure_expr_schema_version"] == 2
    assert all(
        step.pure_projection is not None
        for step in result.validated_bundle.surface.steps
    )


def test_list_values_route_through_wcc_as_values_without_new_nodes(
    tmp_path: Path,
) -> None:
    result = _build_source(
        tmp_path,
        """
        (workflow-lisp
          (:language "0.1")
          (:target-dsl "2.18")
          (defmodule list_wcc_routes)
          (export orchestrate)
          (defworkflow orchestrate () -> List[Int]
            (list/map ((item (list 1 2))) item)))
        """,
        lowering_route="wcc_m4",
    )

    payload = _projection_payload(result)["payload"]
    assert payload["pure_expr_schema_version"] == 2
    assert payload["expr"]["kind"] == "list_map"
