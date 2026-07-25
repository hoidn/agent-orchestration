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


@pytest.mark.parametrize("schema_version", (1, 2))
def test_unimplemented_future_nodes_fail_as_schema_mismatches(
    schema_version: int,
) -> None:
    pure_expr = importlib.import_module("orchestrator.workflow.pure_expr")

    with pytest.raises(pure_expr.PureExprEvaluationError) as excinfo:
        pure_expr.validate_pure_expr_payload(
            _future_list_payload(schema_version)
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
