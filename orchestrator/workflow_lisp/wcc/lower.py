"""Lower normalized WCC M1 bodies back to the current lowered workflow shape."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from ..expressions import FieldAccessExpr, LiteralExpr, NameExpr, RecordExpr, UnionVariantExpr
from ..lowering import LoweredWorkflow, lower_workflow_definitions
from ..spans import SourceSpan
from ..type_env import FrontendTypeEnvironment, TypeRef
from ..typecheck_context import TypedExpr
from ..workflows import (
    CommandBoundaryEnvironment,
    ExternEnvironment,
    TypedWorkflowDef,
    WorkflowCatalog,
)
from ..procedures import ProcedureCatalog, TypedProcedureDef
from .anf import normalize_wcc_body_to_anf
from .elaborate import elaborate_typed_workflow
from .model import (
    WccBody,
    WccFieldAccessAtom,
    WccHalt,
    WccInject,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccRecordAtom,
    WccValue,
)


def lower_wcc_m1_workflow_definitions(
    typed_workflows: tuple[TypedWorkflowDef, ...],
    *,
    typed_procedures: tuple[TypedProcedureDef, ...],
    procedure_catalog: ProcedureCatalog,
    workflow_path: Path,
    workflow_catalog: WorkflowCatalog,
    imported_workflow_bundles: Mapping[str, object],
    extern_environment: ExternEnvironment,
    command_boundary_environment: CommandBoundaryEnvironment,
    type_env: FrontendTypeEnvironment,
) -> tuple[LoweredWorkflow, ...]:
    """Lower pure-subset workflows through WCC M1, then reuse legacy lowering."""

    rewritten = tuple(
        _rewrite_typed_workflow_for_legacy_lowering(
            workflow,
            type_env=type_env,
        )
        for workflow in typed_workflows
    )
    return lower_workflow_definitions(
        rewritten,
        typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
        workflow_path=workflow_path,
        workflow_catalog=workflow_catalog,
        imported_workflow_bundles=imported_workflow_bundles,
        extern_environment=extern_environment,
        command_boundary_environment=command_boundary_environment,
        type_env=type_env,
    )


def _rewrite_typed_workflow_for_legacy_lowering(
    typed_workflow: TypedWorkflowDef,
    *,
    type_env: FrontendTypeEnvironment,
) -> TypedWorkflowDef:
    normalized_body = normalize_wcc_body_to_anf(
        elaborate_typed_workflow(
            typed_workflow,
            type_env=type_env,
        )
    )
    lowered_expr = _inline_expr_from_wcc_body(normalized_body)
    rewritten_body = TypedExpr(
        expr=lowered_expr,
        type_ref=typed_workflow.typed_body.type_ref,
        span=typed_workflow.typed_body.span,
        form_path=typed_workflow.typed_body.form_path,
        effect_summary=typed_workflow.typed_body.effect_summary,
    )
    return replace(typed_workflow, typed_body=rewritten_body)


def _inline_expr_from_wcc_body(body: WccBody):
    env: dict[str, object] = {}
    current = body
    while isinstance(current, WccLet):
        env[current.bound_name] = _inline_expr_from_wcc_value(current.bound_value, env)
        current = current.body
    return _inline_expr_from_wcc_value(current.result, env)


def _inline_expr_from_wcc_value(value: WccValue, env: Mapping[str, object]):
    if isinstance(value, WccLiteralAtom):
        return LiteralExpr(
            value=value.value,
            literal_kind=value.literal_kind,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccNameAtom):
        resolved = env.get(value.name)
        if resolved is not None:
            return resolved
        return NameExpr(
            name=value.name,
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccFieldAccessAtom):
        base_expr = _inline_expr_from_wcc_value(value.base, env)
        if isinstance(base_expr, NameExpr):
            return FieldAccessExpr(
                base=base_expr,
                fields=value.fields,
                span=value.metadata.source_span,
                form_path=value.metadata.form_path,
                expansion_stack=value.metadata.expansion_stack,
            )
        resolved = _resolve_expr_field_value(base_expr, value.fields)
        if resolved is not None:
            return resolved
        raise TypeError(f"unsupported WCC field-access base during lowering: {type(base_expr).__name__}")
    if isinstance(value, WccRecordAtom):
        return RecordExpr(
            type_name=value.type_name,
            fields=tuple(
                (field_name, _inline_expr_from_wcc_value(field_value, env))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    if isinstance(value, WccInject):
        return UnionVariantExpr(
            type_name=value.union_name,
            variant_name=value.variant_name,
            fields=tuple(
                (field_name, _inline_expr_from_wcc_value(field_value, env))
                for field_name, field_value in value.fields
            ),
            span=value.metadata.source_span,
            form_path=value.metadata.form_path,
            expansion_stack=value.metadata.expansion_stack,
        )
    raise TypeError(f"unsupported WCC M1 lowering value: {type(value).__name__}")


def _resolve_expr_field_value(value, field_path: tuple[str, ...]):
    current = value
    for field_name in field_path:
        if isinstance(current, RecordExpr):
            current = _record_field_value(current, field_name)
            continue
        if isinstance(current, UnionVariantExpr):
            current = _union_field_value(current, field_name)
            continue
        return None
    return current


def _record_field_value(record_expr: RecordExpr, field_name: str):
    for current_name, current_value in record_expr.fields:
        if current_name == field_name:
            return current_value
    return None


def _union_field_value(union_expr: UnionVariantExpr, field_name: str):
    for current_name, current_value in union_expr.fields:
        if current_name == field_name:
            return current_value
    return None
