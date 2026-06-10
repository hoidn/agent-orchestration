"""Loop owner for control-family lowering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ..expressions import (
    ContinueExpr,
    DoneExpr,
    FieldAccessExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    RecordExpr,
    UnionVariantExpr,
)
from ..loops import (
    LOOP_STATUS_ALLOWED,
    LOOP_STATUS_OUTPUT_NAME,
    LoopLoweringPlan,
    LoopValueProjection,
    build_loop_lowering_plan,
    internal_loop_contract,
    projection_relpath_fields,
)
from ..procedures import TypedProcedureDef
from ..type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef, UnionTypeRef
from ..typecheck import TypedExpr
from . import core as lowering_core
from .context import (
    _context_with_local_type_binding,
    _copy_context_with_composition_scope,
    _copy_context_with_iteration_scope,
    _LoweringContext,
    _TerminalResult,
)
from .origins import LoweringOrigin, _origin_from_context_source, _record_step_origin
from .values import (
    _assign_nested_local_value,
    _build_record_step_local_value,
    _inline_expr_field_value,
    _normalize_union_field_path,
    _phase_target_inline_ref,
    _record_expr_value_at_path,
    _resolve_inline_expr_value,
    _resolve_inline_field_value,
    _union_variant_expr_value_at_path,
)


def _compile_error(*args, **kwargs):
    return lowering_core._compile_error(*args, **kwargs)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _render_repeat_until_max_iterations(*args, **kwargs):
    return lowering_core._render_repeat_until_max_iterations(*args, **kwargs)


def _resolve_lowering_expr_type(*args, **kwargs):
    return lowering_core._resolve_lowering_expr_type(*args, **kwargs)


def _materialize_values_step(
    *,
    step_name: str,
    step_id: str,
    values: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": step_name,
        "id": step_id,
        "materialize_artifacts": {
            "values": values,
        },
    }


def _lower_loop_recur(*args, **kwargs):
    return _control_lower_loop_recur_impl(*args, **kwargs)


def _control_lower_loop_recur_impl(
    typed_expr: TypedExpr,
    *,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from .control_match import _binding_terminal_for_inline_match, _build_match_projection_anchor_step

    expr = typed_expr.expr
    assert isinstance(expr, LoopRecurExpr)
    state_type = _resolve_lowering_expr_type(expr.initial_state_expr, context=context)
    if state_type is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`loop/recur :state` must lower from a typed workflow input or prior structured result",
            span=expr.initial_state_expr.span,
            form_path=expr.initial_state_expr.form_path,
        )
    result_type = typed_expr.type_ref
    if not isinstance(result_type, (RecordTypeRef, UnionTypeRef, PathTypeRef, PrimitiveTypeRef)):
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`loop/recur` result type cannot lower through the shared validation seam",
            span=expr.span,
            form_path=expr.form_path,
        )

    plan = build_loop_lowering_plan(
        step_name_prefix=context.step_name_prefix,
        state_type_ref=state_type,
        result_type_ref=result_type,
        span=expr.span,
        form_path=expr.form_path,
    )
    seed_step_id = _normalize_generated_step_id(plan.seed_step_name)
    repeat_step_id = _normalize_generated_step_id(plan.repeat_step_name)
    result_step_id = _normalize_generated_step_id(plan.result_normalization_step_name)
    initial_state_value = _resolve_inline_expr_value(expr.initial_state_expr, local_values=local_values)
    state_optional_relpath_fields = _loop_state_optional_relpath_fields(
        expr.initial_state_expr,
        projection=plan.state_projection,
        local_values=local_values,
        context=context,
    )
    if state_optional_relpath_fields != plan.state_projection.optional_relpath_fields:
        plan = replace(
            plan,
            state_projection=replace(
                plan.state_projection,
                optional_relpath_fields=state_optional_relpath_fields,
            ),
        )
    seed_step = _build_loop_seed_step(
        expr=expr,
        state_type=state_type,
        state_projection=plan.state_projection,
        step_name=plan.seed_step_name,
        step_id=seed_step_id,
        context=context,
        local_values=local_values,
        initial_state_value=initial_state_value,
    )
    _record_step_origin(context, step_name=plan.seed_step_name, step_id=seed_step_id, source=expr)
    current_state_step_name = f"{plan.body_projection_step_name}__state"
    current_state_step_id = _normalize_generated_step_id(current_state_step_name)
    current_state_steps = _build_loop_current_state_steps(
        current_state_step_name=current_state_step_name,
        current_state_step_id=current_state_step_id,
        current_state_projection=plan.state_projection,
        plan=plan,
        expr=expr,
        context=context,
    )
    _record_step_origin(context, step_name=current_state_step_name, step_id=current_state_step_id, source=expr)
    current_state_terminal = _TerminalResult(
        step_name=current_state_step_name,
        step_id=current_state_step_id,
        output_refs={
            field.generated_name: f"self.steps.{current_state_step_name}.artifacts.{field.generated_name}"
            for field in plan.state_projection.flattened_fields
        },
        output_kind="if",
        hidden_inputs={},
    )
    loop_body_context = _context_with_local_type_binding(
        context,
        binding_name=expr.binding_name,
        binding_type=state_type,
    )
    loop_body_context = _copy_context_with_iteration_scope(
        loop_body_context,
        iteration_scope="${loop.index}",
    )
    loop_local_values = dict(local_values)
    loop_local_values[expr.binding_name] = _loop_projection_local_value(
        plan.state_projection,
        current_state_terminal.output_refs,
    )
    body_steps, body_terminal = _lower_loop_body_expr(
        expr.body_expr,
        loop_binding_name=expr.binding_name,
        state_projection=plan.state_projection,
        result_projection=plan.result_projection,
        result_type=result_type,
        on_exhausted_result_expr=expr.on_exhausted_result_expr,
        context=loop_body_context,
        local_values=loop_local_values,
        binding_terminal=_binding_terminal_for_inline_match(loop_local_values[expr.binding_name])
        or _TerminalResult(
            step_name=current_state_step_name,
            step_id=current_state_step_id,
            output_refs=current_state_terminal.output_refs,
            output_kind=current_state_terminal.output_kind,
            hidden_inputs={},
        ),
        body_step_name=plan.body_projection_step_name,
    )

    loop_output_contracts = {
        LOOP_STATUS_OUTPUT_NAME: {
            "kind": "scalar",
            "type": "enum",
            "allowed": list(LOOP_STATUS_ALLOWED),
        }
    }
    loop_output_contracts.update(
        {
            field.generated_name: internal_loop_contract(
                field,
                allow_missing_target_fields=plan.state_projection.optional_relpath_fields,
            )
            for field in plan.state_projection.flattened_fields
        }
    )
    loop_output_contracts.update(
        {
            field.generated_name: internal_loop_contract(
                field,
                allow_missing_target_fields=_loop_result_optional_relpath_fields(plan.result_projection),
            )
            for field in plan.result_projection.flattened_fields
        }
    )
    repeat_step = {
        "name": plan.repeat_step_name,
        "id": repeat_step_id,
        "repeat_until": {
            "id": f"{repeat_step_id}__iteration",
            "max_iterations": _render_repeat_until_max_iterations(
                expr.max_iterations_expr,
                local_values=local_values,
            ),
            "steps": [*current_state_steps, *body_steps],
            "outputs": _loop_repeat_outputs_from_terminal(
                loop_output_contracts=loop_output_contracts,
                terminal=body_terminal,
                span=expr.span,
                form_path=expr.form_path,
            ),
            "condition": {
                "compare": {
                    "left": {"ref": f"self.outputs.{LOOP_STATUS_OUTPUT_NAME}"},
                    "op": "eq",
                    "right": "DONE",
                }
            },
        },
    }
    if expr.on_exhausted_result_expr is not None:
        exhaustion_local_values = dict(local_values)
        exhaustion_local_values[expr.binding_name] = _loop_projection_local_value(
            plan.state_projection,
            {
                field.generated_name: f"root.steps.{plan.repeat_step_name}.artifacts.{field.generated_name}"
                for field in plan.state_projection.flattened_fields
            },
        )
        repeat_step["repeat_until"]["on_exhausted"] = {
            "outputs": _loop_on_exhausted_outputs(
                expr.on_exhausted_result_expr,
                plan=plan,
                result_type=result_type,
                context=context,
                local_values=exhaustion_local_values,
                loop_binding_name=expr.binding_name,
            )
        }
    _record_step_origin(context, step_name=plan.repeat_step_name, step_id=repeat_step_id, source=expr)

    normalized_result_fields = lowering_core.derive_workflow_boundary_fields(
        result_type,
        generated_name="return",
        source_path=("return",),
        span=expr.span,
        form_path=expr.form_path,
    )
    if isinstance(result_type, (RecordTypeRef, PathTypeRef, PrimitiveTypeRef)):
        result_values = [
            {
                "name": field.generated_name,
                "source": {
                    "ref": f"root.steps.{plan.repeat_step_name}.artifacts.{_loop_projection_field_name(plan.result_projection, field.source_path[1:])}"
                },
                "contract": dict(field.contract_definition),
            }
            for field in normalized_result_fields
        ]
        result_step = _materialize_values_step(
            step_name=plan.result_normalization_step_name,
            step_id=result_step_id,
            values=result_values,
        )
        result_terminal = _TerminalResult(
            step_name=plan.result_normalization_step_name,
            step_id=result_step_id,
            output_refs={
                field.generated_name: f"root.steps.{plan.result_normalization_step_name}.artifacts.{field.generated_name}"
                for field in normalized_result_fields
            },
            output_kind="step",
            hidden_inputs={},
        )
    elif isinstance(result_type, UnionTypeRef):
        union_cases: dict[str, Any] = {}
        result_projection_fields = {
            field.generated_name: field
            for field in plan.result_projection.flattened_fields
        }
        allow_missing_result_fields = _loop_result_optional_relpath_fields(plan.result_projection)
        for variant in result_type.definition.variants:
            case_outputs = {
                field.generated_name: {
                    **internal_loop_contract(
                        result_projection_fields[
                            _loop_projection_field_name(plan.result_projection, field.source_path[1:])
                        ],
                        allow_missing_target_fields=allow_missing_result_fields,
                    ),
                    "from": {
                        "ref": _loop_result_case_output_ref(
                            loop_expr=expr,
                            plan=plan,
                            variant_name=variant.name,
                            field_path=field.source_path[1:],
                        )
                        or f"root.steps.{plan.repeat_step_name}.artifacts.{_loop_projection_field_name(plan.result_projection, field.source_path[1:])}"
                    },
                }
                for field in normalized_result_fields
            }
            union_cases[variant.name] = {
                "id": _normalize_generated_step_id(
                    f"{plan.result_normalization_step_name}__{variant.name.lower()}"
                ),
                "outputs": case_outputs,
                "steps": [
                    _build_match_projection_anchor_step(
                        match_step_name=plan.result_normalization_step_name,
                        variant_name=variant.name,
                        case_outputs=case_outputs,
                        context=context,
                        span=expr.span,
                    )
                ],
            }
        result_step = {
            "name": plan.result_normalization_step_name,
            "id": result_step_id,
            "match": {
                "ref": f"root.steps.{plan.repeat_step_name}.artifacts.{_loop_projection_field_name(plan.result_projection, ('variant',))}",
                "cases": union_cases,
            },
        }
        result_terminal = _TerminalResult(
            step_name=plan.result_normalization_step_name,
            step_id=result_step_id,
            output_refs={
                field.generated_name: f"root.steps.{plan.result_normalization_step_name}.artifacts.{field.generated_name}"
                for field in normalized_result_fields
            },
            output_kind="match",
            hidden_inputs={},
        )
    else:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`loop/recur` currently lowers only record and union result types",
            span=expr.span,
            form_path=expr.form_path,
        )
    _record_step_origin(
        context,
        step_name=plan.result_normalization_step_name,
        step_id=result_step_id,
        source=expr,
    )
    _record_loop_on_exhausted_origins(
        context=context,
        loop_expr=expr,
        repeat_step_name=plan.repeat_step_name,
        repeat_step_id=repeat_step_id,
        result_step_name=plan.result_normalization_step_name,
        result_step_id=result_step_id,
        normalized_result_fields=normalized_result_fields,
    )
    return [seed_step, repeat_step, result_step], result_terminal


def _build_loop_current_state_steps(
    *,
    current_state_step_name: str,
    current_state_step_id: str,
    current_state_projection: LoopValueProjection,
    plan: Any,
    expr: LoopRecurExpr,
    context: _LoweringContext,
) -> list[dict[str, Any]]:
    seed_marker_name = f"{current_state_step_name}__seed_marker"
    seed_marker_id = _normalize_generated_step_id(seed_marker_name)
    carried_copy_name = f"{current_state_step_name}__use_carried_state"
    seed_copy_name = f"{current_state_step_name}__use_seed_state"
    carried_copy_id = _normalize_generated_step_id(f"{current_state_step_name}__carry")
    seed_copy_id = _normalize_generated_step_id(f"{current_state_step_name}__seed")
    _record_step_origin(context, step_name=seed_marker_name, step_id=seed_marker_id, source=expr)
    _record_step_origin(context, step_name=carried_copy_name, step_id=carried_copy_id, source=expr)
    _record_step_origin(context, step_name=seed_copy_name, step_id=seed_copy_id, source=expr)
    carried_values = [
        {
            "name": field.generated_name,
            "source": {"ref": f"root.steps.{plan.repeat_step_name}.artifacts.{field.generated_name}"},
            "contract": internal_loop_contract(
                field,
                allow_missing_target_fields=current_state_projection.optional_relpath_fields,
            ),
        }
        for field in current_state_projection.flattened_fields
    ]
    seed_values = [
        {
            "name": field.generated_name,
            "source": {"ref": f"root.steps.{plan.seed_step_name}.artifacts.{field.generated_name}"},
            "contract": internal_loop_contract(
                field,
                allow_missing_target_fields=current_state_projection.optional_relpath_fields,
            ),
        }
        for field in current_state_projection.flattened_fields
    ]
    return [
        {
            "name": seed_marker_name,
            "id": seed_marker_id,
            "when": {"equals": {"left": "${loop.index}", "right": "0"}},
            "materialize_artifacts": {
                "values": [
                    {
                        "name": "seed_iteration",
                        "source": {"literal": "seed"},
                        "contract": {"kind": "scalar", "type": "string"},
                    }
                ]
            },
        },
        {
            "name": current_state_step_name,
            "id": current_state_step_id,
            "if": {
                "compare": {
                    "left": {"ref": f"self.steps.{seed_marker_name}.outcome.class"},
                    "op": "eq",
                    "right": "skipped",
                }
            },
            "then": {
                "id": carried_copy_id,
                "outputs": _loop_case_outputs_from_projection(
                    current_state_projection,
                    source_step_name=carried_copy_name,
                    allow_missing_target_fields=current_state_projection.optional_relpath_fields,
                ),
                "steps": [
                    _materialize_values_step(
                        step_name=carried_copy_name,
                        step_id=carried_copy_id,
                        values=carried_values,
                    )
                ],
            },
            "else": {
                "id": seed_copy_id,
                "outputs": _loop_case_outputs_from_projection(
                    current_state_projection,
                    source_step_name=seed_copy_name,
                    allow_missing_target_fields=current_state_projection.optional_relpath_fields,
                ),
                "steps": [
                    _materialize_values_step(
                        step_name=seed_copy_name,
                        step_id=seed_copy_id,
                        values=seed_values,
                    )
                ],
            },
        },
    ]


def _build_loop_seed_step(
    *,
    expr: LoopRecurExpr,
    state_type: TypeRef,
    state_projection: LoopValueProjection,
    step_name: str,
    step_id: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    initial_state_value: Any,
) -> dict[str, Any]:
    from .control_match import _binding_terminal_for_inline_match

    if not isinstance(state_type, UnionTypeRef):
        return _materialize_values_step(
            step_name=step_name,
            step_id=step_id,
            values=_loop_projection_materialize_values(
                expr.initial_state_expr,
                projection=state_projection,
                local_values=local_values,
                context=context,
                allow_missing_target_fields=state_projection.optional_relpath_fields,
                allow_missing_active_fields=True,
            ),
        )

    binding_terminal = _binding_terminal_for_inline_match(initial_state_value)
    if binding_terminal is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="`loop/recur :state` must lower from an existing structured result or workflow input ref",
            span=expr.initial_state_expr.span,
            form_path=expr.initial_state_expr.form_path,
        )

    cases: dict[str, Any] = {}
    for variant in state_type.definition.variants:
        materialize_name = f"{step_name}__materialize_{variant.name.lower()}"
        materialize_step_id = _normalize_generated_step_id(f"{step_name}__{variant.name.lower()}__materialize")
        _record_step_origin(context, step_name=materialize_name, step_id=materialize_step_id, source=expr)
        cases[variant.name] = {
            "id": _normalize_generated_step_id(f"{step_name}__{variant.name.lower()}"),
            "outputs": _loop_case_outputs_from_projection(
                state_projection,
                source_step_name=materialize_name,
                allow_missing_target_fields=state_projection.optional_relpath_fields,
            ),
            "steps": [
                _materialize_values_step(
                    step_name=materialize_name,
                    step_id=materialize_step_id,
                    values=_loop_projection_materialize_values(
                        expr.initial_state_expr,
                        projection=state_projection,
                        local_values=local_values,
                        context=context,
                        active_variant_name=variant.name,
                        allow_missing_target_fields=state_projection.optional_relpath_fields,
                        allow_missing_active_fields=True,
                    ),
                )
            ],
        }
    return {
        "name": step_name,
        "id": step_id,
        "match": {"ref": binding_terminal.output_refs["return__variant"], "cases": cases},
    }


def _loop_case_outputs_from_projection(
    projection: LoopValueProjection,
    *,
    source_step_name: str,
    allow_missing_target_fields: frozenset[str],
) -> dict[str, Any]:
    return {
        field.generated_name: {
            **internal_loop_contract(
                field,
                allow_missing_target_fields=allow_missing_target_fields,
            ),
            "from": {"ref": f"self.steps.{source_step_name}.artifacts.{field.generated_name}"},
        }
        for field in projection.flattened_fields
    }


def _lower_loop_body_expr(
    expr: Any,
    *,
    loop_binding_name: str,
    state_projection: LoopValueProjection,
    result_projection: LoopValueProjection,
    result_type: TypeRef,
    on_exhausted_result_expr: Any | None,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    binding_terminal: _TerminalResult,
    body_step_name: str,
    active_variant_name: str | None = None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from .control_dispatch import _normalize_let_binding
    from .control_match import _binding_terminal_for_inline_match, _build_match_projection_anchor_step

    if isinstance(expr, LetStarExpr):
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
            step_name_prefix=f"{body_step_name}__{binding_name}",
        )
        loop_local_values = dict(local_values)
        if normalized_binding.local_value is not None:
            loop_local_values[binding_name] = (
                _loop_body_scope_value(normalized_binding.local_value)
                if normalized_binding.terminal is not None
                else normalized_binding.local_value
            )
        body_steps, body_terminal = _lower_loop_body_expr(
            body_expr,
            loop_binding_name=loop_binding_name,
            state_projection=state_projection,
            result_projection=result_projection,
            result_type=result_type,
            on_exhausted_result_expr=on_exhausted_result_expr,
            context=_context_with_local_type_binding(
                context,
                binding_name=binding_name,
                binding_type=normalized_binding.binding_type,
            ),
            local_values=loop_local_values,
            binding_terminal=binding_terminal,
            body_step_name=body_step_name,
            active_variant_name=active_variant_name,
        )
        hidden_inputs: dict[str, LoweringOrigin] = {}
        if normalized_binding.terminal is not None:
            hidden_inputs.update(normalized_binding.terminal.hidden_inputs)
        hidden_inputs.update(body_terminal.hidden_inputs)
        return [*normalized_binding.emitted_steps, *body_steps], _TerminalResult(
            step_name=body_terminal.step_name,
            step_id=body_terminal.step_id,
            output_refs=body_terminal.output_refs,
            output_kind=body_terminal.output_kind,
            hidden_inputs=hidden_inputs,
        )
    if isinstance(expr, MatchExpr):
        if not isinstance(expr.subject, NameExpr):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message="`loop/recur` match bodies must branch on a bound loop value in this Stage 3 slice",
                span=expr.subject.span,
                form_path=expr.subject.form_path,
            )
        match_terminal = binding_terminal
        if expr.subject.name != loop_binding_name:
            subject_terminal = _binding_terminal_for_inline_match(
                _resolve_inline_expr_value(expr.subject, local_values=local_values),
            )
            if subject_terminal is None:
                raise _compile_error(
                    code="workflow_return_not_exportable",
                    message="nested `loop/recur` match subjects must lower from structured local refs",
                    span=expr.subject.span,
                    form_path=expr.subject.form_path,
                )
            match_terminal = subject_terminal
        loop_output_contracts = _loop_output_contracts(
            state_projection=state_projection,
            result_projection=result_projection,
        )
        cases: dict[str, Any] = {}
        subject_type = context.local_type_bindings.get(expr.subject.name)
        for arm in expr.arms:
            arm_local_values = {
                name: _loop_parent_scope_value(value)
                for name, value in local_values.items()
            }
            arm_local_values[arm.binding_name] = _loop_parent_scope_value(local_values.get(expr.subject.name))
            next_loop_binding_name = arm.binding_name if expr.subject.name == loop_binding_name else loop_binding_name
            arm_context = _copy_context_with_composition_scope(
                context,
                scope_id=f"{body_step_name}__{arm.variant_name.lower()}",
                parent_scope_id=context.composition_scope_id,
                scope_kind="match_case",
                owner_step_name=body_step_name,
            )
            if isinstance(subject_type, UnionTypeRef):
                arm_context = _context_with_local_type_binding(
                    arm_context,
                    binding_name=arm.binding_name,
                    binding_type=context.type_env.union_variant(
                        subject_type,
                        arm.variant_name,
                        span=expr.subject.span,
                        form_path=expr.subject.form_path,
                    ),
                )
            arm_steps, arm_terminal = _lower_loop_body_expr(
                arm.body,
                loop_binding_name=next_loop_binding_name,
                state_projection=state_projection,
                result_projection=result_projection,
                result_type=result_type,
                on_exhausted_result_expr=on_exhausted_result_expr,
                context=arm_context,
                local_values=arm_local_values,
                binding_terminal=match_terminal,
                body_step_name=f"{body_step_name}__{arm.variant_name.lower()}",
                active_variant_name=arm.variant_name,
            )
            cases[arm.variant_name] = {
                "id": _normalize_generated_step_id(f"{body_step_name}__{arm.variant_name.lower()}"),
                "outputs": {
                    name: {
                        **dict(definition),
                        "from": {"ref": _loop_case_ref(arm_terminal.output_refs[name])},
                    }
                    for name, definition in loop_output_contracts.items()
                },
                "steps": arm_steps,
            }
        step_id = _normalize_generated_step_id(body_step_name)
        _record_step_origin(context, step_name=body_step_name, step_id=step_id, source=expr)
        return [
            {
                "name": body_step_name,
                "id": step_id,
                "match": {
                    "ref": match_terminal.output_refs["return__variant"],
                    "cases": cases,
                },
            }
        ], _TerminalResult(
            step_name=body_step_name,
            step_id=step_id,
            output_refs={
                name: f"root.steps.{body_step_name}.artifacts.{name}"
                for name in _loop_output_contracts(
                    state_projection=state_projection,
                    result_projection=result_projection,
                )
            },
            output_kind="match",
            hidden_inputs={},
        )
    if isinstance(expr, IfExpr):
        condition = lowering_core.render_condition_predicate(
            lowering_core.classify_condition_expr(expr.condition_expr, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
        branch_local_values = {
            name: _loop_parent_scope_value(value)
            for name, value in local_values.items()
        }
        then_steps, then_terminal = _lower_loop_body_expr(
            expr.then_expr,
            loop_binding_name=loop_binding_name,
            state_projection=state_projection,
            result_projection=result_projection,
            result_type=result_type,
            on_exhausted_result_expr=on_exhausted_result_expr,
            context=context,
            local_values=branch_local_values,
            binding_terminal=binding_terminal,
            body_step_name=f"{body_step_name}__then",
            active_variant_name=active_variant_name,
        )
        else_steps, else_terminal = _lower_loop_body_expr(
            expr.else_expr,
            loop_binding_name=loop_binding_name,
            state_projection=state_projection,
            result_projection=result_projection,
            result_type=result_type,
            on_exhausted_result_expr=on_exhausted_result_expr,
            context=context,
            local_values=branch_local_values,
            binding_terminal=binding_terminal,
            body_step_name=f"{body_step_name}__else",
            active_variant_name=active_variant_name,
        )
        loop_output_contracts = _loop_output_contracts(
            state_projection=state_projection,
            result_projection=result_projection,
        )
        then_outputs = {
            name: {
                **dict(definition),
                "from": {"ref": _loop_case_ref(then_terminal.output_refs[name])},
            }
            for name, definition in loop_output_contracts.items()
        }
        else_outputs = {
            name: {
                **dict(definition),
                "from": {"ref": _loop_case_ref(else_terminal.output_refs[name])},
            }
            for name, definition in loop_output_contracts.items()
        }
        if not then_steps:
            then_steps = [
                _build_match_projection_anchor_step(
                    match_step_name=body_step_name,
                    variant_name="then",
                    case_outputs=then_outputs,
                    context=context,
                    span=expr.then_expr.span,
                )
            ]
        if not else_steps:
            else_steps = [
                _build_match_projection_anchor_step(
                    match_step_name=body_step_name,
                    variant_name="else",
                    case_outputs=else_outputs,
                    context=context,
                    span=expr.else_expr.span,
                )
            ]
        step_id = _normalize_generated_step_id(body_step_name)
        _record_step_origin(context, step_name=body_step_name, step_id=step_id, source=expr)
        return [
            {
                "name": body_step_name,
                "id": step_id,
                "if": condition,
                "then": {
                    "id": _normalize_generated_step_id(f"{body_step_name}__then"),
                    "outputs": then_outputs,
                    "steps": then_steps,
                },
                "else": {
                    "id": _normalize_generated_step_id(f"{body_step_name}__else"),
                    "outputs": else_outputs,
                    "steps": else_steps,
                },
            }
        ], _TerminalResult(
            step_name=body_step_name,
            step_id=step_id,
            output_refs={name: f"root.steps.{body_step_name}.artifacts.{name}" for name in loop_output_contracts},
            output_kind="if",
            hidden_inputs={},
        )
    if isinstance(expr, ContinueExpr):
        return _lower_loop_terminal_expr(
            expr,
            body_step_name=body_step_name,
            status_value="CONTINUE",
            state_expr=expr.state_expr,
            result_expr=None,
            on_exhausted_result_expr=on_exhausted_result_expr,
            binding_terminal=binding_terminal,
            state_projection=state_projection,
            result_projection=result_projection,
            result_type=result_type,
            loop_binding_name=loop_binding_name,
            context=context,
            local_values=local_values,
            active_variant_name=active_variant_name,
        )
    if isinstance(expr, DoneExpr):
        return _lower_loop_terminal_expr(
            expr,
            body_step_name=body_step_name,
            status_value="DONE",
            state_expr=NameExpr(
                name=loop_binding_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=getattr(expr, "expansion_stack", ()),
            ),
            result_expr=expr.result_expr,
            on_exhausted_result_expr=None,
            binding_terminal=binding_terminal,
            state_projection=state_projection,
            result_projection=result_projection,
            result_type=result_type,
            loop_binding_name=loop_binding_name,
            context=context,
            local_values=local_values,
            active_variant_name=active_variant_name,
        )
    raise _compile_error(
        code="workflow_return_not_exportable",
        message="`loop/recur` bodies currently lower only terminal continue/done forms and matches over them",
        span=expr.span,
        form_path=expr.form_path,
    )


def _lower_loop_terminal_expr(
    expr: Any,
    *,
    body_step_name: str,
    status_value: str,
    state_expr: Any,
    result_expr: Any | None,
    on_exhausted_result_expr: Any | None,
    binding_terminal: _TerminalResult,
    state_projection: LoopValueProjection,
    result_projection: LoopValueProjection,
    result_type: TypeRef,
    loop_binding_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    active_variant_name: str | None,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    step_id = _normalize_generated_step_id(body_step_name)
    projected_values = [
        {
            "name": LOOP_STATUS_OUTPUT_NAME,
            "source": {"literal": status_value},
            "contract": {"kind": "scalar", "type": "enum", "allowed": list(LOOP_STATUS_ALLOWED)},
        }
    ]
    projected_values.extend(
        _loop_projection_materialize_values(
            state_expr,
            projection=state_projection,
            local_values=local_values,
            context=context,
            active_variant_name=active_variant_name,
            allow_missing_target_fields=state_projection.optional_relpath_fields,
            allow_missing_active_fields=(
                active_variant_name is None and state_projection.union_projection is not None
            ),
        )
    )
    if result_expr is None:
        if on_exhausted_result_expr is None:
            projected_values.extend(
                _loop_placeholder_values(
                    result_projection,
                    allow_missing_target_fields=_loop_result_optional_relpath_fields(result_projection),
                )
            )
        else:
            exhaustion_local_values = dict(local_values)
            exhaustion_local_values[loop_binding_name] = _resolve_inline_expr_value(
                state_expr,
                local_values=local_values,
            )
            projected_values.extend(
                _loop_projection_materialize_values(
                    on_exhausted_result_expr,
                    projection=result_projection,
                    local_values=exhaustion_local_values,
                    context=context,
                    active_variant_name=active_variant_name,
                    allow_missing_target_fields=_loop_result_optional_relpath_fields(result_projection),
                    allow_missing_active_fields=(
                        active_variant_name is None and result_projection.union_projection is not None
                    ),
                )
            )
    else:
        projected_values.extend(
            _loop_projection_materialize_values(
                result_expr,
                projection=result_projection,
                local_values=local_values,
                context=context,
                active_variant_name=active_variant_name,
                allow_missing_target_fields=_loop_result_optional_relpath_fields(result_projection),
                allow_missing_active_fields=(
                    active_variant_name is None and result_projection.union_projection is not None
                ),
            )
        )
    values: list[dict[str, Any]] = []
    output_refs: dict[str, str] = {}
    for value in projected_values:
        source = value.get("source")
        if not isinstance(source, dict):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message="`loop/recur` terminal projection emitted an invalid materialization source",
                span=expr.span,
                form_path=expr.form_path,
            )
        source_ref = source.get("ref")
        if isinstance(source_ref, str):
            output_refs[value["name"]] = source_ref
            continue
        values.append(value)
        output_refs[value["name"]] = f"root.steps.{body_step_name}.artifacts.{value['name']}"
    _record_step_origin(context, step_name=body_step_name, step_id=step_id, source=expr)
    return [
        _materialize_values_step(
            step_name=body_step_name,
            step_id=step_id,
            values=values,
        )
    ], _TerminalResult(
        step_name=body_step_name,
        step_id=step_id,
        output_refs=output_refs,
        output_kind="step",
        hidden_inputs={},
    )


def _loop_output_contracts(
    *,
    state_projection: LoopValueProjection,
    result_projection: LoopValueProjection,
) -> dict[str, dict[str, Any]]:
    outputs = {
        LOOP_STATUS_OUTPUT_NAME: {
            "kind": "scalar",
            "type": "enum",
            "allowed": list(LOOP_STATUS_ALLOWED),
        }
    }
    outputs.update(
        {
            field.generated_name: internal_loop_contract(
                field,
                allow_missing_target_fields=state_projection.optional_relpath_fields,
            )
            for field in state_projection.flattened_fields
        }
    )
    outputs.update(
        {
            field.generated_name: internal_loop_contract(
                field,
                allow_missing_target_fields=_loop_result_optional_relpath_fields(result_projection),
            )
            for field in result_projection.flattened_fields
        }
    )
    return outputs


def _canonicalize_loop_materialize_scope_refs(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility shim retained for staged refactoring; returns steps unchanged."""

    return steps


