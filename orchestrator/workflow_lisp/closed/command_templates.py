"""Compiler-local command scopes, selected while typed arms still exist."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from typing import Any, Literal

from .. import expressions as ex
from ..expression_traversal import iter_child_exprs, is_pure_projection_expr
from ..expressions import (
    BindProcExpr, FieldAccessExpr, IfExpr, LetStarExpr, LiteralExpr, LoopStateSeedExpr,
    LoopStateUpdateExpr, MatchExpr, NameExpr, PhaseTargetExpr, ProcRefLiteralExpr,
    ProviderBundlePathExpr, PureOpExpr, RecordExpr, RecordUpdateExpr, UnionVariantExpr,
)
from ..procedures import ProcedureLoweringMode, _procedure_signature_local_type_bindings, procedure_type_env_for
from ..syntax import target_dsl_supports_generic_unions
from ..procedure_specialization import (
    RUNTIME_REFERENCE, RetainedExpressionFact,
    _build_output_step_local_value, _flatten_boundary_leaf_paths,
    _resolve_inline_expr_value, inline_expr_field_value, inline_let_field_value,
    inline_procedure_bindings, resolved_surface_proc_ref, select_surface_procedure_call,
    schema1_iteration_private_override_applies,
)
from ..type_env import RecordTypeRef, UnionTypeRef, VariantCaseTypeRef
from ..wcc.anf import normalize_wcc_body_to_anf
from ..wcc import model as w
from ..wcc.model import (
    WccBody, WccCase, WccHalt, WccIf, WccJoin, WccJump, WccLet,
    WccLoopContinue, WccLoopDone, WccNameAtom, WccPerform, WccRecJoin, WccParallelMap,
)
from .names import canonical_type_descriptor
from orchestrator.contracts.closed_program.program import _canonical_json


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
    closed_program: bool = False
    workflow_return_types: Mapping[str, Any] = field(default_factory=dict)
    procedure_return_types: Mapping[str, Any] = field(default_factory=dict)
    procedure_owners: Mapping[str, Any] = field(default_factory=dict)
    base_workflow_return_types: Mapping[str, Any] = field(default_factory=dict)


def _direct_outputs_available(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> bool:
    fields = inline_output_boundary_fields(
        expr, type_ref=result_type, type_env=facts.type_env, signature=facts.signature,
    )
    return direct_output_leaves_available(
        is_direct_reference(inline_expr_field_value(
            expr, field_path=boundary.source_path[1:], local_values=local_values,
            bound_record_fields=target_dsl_supports_generic_unions(facts.type_env.target_dsl_version),
            phase_target_values=facts.phase_target_values, retain_expression_facts=facts.closed_program,
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
    ex.RunRefExpr,
    ex.PathJoinUnderExpr, ex.UnionVariantTagExpr, ex.GeneratedRelpathSeedExpr,
)


def expression_control_summary(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> bool:
    return _expression_control_fact(expr, result_type=result_type, facts=facts, local_values=local_values)[0]


def _expression_control_fact(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    if isinstance(expr, _CONTROL_EMITTERS):
        return True, ()
    if isinstance(expr, _LEAF_EMITTERS):
        return False, _leaf_output_names(expr, result_type=result_type,
            type_env=facts.type_env if facts is not None and facts.closed_program else None)
    if isinstance(expr, ex.LetStarExpr):
        if compiler_owned_pure_let(expr, target_dsl_version=facts.type_env.target_dsl_version):
            return False, _projection_output_names(expr, result_type=result_type, facts=facts)
        return _let_control_fact(expr, result_type=result_type, facts=facts, local_values=local_values)
    from orchestrator.workflow_lisp.procedures import (LowerableProcedureCall)

    if isinstance(expr, (ex.ProcedureCallExpr, LowerableProcedureCall)):
        return _procedure_control_fact(expr, facts=facts, local_values=local_values)
    if isinstance(expr, ex.WithPhaseExpr):
        return _expression_control_fact(expr.body, result_type=result_type, facts=_with_phase_facts(expr, facts=facts, local_values=local_values), local_values=local_values)
    raise ValueError(f"no selected surface-control rule for {type(expr).__name__}")


def _with_phase_facts(expr: Any, *, facts: ControlFacts, local_values: Mapping[str, Any]) -> ControlFacts:
    scope, targets = selected_phase_scope(
        _resolve_inline_expr_value(expr.ctx_expr, local_values=local_values, retain_expression_facts=facts.closed_program),
        phase_name=expr.phase_name, ctx_expr=expr.ctx_expr, span=expr.span, form_path=expr.form_path,
    )
    return replace(facts, phase_target_values=targets)

def _leaf_output_names(expr: Any, *, result_type: Any, type_env: Any | None) -> tuple[str, ...]:
    if isinstance(expr, ex.ProviderResultExpr):
        captured = provider_capture_artifact_names(result_type, capture_context=expr.capture_context == "portable")
        if captured is not None:
            return tuple(captured)
    if isinstance(result_type, (RecordTypeRef, UnionTypeRef)):
        return tuple(name for name, _ in _flatten_boundary_leaf_paths(
            result_type, generated_name="return", type_env=type_env))
    return ("return",)


def _projection_output_names(expr: Any, *, result_type: Any, facts: ControlFacts) -> tuple[str, ...]:
    from ..contracts import derive_workflow_boundary_fields, root_workflow_boundary_field

    if isinstance(result_type, (RecordTypeRef, UnionTypeRef)):
        return tuple(boundary.generated_name for boundary in derive_workflow_boundary_fields(
            result_type, generated_name="return", source_path=("return",),
            span=expr.span, form_path=expr.form_path, type_env=facts.type_env,
        ))
    root_workflow_boundary_field(
        result_type, span=expr.span, form_path=expr.form_path, type_env=facts.type_env,
    )
    return ("return",)


def _binding_projection_output_names(expr: Any, *, name: str, result_type: Any, facts: ControlFacts) -> tuple[str, ...]:
    from ..contracts import derive_workflow_boundary_fields
    from ..syntax import target_dsl_supports_pure_call_composition

    if not isinstance(result_type, (RecordTypeRef, UnionTypeRef)):
        return _projection_output_names(expr, result_type=result_type, facts=facts)
    boundaries = derive_workflow_boundary_fields(
        result_type, generated_name=name, source_path=(name,), span=expr.span, form_path=expr.form_path, type_env=facts.type_env,
    )
    aliases = binding_projection_output_aliases(
        boundaries, whole_value=False,
        pure_call_composition=target_dsl_supports_pure_call_composition(facts.type_env.target_dsl_version),
    )
    return tuple(aliases if aliases is not None else (boundary.generated_name for boundary in boundaries))


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


def _closed_binding_type(expr, *, facts, capture_source=None):
    from ..wcc.elaborate import binding_type_for_elaboration

    return binding_type_for_elaboration(
        expr, type_env=facts.type_env, value_env=facts.local_type_bindings,
        workflow_return_types=facts.workflow_return_types, procedure_return_types=facts.procedure_return_types,
        closed_program=True, capture_source=capture_source,
    )


def _binding_control_fact(expr: Any, *, name: str, facts: ControlFacts, local_values: Mapping[str, Any], capture_source=None) -> tuple[bool, Any, Any]:
    from ..procedure_refs import ResolvedProcRefValue
    from ..workflow_refs import ResolvedWorkflowRef, resolve_workflow_ref_expr, workflow_ref_type_from_signature

    if facts.closed_program:
        reference = _resolve_inline_expr_value(expr, local_values=local_values, retain_expression_facts=facts.closed_program)
        if isinstance(reference, ex.WorkflowRefLiteralExpr):
            reference = resolve_workflow_ref_expr(reference, workflow_catalog=facts.workflow_catalog,
                span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack,
                typed_workflows_by_name=facts.workflows_by_name, allow_extern_rebinding=True)
        if isinstance(reference, ResolvedWorkflowRef):
            signature = facts.workflow_catalog.signatures_by_name[reference.workflow_name]
            return False, reference, workflow_ref_type_from_signature(signature)

    if is_inline_let_binding_expr(expr):
        value = _resolve_inline_expr_value(expr, local_values=local_values, retain_expression_facts=facts.closed_program)
        if isinstance(expr, (ex.ProcRefLiteralExpr, ex.BindProcExpr)):
            value = resolved_surface_proc_ref(
                value, typed_procedures=facts.typed_procedures, local_values=local_values,
                procedure_catalog=facts.procedure_catalog,
            )
        if isinstance(value, ResolvedProcRefValue):
            type_ref = value.residual_type_ref
        else:
            type_ref = _closed_binding_type(expr, facts=facts, capture_source=capture_source)
        return False, value, type_ref
    return _effectful_binding_control_fact(expr, name=name, facts=facts, local_values=local_values, capture_source=capture_source)


def _effectful_binding_control_fact(expr: Any, *, name: str, facts: ControlFacts, local_values: Mapping[str, Any], capture_source=None) -> tuple[bool, Any, Any]:
    type_ref = _closed_binding_type(expr, facts=facts, capture_source=capture_source)
    if isinstance(expr, (ex.WithPhaseExpr, ex.ProviderResultExpr)):
        selected = "expression"
    else:
        selected, _ = surface_binding_materialization(
            expr, resolved_binding=None if isinstance(expr, ex.MatchExpr) else _resolve_inline_expr_value(expr, local_values=local_values, retain_expression_facts=facts.closed_program),
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
        bindings, body=expr.body, field_path=boundary.source_path[1:], local_values=local_values, retain_expression_facts=facts.closed_program,
    )) for boundary in boundaries)


def _let_control_fact(expr: Any, *, result_type: Any, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    values = dict(local_values)
    for index, (name, bound) in enumerate(expr.bindings):
        capture_source = expr.binding_capture_sources[index] if index < len(expr.binding_capture_sources) else None
        control, value, type_ref = _binding_control_fact(
            bound, name=name, facts=facts, local_values=values, capture_source=capture_source,
        )
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


def _procedure_return_types(procedure, *, facts, source_program):
    from ..wcc.elaborate import prepare_elaboration_call_types

    _, return_types = prepare_elaboration_call_types(
        procedure.typed_body, resolved_procedures_by_name=source_program.procedures,
        procedure_return_types=facts.procedure_return_types, closed_program=True,
    )
    return return_types


def _private_procedure_output_names(expr: Any, *, result_type: Any, closed_program: bool, type_env: Any) -> tuple[str, ...]:
    if closed_program:
        return _leaf_output_names(expr, result_type=result_type, type_env=type_env)
    return tuple(name for name, _ in _flatten_boundary_leaf_paths(result_type, generated_name="return"))


def _procedure_control_fact(expr: Any, *, facts: ControlFacts, local_values: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    from orchestrator.workflow_lisp.procedures import (LowerableProcedureCall)

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
        return False, _private_procedure_output_names(
            expr, result_type=procedure.typed_body.type_ref, closed_program=facts.closed_program,
            type_env=env,
        )
    values = inline_procedure_bindings(procedure, caller_values=local_values, actual_values=tuple(
        _resolve_inline_expr_value(arg, local_values=local_values, retain_expression_facts=facts.closed_program) for arg in args
    ))
    owner_returns = facts.workflow_return_types
    owner_catalog, owner_workflows = facts.workflow_catalog, facts.workflows_by_name
    if facts.closed_program:
        from ..closed.frontend import workflow_catalog_for, workflow_return_types_for

        _indexed_procedure, source_program = facts.procedure_owners[procedure.definition.name]
        owner_returns = workflow_return_types_for(source_program, procedure.definition.name,
            base_return_types=facts.base_workflow_return_types)
        owner_catalog = workflow_catalog_for(source_program, procedure.definition.name)
        owner_workflows = source_program.workflows
    child = replace(
        facts, type_env=env,
        local_type_bindings=(_procedure_signature_local_type_bindings(procedure) if facts.closed_program
            else {**facts.local_type_bindings, **_procedure_signature_local_type_bindings(procedure)}),
        active_procedure_calls=facts.active_procedure_calls | {procedure.signature.name},
        workflow_return_types=owner_returns,
        workflow_catalog=owner_catalog, workflows_by_name=owner_workflows,
        procedure_return_types=(_procedure_return_types(procedure, facts=facts, source_program=source_program) if facts.closed_program else facts.procedure_return_types),
    )
    body = procedure.typed_body
    if isinstance(body.expr, ex.NameExpr) and not isinstance(body.type_ref, (RecordTypeRef, UnionTypeRef)) and _direct_outputs_available(
        body.expr, result_type=body.type_ref, facts=child, local_values=values,
    ):
        return False, ("return",)
    return _expression_control_fact(body.expr, result_type=body.type_ref, facts=child, local_values=values)


def _check_procedure_cycle(procedure: Any, *, call: Any, facts: ControlFacts) -> None:
    from ..procedure_specialization import _value_compile_error as _compile_error

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


def projection_artifact_names(output_contracts: Mapping[str, Any]) -> dict[str, str]:
    """Select logical outputs without constructing runtime references."""
    if set(output_contracts) == {"__result__"}:
        return {"return": "__result__"}
    return {name: name for name in output_contracts}


def provider_capture_artifact_names(result_type: Any, *, capture_context: bool) -> dict[str, str] | None:
    from ..context_types import is_contextual_type

    if not capture_context or not is_contextual_type(result_type):
        return None
    return {"return__result": "result", "return__context": "context"}


def binding_projection_output_aliases(boundary_fields: tuple[Any, ...], *, whole_value: bool, pure_call_composition: bool) -> dict[str, str] | None:
    if whole_value or not boundary_fields or not pure_call_composition:
        return None
    return {
        f"return__{'__'.join(boundary.source_path[1:])}": boundary.generated_name
        for boundary in boundary_fields
    }


def selected_phase_scope(context_value: Any, *, phase_name: str, ctx_expr: Any, span: Any, form_path: tuple[str, ...]) -> tuple[Any, Mapping[str, Any]]:
    """Select phase metadata and target availability without deriving paths."""
    from ..phase import IMPLEMENTATION_ATTEMPT_PHASE_NAME, PHASE_TARGET_SPECS, PhaseScope
    from ..procedure_specialization import RUNTIME_REFERENCE
    from ..procedure_specialization import _value_compile_error as _compile_error

    if not isinstance(context_value, Mapping):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires the phase context to resolve from workflow inputs",
            span=ctx_expr.span, form_path=ctx_expr.form_path,
        )
    if "implementation_state_bundle_path" not in context_value:
        if not all(is_direct_reference(context_value.get(name)) for name in ("state-root", "artifact-root")):
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="`with-phase` lowering requires generic phase roots to resolve from workflow inputs",
                span=ctx_expr.span, form_path=ctx_expr.form_path,
            )
        return PhaseScope(context_record_name="PhaseCtx", phase_name=phase_name, target_types={}), {
            name: RUNTIME_REFERENCE for name in PHASE_TARGET_SPECS
        }
    if phase_name != IMPLEMENTATION_ATTEMPT_PHASE_NAME:
        raise _compile_error(
            code="phase_context_invalid",
            message="`with-phase` supports only the `implementation` phase in the legacy bridge",
            span=span, form_path=form_path,
        )
    return _selected_implementation_phase_scope(context_value, phase_name=phase_name, ctx_expr=ctx_expr)


def _selected_implementation_phase_scope(context_value: Mapping[str, Any], *, phase_name: str, ctx_expr: Any) -> tuple[Any, Mapping[str, Any]]:
    from ..phase import PhaseScope
    from ..procedure_specialization import _value_compile_error as _compile_error

    fields = {"execution-report": "execution_report_target", "progress-report": "progress_report_target"}
    if not all(is_direct_reference(context_value.get(name)) for name in ("implementation_state_bundle_path", *fields.values())):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires bound relpath fields on the phase context",
            span=ctx_expr.span, form_path=ctx_expr.form_path,
        )
    return PhaseScope(
        context_record_name="ImplementationAttemptPhaseCtx", phase_name=phase_name,
        bundle_path_field="implementation_state_bundle_path", target_fields=fields,
    ), {name: context_value[field] for name, field in fields.items()}


def helper_capture_names(expr: Any, *, local_type_bindings: Mapping[str, Any]) -> tuple[str, ...]:
    used_names: set[str] = set()

    def capture(name: str, bound_names: frozenset[str]) -> None:
        if name in local_type_bindings and name not in bound_names:
            used_names.add(name)

    def walk(node: Any, bound_names: frozenset[str]) -> None:
        if isinstance(node, NameExpr):
            capture(node.name, bound_names)
            return
        if isinstance(node, FieldAccessExpr) and isinstance(node.base, NameExpr):
            capture(node.base.name, bound_names)
            walk(node.base, bound_names)
            return
        if isinstance(node, LetStarExpr):
            child_bound = set(bound_names)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, frozenset(child_bound))
                child_bound.add(binding_name)
            walk(node.body, frozenset(child_bound))
            return
        # schema1_compatibility: legacy branch-local ref analysis walks authored match expressions.
        if isinstance(node, MatchExpr):
            walk(node.subject, bound_names)
            for arm in node.arms:
                walk(arm.body, bound_names | {arm.binding_name})
            return
        for child in iter_child_exprs(node):
            walk(child, bound_names)

    walk(expr, frozenset())
    return tuple(name for name in local_type_bindings if name in used_names)


def inline_output_boundary_fields(expr: Any, *, type_ref: Any, type_env: Any, signature: Any):
    from dataclasses import replace
    from ..contracts import derive_workflow_boundary_fields, root_workflow_boundary_field
    from ..syntax import target_dsl_supports_trial
    from ..type_env import RecordTypeRef

    allow_direct = (
        type_ref == signature.return_type_ref
        and isinstance(getattr(signature, "compiler_direct_result_contract_digest", None), str)
        and target_dsl_supports_trial(type_env.target_dsl_version)
    )
    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return derive_workflow_boundary_fields(
            type_ref, generated_name="return", source_path=("return",),
            span=expr.span, form_path=expr.form_path,
            allow_transportable_value=allow_direct, type_env=type_env,
        )
    return (replace(root_workflow_boundary_field(
        type_ref, span=expr.span, form_path=expr.form_path, type_env=type_env,
    ), generated_name="return"),)


WccBindingKind = Literal["alias", "expansion_projection", "whole_value", "request_projection", "if_projection"]
SurfaceBindingKind = Literal["match", "projection", "expression"]

def is_direct_reference(value: Any) -> bool:
    return isinstance(value, str) or value is RUNTIME_REFERENCE


def is_inline_let_binding_expr(expr: Any) -> bool:
    return isinstance(expr, (
        NameExpr, FieldAccessExpr, PhaseTargetExpr, LiteralExpr, RecordExpr,
        RecordUpdateExpr, LoopStateSeedExpr, LoopStateUpdateExpr, UnionVariantExpr,
        ProviderBundlePathExpr, ProcRefLiteralExpr, BindProcExpr, PureOpExpr,
    ))


def pure_projection_binding_candidate(resolved_binding: Any) -> Any | None:
    if isinstance(resolved_binding, RetainedExpressionFact):
        return resolved_binding if resolved_binding.projection_candidate else None
    if resolved_binding is None or is_direct_reference(resolved_binding) or isinstance(resolved_binding, Mapping):
        return None
    return resolved_binding if is_pure_projection_expr(resolved_binding) else None


def surface_binding_materialization(
    expr: Any, *, resolved_binding: Any,
) -> tuple[SurfaceBindingKind, Any]:
    if isinstance(expr, MatchExpr):
        return "match", expr
    candidate = pure_projection_binding_candidate(resolved_binding)
    if candidate is not None:
        return "projection", candidate
    return "expression", expr


def wcc_binding_materialization(
    expr: Any, *, expansion_owned: bool, existing_ref: Any, resolved_binding: Any,
    run_ref_demand: bool, provider_context_demand: bool, request_input_demand: bool,
) -> tuple[WccBindingKind, Any]:
    """Preserve owner priority without constructing steps or reference strings.

    ``resolved_binding`` is the existing resolver's result, consulted only
    outside the expansion-owned projection branch. ``existing_ref`` is the
    owner's already available Name binding, never a reconstructed projection.
    """
    if expansion_owned and is_pure_projection_expr(expr):
        if isinstance(expr, NameExpr) and is_direct_reference(existing_ref):
            return "alias", existing_ref
        return "expansion_projection", expr
    return _wcc_resolved_binding_materialization(
        expr, resolved_binding=resolved_binding, run_ref_demand=run_ref_demand,
        provider_context_demand=provider_context_demand,
        request_input_demand=request_input_demand,
    )


def _wcc_resolved_binding_materialization(
    expr: Any, *, resolved_binding: Any, run_ref_demand: bool,
    provider_context_demand: bool, request_input_demand: bool,
) -> tuple[WccBindingKind, Any]:
    if is_pure_projection_expr(expr):
        if run_ref_demand:
            resolved_binding = expr
        if provider_context_demand and _provider_context_requires_whole_value(expr, resolved_binding):
            return "whole_value", expr
        if request_input_demand:
            if is_direct_reference(resolved_binding) or isinstance(resolved_binding, LiteralExpr):
                return "alias", resolved_binding
            return "request_projection", expr
    if isinstance(expr, IfExpr):
        candidate = pure_projection_binding_candidate(resolved_binding)
        if candidate is not None:
            return "if_projection", candidate
    return "alias", resolved_binding


def _provider_context_requires_whole_value(expr: Any, resolved_binding: Any) -> bool:
    return not isinstance(expr, FieldAccessExpr) or isinstance(resolved_binding, Mapping)


def _wcc_continuation_binding_demands(
    root: WccBody,
) -> dict[int, tuple[frozenset[str], frozenset[str], frozenset[str]]]:
    """Collect the operation operands demanded by every immutable WCC body.

    ANF lowering consults the demand set for a ``WccLet`` continuation only.
    Keeping the lookup local to this one lowering call avoids repeatedly
    walking the same nested continuation for every earlier binding.
    """

    empty = (frozenset(), frozenset(), frozenset())
    by_body_id: dict[
        int,
        tuple[frozenset[str], frozenset[str], frozenset[str]],
    ] = {}

    def merge(
        *demands: tuple[frozenset[str], frozenset[str], frozenset[str]],
    ) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        if not demands:
            return empty
        merged = demands[0]
        for incoming in demands[1:]:
            fields = tuple(
                existing
                if incoming_field.issubset(existing)
                else incoming_field
                if existing.issubset(incoming_field)
                else existing | incoming_field
                for existing, incoming_field in zip(merged, incoming, strict=True)
            )
            if all(field is existing for field, existing in zip(fields, merged, strict=True)):
                continue
            if all(field is incoming_field for field, incoming_field in zip(fields, incoming, strict=True)):
                merged = incoming
                continue
            merged = fields  # type: ignore[assignment]
        return merged

    def referenced_names(value: object) -> frozenset[str]:
        if isinstance(value, WccNameAtom):
            return frozenset((value.name,))
        if isinstance(value, Mapping):
            return frozenset().union(
                *(referenced_names(item) for item in value.values())
            )
        if isinstance(value, (tuple, list)):
            return frozenset().union(*(referenced_names(item) for item in value))
        if is_dataclass(value):
            return frozenset().union(
                *(referenced_names(getattr(value, field_info.name)) for field_info in fields(value))
            )
        return frozenset()

    def perform_demand(
        value: WccPerform,
    ) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        if value.perform_kind == "run_ref":
            # A confined site's `:commit` operand is its sole positional argument.
            return (referenced_names((value.positional_args, value.keyword_args)), frozenset(), frozenset())
        if value.perform_kind == "provider_result":
            payload = value.operation_payload
            context_expr = (
                payload.get("context_expr") if isinstance(payload, Mapping) else None
            )
            return (frozenset(), referenced_names(context_expr), frozenset())
        if value.perform_kind == "request_input":
            return (frozenset(), frozenset(), referenced_names(value.positional_args))
        return empty

    def value_demand(
        value: object,
    ) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        if isinstance(value, WccPerform):
            return perform_demand(value)
        if isinstance(value, (WccLet, WccCase, WccIf, WccJoin, WccRecJoin, WccParallelMap, WccHalt, WccJump, WccLoopContinue, WccLoopDone)):
            return body_demand(value)
        if isinstance(value, Mapping):
            return merge(*(value_demand(item) for item in value.values()))
        if isinstance(value, (tuple, list)):
            return merge(*(value_demand(item) for item in value))
        if is_dataclass(value):
            return merge(
                *(value_demand(getattr(value, field_info.name)) for field_info in fields(value))
            )
        return empty

    def terminal_demand(body: WccBody) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        if isinstance(body, WccLoopContinue):
            return value_demand(body.state_args)
        if isinstance(body, WccLoopDone):
            return merge(value_demand(body.result), value_demand(body.state))
        if isinstance(body, WccJump):
            return value_demand(body.args)
        return value_demand(body.result)

    def body_demand(
        body: WccBody,
    ) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        existing = by_body_id.get(id(body))
        if existing is not None:
            return existing
        if isinstance(body, WccLet):
            demand = merge(value_demand(body.bound_value), body_demand(body.body))
        elif isinstance(body, WccCase):
            demand = merge(
                value_demand(body.subject),
                *(body_demand(arm.body) for arm in body.arms),
            )
        elif isinstance(body, WccIf):
            demand = merge(
                value_demand(body.condition),
                body_demand(body.then_body),
                body_demand(body.else_body),
            )
        elif isinstance(body, WccJoin):
            demand = merge(body_demand(body.body), body_demand(body.continuation))
        elif isinstance(body, WccParallelMap):
            demand = merge(value_demand(body.source),
                body_demand(body.workspace_body), body_demand(body.body))
        elif isinstance(body, WccRecJoin):
            demand = merge(
                value_demand(body.budget),
                value_demand(body.initial_state),
                body_demand(body.body),
                value_demand(body.exhaustion),
            )
        else:
            demand = terminal_demand(body)
        by_body_id[id(body)] = demand
        return demand

    body_demand(root)
    return by_body_id


def direct_output_leaves_available(leaf_availability: Iterable[bool]) -> bool:
    """A shortcut requires availability of every projected boundary leaf."""
    return all(leaf_availability)


def compiler_owned_pure_let(expr: Any, *, target_dsl_version: str) -> bool:
    from ..expression_traversal import walk_expr
    from ..syntax import ProcedureExpansionFrame, target_dsl_supports_pure_call_composition

    return (
        target_dsl_supports_pure_call_composition(target_dsl_version)
        and any(isinstance(frame, ProcedureExpansionFrame) for node in walk_expr(expr) for frame in node.expansion_stack)
        and is_pure_projection_expr(expr)
    )


_CALL_CHILD_FIELDS = {
    w.WccLet: ("bound_value", "body"),
    w.WccIf: ("condition", "then_body", "else_body"),
    w.WccJoin: ("body", "continuation"),
    w.WccJump: ("args",),
    w.WccRecJoin: ("budget", "initial_state", "body", "exhaustion"),
    w.WccParallelMap: ("source", "workspace_body", "body"),
    w.WccLoopContinue: ("state_args",),
    w.WccLoopDone: ("result", "state"),
    w.WccHalt: ("result",),
    w.WccCall: ("args", "specialization_captures"),
    w.WccSpecializationCapture: ("value",),
    w.WccPerform: ("positional_args", "keyword_args"),
    w.WccSelect: ("condition", "then_arm", "else_arm"),
    w.WccFieldAccessAtom: ("base",),
    w.WccRecordAtom: ("fields",),
    w.WccInject: ("fields",),
    w.WccPureOp: ("args",),
    w.WccOpaqueFrontendValue: ("normalized_body",),
    w.WccProviderSupervision: ("settlement_body",),
    w.WccProviderPeerGroup: ("settlement_body",),
}


def _wcc_call_nodes(node, variants=()):
    """The owner's ordinary semantic edges, excluding source and child capsules."""
    if isinstance(node, w.WccCase):
        yield from _wcc_call_nodes(node.subject, variants)
        for arm in node.arms:
            yield from _wcc_call_nodes(arm.body, (*variants, arm.variant_name))
        return
    if isinstance(node, w.WccSelectArm):
        for binding in node.prefix:
            yield from _wcc_call_nodes(binding.bound_value, variants)
        yield from _wcc_call_nodes(node.value, variants)
        return
    if isinstance(node, (tuple, list)):
        for child in node:
            yield from _wcc_call_nodes(child, variants)
        return
    for field in _CALL_CHILD_FIELDS.get(type(node), ()):
        yield from _wcc_call_nodes(getattr(node, field), variants)
    if isinstance(node, w.WccCall) or isinstance(node, w.WccPerform) and node.perform_kind == "workflow_call":
        yield node, variants


