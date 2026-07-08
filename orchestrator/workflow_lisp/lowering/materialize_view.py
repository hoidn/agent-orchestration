"""Lowering helpers for compiler-generated materialize_view steps."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.references import MaterializeViewBindingReference
from orchestrator.workflow.state_layout import GeneratedPathPrivacy
from orchestrator.workflow.view_renderer import VIEW_RENDERER_SCHEMA_VERSION, resolve_view_renderer

from ..contracts import derive_workflow_boundary_fields
from ..expressions import GeneratedRelpathSeedExpr, LiteralExpr, MaterializeViewExpr
from ..type_env import PathTypeRef
from ..typecheck import TypedExpr
from . import core as lowering_core
from .context import _compile_error, _LoweringContext, _TerminalResult
from .generated_paths import allocate_materialized_value_view
from .origins import GeneratedSemanticEffectBinding, _record_step_origin
from .pure_projection import _infer_expr_type, _type_descriptor
from .values import ProjectedPathRef, _resolve_inline_expr_value


MATERIALIZE_VIEW_EFFECT_KIND = "materialize_view"


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def lower_materialize_view_step(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    assert isinstance(expr, MaterializeViewExpr)
    assert isinstance(typed_expr.type_ref, PathTypeRef)

    step_name = f"{context.step_name_prefix}__materialize-view__{_workflow_slug(expr.view_name)}"
    step_id = _normalize_generated_step_id(step_name)
    renderer = resolve_view_renderer(expr.renderer_id, expr.renderer_version)
    value_type = _infer_expr_type(
        expr.value_expr,
        context=context,
        lexical_types={},
    )
    value_document = _materialize_view_value_document(
        expr.value_expr,
        local_values=local_values,
    )
    target_value = _target_path_value(
        expr,
        context=context,
        local_values=local_values,
        file_extension=renderer.file_extension,
    )
    output_contracts = _output_contracts_for_path_type(typed_expr.type_ref, expr=expr)
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    context.generated_semantic_effects.append(
        GeneratedSemanticEffectBinding(
            effect_key=f"{MATERIALIZE_VIEW_EFFECT_KIND}:{step_id}",
            step_id=step_id,
            effect_kind=MATERIALIZE_VIEW_EFFECT_KIND,
            origin=context.step_spans[step_id],
            details={
                "renderer_id": expr.renderer_id,
                "renderer_version": expr.renderer_version,
                "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
                "value_type": _type_descriptor(value_type, type_env=context.type_env),
                "target_path": target_value["surface_value"],
                "target_allocation_id": target_value["allocation_id"],
                "authority_class": "materialized_view",
            },
        )
    )
    step = {
        "name": step_name,
        "id": step_id,
        "materialize_view": {
            "renderer_id": expr.renderer_id,
            "renderer_version": expr.renderer_version,
            "view_renderer_schema_version": VIEW_RENDERER_SCHEMA_VERSION,
            "value_type": _type_descriptor(value_type, type_env=context.type_env),
            "value_document": value_document,
            "target_path": target_value["runtime_value"],
            "target_allocation_id": target_value["allocation_id"],
            "authority_class": "materialized_view",
            "output_contracts": output_contracts,
        },
    }
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs={"return": f"root.steps.{step_name}.artifacts.return"},
        output_kind="step",
        hidden_inputs={},
    )


def _output_contracts_for_path_type(path_type: PathTypeRef, *, expr: MaterializeViewExpr) -> dict[str, dict[str, Any]]:
    fields = derive_workflow_boundary_fields(
        path_type,
        generated_name="return",
        source_path=("return",),
        span=expr.span,
        form_path=expr.form_path,
    )
    return {
        field.generated_name: dict(field.contract_definition)
        for field in fields
    }


def _materialize_view_value_document(expr: Any, *, local_values: Mapping[str, Any]) -> Any:
    resolved = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(resolved, LiteralExpr):
        return resolved.value
    if isinstance(resolved, GeneratedRelpathSeedExpr):
        return resolved.literal_path
    if isinstance(resolved, ProjectedPathRef):
        return MaterializeViewBindingReference(ref=resolved.ref)
    if isinstance(resolved, str):
        return MaterializeViewBindingReference(ref=resolved)
    if isinstance(resolved, Mapping):
        return {
            str(key): _materialize_view_value_document(value, local_values=local_values)
            for key, value in resolved.items()
        }
    if isinstance(resolved, list):
        return [_materialize_view_value_document(item, local_values=local_values) for item in resolved]
    if isinstance(resolved, tuple):
        return [_materialize_view_value_document(item, local_values=local_values) for item in resolved]
    raise _compile_error(
        code="materialize_view_value_type_invalid",
        message="`materialize-view :value` must lower from literals, bound values, or inline records",
        span=expr.span,
        form_path=expr.form_path,
    )


def _target_path_value(
    expr: MaterializeViewExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    file_extension: str,
) -> dict[str, Any]:
    if expr.target_expr is not None:
        resolved = _resolve_inline_expr_value(expr.target_expr, local_values=local_values)
        if isinstance(resolved, LiteralExpr) and isinstance(resolved.value, str):
            return {
                "runtime_value": resolved.value,
                "surface_value": resolved.value,
                "allocation_id": None,
            }
        if isinstance(resolved, GeneratedRelpathSeedExpr):
            return {
                "runtime_value": resolved.literal_path,
                "surface_value": resolved.literal_path,
                "allocation_id": None,
            }
        if isinstance(resolved, ProjectedPathRef):
            return {
                "runtime_value": {"ref": resolved.ref},
                "surface_value": resolved.ref,
                "allocation_id": None,
            }
        if isinstance(resolved, str):
            return {
                "runtime_value": {"ref": resolved},
                "surface_value": resolved,
                "allocation_id": None,
            }
        raise _compile_error(
            code="materialize_view_target_contract_invalid",
            message="`materialize-view :target` must lower from a path literal or existing path binding",
            span=expr.target_expr.span,
            form_path=expr.target_expr.form_path,
        )
    under = typed_path_under(context=context, expr=expr)
    path_template = f"{under}/workflow_lisp_views/{_workflow_slug(context.workflow_name)}/{expr.view_name}{file_extension}"
    allocation = allocate_materialized_value_view(
        context=context,
        source_expr=expr,
        path_template=path_template,
        stable_target=expr.view_name,
        privacy=GeneratedPathPrivacy.PRIVATE_GENERATED,
    )
    return {
        "runtime_value": allocation.concrete_path_template,
        "surface_value": allocation.concrete_path_template,
        "allocation_id": allocation.allocation_id,
    }


def typed_path_under(*, context: _LoweringContext, expr: MaterializeViewExpr) -> str:
    returns_type = context.type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    assert isinstance(returns_type, PathTypeRef)
    return returns_type.definition.under


def _workflow_slug(value: str) -> str:
    return "".join(character if character.isalnum() else "-" for character in value).strip("-") or "workflow"
