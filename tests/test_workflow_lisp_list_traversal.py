from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import build_syntax_module


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