def _call_coordinate(call, variants):
    return call.metadata.scope_id, call.metadata.node_id, tuple(variants)


def command_call_occurrences(body, call_declaration_identity):
    """Index coordinates only; no lexical facts or requests enter this table."""
    result, counts = {}, {}
    for call, variants in _wcc_call_nodes(body):
        coordinate = _call_coordinate(call, variants)
        if coordinate in result:
            raise ValueError("command call has a duplicated WCC coordinate")
        did = call_declaration_identity(call)
        encoded = _canonical_json(did)
        occurrence = counts.get(encoded, 0)
        counts[encoded] = occurrence + 1
        result[coordinate] = (did, occurrence)
    return result


def _call_preparation_callbacks(neutral, resolver, preparator):
    if preparator is None:
        return None, lambda final: None
    if resolver is None:
        raise ValueError("command call preparation requires its declaration resolver")
    inventory = command_call_occurrences(neutral, resolver)
    consumed = set()

    def consume(expr, call, context, actual_values, *, variants):
        coordinate = _call_coordinate(call, variants)
        if coordinate not in inventory or coordinate in consumed:
            raise ValueError("command call callback is unknown or repeated")
        consumed.add(coordinate)
        preparator(inventory[coordinate], expr, call, context, actual_values)

    def verify(final):
        if consumed != inventory.keys() or command_call_occurrences(final, resolver) != inventory:
            raise ValueError("command call preparation does not cover its final WCC inventory")

    return consume, verify