def _loop_repeat_outputs_from_terminal(
    *,
    loop_output_contracts: Mapping[str, Mapping[str, Any]],
    terminal: _TerminalResult,
    span,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    for output_name, definition in loop_output_contracts.items():
        output_ref = terminal.output_refs.get(output_name)
        if not isinstance(output_ref, str):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"`loop/recur` body did not expose projected output `{output_name}`",
                span=span,
                form_path=form_path,
            )
        outputs[output_name] = {
            **dict(definition),
            "from": {"ref": _conditional_case_ref(output_ref, terminal_step_name=terminal.step_name)},
        }
    return outputs


def _loop_projection_materialize_values(
    expr: Any,
    *,
    projection: LoopValueProjection,
    local_values: Mapping[str, Any],
    context: _LoweringContext,
    active_variant_name: str | None = None,
    allow_missing_target_fields: frozenset[str] = frozenset(),
    allow_missing_active_fields: bool = False,
) -> list[dict[str, Any]]:
    from ..loop_state import loop_state_field_origin

    resolved_value = _resolve_inline_expr_value(expr, local_values=local_values)

    def current_value_for(field_path: tuple[str, ...]) -> Any:
        if isinstance(expr, UnionVariantExpr):
            return _inline_expr_field_value(
                expr,
                field_path=field_path,
                local_values=local_values,
                context=context,
            )
        current_value = resolved_value
        if field_path:
            current_value = _resolve_inline_field_value(
                resolved_value,
                field_path=field_path,
                local_values=local_values,
            )
        if isinstance(current_value, PhaseTargetExpr) and context is not None:
            return _phase_target_inline_ref(current_value, context=context)
        return current_value

    values: list[dict[str, Any]] = []
    if active_variant_name is not None and projection.union_projection is not None:
        projected_variant_name = (
            expr.variant_name if isinstance(expr, UnionVariantExpr) else active_variant_name
        )
        active_variant_fields = {
            field.generated_name
            for field in projection.union_projection.variant_fields.get(projected_variant_name, ())
        }
        shared_field_names = {
            field.generated_name for field in projection.union_projection.shared_fields
        }
        discriminant_name = projection.union_projection.discriminant_field.generated_name
        for field in projection.flattened_fields:
            contract_allow_missing = frozenset()
            relative_path = field.source_path[1:]
            if field.contract_definition.get("type") in {"path", "relpath"}:
                field_origin = loop_state_field_origin(expr, relative_path)
                if field_origin is not None:
                    context.generated_path_spans.setdefault(
                        f"{context.step_name_prefix}.{field.generated_name}",
                        _origin_from_context_source(context, field_origin),
                    )
            if field.generated_name == discriminant_name:
                source: dict[str, Any] = {"literal": projected_variant_name}
            elif field.generated_name in shared_field_names or field.generated_name in active_variant_fields:
                current_value = current_value_for(relative_path)
                if isinstance(current_value, LiteralExpr):
                    source = {"literal": current_value.value}
                elif isinstance(current_value, GeneratedRelpathSeedExpr):
                    context.generated_path_spans.setdefault(
                        current_value.literal_path,
                        _origin_from_context_source(context, current_value),
                    )
                    source = {"literal": current_value.literal_path}
                elif isinstance(current_value, str):
                    source = {"ref": current_value}
                else:
                    raise _compile_error(
                        code="workflow_return_not_exportable",
                        message=(
                            f"`loop/recur` could not project `{field.generated_name}` from "
                            f"`{type(expr).__name__}` in this Stage 3 slice"
                        ),
                        span=expr.span,
                        form_path=expr.form_path,
                    )
            else:
                source = {"literal": projection.placeholder_literals[field.generated_name]}
                contract_allow_missing = allow_missing_target_fields
            values.append(
                {
                    "name": field.generated_name,
                    "source": source,
                    "contract": internal_loop_contract(
                        field,
                        allow_missing_target_fields=contract_allow_missing,
                    ),
                }
            )
        return values
    for field in projection.flattened_fields:
        relative_path = field.source_path[1:]
        if field.contract_definition.get("type") in {"path", "relpath"}:
            field_origin = loop_state_field_origin(expr, relative_path)
            if field_origin is not None:
                context.generated_path_spans.setdefault(
                    f"{context.step_name_prefix}.{field.generated_name}",
                    _origin_from_context_source(context, field_origin),
                )
        current_value = current_value_for(relative_path)
        if isinstance(current_value, LiteralExpr):
            source = {"literal": current_value.value}
        elif isinstance(current_value, GeneratedRelpathSeedExpr):
            context.generated_path_spans.setdefault(
                current_value.literal_path,
                _origin_from_context_source(context, current_value),
            )
            source = {"literal": current_value.literal_path}
        elif isinstance(current_value, str):
            source = {"ref": current_value}
        else:
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"`loop/recur` could not project `{field.generated_name}` from "
                    f"`{type(expr).__name__}` in this Stage 3 slice"
                ),
                span=expr.span,
                form_path=expr.form_path,
            )
        values.append(
            {
                "name": field.generated_name,
                "source": source,
                "contract": internal_loop_contract(
                    field,
                    allow_missing_target_fields=(
                        allow_missing_target_fields if allow_missing_active_fields else frozenset()
                    ),
                ),
            }
        )
    return values


