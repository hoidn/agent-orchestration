"""Internal lowering-route contracts for Workflow Lisp Stage 3 compilation."""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..effects import EMPTY_EFFECT_SUMMARY
from ..expressions import (
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    NameExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProviderResultExpr,
    RecordExpr,
    UnionVariantExpr,
    WithPhaseExpr,
)
from ..type_env import WorkflowRefTypeRef
from ..procedures import TypedProcedureDef
from ..workflows import TypedWorkflowDef, WorkflowSignature


class LoweringRoute(str, Enum):
    """Compiler-internal Stage 3 lowering routes."""

    LEGACY = "legacy"
    WCC_M1 = "wcc_m1"
    WCC_M2 = "wcc_m2"


DEFAULT_LOWERING_ROUTE = LoweringRoute.LEGACY
_PURE_WCC_M1_EXPR_TYPES = (
    LiteralExpr,
    NameExpr,
    FieldAccessExpr,
    RecordExpr,
    UnionVariantExpr,
    LetStarExpr,
)


def normalize_lowering_route(route: LoweringRoute | str | None) -> LoweringRoute:
    """Resolve the caller-provided route selector to one enum value."""

    if route is None:
        return DEFAULT_LOWERING_ROUTE
    if isinstance(route, LoweringRoute):
        return route
    return LoweringRoute(route)


def validate_wcc_m1_route_supported(typed_workflows: tuple[TypedWorkflowDef, ...]) -> None:
    """Reject typed workflows that fall outside the WCC M1 pure subset."""

    for workflow in typed_workflows:
        if workflow.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise _unsupported_route(
                workflow_name=workflow.definition.name,
                span=workflow.definition.span,
                form_path=workflow.definition.form_path,
                expansion_stack=workflow.definition.expansion_stack,
                message=(
                    "WCC M1 lowering supports only pure value workflows; "
                    f"`{workflow.definition.name}` carries effects"
                ),
            )
        _validate_wcc_m1_expr_supported(workflow.typed_body.expr, workflow_name=workflow.definition.name)


def validate_wcc_m2_route_supported(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    typed_procedures: tuple[TypedProcedureDef, ...],
) -> None:
    """Reject callables outside the bounded WCC M2 preview subset."""

    local_workflow_signatures = {
        workflow.definition.name: workflow.signature for workflow in typed_workflows
    }
    for workflow in typed_workflows:
        _validate_wcc_m2_expr_supported(
            workflow.typed_body.expr,
            workflow_name=workflow.definition.name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=frozenset(
                param_name
                for param_name, type_ref in workflow.signature.params
                if isinstance(type_ref, WorkflowRefTypeRef)
            ),
        )
    for procedure in typed_procedures:
        _validate_wcc_m2_expr_supported(
            procedure.typed_body.expr,
            workflow_name=procedure.definition.name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=frozenset(
                param_name
                for param_name, type_ref in procedure.signature.params
                if isinstance(type_ref, WorkflowRefTypeRef)
            ),
        )


def _validate_wcc_m1_expr_supported(expr, *, workflow_name: str) -> None:
    if isinstance(expr, LetStarExpr):
        for _, binding_expr in expr.bindings:
            _validate_wcc_m1_expr_supported(binding_expr, workflow_name=workflow_name)
        _validate_wcc_m1_expr_supported(expr.body, workflow_name=workflow_name)
        return
    if isinstance(expr, RecordExpr):
        for _, field_expr in expr.fields:
            _validate_wcc_m1_expr_supported(field_expr, workflow_name=workflow_name)
        return
    if isinstance(expr, UnionVariantExpr):
        for _, field_expr in expr.fields:
            _validate_wcc_m1_expr_supported(field_expr, workflow_name=workflow_name)
        return
    if isinstance(expr, FieldAccessExpr):
        _validate_wcc_m1_expr_supported(expr.base, workflow_name=workflow_name)
        return
    if isinstance(expr, _PURE_WCC_M1_EXPR_TYPES[:-1]):
        return
    raise _unsupported_route(
        workflow_name=workflow_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
        message=(
            "WCC M1 lowering supports only the pure value subset; "
            f"`{workflow_name}` uses unsupported `{type(expr).__name__}`"
        ),
    )