def binding_demand_key(metadata, variants):
    """The actual WCC binder, inside its existing variant frame."""
    return (variants, metadata.scope_id, metadata.node_id, metadata.binding_identity)


def _children(node):
    if isinstance(node, Mapping):
        return node.values()
    if isinstance(node, (tuple, list)):
        return node
    if is_dataclass(node):
        return (getattr(node, field.name) for field in fields(node)
            if field.name not in {"metadata", "bound_type_ref", "binding_type_ref", "command_scope"})
    return ()


def continuation_binding_demands(body):
    """Project only the three demand bits from the ordinary neutral ANF."""
    scanned = _wcc_continuation_binding_demands(body)
    result = {}

    def record_binding_demand(node, variants):
        if isinstance(node, WccLet):
            names = (node.bound_name,)
            continuation = node.body
        elif isinstance(node, WccJoin):
            names = tuple(param.name for param in node.params)
            continuation = node.continuation
        else:
            return
        for name in names:
            key = (*binding_demand_key(node.metadata, variants), name)
            result.setdefault(key[:-1], []).append((name, tuple(name in demand for demand in scanned[id(continuation)])))

    def visit(node, variants=()):
        record_binding_demand(node, variants)
        if isinstance(node, WccCase):
            visit(node.subject, variants)
            for arm in node.arms:
                visit(arm.body, (*variants, arm.variant_name))
            return
        if isinstance(node, w.WccSelectArm):
            for binding in node.prefix:
                record_binding_demand(binding, variants)
                visit(binding.bound_value, variants)
            visit(node.value, variants)
            return
        for child in _children(node):
            visit(child, variants)

    visit(body)
    return result