def _loop_placeholder_values(
    projection: LoopValueProjection,
    *,
    allow_missing_target_fields: frozenset[str],
) -> list[dict[str, Any]]:
    return [
        {
            "name": field.generated_name,
            "source": {"literal": projection.placeholder_literals[field.generated_name]},
            "contract": internal_loop_contract(
                field,
                allow_missing_target_fields=allow_missing_target_fields,
            ),
        }
        for field in projection.flattened_fields
    ]


def _loop_on_exhausted_outputs(
    expr: Any,
    *,
    plan: LoopLoweringPlan,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    loop_binding_name: str,
) -> dict[str, Any]:
    active_variant_name = expr.variant_name if isinstance(expr, UnionVariantExpr) else None
    outputs: dict[str, Any] = {LOOP_STATUS_OUTPUT_NAME: "DONE"}
    result_fields_by_name = {field.generated_name: field for field in plan.result_projection.flattened_fields}
    for value in _loop_projection_materialize_values(
        expr,
        projection=plan.result_projection,
        local_values=local_values,
        context=context,
        active_variant_name=active_variant_name,
        allow_missing_target_fields=_loop_result_optional_relpath_fields(plan.result_projection),
    ):
        result_field = result_fields_by_name[value["name"]]
        if value.get("contract", {}).get("kind") != "scalar":
            field_expr = _loop_on_exhausted_expr_at_path(expr, result_field.source_path[1:])
            if field_expr is None:
                continue
            if not _loop_on_exhausted_non_scalar_uses_loop_state(
                expr,
                loop_binding_name=loop_binding_name,
                field_path=result_field.source_path[1:],
                require_exact_state_field_path=not isinstance(result_type, UnionTypeRef),
            ):
                field_name = "__".join(result_field.source_path[1:]) or result_field.generated_name
                raise _compile_error(
                    code="workflow_return_not_exportable",
                    message=(
                        f"`loop/recur :on-exhausted` non-scalar field `{field_name}` must "
                        "project from loop state so final normalization can reuse loop-frame outputs"
                    ),
                    span=field_expr.span,
                    form_path=field_expr.form_path,
            )
            continue
        source = value["source"]
        if "literal" in source:
            outputs[value["name"]] = source["literal"]
        elif "ref" in source:
            field_expr = _loop_on_exhausted_expr_at_path(expr, result_field.source_path[1:])
            if isinstance(result_type, UnionTypeRef) and _loop_on_exhausted_scalar_uses_loop_state(
                field_expr,
                loop_binding_name=loop_binding_name,
            ):
                continue
            outputs[value["name"]] = {"ref": source["ref"]}
        else:
            raise _compile_error(
                code="workflow_return_not_exportable",
                message="`loop/recur` exhaustion projection emitted an unsupported source",
                span=expr.span,
                form_path=expr.form_path,
            )
    return outputs


