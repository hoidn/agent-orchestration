"""Dispatch owner for recursive control-flow lowering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..conditionals import classify_condition_expr, render_condition_predicate
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    PureOpExpr,
    ProcRefLiteralExpr,
    ProcedureCallExpr,
    ProduceOneOfExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    RecordExpr,
    RecordUpdateExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
)
from ..procedure_refs import ResolvedProcRefValue
from ..type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from . import core as lowering_core
from .context import (
    _context_with_local_type_binding,
    _copy_context_with_step_prefix,
    _LoweringContext,
    _NormalizedBindingResult,
    _TerminalResult,
)
from .effects import _lower_provider_result
from .origins import LoweringOrigin, _record_step_origin
from .pure_projection import (
    is_pure_projection_expr,
    lower_pure_projection_step,
    output_contracts_for_boundary_type,
)
from .values import (
    _build_output_step_local_value,
    _resolve_inline_expr_value,
    attach_provider_bundle_identity,
)


_INTRINSIC_FORM_LOWERING_COUNTS: dict[str, int] = {}


def record_intrinsic_form_lowering(form_name: str) -> None:
    """Record one compatibility-lane intrinsic lowering hit for test evidence."""

    _INTRINSIC_FORM_LOWERING_COUNTS[form_name] = _INTRINSIC_FORM_LOWERING_COUNTS.get(form_name, 0) + 1


def intrinsic_form_lowering_counts() -> dict[str, int]:
    """Return a snapshot of intrinsic compatibility-lane lowering counts."""

    return dict(_INTRINSIC_FORM_LOWERING_COUNTS)


def reset_intrinsic_form_lowering_counts() -> None:
    """Clear intrinsic compatibility-lane lowering counts."""

    _INTRINSIC_FORM_LOWERING_COUNTS.clear()


def _compile_error(*args, **kwargs):
    return lowering_core._compile_error(*args, **kwargs)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _lower_composed_with_phase(*args, **kwargs):
    return lowering_core._lower_composed_with_phase(*args, **kwargs)


def _output_contracts_for_type(*args, **kwargs):
    return lowering_core._output_contracts_for_type(*args, **kwargs)


def _lower_conditional_branch_expr(*args, **kwargs):
    return lowering_core._lower_conditional_branch_expr(*args, **kwargs)


def _binding_type_for_expr(*args, **kwargs):
    return lowering_core._binding_type_for_expr(*args, **kwargs)


def _infer_inline_binding_type(*args, **kwargs):
    return lowering_core._infer_inline_binding_type(*args, **kwargs)


def _resolved_proc_ref_value(*args, **kwargs):
    return lowering_core._resolved_proc_ref_value(*args, **kwargs)


def _inline_output_refs_for_expr(*args, **kwargs):
    return lowering_core._inline_output_refs_for_expr(*args, **kwargs)


def _lower_command_result(*args, **kwargs):
    return lowering_core._lower_command_result(*args, **kwargs)


def _lower_with_phase(*args, **kwargs):
    return lowering_core._lower_with_phase(*args, **kwargs)


def _lower_run_provider_phase(*args, **kwargs):
    return lowering_core._lower_run_provider_phase(*args, **kwargs)


def _lower_produce_one_of(*args, **kwargs):
    return lowering_core._lower_produce_one_of(*args, **kwargs)


def _lower_resume_or_start(*args, **kwargs):
    return lowering_core._lower_resume_or_start(*args, **kwargs)


def _lower_resource_transition(*args, **kwargs):
    return lowering_core._lower_resource_transition(*args, **kwargs)


def _lower_finalize_selected_item(*args, **kwargs):
    record_intrinsic_form_lowering("finalize-selected-item")
    return lowering_core._lower_finalize_selected_item(*args, **kwargs)


def _lower_backlog_drain(*args, **kwargs):
    record_intrinsic_form_lowering("backlog-drain")
    return lowering_core._lower_backlog_drain(*args, **kwargs)


def _lower_call_expr(*args, **kwargs):
    return lowering_core._lower_call_expr(*args, **kwargs)


def _lower_record_expr(*args, **kwargs):
    return lowering_core._lower_record_expr(*args, **kwargs)


def _lower_union_variant_expr(*args, **kwargs):
    return lowering_core._lower_union_variant_expr(*args, **kwargs)


def _lower_expression(*args, **kwargs):
    return _control_lower_expression_impl(*args, **kwargs)


def _lower_let_star(*args, **kwargs):
    return _control_lower_let_star_impl(*args, **kwargs)


def _lower_if_expr(*args, **kwargs):
    return _control_lower_if_expr_impl(*args, **kwargs)


def _is_inline_let_binding_expr(*args, **kwargs):
    return _control_is_inline_let_binding_expr_impl(*args, **kwargs)


def _control_lower_expression_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    # schema1_compatibility: retained legacy direct lowerers for explicit schema-1 builds only.
    if isinstance(expr, CommandResultExpr):
        return _lower_command_result(typed_expr, context=context, local_values=local_values)
    # schema1_compatibility: retained legacy direct lowerers for explicit schema-1 builds only.
    if isinstance(expr, ProviderResultExpr):
        return _lower_provider_result(
            expr,
            result_type=typed_expr.type_ref,
            context=context,
            local_values=local_values,
        )
    if isinstance(expr, RunProviderPhaseExpr):
        return _lower_run_provider_phase(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ProduceOneOfExpr):
        return _lower_produce_one_of(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ResumeOrStartExpr):
        return _lower_resume_or_start(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ResourceTransitionExpr):
        return _lower_resource_transition(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, FinalizeSelectedItemExpr):
        return _lower_finalize_selected_item(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, BacklogDrainExpr):
        return _lower_backlog_drain(typed_expr, context=context, local_values=local_values)
    # schema1_compatibility: covered loops lower through WCC for promoted schema-2 compiles.
    if isinstance(expr, LoopRecurExpr):
        from .control_loops import _lower_loop_recur

        return _lower_loop_recur(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, CallExpr):
        return _lower_call_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, ProcedureCallExpr):
        from .procedures import _lower_procedure_call_expr

        return _lower_procedure_call_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, UnionVariantExpr):
        return _lower_union_variant_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, RecordExpr):
        return _lower_record_expr(typed_expr, context=context, local_values=local_values)
    # schema1_compatibility: covered matches lower through WCC for promoted schema-2 compiles.
    if isinstance(expr, MatchExpr):
        from .control_match import _lower_binding_match_expr

        return _lower_binding_match_expr(
            expr,
            result_type=typed_expr.type_ref,
            context=context,
            local_values=local_values,
            step_name_prefix=context.step_name_prefix,
        )
    if isinstance(expr, LetStarExpr):
        return _lower_let_star(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, IfExpr):
        return _lower_if_expr(typed_expr, context=context, local_values=local_values)
    if isinstance(expr, WithPhaseExpr):
        return _lower_with_phase(typed_expr, context=context, local_values=local_values)
    raise _compile_error(
        code="workflow_return_not_exportable",
        message=f"workflow `{context.workflow_name}` cannot lower expression `{type(expr).__name__}` in Stage 3",
        span=typed_expr.span,
        form_path=typed_expr.form_path,
    )


def _control_lower_let_star_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    expr = typed_expr.expr
    assert isinstance(expr, LetStarExpr)
    binding_name, binding_expr = expr.bindings[0]
    body_expr: Any = expr.body
    if len(expr.bindings) > 1:
        body_expr = LetStarExpr(
            bindings=expr.bindings[1:],
            body=expr.body,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    normalized_binding = _normalize_let_binding(
        binding_name,
        binding_expr,
        context=context,
        local_values=local_values,
        step_name_prefix=f"{context.step_name_prefix}__{binding_name}",
    )
    local_bindings = dict(local_values)
    if normalized_binding.local_value is not None:
        local_bindings[binding_name] = normalized_binding.local_value
    body_context = _context_with_local_type_binding(
        context,
        binding_name=binding_name,
        binding_type=normalized_binding.binding_type,
    )
    output_refs = _inline_output_refs_for_expr(
        body_expr,
        type_ref=typed_expr.type_ref,
        local_values=local_bindings,
        context=body_context,
    )
    if output_refs is not None:
        resolved_body_value = _resolve_inline_expr_value(body_expr, local_values=local_bindings)
        returned_union_type_name = (
            resolved_body_value.get("__lowering_returned_union_type")
            if isinstance(resolved_body_value, Mapping)
            else None
        )
        lowered_steps, terminal = [], _TerminalResult(
            step_name=context.step_name_prefix,
            step_id=_normalize_generated_step_id(context.step_name_prefix),
            output_refs=output_refs,
            output_kind="projection",
            hidden_inputs={},
            returned_union_type_name=returned_union_type_name,
        )
    else:
        lowered_steps, terminal = _lower_expression(
            TypedExpr(
                expr=body_expr,
                type_ref=typed_expr.type_ref,
                span=body_expr.span,
                form_path=body_expr.form_path,
            ),
            context=body_context,
            local_values=local_bindings,
        )
    hidden_inputs: dict[str, LoweringOrigin] = {}
    if normalized_binding.terminal is not None:
        hidden_inputs.update(normalized_binding.terminal.hidden_inputs)
    hidden_inputs.update(terminal.hidden_inputs)
    return [*normalized_binding.emitted_steps, *lowered_steps], _TerminalResult(
        step_name=terminal.step_name,
        step_id=terminal.step_id,
        output_refs=terminal.output_refs,
        output_kind=terminal.output_kind,
        hidden_inputs=hidden_inputs,
        returned_union_type_name=terminal.returned_union_type_name,
        returned_union_variant_name=terminal.returned_union_variant_name,
    )


def _control_is_inline_let_binding_expr_impl(expr: Any) -> bool:
    return isinstance(
        expr,
        (
            NameExpr,
            FieldAccessExpr,
            PhaseTargetExpr,
            LiteralExpr,
            RecordExpr,
            RecordUpdateExpr,
            LoopStateSeedExpr,
            LoopStateUpdateExpr,
            UnionVariantExpr,
            ProviderBundlePathExpr,
            ProcRefLiteralExpr,
            BindProcExpr,
            PureOpExpr,
        ),
    )


def _normalize_let_binding(
    binding_name: str,
    binding_expr: Any,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str,
) -> _NormalizedBindingResult:
    if _is_inline_let_binding_expr(binding_expr):
        resolved_binding = _resolve_inline_expr_value(
            binding_expr,
            local_values=local_values,
        )
        if isinstance(binding_expr, (ProcRefLiteralExpr, BindProcExpr)):
            resolved_binding = _resolved_proc_ref_value(
                resolved_binding,
                context=context,
                local_values=local_values,
            )
        binding_type = (
            resolved_binding.residual_type_ref
            if isinstance(resolved_binding, ResolvedProcRefValue)
            else _infer_inline_binding_type(binding_expr, context=context)
        )
        return _NormalizedBindingResult(
            binding_type=binding_type,
            emitted_steps=[],
            terminal=None,
            local_value=resolved_binding,
        )

    binding_type = _binding_type_for_expr(binding_expr, context=context)
    binding_steps, binding_terminal = _lower_effectful_binding_expr(
        binding_expr,
        binding_type=binding_type,
        context=context,
        local_values=local_values,
        step_name_prefix=step_name_prefix,
    )
    local_value = _binding_local_value_from_terminal(
        binding_expr,
        binding_type=binding_type,
        binding_terminal=binding_terminal,
    )
    if binding_terminal is not None and context.composition_scope_kind == "match_case":
        local_value = _match_case_scope_value(local_value)
    return _NormalizedBindingResult(
        binding_type=binding_type,
        emitted_steps=binding_steps,
        terminal=binding_terminal,
        local_value=local_value,
    )


def _lower_effectful_binding_expr(
    expr: Any,
    *,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    if isinstance(expr, WithPhaseExpr):
        return _lower_composed_with_phase(
            expr,
            result_type=binding_type,
            context=context,
            local_values=local_values,
            step_name_prefix=step_name_prefix,
        )
    # emitter: phase composition reuses the provider-result owner emitter.
    if isinstance(expr, ProviderResultExpr):
        return _lower_provider_result(
            expr,
            result_type=binding_type,
            context=context,
            local_values=local_values,
            step_name=step_name_prefix,
        )
    # schema1_compatibility: retained for explicit legacy composed match lowering.
    if isinstance(expr, MatchExpr):
        from .control_match import _lower_binding_match_expr

        return _lower_binding_match_expr(
            expr,
            result_type=binding_type,
            context=context,
            local_values=local_values,
            step_name_prefix=step_name_prefix,
        )
    pure_projection_candidate = _pure_projection_binding_candidate(
        expr,
        local_values=local_values,
    )
    if pure_projection_candidate is not None:
        return _lower_pure_projection_binding_expr(
            pure_projection_candidate,
            source_expr=expr,
            binding_name=step_name_prefix.rsplit("__", 1)[-1],
            binding_type=binding_type,
            context=context,
            local_values=local_values,
            step_name_prefix=step_name_prefix,
        )
    return _lower_expression(
        TypedExpr(
            expr=expr,
            type_ref=binding_type,
            span=expr.span,
            form_path=expr.form_path,
        ),
        context=_copy_context_with_step_prefix(
            context,
            step_name_prefix=step_name_prefix,
        ),
        local_values=local_values,
    )


def _pure_projection_binding_candidate(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
) -> Any | None:
    candidate = _resolve_inline_expr_value(expr, local_values=local_values)
    if candidate is None or isinstance(candidate, (str, Mapping)):
        return None
    if is_pure_projection_expr(candidate):
        return candidate
    return None


def _lower_pure_projection_binding_expr(
    expr: Any,
    *,
    source_expr: Any,
    binding_name: str,
    binding_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    lowered = lower_pure_projection_step(
        expr,
        result_type=binding_type,
        context=context,
        local_values=local_values,
        step_name=step_name_prefix,
        step_id=_normalize_generated_step_id(step_name_prefix),
        source_expr=source_expr,
        stable_target="binding_projection",
        output_contracts=output_contracts_for_boundary_type(
            binding_type,
            generated_name=binding_name,
            span=source_expr.span,
            form_path=source_expr.form_path,
        ),
    )
    return [lowered.step], _TerminalResult(
        step_name=step_name_prefix,
        step_id=_normalize_generated_step_id(step_name_prefix),
        output_refs=lowered.output_refs,
        output_kind="projection",
        hidden_inputs={},
        returned_union_type_name=(
            binding_type.name
            if isinstance(binding_type, UnionTypeRef)
            else None
        ),
    )


def _binding_local_value_from_terminal(
    expr: Any,
    *,
    binding_type: TypeRef,
    binding_terminal: _TerminalResult,
) -> Any | None:
    if isinstance(binding_type, (RecordTypeRef, UnionTypeRef)):
        local_value = _build_output_step_local_value(binding_terminal.output_refs)
        if (
            isinstance(binding_type, UnionTypeRef)
            and binding_terminal.returned_union_type_name is not None
            and binding_terminal.returned_union_variant_name is None
        ):
            local_value["__lowering_returned_union_type"] = binding_terminal.returned_union_type_name
        # schema1_compatibility: legacy provider-result bindings carry provider bundle identity.
        if isinstance(expr, ProviderResultExpr) and binding_terminal.provider_bundle_identity is not None:
            return attach_provider_bundle_identity(
                local_value,
                provider_bundle_identity=binding_terminal.provider_bundle_identity,
            )
        return local_value
    if isinstance(binding_type, (PathTypeRef, PrimitiveTypeRef)) and "return" in binding_terminal.output_refs:
        return binding_terminal.output_refs["return"]
    if isinstance(expr, LiteralExpr):
        return expr
    return None


def _control_lower_if_expr_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from .control_match import _build_match_projection_anchor_step

    expr = typed_expr.expr
    assert isinstance(expr, IfExpr)
    step_name = context.step_name_prefix
    step_id = _normalize_generated_step_id(step_name)
    condition = render_condition_predicate(
        classify_condition_expr(expr.condition_expr, type_ref=PrimitiveTypeRef(name="Bool")),
        local_values=local_values,
    )
    output_contracts = _output_contracts_for_type(
        typed_expr.type_ref,
        context=context,
        span=expr.span,
        form_path=expr.form_path,
    )
    then_steps, then_terminal = _lower_conditional_branch_expr(
        expr.then_expr,
        result_type=typed_expr.type_ref,
        step_name=f"{step_name}__then",
        context=context,
        local_values=local_values,
    )
    else_steps, else_terminal = _lower_conditional_branch_expr(
        expr.else_expr,
        result_type=typed_expr.type_ref,
        step_name=f"{step_name}__else",
        context=context,
        local_values=local_values,
    )
    then_outputs = lowering_core._conditional_case_outputs(
        then_terminal,
        output_contracts=output_contracts,
        span=expr.then_expr.span,
        form_path=expr.then_expr.form_path,
    )
    else_outputs = lowering_core._conditional_case_outputs(
        else_terminal,
        output_contracts=output_contracts,
        span=expr.else_expr.span,
        form_path=expr.else_expr.form_path,
    )
    if not then_steps:
        then_steps = [
            _build_match_projection_anchor_step(
                match_step_name=step_name,
                variant_name="then",
                case_outputs=then_outputs,
                context=context,
                span=expr.then_expr.span,
            )
        ]
    if not else_steps:
        else_steps = [
            _build_match_projection_anchor_step(
                match_step_name=step_name,
                variant_name="else",
                case_outputs=else_outputs,
                context=context,
                span=expr.else_expr.span,
            )
        ]
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    return [
        {
            "name": step_name,
            "id": step_id,
            "if": condition,
            "then": {
                "id": _normalize_generated_step_id(f"{step_name}__then"),
                "outputs": then_outputs,
                "steps": then_steps,
            },
            "else": {
                "id": _normalize_generated_step_id(f"{step_name}__else"),
                "outputs": else_outputs,
                "steps": else_steps,
            },
        }
    ], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=lowering_core._conditional_output_refs(
            step_name=step_name,
            output_contracts=output_contracts,
            result_type=typed_expr.type_ref,
        ),
        output_kind="if",
        hidden_inputs={**then_terminal.hidden_inputs, **else_terminal.hidden_inputs},
    )


def _match_case_scope_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("root.steps."):
            return "self.steps." + value.removeprefix("root.steps.")
        return value
    if isinstance(value, Mapping):
        return {name: _match_case_scope_value(item) for name, item in value.items()}
    return value