def runtime_binding_value(type_ref, *, facts, span, form_path):
    if isinstance(type_ref, UnionTypeRef):
        return _union_runtime_value(type_ref, facts=facts, span=span, form_path=form_path)
    if isinstance(type_ref, (RecordTypeRef, VariantCaseTypeRef)):
        return {field.name: runtime_binding_value(facts.type_env.record_field(
            type_ref, field.name, span=span, form_path=form_path),
            facts=facts, span=span, form_path=form_path) for field in type_ref.definition.fields}
    return RUNTIME_REFERENCE


def _runtime_shape(value):
    if isinstance(value, Mapping):
        return tuple((name, _runtime_shape(child)) for name, child in value.items())
    return None


def _union_runtime_value(type_ref, *, facts, span, form_path):
    values, conflicts = {}, set()
    for fields in type_ref.variant_field_types.values():
        for name, field_type in fields.items():
            value = runtime_binding_value(field_type, facts=facts, span=span, form_path=form_path)
            if name in values and _runtime_shape(values[name]) != _runtime_shape(value):
                conflicts.add(name)
            values.setdefault(name, value)
    return {"variant": RUNTIME_REFERENCE, **{name: value for name, value in values.items() if name not in conflicts}}


def _proven_runtime_value(value, old_type, new_type, *, control, operand):
    if not isinstance(old_type, UnionTypeRef) or not isinstance(new_type, VariantCaseTypeRef) or not isinstance(value, Mapping):
        return value
    payload = runtime_binding_value(new_type, facts=control,
        span=operand.metadata.source_span, form_path=operand.metadata.form_path)
    return {name: value.get(name, runtime) for name, runtime in payload.items()}