def _loop_on_exhausted_expr_at_path(expr: Any, field_path: tuple[str, ...]) -> Any | None:
    if isinstance(expr, RecordExpr):
        if not field_path:
            return expr
        return _record_expr_value_at_path(expr, field_path)
    if isinstance(expr, UnionVariantExpr):
        return _union_variant_expr_value_at_path(expr, field_path)
    if not field_path:
        return expr
    return None


def _loop_on_exhausted_scalar_uses_loop_state(
    field_expr: Any | None,
    *,
    loop_binding_name: str,
) -> bool:
    if not isinstance(field_expr, FieldAccessExpr):
        return False
    base = field_expr.base
    while isinstance(base, FieldAccessExpr):
        base = base.base
    return isinstance(base, NameExpr) and base.name == loop_binding_name


def _loop_on_exhausted_non_scalar_uses_loop_state(
    expr: Any,
    *,
    loop_binding_name: str,
    field_path: tuple[str, ...],
    require_exact_state_field_path: bool,
) -> bool:
    field_expr = _loop_on_exhausted_expr_at_path(expr, field_path)
    if isinstance(field_expr, NameExpr):
        return not field_path and field_expr.name == loop_binding_name
    if not isinstance(field_expr, FieldAccessExpr):
        return False
    if require_exact_state_field_path and tuple(field_expr.fields) != field_path:
        return False
    base = field_expr.base
    while isinstance(base, FieldAccessExpr):
        base = base.base
    return isinstance(base, NameExpr) and base.name == loop_binding_name


