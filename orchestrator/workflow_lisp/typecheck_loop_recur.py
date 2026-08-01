"""Bounded loop/recur typecheck ownership for Workflow Lisp."""

from __future__ import annotations

from dataclasses import replace

from .effects import (
    EMPTY_EFFECT_SUMMARY,
    EffectSummary,
    effect_summary_contains_runs_ref,
    merge_effect_summaries,
)
from .expressions import LoopRecurExpr
from .loops import LoopControlTypeRef, ensure_loop_projectable_type
from .type_env import PrimitiveTypeRef
from .typecheck_context import (
    LoopTypecheckContext,
    TypecheckContext,
    TypedExpr,
    _type_label,
    raise_error,
    raise_run_ref_placement_invalid,
)
from .typecheck_proofs import ProofScope


def typecheck_loop_recur_expr(
    expr: LoopRecurExpr,
    *,
    context: TypecheckContext,
    recurse,
    check,
    typed_factory,
) -> TypedExpr:
    """Typecheck one bounded loop while preserving the shared session stack."""

    type_env = context.type_env
    value_env = context.value_env
    workflow_catalog = context.workflow_catalog
    procedure_catalog = context.procedure_catalog
    extern_environment = context.extern_environment
    command_boundary_environment = context.command_boundary_environment
    active_phase_scope = context.active_phase_scope
    procedure_effects_by_name = context.procedure_effects_by_name
    workflow_effects_by_name = context.workflow_effects_by_name
    proc_ref_resolution_context = context.proc_ref_resolution_context
    prompt_catalog = context.prompt_catalog
    session_state = context.session_state

    typed_max = recurse(expr.max_iterations_expr)
    if effect_summary_contains_runs_ref(typed_max.effect_summary):
        raise_run_ref_placement_invalid(
            typed_max.expr,
            reason="is not permitted in `loop/recur` :max",
        )
    if typed_max.type_ref != PrimitiveTypeRef(name="Int"):
        raise_error(
            "`loop/recur :max` must resolve to `Int`",
            code="loop_recur_max_invalid",
            span=expr.max_iterations_expr.span,
            form_path=expr.max_iterations_expr.form_path,
        )
    typed_state = recurse(expr.initial_state_expr)
    if effect_summary_contains_runs_ref(typed_state.effect_summary):
        raise_run_ref_placement_invalid(
            typed_state.expr,
            reason="is not permitted in `loop/recur` state",
        )
    ensure_loop_projectable_type(
        typed_state.type_ref,
        code="loop_recur_state_type_invalid",
        span=expr.initial_state_expr.span,
        form_path=expr.initial_state_expr.form_path,
    )
    session_state.loop_context.append(
        LoopTypecheckContext(state_type_ref=typed_state.type_ref)
    )
    try:
        typed_body = recurse(
            expr.body_expr,
            value_env={**value_env, expr.binding_name: typed_state.type_ref},
            proof_scope=ProofScope(facts={}),
        )
    finally:
        session_state.loop_context.pop()
    if effect_summary_contains_runs_ref(typed_body.effect_summary):
        raise_run_ref_placement_invalid(
            typed_body.expr,
            reason="is not permitted in a `loop/recur` body",
        )
    if not isinstance(typed_body.type_ref, LoopControlTypeRef):
        raise_error(
            "`loop/recur` body must terminate with `continue` or `done`",
            code="loop_recur_missing_done",
            span=expr.body_expr.span,
            form_path=expr.body_expr.form_path,
        )
    if typed_body.type_ref.result_type_ref is None:
        raise_error(
            "`loop/recur` body must contain at least one reachable `done`",
            code="loop_recur_missing_done",
            span=expr.body_expr.span,
            form_path=expr.body_expr.form_path,
        )
    ensure_loop_projectable_type(
        typed_body.type_ref.result_type_ref,
        code="loop_recur_result_type_invalid",
        span=expr.body_expr.span,
        form_path=expr.body_expr.form_path,
    )
    exhaustion_summaries: list[EffectSummary] = []
    typed_exhausted_expr = None
    if expr.on_exhausted_result_expr is not None:
        typed_exhausted = check(
            expr.on_exhausted_result_expr,
            type_env=type_env,
            value_env={**value_env, expr.binding_name: typed_state.type_ref},
            proof_scope=ProofScope(facts={}),
            workflow_catalog=workflow_catalog,
            procedure_catalog=procedure_catalog,
            extern_environment=extern_environment,
            command_boundary_environment=command_boundary_environment,
            active_phase_scope=active_phase_scope,
            procedure_effects_by_name=procedure_effects_by_name,
            workflow_effects_by_name=workflow_effects_by_name,
            proc_ref_resolution_context=proc_ref_resolution_context,
            prompt_catalog=prompt_catalog,
        )
        if effect_summary_contains_runs_ref(typed_exhausted.effect_summary):
            raise_run_ref_placement_invalid(
                typed_exhausted.expr,
                reason="is not permitted in `loop/recur` exhaustion",
            )
        if typed_exhausted.type_ref != typed_body.type_ref.result_type_ref:
            raise_error(
                f"`loop/recur` exhaustion result expected `{_type_label(typed_body.type_ref.result_type_ref)}`"
                f" but got `{_type_label(typed_exhausted.type_ref)}`",
                code="loop_recur_done_type_mismatch",
                span=expr.on_exhausted_result_expr.span,
                form_path=expr.on_exhausted_result_expr.form_path,
            )
        if typed_exhausted.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise_error(
                "`loop/recur` exhaustion projection must be pure",
                code="loop_recur_contract_invalid",
                span=expr.on_exhausted_result_expr.span,
                form_path=expr.on_exhausted_result_expr.form_path,
            )
        exhaustion_summaries.append(typed_exhausted.effect_summary)
        typed_exhausted_expr = typed_exhausted.expr
    return typed_factory(
        expr=replace(
            expr,
            max_iterations_expr=typed_max.expr,
            initial_state_expr=typed_state.expr,
            body_expr=typed_body.expr,
            on_exhausted_result_expr=typed_exhausted_expr,
        ),
        type_ref=typed_body.type_ref.result_type_ref,
        effect=merge_effect_summaries(
            typed_max.effect_summary,
            typed_state.effect_summary,
            typed_body.effect_summary,
            *exhaustion_summaries,
        ),
    )