def _runtime_capture_names(expr, *, types, values):
    from ..wcc.elaborate import _is_compile_time_reference_value

    return tuple(name for name in helper_capture_names(expr, local_type_bindings=types)
        if not _is_compile_time_reference_value(values.get(name)))


def _initial_bindings(typed_body, *, inputs, scope, facts, procedure_edges, local_values):
    from ..wcc.elaborate import _elaborate_atomic_value, _is_compile_time_reference_value

    compile_time = inputs.get("compile_time_bindings", {})
    operands, values = {}, dict(compile_time)
    for name, type_ref in inputs["value_env"].items():
        if name in compile_time:
            if _is_compile_time_reference_value(compile_time[name]):
                continue
            operands[name] = _elaborate_atomic_value(compile_time[name], scope=scope,
                type_env=facts.type_env, value_env=inputs["value_env"],
                workflow_return_types=facts.workflow_return_types,
                procedure_return_types=facts.procedure_return_types,
                effect_summary=typed_body.effect_summary, procedure_edges_by_site=procedure_edges,
                compile_time_bindings=compile_time)
            continue
        operands[name] = WccNameAtom(metadata=scope.atom_metadata(role=f"name:{name}", type_ref=type_ref,
            source_span=typed_body.expr.span, form_path=typed_body.expr.form_path,
            binding_identity=typed_body.binding_environment.get(name)), name=name)
        values[name] = runtime_binding_value(type_ref, facts=facts,
            span=typed_body.expr.span, form_path=typed_body.expr.form_path)
    values = {name: _resolve_inline_expr_value(value, local_values=values, retain_expression_facts=True)
        for name, value in values.items()}
    values.update(local_values or {})
    return operands, values