def _record_loop_on_exhausted_origins(
    *,
    context: _LoweringContext,
    loop_expr: LoopRecurExpr,
    repeat_step_name: str,
    repeat_step_id: str,
    result_step_name: str,
    result_step_id: str,
    normalized_result_fields: list[Any],
) -> None:
    on_exhausted = loop_expr.on_exhausted_result_expr
    if on_exhausted is None:
        return

    _record_step_origin(context, step_name=repeat_step_name, step_id=repeat_step_id, source=on_exhausted)
    _record_step_origin(context, step_name=result_step_name, step_id=result_step_id, source=on_exhausted)
    output_origin = _origin_from_context_source(context, on_exhausted)
    for field in normalized_result_fields:
        if _loop_on_exhausted_expr_at_path(on_exhausted, field.source_path[1:]) is None:
            continue
        context.generated_output_spans[field.generated_name] = output_origin


def _loop_result_optional_relpath_fields(projection: LoopValueProjection) -> frozenset[str]:
    return projection_relpath_fields(projection)


def _loop_state_optional_relpath_fields(
    expr: Any,
    *,
    projection: LoopValueProjection,
    local_values: Mapping[str, Any],
    context: _LoweringContext,
) -> frozenset[str]:
    optional_fields = set(projection.optional_relpath_fields)
    resolved_value = _resolve_inline_expr_value(expr, local_values=local_values)

    def current_value_for(field_path: tuple[str, ...]) -> Any:
        if isinstance(expr, UnionVariantExpr):
            return _inline_expr_field_value(
                expr,
                field_path=field_path,
                local_values=local_values,
                context=context,
            )
        current_value = resolved_value
        if field_path:
            current_value = _resolve_inline_field_value(
                resolved_value,
                field_path=field_path,
                local_values=local_values,
            )
        if isinstance(current_value, PhaseTargetExpr):
            return _phase_target_inline_ref(current_value, context=context)
        return current_value

    for field in projection.flattened_fields:
        if field.contract_definition.get("type") != "relpath":
            continue
        current_value = current_value_for(field.source_path[1:])
        if isinstance(current_value, GeneratedRelpathSeedExpr):
            optional_fields.add(field.generated_name)

    return frozenset(optional_fields)


