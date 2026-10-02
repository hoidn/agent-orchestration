"""Pure selected surface-control analysis over existing typed binding facts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from .. import expressions as ex
from ..procedures import ProcedureLoweringMode, procedure_type_env_for
from ..syntax import target_dsl_supports_generic_unions
from ..type_env import RecordTypeRef, UnionTypeRef
from .command_control_decisions import (
    binding_projection_output_aliases, inline_output_boundary_fields, inline_procedure_bindings,
    projection_artifact_names, provider_capture_artifact_names, resolved_surface_proc_ref,
    select_surface_procedure_call, selected_phase_scope,
)
from .command_transport_decisions import (
    RUNTIME_REFERENCE, compiler_owned_pure_let, direct_output_leaves_available,
    is_direct_reference, is_inline_let_binding_expr,
    schema1_iteration_private_override_applies, surface_binding_materialization,
)
from .values import (
    _build_output_step_local_value, _flatten_boundary_leaf_paths,
    _procedure_signature_local_type_bindings, _resolve_inline_expr_value,
    inline_expr_field_value, inline_let_field_value,
)


@dataclass(frozen=True)
class ControlFacts:
    """Compiler-local typed data; no emission hooks or generated references."""

    signature: Any
    type_env: Any
    local_type_bindings: Mapping[str, Any]
    typed_procedures: Mapping[str, Any]
    workflow_catalog: Any
    workflows_by_name: Mapping[str, Any]
    procedure_type_envs: Mapping[str, Any]
    workflow_name: str
    iteration_scope: Any = None
    phase_scope: Any = None
    phase_target_values: Mapping[str, Any] | None = None
    procedure_catalog: Any = None
    active_procedure_calls: frozenset[str] = frozenset()
    lowered_callees: Mapping[str, Any] = field(default_factory=dict)
    retained_binding_types: Mapping[str, Any] = field(default_factory=dict)
    procedure_binding_types: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


def control_facts_for_context(context: Any) -> ControlFacts:
    phase = context.phase_scope
    return ControlFacts(
        signature=context.signature, type_env=context.type_env,
        local_type_bindings=context.local_type_bindings,
        typed_procedures=context.typed_procedures, workflow_catalog=context.workflow_catalog,
        workflows_by_name=context.workflows_by_name, procedure_type_envs=context.procedure_type_envs,
        workflow_name=context.workflow_name, iteration_scope=context.iteration_scope,
        phase_scope=phase, phase_target_values=None if phase is None else phase.target_refs,
        procedure_catalog=getattr(context, "procedure_catalog", None),
        active_procedure_calls=context.active_procedure_calls, lowered_callees=context.lowered_callees,
    )


def _direct_outputs_available(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> bool:
    fields = inline_output_boundary_fields(
        expr, type_ref=result_type, type_env=facts.type_env, signature=facts.signature,
    )
    return direct_output_leaves_available(
        is_direct_reference(inline_expr_field_value(
            expr, field_path=boundary.source_path[1:], local_values=local_values,
            bound_record_fields=target_dsl_supports_generic_unions(facts.type_env.target_dsl_version),
            phase_target_values=facts.phase_target_values,
        )) for boundary in fields
    )


def branch_control_summary(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> bool:
    if _direct_outputs_available(expr, result_type=result_type, facts=facts, local_values=local_values):
        return False
    return expression_control_summary(expr, result_type=result_type, facts=facts, local_values=local_values)


_CONTROL_EMITTERS = (
    ex.IfExpr, ex.MatchExpr, ex.LoopRecurExpr, ex.ProduceOneOfExpr,
    ex.ResumeOrStartExpr, ex.FinalizeSelectedItemExpr,
)
_LEAF_EMITTERS = (
    ex.CommandResultExpr, ex.ProviderResultExpr, ex.RequestInputExpr, ex.CallExpr,
    ex.RunProviderPhaseExpr, ex.ResourceTransitionExpr, ex.RecordExpr, ex.UnionVariantExpr,
    ex.NameExpr, ex.FieldAccessExpr, ex.LiteralExpr, ex.PhaseTargetExpr, ex.PureOpExpr,
    ex.RecordUpdateExpr, ex.LoopStateSeedExpr, ex.LoopStateUpdateExpr, ex.ProviderBundlePathExpr,
    ex.EnumMemberExpr, ex.ListExpr, ex.ListMapExpr, ex.CompilerListNonemptyHeadExpr,
    ex.PathJoinUnderExpr, ex.UnionVariantTagExpr, ex.GeneratedRelpathSeedExpr,
)


def expression_control_summary(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> bool:
    return _expression_control_fact(expr, result_type=result_type, facts=facts, local_values=local_values)[0]


def _expression_control_fact(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    if isinstance(expr, _CONTROL_EMITTERS):
        return True, ()
    if isinstance(expr, _LEAF_EMITTERS):
        return False, _leaf_output_names(expr, result_type=result_type)
    if isinstance(expr, ex.LetStarExpr):
        if compiler_owned_pure_let(expr, target_dsl_version=facts.type_env.target_dsl_version):
            return False, _projection_output_names(expr, result_type=result_type, facts=facts)
        return _let_control_fact(expr, result_type=result_type, facts=facts, local_values=local_values)
    from .procedures import LowerableProcedureCall

    if isinstance(expr, (ex.ProcedureCallExpr, LowerableProcedureCall)):
        return _procedure_control_fact(expr, facts=facts, local_values=local_values)
    if isinstance(expr, ex.WithPhaseExpr):
        return _expression_control_fact(expr.body, result_type=result_type, facts=_with_phase_facts(expr, facts=facts, local_values=local_values), local_values=local_values)
    raise ValueError(f"no selected surface-control rule for {type(expr).__name__}")


def _with_phase_facts(expr: Any, *, facts: ControlFacts, local_values: Mapping[str, Any]) -> ControlFacts:
    from .context import _ActivePhaseScope

    scope, targets = selected_phase_scope(
        _resolve_inline_expr_value(expr.ctx_expr, local_values=local_values),
        phase_name=expr.phase_name, ctx_expr=expr.ctx_expr, span=expr.span, form_path=expr.form_path,
    )
    return replace(facts, phase_scope=_ActivePhaseScope(
        scope=scope, bundle_path_ref=RUNTIME_REFERENCE, target_refs=targets,
    ), phase_target_values=targets)


def _leaf_output_names(expr: Any, *, result_type: Any) -> tuple[str, ...]:
    if isinstance(expr, ex.ProviderResultExpr):
        captured = provider_capture_artifact_names(result_type, capture_context=expr.capture_context == "portable")
        if captured is not None:
            return tuple(captured)
    if isinstance(result_type, (RecordTypeRef, UnionTypeRef)):
        return tuple(name for name, _ in _flatten_boundary_leaf_paths(result_type, generated_name="return"))
    return ("return",)


def _projection_output_names(expr: Any, *, result_type: Any, facts: ControlFacts) -> tuple[str, ...]:
    from .pure_projection import output_contracts_for_type

    return tuple(projection_artifact_names(output_contracts_for_type(
        result_type, type_env=facts.type_env, span=expr.span, form_path=expr.form_path,
    )))


def _binding_projection_output_names(expr: Any, *, name: str, result_type: Any, facts: ControlFacts) -> tuple[str, ...]:
    from ..contracts import derive_workflow_boundary_fields
    from ..syntax import target_dsl_supports_pure_call_composition
    from .pure_projection import output_contracts_for_boundary_type

    if not isinstance(result_type, (RecordTypeRef, UnionTypeRef)):
        return _projection_output_names(expr, result_type=result_type, facts=facts)
    boundaries = derive_workflow_boundary_fields(
        result_type, generated_name=name, source_path=(name,), span=expr.span, form_path=expr.form_path, type_env=facts.type_env,
    )
    contracts = output_contracts_for_boundary_type(
        result_type, generated_name=name, span=expr.span, form_path=expr.form_path, type_env=facts.type_env,
    )
    aliases = binding_projection_output_aliases(
        boundaries, whole_value=False,
        pure_call_composition=target_dsl_supports_pure_call_composition(facts.type_env.target_dsl_version),
    )
    return tuple(aliases if aliases is not None else projection_artifact_names(contracts))


def _materialized_binding_value(type_ref: Any, *, output_names: tuple[str, ...], facts: ControlFacts) -> Any:
    if not isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return RUNTIME_REFERENCE if "return" in output_names else None
    from ..syntax import target_dsl_supports_rich_loop_values

    preserve_paths = target_dsl_supports_rich_loop_values(facts.type_env.target_dsl_version)
    return _build_output_step_local_value(
        {name: RUNTIME_REFERENCE for name in output_names},
        type_ref=type_ref if preserve_paths else None,
        type_env=facts.type_env if preserve_paths else None,
    )


def _binding_control_fact(expr: Any, *, name: str, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    from .core import _infer_inline_binding_type
    from ..procedure_refs import ResolvedProcRefValue

    if is_inline_let_binding_expr(expr):
        value = _resolve_inline_expr_value(expr, local_values=local_values)
        if isinstance(expr, (ex.ProcRefLiteralExpr, ex.BindProcExpr)):
            value = resolved_surface_proc_ref(
                value, typed_procedures=facts.typed_procedures, local_values=local_values,
                procedure_catalog=facts.procedure_catalog,
            )
        type_ref = facts.retained_binding_types.get(name)
        if type_ref is None:
            type_ref = value.residual_type_ref if isinstance(value, ResolvedProcRefValue) else _infer_inline_binding_type(expr, context=facts)
        return False, value, type_ref
    return _effectful_binding_control_fact(expr, name=name, facts=facts, local_values=local_values)


def _effectful_binding_control_fact(expr: Any, *, name: str, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, Any, Any]:
    from .core import _resolve_lowering_expr_type

    type_ref = facts.retained_binding_types.get(name)
    if type_ref is None:
        type_ref = _resolve_lowering_expr_type(expr, context=facts)
    if isinstance(expr, (ex.WithPhaseExpr, ex.ProviderResultExpr)):
        selected = "expression"
    else:
        selected, _ = surface_binding_materialization(
            expr, resolved_binding=None if isinstance(expr, ex.MatchExpr) else _resolve_inline_expr_value(expr, local_values=local_values),
        )
    if selected == "projection":
        control, output_names = False, _binding_projection_output_names(expr, name=name, result_type=type_ref, facts=facts)
    elif selected == "match":
        control, output_names = True, ()
    else:
        control, output_names = _expression_control_fact(expr, result_type=type_ref, facts=facts, local_values=local_values)
    if control:
        return True, None, type_ref
    if type_ref is None:
        raise ValueError(f"missing typed binding fact for {type(expr).__name__}")
    return False, _materialized_binding_value(type_ref, output_names=output_names, facts=facts), type_ref


def _suffix_outputs_available(expr: Any, bindings: tuple[Any, ...], *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> bool:
    if not bindings:
        return _direct_outputs_available(expr.body, result_type=result_type, facts=facts, local_values=local_values)
    boundaries = inline_output_boundary_fields(
        expr, type_ref=result_type, type_env=facts.type_env, signature=facts.signature,
    )
    return direct_output_leaves_available(is_direct_reference(inline_let_field_value(
        bindings, body=expr.body, field_path=boundary.source_path[1:], local_values=local_values,
    )) for boundary in boundaries)


def _let_control_fact(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    values = dict(local_values)
    for index, (name, bound) in enumerate(expr.bindings):
        control, value, type_ref = _binding_control_fact(bound, name=name, facts=facts, local_values=values)
        if control:
            return True, ()
        if value is not None:
            values[name] = value
        if type_ref is not None:
            facts = replace(facts, local_type_bindings={**facts.local_type_bindings, name: type_ref})
        if _suffix_outputs_available(expr, expr.bindings[index + 1:], result_type=result_type, facts=facts, local_values=values):
            return False, tuple(boundary.generated_name for boundary in inline_output_boundary_fields(
                expr.body, type_ref=result_type, type_env=facts.type_env, signature=facts.signature,
            ))
    return _expression_control_fact(expr.body, result_type=result_type, facts=facts, local_values=values)


def _procedure_control_fact(expr: Any, *, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    from .procedures import LowerableProcedureCall

    call = expr if isinstance(expr, LowerableProcedureCall) else LowerableProcedureCall(
        callee_name=expr.callee_name, args=expr.args, span=expr.span,
        form_path=expr.form_path, expansion_stack=expr.expansion_stack,
    )
    procedure, args = select_surface_procedure_call(
        call, local_values=local_values, typed_procedures=facts.typed_procedures,
        procedure_catalog=facts.procedure_catalog, workflow_catalog=facts.workflow_catalog,
        typed_workflows=facts.workflows_by_name,
    )
    _check_procedure_cycle(procedure, call=call, facts=facts)
    env = procedure_type_env_for(procedure, procedure_type_envs=facts.procedure_type_envs, default=facts.type_env)
    if procedure.resolved_lowering_mode == ProcedureLoweringMode.PRIVATE_WORKFLOW or schema1_iteration_private_override_applies(
        procedure, iteration_scope=facts.iteration_scope, workflow_name=facts.workflow_name,
        default_type_env=facts.type_env, typed_procedures=facts.typed_procedures,
        procedure_type_envs=facts.procedure_type_envs, workflow_signatures=facts.workflow_catalog.signatures_by_name,
    ):
        return False, tuple(name for name, _ in _flatten_boundary_leaf_paths(procedure.typed_body.type_ref, generated_name="return"))
    values = inline_procedure_bindings(procedure, caller_values=local_values, actual_values=tuple(
        _resolve_inline_expr_value(arg, local_values=local_values) for arg in args
    ))
    child = replace(
        facts, type_env=env,
        local_type_bindings={**facts.local_type_bindings, **_procedure_signature_local_type_bindings(procedure)},
        active_procedure_calls=facts.active_procedure_calls | {procedure.signature.name},
        retained_binding_types=facts.procedure_binding_types.get(procedure.signature.name, {}),
    )
    body = procedure.typed_body
    if isinstance(body.expr, ex.NameExpr) and not isinstance(body.type_ref, (RecordTypeRef, UnionTypeRef)) and _direct_outputs_available(
        body.expr, result_type=body.type_ref, facts=child, local_values=values,
    ):
        return False, ("return",)
    return _expression_control_fact(body.expr, result_type=body.type_ref, facts=child, local_values=values)


def _check_procedure_cycle(procedure: Any, *, call: Any, facts: ControlFacts) -> None:
    from .context import _compile_error

    if procedure.signature.name not in facts.active_procedure_calls:
        return
    specialized = procedure.specialization is not None and (
        getattr(procedure.specialization, "proc_ref_bindings", {}) or getattr(procedure.specialization, "value_bindings", {})
    )
    raise _compile_error(
        code="proc_ref_specialization_cycle" if specialized else "proc_lowering_cycle",
        message=f"recursive procedure specialization cycle detected for `{procedure.signature.name}`",
        span=call.span, form_path=call.form_path,
    )