def command_loop_index_name(loop_name):
    """One unspellable compiler binder owned by the existing WCC loop."""
    return f"\0command-index:{loop_name}"


def command_parallel_index_name(node_id):
    """An item index uses the existing command index namespace."""
    return command_loop_index_name(node_id)


def _command_slot(expression, *, roots, source_program, index):
    from orchestrator.variables.substitution import parse_variable_expression
    from orchestrator.workflow.type_descriptor import command_boundary_row

    path, filters = parse_variable_expression(expression)
    if path == "loop.index" and index is not None:
        return {"kind": "slot", "name": ["loop-index"], "path": [],
            "filters": list(filters), "value": index}
    if not path.startswith("inputs."):
        return {"kind": "missing", "expression": expression}
    native_wire, *suffix = path[len("inputs."):].split(".")
    for source_formal, operand in roots:
        descriptor = canonical_type_descriptor(operand.metadata.type_ref, typed=source_program)
        if command_boundary_row(source_formal, descriptor, native_wire) is not None:
            return {"kind": "slot", "name": ["input", source_formal, native_wire],
                "path": suffix, "filters": list(filters), "value": operand}
    return {"kind": "missing", "expression": expression}


def _literal_command_plan(literal, *, roots, source_program, index):
    from orchestrator.variables.substitution import _ESCAPED_DOLLAR, tokenize_template

    parts = []
    for is_expression, token in tokenize_template(str(literal)):
        if is_expression:
            parts.append(_command_slot(token, roots=roots, source_program=source_program, index=index))
        else:
            text = token.replace(_ESCAPED_DOLLAR, "$")
            if text:
                if parts and parts[-1]["kind"] == "text":
                    parts[-1]["text"] += text
                else:
                    parts.append({"kind": "text", "text": text})
    return {"kind": "template", "parts": parts}