def _loop_result_case_output_ref(
    *,
    loop_expr: LoopRecurExpr,
    plan: LoopLoweringPlan,
    variant_name: str,
    field_path: tuple[str, ...],
) -> str | None:
    on_exhausted = loop_expr.on_exhausted_result_expr
    if not isinstance(on_exhausted, UnionVariantExpr) or on_exhausted.variant_name != variant_name:
        return None
    field_value = _union_variant_expr_value_at_path(on_exhausted, field_path)
    if not isinstance(field_value, FieldAccessExpr):
        return None
    if not isinstance(field_value.base, NameExpr) or field_value.base.name != loop_expr.binding_name:
        return None
    return (
        f"root.steps.{plan.repeat_step_name}.artifacts."
        f"{_loop_projection_field_name(plan.state_projection, tuple(field_value.fields))}"
    )


def _loop_case_ref(ref: str) -> str:
    if ref.startswith("root.steps."):
        return "self.steps." + ref.removeprefix("root.steps.")
    return ref


def _conditional_case_ref(ref: str, *, terminal_step_name: str) -> str:
    if terminal_step_name and ref.startswith(f"root.steps.{terminal_step_name}"):
        return "self.steps." + ref.removeprefix("root.steps.")
    return ref


def _loop_projection_local_value(
    projection: LoopValueProjection,
    output_refs: Mapping[str, str],
) -> Any:
    if len(projection.flattened_fields) == 1 and projection.flattened_fields[0].source_path == (projection.prefix,):
        return output_refs[projection.flattened_fields[0].generated_name]
    local_value: dict[str, Any] = {}
    for field in projection.flattened_fields:
        ref = output_refs[field.generated_name]
        relative_path = field.source_path[1:]
        if not relative_path:
            return ref
        _assign_nested_local_value(local_value, relative_path, ref)
    return local_value


def _loop_projection_field_name(
    projection: LoopValueProjection,
    field_path: tuple[str, ...],
) -> str:
    if not field_path:
        return projection.prefix
    return f"{projection.prefix}__{'__'.join(field_path)}"


def _loop_parent_scope_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("self.steps."):
            return "parent.steps." + value.removeprefix("self.steps.")
        if value.startswith("root.steps."):
            return "parent.steps." + value.removeprefix("root.steps.")
        return value
    if isinstance(value, Mapping):
        return {name: _loop_parent_scope_value(item) for name, item in value.items()}
    return value


def _loop_body_scope_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("root.steps."):
            return "self.steps." + value.removeprefix("root.steps.")
        return value
    if isinstance(value, Mapping):
        return {name: _loop_body_scope_value(item) for name, item in value.items()}
    return value


def _inline_procedure_step_prefix(
    *,
    context: _LoweringContext,
    callee_name: str,
    procedure: TypedProcedureDef,
    ordinal: int,
) -> str:
    if procedure.definition.name.startswith("%rl."):
        compact_name = procedure.definition.name.removeprefix("%").replace(".", "_").replace("-", "_")
        return f"{compact_name}_{ordinal}"
    return f"{context.step_name_prefix}__{callee_name}_{ordinal}"