def _validate_wcc_m2_expr_supported(
    expr,
    *,
    workflow_name: str,
    local_workflow_signatures: Mapping[str, WorkflowSignature],
    workflow_ref_value_names: frozenset[str],
) -> None:
    if isinstance(expr, WithPhaseExpr):
        _validate_wcc_m2_expr_supported(
            expr.ctx_expr,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        _validate_wcc_m2_expr_supported(
            expr.body,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        return
    if isinstance(expr, LetStarExpr):
        for _, binding_expr in expr.bindings:
            _validate_wcc_m2_expr_supported(
                binding_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        _validate_wcc_m2_expr_supported(
            expr.body,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        return
    if isinstance(expr, RecordExpr):
        for _, field_expr in expr.fields:
            _validate_wcc_m2_expr_supported(
                field_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, UnionVariantExpr):
        for _, field_expr in expr.fields:
            _validate_wcc_m2_expr_supported(
                field_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, FieldAccessExpr):
        _validate_wcc_m2_expr_supported(
            expr.base,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        return
    if isinstance(expr, CommandResultExpr):
        for arg_expr in expr.argv:
            _validate_wcc_m2_expr_supported(
                arg_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, ProviderResultExpr):
        _validate_wcc_m2_expr_supported(
            expr.provider,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        _validate_wcc_m2_expr_supported(
            expr.prompt,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        for arg_expr in expr.inputs:
            _validate_wcc_m2_expr_supported(
                arg_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, CallExpr):
        if expr.callee_name in workflow_ref_value_names:
            raise _unsupported_route(
                workflow_name=workflow_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                message=(
                    "WCC M2 lowering does not support workflow-ref call shapes; "
                    f"`{workflow_name}` calls workflow-ref binding `{expr.callee_name}`"
                ),
            )
        signature = local_workflow_signatures.get(expr.callee_name)
        if signature is None:
            raise _unsupported_route(
                workflow_name=workflow_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                message=(
                    "WCC M2 lowering supports only same-file direct workflow calls; "
                    f"`{workflow_name}` calls non-local workflow `{expr.callee_name}`"
                ),
            )
        if any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in signature.params):
            raise _unsupported_route(
                workflow_name=workflow_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                message=(
                    "WCC M2 lowering does not support workflow-ref call shapes; "
                    f"`{workflow_name}` calls `{expr.callee_name}` which requires WorkflowRef bindings"
                ),
            )
        for _, binding_expr in expr.bindings:
            _validate_wcc_m2_expr_supported(
                binding_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, ProcedureCallExpr):
        for arg_expr in expr.args:
            _validate_wcc_m2_expr_supported(
                arg_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, BindProcExpr):
        _validate_wcc_m2_expr_supported(
            expr.base_expr,
            workflow_name=workflow_name,
            local_workflow_signatures=local_workflow_signatures,
            workflow_ref_value_names=workflow_ref_value_names,
        )
        for binding in expr.bindings:
            _validate_wcc_m2_expr_supported(
                binding.value_expr,
                workflow_name=workflow_name,
                local_workflow_signatures=local_workflow_signatures,
                workflow_ref_value_names=workflow_ref_value_names,
            )
        return
    if isinstance(expr, (LiteralExpr, NameExpr, ProcRefLiteralExpr)):
        return
    raise _unsupported_route(
        workflow_name=workflow_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
        message=(
            "WCC M2 lowering supports only the bounded straight-line subset; "
            f"`{workflow_name}` uses unsupported `{type(expr).__name__}`"
        ),
    )


def _unsupported_route(
    *,
    workflow_name: str,
    span,
    form_path: tuple[str, ...],
    expansion_stack,
    message: str,
) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="wcc_lowering_route_unsupported",
                message=message,
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
                phase="lowering",
            ),
        )
    )