@dataclass(frozen=True)
class CommandScopeContext:
    control: object
    values: Mapping
    operands: Mapping
    demands: Mapping
    owner: str
    retained_bindings: tuple = ()
    include_command_plans: bool = False
    source_program: object = None
    command_bindings: object = None
    command_roots: tuple = ()
    command_index: object = None
    call_preparator: object = None
    io_routes: object = None
    io_bind: object = None

    def prepare_call(self, expr, call, *, variants, procedure_arguments=None):
        from ..wcc.anf import _normalize_call, _normalize_perform
        from ..wcc.model import WccCall

        if self.call_preparator is None:
            return
        if isinstance(call, WccCall):
            _, normalized = _normalize_call(call)
            expressions = tuple(argument for _, argument in procedure_arguments)
            original_args, normalized_args = call.args, normalized.args
        else:
            _, normalized = _normalize_perform(call)
            expressions = tuple(value for _, value in expr.bindings)
            original_args = tuple(value for _, value in call.keyword_args)
            normalized_args = tuple(value for _, value in normalized.keyword_args)
        actual_values = tuple(
            _resolve_inline_expr_value(argument, local_values=self.values, retain_expression_facts=True)
            if original == operand else runtime_binding_value(operand.metadata.type_ref,
                facts=self.control, span=argument.span, form_path=argument.form_path)
            for argument, original, operand in zip(expressions, original_args, normalized_args, strict=True))
        self.call_preparator(expr, normalized, self, actual_values, variants=variants)

    def plan_command(self, expr, perform):
        from ..expressions import LiteralExpr
        from ..wcc.anf import _normalize_perform

        if not self.include_command_plans:
            return perform
        payload = perform.operation_payload
        if payload["adapter_name"] is not None:
            plans = []
        else:
            binding = self.command_bindings[perform.target_name]
            offset = len(binding.stable_command)
            _, normalized = _normalize_perform(perform)
            plans = []
            for index in range(offset, len(perform.positional_args)):
                operand = perform.positional_args[index]
                resolved = _resolve_inline_expr_value(expr.argv[index], local_values=self.values, retain_expression_facts=True)
                if normalized.positional_args[index] != operand or not isinstance(resolved, LiteralExpr):
                    plans.append({"kind": "value"})
                else:
                    plans.append(_literal_command_plan(resolved.value,
                        roots=self.command_roots, source_program=self.source_program,
                        index=self.command_index))
        return replace(perform, operation_payload={**payload, "argv_transport": plans})

    def narrow(self, value_env):
        types = {name: value_env.get(name, type_ref) for name, type_ref in self.control.local_type_bindings.items()}
        operands = dict(self.operands)
        values = dict(self.values)
        control = replace(self.control, local_type_bindings=types)
        retained = list(self.retained_bindings)
        for name, type_ref in types.items():
            operand = operands.get(name)
            if operand is None or operand.metadata.type_ref == type_ref:
                continue
            original = next(row for row in reversed(retained) if row[4] == operand)
            values[name] = _proven_runtime_value(values[name], operand.metadata.type_ref, type_ref,
                control=control, operand=operand)
            operand = replace(operand, metadata=replace(operand.metadata, type_ref=type_ref))
            operands[name] = operand
            retained.append((original[0],
                operand.metadata.binding_identity, type_ref, values[name], operand))
        return replace(self, control=control, values=values,
            operands=operands, retained_bindings=tuple(retained))

    def compile_time_bind(self, expr, *, name, type_ref):
        _, value, _ = _binding_control_fact(expr, name=name, facts=self.control, local_values=self.values)
        routes = {} if self.io_routes is None else dict(self.io_routes)
        if self.io_bind is not None:
            routes[name] = self.io_bind(expr, routes)
        return replace(self, values={**self.values, name: value},
            io_routes=routes,
            control=replace(self.control, local_type_bindings={**self.control.local_type_bindings, name: type_ref}))

    def binding_demands(self, metadata, variants):
        key = binding_demand_key(metadata, variants)
        matches = self.demands.get(key, ())
        if len(matches) != 1:
            raise ValueError("command continuation has no unique retained WCC binder")
        return matches[0][1]

    def bind(self, expr, *, name, type_ref, operand, metadata, variants, expansion_owned=False, capture_source=None):
        demands = self.binding_demands(metadata, variants)
        if capture_source is not None:
            source_identity, source_type = capture_source
            matches = (row for row in reversed(self.retained_bindings)
                if row[1] == source_identity and row[2] == source_type)
            retained = next(matches, None)
            if retained is None:
                raise ValueError("command capture has no retained binder in its lexical frame")
            value = retained[3]
        elif self.owner in {"surface", "loop"}:
            _, value, _ = _binding_control_fact(expr, name=name, facts=self.control,
                local_values=self.values, capture_source=capture_source)
        else:
            value = self._wcc_binding_value(expr, demands=demands, expansion_owned=expansion_owned)
        if value is None:
            value = runtime_binding_value(type_ref, facts=self.control, span=expr.span, form_path=expr.form_path)
        return replace(self,
            control=replace(self.control, local_type_bindings={**self.control.local_type_bindings, name: type_ref}),
            values={**self.values, name: value}, operands={**self.operands, name: operand},
            retained_bindings=(*self.retained_bindings,
                (binding_demand_key(metadata, variants), metadata.binding_identity, type_ref, value, operand)))

    def _wcc_binding_value(self, expr, *, demands, expansion_owned):
        from ..conditionals import _contains_effect
        from ..expressions import NameExpr
        from ..expression_traversal import is_pure_projection_expr

        if _contains_effect(expr):
            return None
        resolved = None if expansion_owned and is_pure_projection_expr(expr) else _resolve_inline_expr_value(expr, local_values=self.values, retain_expression_facts=True)
        kind, value = wcc_binding_materialization(expr, expansion_owned=expansion_owned,
            existing_ref=self.values.get(expr.name) if isinstance(expr, NameExpr) else None,
            resolved_binding=resolved, run_ref_demand=demands[0],
            provider_context_demand=demands[1], request_input_demand=demands[2])
        return value if kind == "alias" else None

    def arm(self, expr, *, result_type, name, type_ref, operand, value_env):
        from ..wcc.elaborate import _is_compile_time_reference_value

        types = {**self.control.local_type_bindings, name: type_ref}
        control = replace(self.control, local_type_bindings=types)
        value = runtime_binding_value(type_ref, facts=control, span=expr.span, form_path=expr.form_path)
        child = replace(self, control=control, values={**self.values, name: value},
            operands={**self.operands, name: operand}, retained_bindings=(*self.retained_bindings,
                (binding_demand_key(operand.metadata, (type_ref.variant_name,)),
                    operand.metadata.binding_identity, type_ref, value, operand)))
        if self.owner != "surface" or not branch_control_summary(
            expr, result_type=result_type, facts=control, local_values=child.values,
        ):
            return None, child
        names = _runtime_capture_names(expr, types=types, values=child.values)
        roots = tuple((name, child.operands[name]) for name in names)
        values = {name: value for name, value in child.values.items() if _is_compile_time_reference_value(value)}
        values.update({name: runtime_binding_value(value_env[name], facts=control,
            span=expr.span, form_path=expr.form_path) for name in names})
        operands = dict(roots)
        retained = tuple((binding_demand_key(operand.metadata, (type_ref.variant_name,)),
            operand.metadata.binding_identity, value_env[name], values[name], operand)
            for name, operand in roots)
        return roots, replace(child, values=values, operands=operands, retained_bindings=retained,
            command_roots=roots, command_index=None,
            control=replace(control, local_type_bindings={name: value_env[name] for name in names},
                iteration_scope=None, workflow_name=f"%composition.{control.workflow_name}"))


def _validate_command_scope_inputs(producer_lowering_schema, closed_program,
    include_command_plans, source_program, command_bindings):
    if type(producer_lowering_schema) is not int or producer_lowering_schema not in (1, 2):
        raise ValueError("command scope analysis requires the producer's schema 1 or 2")
    if not closed_program:
        raise ValueError("command scope analysis requires closed elaboration")
    if include_command_plans and (source_program is None or command_bindings is None):
        raise ValueError("command plans require the exact source and command binding owner")


def elaborate_command_scopes(typed_body, *, incoming_command_facts,
    producer_lowering_schema, local_values=None, include_command_plans=False,
    source_program=None, command_bindings=None, command_roots=None,
    call_preparator=None, call_declaration_identity=None, command_root_names=None,
    command_index_name=None, io_routes=None, io_bind=None, capture_source_bindings=(), **elaboration_inputs):
    """Elaborate the exact same owner twice; only the second selects arm scopes."""
    from ..wcc.elaborate import elaborate_typed_workflow_body, prepare_elaboration_call_types
    from ..wcc.model import WccIdentityFactory

    _validate_command_scope_inputs(
        producer_lowering_schema, elaboration_inputs.get("closed_program"),
        include_command_plans, source_program, command_bindings,
    )
    inputs = dict(elaboration_inputs)
    inputs.update(workflow_catalog=incoming_command_facts.workflow_catalog,
        typed_workflows_by_name=incoming_command_facts.workflows_by_name)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(typed_body, **inputs))
    prepare_call, verify_calls = _call_preparation_callbacks(neutral, call_declaration_identity, call_preparator)
    edges, returns = prepare_elaboration_call_types(typed_body,
        resolved_procedures_by_name=inputs.get("resolved_procedures_by_name"),
        procedure_return_types=inputs.get("procedure_return_types"), closed_program=True)
    facts = replace(incoming_command_facts, closed_program=True,
        local_type_bindings=dict(inputs["value_env"]),
        workflow_return_types=inputs.get("workflow_return_types", {}), procedure_return_types=returns)
    scope = WccIdentityFactory(owner_name=inputs["owner_name"], lexical_owner_chain=("workflow",),
        route_schema_version=inputs["route_schema_version"], closed_program=True)
    operands, values = _initial_bindings(typed_body, inputs=inputs, scope=scope,
        facts=facts, procedure_edges=edges, local_values=local_values)
    if command_root_names is not None:
        command_roots = tuple((formal, operands[name]) for formal, name in command_root_names.items())
    retained = tuple((binding_demand_key(operand.metadata, ()), typed_body.binding_environment.get(name),
        inputs["value_env"][name], values[name], operand) for name, operand in operands.items())
    for name, identity, type_ref in capture_source_bindings:
        if identity is None or name not in operands or inputs["value_env"].get(name) != type_ref:
            raise ValueError("capture source frame seed has no exact typed slot")
        operand = operands[name]
        retained += ((binding_demand_key(operand.metadata, ()), identity,
            type_ref, values[name], operand),)
    context = CommandScopeContext(facts, values, operands, continuation_binding_demands(neutral),
        "surface" if producer_lowering_schema == 1 else "wcc", retained,
        include_command_plans=include_command_plans, source_program=source_program,
        command_bindings=command_bindings,
        command_roots=tuple(operands.items()) if command_roots is None else command_roots,
        command_index=operands.get(command_index_name),
        call_preparator=prepare_call, io_routes=io_routes or {}, io_bind=io_bind)
    annotated = elaborate_typed_workflow_body(typed_body, **inputs, command_scope_context=context)
    result = normalize_wcc_body_to_anf(annotated)
    verify_calls(result)
    return result
