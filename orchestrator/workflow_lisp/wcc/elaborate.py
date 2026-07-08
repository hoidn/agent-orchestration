"""Elaboration from typed frontend expressions into Workflow Core Calculus."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ..conditionals import classify_condition_expr
from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..effects import EffectSummary
from ..expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MaterializeViewExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    PureOpExpr,
    ProduceOneOfExpr,
    ProcedureCallExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
)
from ..type_env import (
    FrontendTypeEnvironment,
    OptionalTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    VariantCaseTypeRef,
    type_refs_compatible,
)
from ..typecheck_context import TypedExpr
from ..loops import LoopControlTypeRef
from ..loop_state import carrier_metadata_for_expr
from ..lowering.pure_projection import is_pure_projection_expr
from ..workflows import TypedWorkflowDef
from .model import (
    WccBody,
    WccCase,
    WccCaseArm,
    WccCall,
    WccFieldAccessAtom,
    WccHalt,
    WccIdentityFactory,
    WccIf,
    WccInject,
    WccJoin,
    WccJoinParam,
    WccJump,
    WccLet,
    WccLiteralAtom,
    WccLoopContinue,
    WccLoopDone,
    WccNameAtom,
    WccOpaqueFrontendValue,
    WccPhaseScope,
    WccPhaseTargetAtom,
    WccPerform,
    WccPureOp,
    WccProduceOneOfPayload,
    WccRecJoin,
    WccRecordAtom,
    WccResumeOrStartPayload,
    WccRunProviderPhasePayload,
    WccValue,
)


def elaborate_typed_workflow_body(
    typed_body: TypedExpr,
    *,
    owner_name: str,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef] | None = None,
    procedure_return_types: Mapping[str, TypeRef] | None = None,
    route_schema_version: str | None = None,
) -> WccBody:
    """Elaborate one typed workflow body into WCC."""

    scope = WccIdentityFactory(
        owner_name=owner_name,
        lexical_owner_chain=("workflow",),
        route_schema_version=route_schema_version or WccIdentityFactory.route_schema_version,
    )
    procedure_edges_by_site = {
        (edge.span, edge.form_path): edge.callee_name
        for edge in typed_body.effect_summary.procedure_edges
        if edge.span is not None
    }
    return _elaborate_expr_to_body(
        typed_body.expr,
        scope=scope,
        type_env=type_env,
        value_env=dict(value_env),
        workflow_return_types=dict(workflow_return_types or {}),
        procedure_return_types=dict(procedure_return_types or {}),
        effect_summary=typed_body.effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings={},
    )


def elaborate_typed_workflow(
    typed_workflow: TypedWorkflowDef,
    *,
    type_env: FrontendTypeEnvironment,
    workflow_return_types: Mapping[str, TypeRef] | None = None,
    procedure_return_types: Mapping[str, TypeRef] | None = None,
    route_schema_version: str | None = None,
) -> WccBody:
    """Convenience wrapper for elaborating one typed workflow definition."""

    return elaborate_typed_workflow_body(
        typed_workflow.typed_body,
        owner_name=typed_workflow.definition.name,
        type_env=type_env,
        value_env=dict(typed_workflow.signature.params),
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        route_schema_version=route_schema_version,
    )


def _body_to_prefix_and_value(body: WccBody) -> tuple[tuple[WccLet, ...], WccValue]:
    prefix: list[WccLet] = []
    current = body
    while isinstance(current, WccLet):
        prefix.append(current)
        current = current.body
    if not isinstance(current, WccHalt):
        raise TypeError(f"expected linear WCC value body, found `{type(current).__name__}`")
    return tuple(prefix), current.result


def _wrap_prefix_lets(prefix: tuple[WccLet, ...], tail: WccBody) -> WccBody:
    current = tail
    for let_node in reversed(prefix):
        current = replace(let_node, body=current)
    return current


def _generated_join_name(scope: WccIdentityFactory, *, binding_name: str) -> str:
    return f"__wcc_join_{binding_name}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _phase_scope_from_expr(expr: WithPhaseExpr) -> WccPhaseScope:
    return WccPhaseScope(
        ctx_expr=expr.ctx_expr,
        phase_name=expr.phase_name,
        source_span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _elaborate_expr_to_body(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    if isinstance(expr, WithPhaseExpr):
        return _elaborate_expr_to_body(
            expr.body,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=_phase_scope_from_expr(expr),
        )
    if isinstance(expr, LetStarExpr):
        return _elaborate_let_star(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, MatchExpr):
        return _elaborate_match_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, IfExpr) and not is_pure_projection_expr(expr):
        return _elaborate_if_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, LoopRecurExpr):
        return _elaborate_loop_recur_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, ContinueExpr):
        prefix, state_value = _elaborate_expr_to_value(
            expr.state_expr,
            scope=scope.child_scope("loop-continue", authored_binding_name="state"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        continue_node = WccLoopContinue(
            metadata=scope.body_metadata(
                role="loop:continue",
                type_ref=_infer_expr_type(
                    expr.state_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                ),
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            target_name="__wcc_current_loop__",
            state_args=(state_value,),
        )
        return _wrap_prefix_lets(prefix, continue_node)
    if isinstance(expr, DoneExpr):
        prefix, result_value = _elaborate_expr_to_value(
            expr.result_expr,
            scope=scope.child_scope("loop-done", authored_binding_name="result"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        done_node = WccLoopDone(
            metadata=scope.body_metadata(
                role="loop:done",
                type_ref=_infer_expr_type(
                    expr.result_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                ),
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
                effect_summary=effect_summary,
                phase_scope=active_phase_scope,
            ),
            result=result_value,
        )
        return _wrap_prefix_lets(prefix, done_node)
    if isinstance(
        expr,
        (
            BacklogDrainExpr,
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            MaterializeViewExpr,
            FinalizeSelectedItemExpr,
            CallExpr,
            ProcedureCallExpr,
        ),
    ):
        return _elaborate_effect_expr_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    if isinstance(expr, (RecordExpr, UnionVariantExpr)) and any(
        isinstance(field_expr, MatchExpr) for _, field_expr in expr.fields
    ):
        return _elaborate_constructor_field_matches_to_body(
            expr,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    prefix, value = _elaborate_expr_to_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    halt = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=_infer_expr_type(
                expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=value,
    )
    return _wrap_prefix_lets(prefix, halt)


def _elaborate_let_star(
    expr: LetStarExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )

    def build(
        index: int,
        local_env: Mapping[str, TypeRef],
        local_scope: WccIdentityFactory,
        local_compile_time_bindings: Mapping[str, object],
    ) -> WccBody:
        if index >= len(expr.bindings):
            return _elaborate_expr_to_body(
                expr.body,
                scope=local_scope.child_scope("body", authored_binding_name="result"),
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )

        binding_name, binding_expr = expr.bindings[index]
        binding_type = _infer_expr_type(
            binding_expr,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        next_env = dict(local_env)
        next_env[binding_name] = binding_type
        if isinstance(binding_expr, BindProcExpr):
            next_compile_time_bindings = dict(local_compile_time_bindings)
            next_compile_time_bindings[binding_name] = binding_expr
            return build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                next_compile_time_bindings,
            )
        if isinstance(
            binding_expr,
            (
                BacklogDrainExpr,
                ProviderResultExpr,
                CommandResultExpr,
                RunProviderPhaseExpr,
                ProduceOneOfExpr,
                ResumeOrStartExpr,
                ResourceTransitionExpr,
                FinalizeSelectedItemExpr,
                CallExpr,
                ProcedureCallExpr,
            ),
        ):
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                local_compile_time_bindings,
            )
            return _elaborate_effect_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
                continuation=tail,
                let_result_type=result_type,
                scope=local_scope,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )

        if isinstance(binding_expr, MatchExpr):
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                local_compile_time_bindings,
            )
            return _elaborate_non_tail_match_binding(
                binding_name=binding_name,
                binding_type=binding_type,
                match_expr=binding_expr,
                continuation=tail,
                scope=local_scope.child_scope("match", authored_binding_name=binding_name),
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )

        if isinstance(binding_expr, IfExpr) and not is_pure_projection_expr(binding_expr):
            tail = build(
                index + 1,
                next_env,
                local_scope.child_scope("body", authored_binding_name=binding_name),
                local_compile_time_bindings,
            )
            binding_scope = local_scope.child_scope("if", authored_binding_name=binding_name)
            binding_body = _elaborate_if_to_body(
                binding_expr,
                scope=binding_scope,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=local_compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            return _elaborate_control_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
                binding_body=binding_body,
                continuation=tail,
                scope=binding_scope,
                effect_summary=effect_summary,
                active_phase_scope=active_phase_scope,
            )

        binding_scope = local_scope.child_scope("binding", authored_binding_name=binding_name)
        binding_body = _elaborate_expr_to_body(
            binding_expr,
            scope=binding_scope,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=local_compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        tail = build(
            index + 1,
            next_env,
            local_scope.child_scope("body", authored_binding_name=binding_name),
            local_compile_time_bindings,
        )
        if not _is_linear_value_body(binding_body):
            return _elaborate_control_binding_to_body(
                binding_name=binding_name,
                binding_type=binding_type,
                binding_expr=binding_expr,
                binding_body=binding_body,
                continuation=tail,
                scope=binding_scope,
                effect_summary=effect_summary,
                active_phase_scope=active_phase_scope,
            )

        prefix, value = _body_to_prefix_and_value(binding_body)
        let_node = WccLet(
            metadata=local_scope.body_metadata(
                role=f"let:{binding_name}",
                type_ref=result_type,
                source_span=binding_expr.span,
                form_path=binding_expr.form_path,
                expansion_stack=binding_expr.expansion_stack,
            ),
            bound_name=binding_name,
            bound_type_ref=binding_type,
            bound_value=value,
            body=tail,
        )
        return _wrap_prefix_lets(prefix, let_node)

    return build(0, dict(value_env), scope, dict(compile_time_bindings))


def _elaborate_loop_recur_to_body(
    expr: LoopRecurExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    state_type = _infer_expr_type(
        expr.initial_state_expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    loop_scope = scope.child_scope("rec-join", authored_binding_name=expr.binding_name)
    loop_name = f"__wcc_loop_{expr.binding_name}_{loop_scope.scope_id.rsplit(':', 1)[-1]}"
    state_prefix, initial_state = _elaborate_expr_to_value(
        expr.initial_state_expr,
        scope=loop_scope.child_scope("loop-state", authored_binding_name=expr.binding_name),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    budget_prefix, budget = _elaborate_expr_to_value(
        expr.max_iterations_expr,
        scope=loop_scope.child_scope("loop-budget", authored_binding_name=expr.binding_name),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    loop_env = dict(value_env)
    loop_env[expr.binding_name] = state_type
    body = _retarget_loop_continue(
        _elaborate_expr_to_body(
            expr.body_expr,
            scope=loop_scope.child_scope("loop-body", authored_binding_name=expr.binding_name),
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
        loop_name=loop_name,
    )
    exhaustion = None
    if expr.on_exhausted_result_expr is not None:
        exhaustion = _elaborate_expr_to_body(
            expr.on_exhausted_result_expr,
            scope=loop_scope.child_scope("loop-exhaustion", authored_binding_name=expr.binding_name),
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    rec_join = WccRecJoin(
        metadata=loop_scope.body_metadata(
            role=f"rec-join:{expr.binding_name}",
            type_ref=result_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        loop_name=loop_name,
        params=(WccJoinParam(name=expr.binding_name, type_ref=state_type),),
        budget=budget,
        body=body,
        exhaustion=exhaustion,
        initial_state=initial_state,
    )
    return _wrap_prefix_lets((*state_prefix, *budget_prefix), rec_join)


def _retarget_loop_continue(body: WccBody, *, loop_name: str) -> WccBody:
    if isinstance(body, WccLoopContinue):
        return replace(body, target_name=loop_name)
    if isinstance(body, WccLet):
        return replace(body, body=_retarget_loop_continue(body.body, loop_name=loop_name))
    if isinstance(body, WccCase):
        return replace(
            body,
            arms=tuple(
                WccCaseArm(
                    variant_name=arm.variant_name,
                    binding_name=arm.binding_name,
                    binding_type_ref=arm.binding_type_ref,
                    body=_retarget_loop_continue(arm.body, loop_name=loop_name),
                )
                for arm in body.arms
            ),
        )
    if isinstance(body, WccIf):
        return replace(
            body,
            then_body=_retarget_loop_continue(body.then_body, loop_name=loop_name),
            else_body=_retarget_loop_continue(body.else_body, loop_name=loop_name),
        )
    return body


def _is_linear_value_body(body: WccBody) -> bool:
    current = body
    while isinstance(current, WccLet):
        current = current.body
    return isinstance(current, WccHalt)


def _elaborate_control_binding_to_body(
    *,
    binding_name: str,
    binding_type: TypeRef,
    binding_expr,
    binding_body: WccBody,
    continuation: WccBody,
    scope: WccIdentityFactory,
    effect_summary: EffectSummary,
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    join_name = _generated_join_name(scope, binding_name=binding_name)
    return WccJoin(
        metadata=scope.body_metadata(
            role=f"join:{binding_name}",
            type_ref=continuation.metadata.type_ref,
            source_span=binding_expr.span,
            form_path=binding_expr.form_path,
            expansion_stack=binding_expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        join_name=join_name,
        params=(WccJoinParam(name=binding_name, type_ref=binding_type),),
        body=_replace_halts_with_jump(
            binding_body,
            join_name=join_name,
            result_type=binding_type,
            scope=scope.child_scope("jump", authored_binding_name=binding_name),
        ),
        continuation=continuation,
    )


def _elaborate_expr_to_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> tuple[tuple[WccLet, ...], WccValue]:
    if isinstance(expr, LiteralExpr):
        return (
            (),
            WccLiteralAtom(
                metadata=scope.atom_metadata(
                    role=f"literal:{expr.literal_kind}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=expr.value,
                literal_kind=expr.literal_kind,
            ),
        )
    if isinstance(expr, EnumMemberExpr):
        return (
            (),
            WccLiteralAtom(
                metadata=scope.atom_metadata(
                    role=f"literal:enum:{expr.enum_name}.{expr.member_name}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                value=expr.member_name,
                literal_kind="enum",
            ),
        )
    if isinstance(expr, NameExpr):
        return (
            (),
            WccNameAtom(
                metadata=scope.atom_metadata(
                    role=f"name:{expr.name}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                name=expr.name,
            ),
        )
    if isinstance(expr, PhaseTargetExpr):
        return (
            (),
            WccPhaseTargetAtom(
                metadata=scope.atom_metadata(
                    role=f"phase-target:{expr.target_name}",
                    type_ref=PrimitiveTypeRef(name="String"),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                target_name=expr.target_name,
            ),
        )
    if isinstance(
        expr,
        (
            LoopStateSeedExpr,
            LoopStateUpdateExpr,
            GeneratedRelpathSeedExpr,
            ProviderBundlePathExpr,
            ResourceTransitionExpr,
        ),
    ):
        return (
            (),
            WccOpaqueFrontendValue(
                metadata=scope.atom_metadata(
                    role=f"opaque:{type(expr).__name__}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr=expr,
            ),
        )
    if isinstance(expr, FieldAccessExpr):
        base_type = value_env[expr.base.name]
        return (
            (),
            WccFieldAccessAtom(
                metadata=scope.atom_metadata(
                    role=f"field:{'.'.join((expr.base.name, *expr.fields))}",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                base=WccNameAtom(
                    metadata=scope.atom_metadata(
                        role=f"name:{expr.base.name}",
                        type_ref=base_type,
                        source_span=expr.base.span,
                        form_path=expr.base.form_path,
                        expansion_stack=expr.base.expansion_stack,
                    ),
                    name=expr.base.name,
                ),
                fields=expr.fields,
            ),
        )
    if isinstance(expr, RecordExpr):
        record_type = _require_record_type(expr, type_env=type_env)
        prefix: list[WccLet] = []
        fields: list[tuple[str, WccValue]] = []
        for field_name, field_expr in expr.fields:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("record-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            fields.append((field_name, field_value))
        return (
            tuple(prefix),
            WccRecordAtom(
                metadata=scope.atom_metadata(
                    role=f"record:{expr.type_name}",
                    type_ref=record_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                type_name=expr.type_name,
                fields=tuple(fields),
            ),
        )
    if isinstance(expr, PureOpExpr):
        result_type = _infer_expr_type(
            expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        prefix: list[WccLet] = []
        args: list[WccValue] = []
        for index, arg_expr in enumerate(expr.args):
            arg_body = _elaborate_expr_to_body(
                arg_expr,
                scope=scope.child_scope("pure-op-arg", authored_binding_name=str(index)),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            arg_prefix, arg_value = _body_to_prefix_and_value(arg_body)
            prefix.extend(arg_prefix)
            args.append(arg_value)
        return (
            tuple(prefix),
            WccPureOp(
                metadata=scope.value_metadata(
                    role=f"pure-op:{expr.operator}",
                    type_ref=result_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                operator=expr.operator,
                args=tuple(args),
            ),
        )
    if isinstance(expr, RecordUpdateExpr):
        result_type = _infer_expr_type(
            expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        prefix: list[WccLet] = []
        base_body = _elaborate_expr_to_body(
            expr.base_expr,
            scope=scope.child_scope("record-update-base", authored_binding_name="base"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        base_prefix, base_value = _body_to_prefix_and_value(base_body)
        prefix.extend(base_prefix)
        args: list[WccValue] = [base_value]
        field_names: list[str] = []
        for field_name, field_expr in expr.overrides:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("record-update-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            field_names.append(field_name)
            args.append(field_value)
        return (
            tuple(prefix),
            WccPureOp(
                metadata=scope.value_metadata(
                    role="pure-op:record-update",
                    type_ref=result_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                operator="record-update",
                args=tuple(args),
                field_names=tuple(field_names),
            ),
        )
    if isinstance(expr, UnionVariantExpr):
        union_type = _require_union_type(expr, type_env=type_env)
        prefix: list[WccLet] = []
        fields: list[tuple[str, WccValue]] = []
        for field_name, field_expr in expr.fields:
            field_body = _elaborate_expr_to_body(
                field_expr,
                scope=scope.child_scope("union-field", authored_binding_name=field_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            field_prefix, field_value = _body_to_prefix_and_value(field_body)
            prefix.extend(field_prefix)
            fields.append((field_name, field_value))
        return (
            tuple(prefix),
            WccInject(
                metadata=scope.value_metadata(
                    role=f"inject:{expr.variant_name}",
                    type_ref=union_type,
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                union_name=expr.type_name,
                variant_name=expr.variant_name,
                fields=tuple(fields),
            ),
        )
    if isinstance(expr, LetStarExpr):
        prefix, value = _body_to_prefix_and_value(
            _elaborate_let_star(
                expr,
                scope=scope,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
        )
        return prefix, value
    if isinstance(expr, IfExpr):
        return (
            (),
            WccOpaqueFrontendValue(
                metadata=scope.value_metadata(
                    role="opaque:IfExpr",
                    type_ref=_infer_expr_type(
                        expr,
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                    ),
                    source_span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
                expr=expr,
            ),
        )
    raise TypeError(f"unsupported WCC elaboration node: {type(expr).__name__}")


def _elaborate_constructor_field_matches_to_body(
    expr: RecordExpr | UnionVariantExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    wrappers: list[object] = []
    field_values: list[tuple[str, WccValue]] = []
    generated_env: dict[str, TypeRef] = {}

    for field_name, field_expr in expr.fields:
        if isinstance(field_expr, MatchExpr):
            binding_scope = scope.child_scope("constructor-field-match", authored_binding_name=field_name)
            binding_name = _generated_value_binding_name_from_scope(binding_scope, role=field_name)
            binding_type = _infer_expr_type(
                field_expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            )
            generated_env[binding_name] = binding_type
            field_values.append(
                (
                    field_name,
                    WccNameAtom(
                        metadata=binding_scope.atom_metadata(
                            role=f"name:{binding_name}",
                            type_ref=binding_type,
                            source_span=field_expr.span,
                            form_path=field_expr.form_path,
                            expansion_stack=field_expr.expansion_stack,
                        ),
                        name=binding_name,
                    ),
                )
            )
            wrappers.append(("match", binding_name, binding_type, field_expr, binding_scope))
            continue

        field_body = _elaborate_expr_to_body(
            field_expr,
            scope=scope.child_scope("constructor-field", authored_binding_name=field_name),
            type_env=type_env,
            value_env={**value_env, **generated_env},
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        field_prefix, field_value = _body_to_prefix_and_value(field_body)
        wrappers.append(("prefix", field_prefix))
        field_values.append((field_name, field_value))

    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env={**value_env, **generated_env},
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    if isinstance(expr, RecordExpr):
        result_value: WccValue = WccRecordAtom(
            metadata=scope.atom_metadata(
                role=f"record:{expr.type_name}",
                type_ref=result_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            type_name=expr.type_name,
            fields=tuple(field_values),
        )
    else:
        result_value = WccInject(
            metadata=scope.value_metadata(
                role=f"inject:{expr.variant_name}",
                type_ref=result_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            union_name=expr.type_name,
            variant_name=expr.variant_name,
            fields=tuple(field_values),
        )

    current: WccBody = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=result_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=result_value,
    )
    for wrapper in reversed(wrappers):
        if wrapper[0] == "prefix":
            current = _wrap_prefix_lets(wrapper[1], current)
            continue
        _, binding_name, binding_type, match_expr, binding_scope = wrapper
        current = _elaborate_non_tail_match_binding(
            binding_name=binding_name,
            binding_type=binding_type,
            match_expr=match_expr,
            continuation=current,
            scope=binding_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    return current


def _elaborate_match_to_body(
    expr: MatchExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    subject_type = _infer_expr_type(
        expr.subject,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    if isinstance(
        expr.subject,
        (
            BacklogDrainExpr,
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            ResourceTransitionExpr,
            FinalizeSelectedItemExpr,
            CallExpr,
            ProcedureCallExpr,
        ),
    ):
        subject_binding_scope = scope.child_scope("match-subject-effect", authored_binding_name="subject")
        subject_binding_name = _generated_effect_binding_name_from_scope(
            subject_binding_scope,
            role="subject",
        )
        subject_atom = WccNameAtom(
            metadata=subject_binding_scope.atom_metadata(
                role=f"name:{subject_binding_name}",
                type_ref=subject_type,
                source_span=expr.subject.span,
                form_path=expr.subject.form_path,
                expansion_stack=expr.subject.expansion_stack,
            ),
            name=subject_binding_name,
        )
        case_body = _elaborate_match_case_with_subject(
            expr,
            subject=subject_atom,
            scope=scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        return _elaborate_effect_binding_to_body(
            binding_name=subject_binding_name,
            binding_type=subject_type,
            binding_expr=expr.subject,
            continuation=case_body,
            let_result_type=case_body.metadata.type_ref,
            scope=subject_binding_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
    subject = _elaborate_atomic_value(
        expr.subject,
        scope=scope.child_scope("match-subject", authored_binding_name="subject"),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return _elaborate_match_case_with_subject(
        expr,
        subject=subject,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )


def _elaborate_match_case_with_subject(
    expr: MatchExpr,
    *,
    subject: WccValue,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccCase:
    return WccCase(
        metadata=scope.body_metadata(
            role="case:match",
            type_ref=_infer_expr_type(
                expr,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            ),
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        subject=subject,
        arms=tuple(
            _elaborate_case_arm(
                expr,
                arm,
                scope=scope.child_scope("match-arm", authored_binding_name=arm.binding_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            for arm in expr.arms
        ),
    )


def _elaborate_if_to_body(
    expr: IfExpr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    condition_prefix, condition = _elaborate_expr_to_value(
        expr.condition_expr,
        scope=scope.child_scope("if-condition"),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    condition_shape = classify_condition_expr(
        expr.condition_expr,
        type_ref=PrimitiveTypeRef(name="Bool"),
    )
    if_body = WccIf(
        metadata=scope.body_metadata(
            role="if",
            type_ref=result_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        condition=condition,
        condition_shape=condition_shape,
        then_body=_elaborate_expr_to_body(
            expr.then_expr,
            scope=scope.child_scope("if-then"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
        else_body=_elaborate_expr_to_body(
            expr.else_expr,
            scope=scope.child_scope("if-else"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
    )
    return _wrap_prefix_lets(condition_prefix, if_body)


def _elaborate_case_arm(
    match_expr: MatchExpr,
    arm,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccCaseArm:
    subject_type = _infer_expr_type(
        match_expr.subject,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    if not isinstance(subject_type, UnionTypeRef):
        raise TypeError("match subject must elaborate from a union type")
    binding_type_ref = type_env.union_variant(
        subject_type,
        arm.variant_name,
        span=arm.span,
        form_path=arm.form_path,
        expansion_stack=arm.expansion_stack,
    )
    arm_env = dict(value_env)
    arm_env[arm.binding_name] = binding_type_ref
    return WccCaseArm(
        variant_name=arm.variant_name,
        binding_name=arm.binding_name,
        binding_type_ref=binding_type_ref,
        body=_elaborate_expr_to_body(
            arm.body,
            scope=scope,
            type_env=type_env,
            value_env=arm_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
    )


def _elaborate_non_tail_match_binding(
    *,
    binding_name: str,
    binding_type: TypeRef,
    match_expr: MatchExpr,
    continuation: WccBody,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    join_name = _generated_join_name(scope, binding_name=binding_name)
    case_body = _elaborate_match_to_body(
        match_expr,
        scope=scope.child_scope("case", authored_binding_name=binding_name),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    return WccJoin(
        metadata=scope.body_metadata(
            role=f"join:{binding_name}",
            type_ref=continuation.metadata.type_ref,
            source_span=match_expr.span,
            form_path=match_expr.form_path,
            expansion_stack=match_expr.expansion_stack,
            effect_summary=effect_summary,
            phase_scope=active_phase_scope,
        ),
        join_name=join_name,
        params=(WccJoinParam(name=binding_name, type_ref=binding_type),),
        body=_replace_halts_with_jump(
            case_body,
            join_name=join_name,
            result_type=binding_type,
            scope=scope.child_scope("jump", authored_binding_name=binding_name),
        ),
        continuation=continuation,
    )


def _replace_halts_with_jump(
    body: WccBody,
    *,
    join_name: str,
    result_type: TypeRef,
    scope: WccIdentityFactory,
) -> WccBody:
    if isinstance(body, WccLet):
        return replace(
            body,
            body=_replace_halts_with_jump(
                body.body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("let-tail", authored_binding_name=body.bound_name),
            ),
        )
    if isinstance(body, WccCase):
        return replace(
            body,
            arms=tuple(
                replace(
                    arm,
                    body=_replace_halts_with_jump(
                        arm.body,
                        join_name=join_name,
                        result_type=result_type,
                        scope=scope.child_scope("arm-tail", authored_binding_name=arm.binding_name),
                    ),
                )
                for arm in body.arms
            ),
        )
    if isinstance(body, WccIf):
        return replace(
            body,
            then_body=_replace_halts_with_jump(
                body.then_body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("if-then"),
            ),
            else_body=_replace_halts_with_jump(
                body.else_body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("if-else"),
            ),
        )
    if isinstance(body, WccJoin):
        return replace(
            body,
            body=_replace_halts_with_jump(
                body.body,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("join-body", authored_binding_name=body.join_name),
            ),
            continuation=_replace_halts_with_jump(
                body.continuation,
                join_name=join_name,
                result_type=result_type,
                scope=scope.child_scope("join-cont", authored_binding_name=body.join_name),
            ),
        )
    if isinstance(body, WccRecJoin):
        return body
    if isinstance(body, WccHalt):
        return WccJump(
            metadata=scope.body_metadata(
                role=f"jump:{join_name}",
                type_ref=result_type,
                source_span=body.metadata.source_span,
                form_path=body.metadata.form_path,
                expansion_stack=body.metadata.expansion_stack,
                effect_summary=body.metadata.effect_summary,
                proof_context=body.metadata.proof_context,
                allocation_requests=body.metadata.allocation_requests,
                phase_scope=body.metadata.phase_scope,
            ),
            join_name=join_name,
            args=(body.result,),
        )
    if isinstance(body, WccJump):
        return body
    raise TypeError(f"unsupported WCC control rewrite node: {type(body).__name__}")


def _elaborate_effect_expr_to_body(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    binding_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    binding_name = _generated_effect_binding_name_from_scope(scope, role="result")
    halt = WccHalt(
        metadata=scope.body_metadata(
            role="halt:return",
            type_ref=binding_type,
            source_span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result=WccNameAtom(
            metadata=scope.atom_metadata(
                role=f"name:{binding_name}",
                type_ref=binding_type,
                source_span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            ),
            name=binding_name,
        ),
    )
    return _elaborate_effect_binding_to_body(
        binding_name=binding_name,
        binding_type=binding_type,
        binding_expr=expr,
        continuation=halt,
        let_result_type=binding_type,
        scope=scope.child_scope("effect", authored_binding_name="result"),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )


def _elaborate_effect_binding_to_body(
    *,
    binding_name: str,
    binding_type: TypeRef,
    binding_expr,
    continuation: WccBody,
    let_result_type: TypeRef,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBody:
    normalized_expr, match_bindings = _prebind_effect_argument_matches(
        binding_expr,
        scope=scope.child_scope("effect-args", authored_binding_name=binding_name),
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    current: WccBody = WccLet(
        metadata=scope.body_metadata(
            role=f"let:{binding_name}",
            type_ref=let_result_type,
            source_span=binding_expr.span,
            form_path=binding_expr.form_path,
            expansion_stack=binding_expr.expansion_stack,
        ),
        bound_name=binding_name,
        bound_type_ref=binding_type,
        bound_value=_elaborate_effect_expr_to_binding_value(
            normalized_expr,
            scope=scope.child_scope("binding", authored_binding_name=binding_name),
            type_env=type_env,
            value_env={**value_env, **{name: type_ref for name, type_ref, _ in match_bindings}},
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        ),
        body=continuation,
    )
    for arg_name, arg_type, prebound_expr in reversed(match_bindings):
        if isinstance(prebound_expr, MatchExpr):
            current = _elaborate_non_tail_match_binding(
                binding_name=arg_name,
                binding_type=arg_type,
                match_expr=prebound_expr,
                continuation=current,
                scope=scope.child_scope("effect-arg-match", authored_binding_name=arg_name),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            continue
        prebound_scope = scope.child_scope("effect-arg-value", authored_binding_name=arg_name)
        prebound_body = _elaborate_expr_to_body(
            prebound_expr,
            scope=prebound_scope,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        prebound_prefix, prebound_value = _body_to_prefix_and_value(prebound_body)
        current = WccLet(
            metadata=prebound_scope.body_metadata(
                role=f"let:{arg_name}",
                type_ref=arg_type,
                source_span=prebound_expr.span,
                form_path=prebound_expr.form_path,
                expansion_stack=prebound_expr.expansion_stack,
            ),
            bound_name=arg_name,
            bound_type_ref=arg_type,
            bound_value=prebound_value,
            body=current,
        )
        for prefix_let in reversed(prebound_prefix):
            current = replace(prefix_let, body=current)
    return current


def _prebind_effect_argument_matches(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
) -> tuple[object, tuple[tuple[str, TypeRef, object], ...]]:
    match_bindings: list[tuple[str, TypeRef, object]] = []

    def replace_arg(arg_expr, *, role: str):
        if not isinstance(arg_expr, (MatchExpr, LetStarExpr)):
            return arg_expr
        binding_type = _infer_expr_type(
            arg_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        binding_name = _generated_effect_binding_name_from_scope(scope, role=role)
        match_bindings.append((binding_name, binding_type, arg_expr))
        return NameExpr(
            name=binding_name,
            span=arg_expr.span,
            form_path=arg_expr.form_path,
            expansion_stack=arg_expr.expansion_stack,
        )

    if isinstance(expr, ProviderResultExpr):
        return (
            replace(
                expr,
                inputs=tuple(
                    replace_arg(input_expr, role=f"provider-input:{index}")
                    for index, input_expr in enumerate(expr.inputs)
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, CommandResultExpr):
        return (
            replace(
                expr,
                argv=tuple(
                    replace_arg(arg_expr, role=f"command-arg:{index}")
                    for index, arg_expr in enumerate(expr.argv)
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, RunProviderPhaseExpr):
        return (
            replace(
                expr,
                ctx_expr=replace_arg(expr.ctx_expr, role="run-provider-phase:ctx"),
                inputs_expr=replace_arg(expr.inputs_expr, role="run-provider-phase:inputs"),
                provider=replace_arg(expr.provider, role="run-provider-phase:provider"),
                prompt=replace_arg(expr.prompt, role="run-provider-phase:prompt"),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, ProduceOneOfExpr):
        producer = replace(
            expr.producer,
            provider_expr=(
                replace_arg(expr.producer.provider_expr, role="produce-one-of:provider")
                if expr.producer.provider_expr is not None
                else None
            ),
            prompt_expr=(
                replace_arg(expr.producer.prompt_expr, role="produce-one-of:prompt")
                if expr.producer.prompt_expr is not None
                else None
            ),
            inputs=tuple(
                replace_arg(input_expr, role=f"produce-one-of:input:{index}")
                for index, input_expr in enumerate(expr.producer.inputs)
            ),
        )
        candidates = tuple(
            replace(
                candidate,
                fields=tuple(
                    replace(
                        field,
                        target_expr=(
                            replace_arg(field.target_expr, role=f"produce-one-of:{candidate.variant_name}:{field.field_name}")
                            if field.target_expr is not None
                            else None
                        ),
                    )
                    for field in candidate.fields
                ),
            )
            for candidate in expr.candidates
        )
        return (
            replace(expr, ctx_expr=replace_arg(expr.ctx_expr, role="produce-one-of:ctx"), producer=producer, candidates=candidates),
            tuple(match_bindings),
        )
    if isinstance(expr, CallExpr):
        return (
            replace(
                expr,
                bindings=tuple(
                    (binding_name, replace_arg(binding_expr, role=f"workflow-binding:{binding_name}"))
                    for binding_name, binding_expr in expr.bindings
                ),
            ),
            tuple(match_bindings),
        )
    if isinstance(expr, ProcedureCallExpr):
        return (
            replace(
                expr,
                args=tuple(
                    replace_arg(arg_expr, role=f"procedure-arg:{index}")
                    for index, arg_expr in enumerate(expr.args)
                ),
            ),
            tuple(match_bindings),
        )
    return expr, ()


def _elaborate_effect_expr_to_binding_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccBindingValue:
    result_type = _infer_expr_type(
        expr,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
    )
    metadata_kwargs = dict(
        type_ref=result_type,
        source_span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
        effect_summary=effect_summary,
        phase_scope=active_phase_scope,
    )
    if isinstance(expr, ProviderResultExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:provider_result", **metadata_kwargs),
            perform_kind="provider_result",
            target_name=_require_name_expr(expr.provider),
            prompt_name=_require_name_expr(expr.prompt),
            positional_args=tuple(
                _elaborate_atomic_value(
                    item,
                    scope=scope.child_scope("provider-input", authored_binding_name=str(index)),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
                for index, item in enumerate(expr.inputs)
            ),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
        )
    if isinstance(expr, CommandResultExpr):
        adapter_inputs = tuple(
            (
                field_name,
                _elaborate_atomic_value(
                    value_expr,
                    scope=scope.child_scope("command-adapter-input", authored_binding_name=field_name),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
            )
            for field_name, value_expr in expr.adapter_inputs
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:command_result", **metadata_kwargs),
            perform_kind="command_result",
            target_name=expr.step_name,
            prompt_name=None,
            positional_args=tuple(
                _elaborate_atomic_value(
                    item,
                    scope=scope.child_scope("command-arg", authored_binding_name=str(index)),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
                for index, item in enumerate(expr.argv)
            ),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload={
                "adapter_name": expr.adapter_name,
                "adapter_inputs": adapter_inputs,
            },
        )
    if isinstance(expr, RunProviderPhaseExpr):
        ctx_value = _elaborate_atomic_value(
            expr.ctx_expr,
            scope=scope.child_scope("run-provider-phase", authored_binding_name="ctx"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        inputs_value = _elaborate_atomic_value(
            expr.inputs_expr,
            scope=scope.child_scope("run-provider-phase", authored_binding_name="inputs"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:run_provider_phase", **metadata_kwargs),
            perform_kind="run_provider_phase",
            target_name=_require_name_expr(expr.provider),
            prompt_name=_require_name_expr(expr.prompt),
            positional_args=(ctx_value, inputs_value),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=WccRunProviderPhasePayload(
                phase_name=expr.phase_name,
                ctx_expr=ctx_value,
                inputs_expr=inputs_value,
                provider_name=_require_name_expr(expr.provider),
                prompt_name=_require_name_expr(expr.prompt),
            ),
        )
    if isinstance(expr, ProduceOneOfExpr):
        ctx_value = _elaborate_atomic_value(
            expr.ctx_expr,
            scope=scope.child_scope("produce-one-of", authored_binding_name="ctx"),
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
            effect_summary=effect_summary,
            procedure_edges_by_site=procedure_edges_by_site,
            compile_time_bindings=compile_time_bindings,
            active_phase_scope=active_phase_scope,
        )
        producer_inputs = tuple(
            _elaborate_atomic_value(
                item,
                scope=scope.child_scope("produce-one-of-input", authored_binding_name=str(index)),
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
                effect_summary=effect_summary,
                procedure_edges_by_site=procedure_edges_by_site,
                compile_time_bindings=compile_time_bindings,
                active_phase_scope=active_phase_scope,
            )
            for index, item in enumerate(expr.producer.inputs)
        )
        return WccPerform(
            metadata=scope.value_metadata(role="perform:produce_one_of", **metadata_kwargs),
            perform_kind="produce_one_of",
            target_name=_require_name_expr(expr.producer.provider_expr),
            prompt_name=_require_name_expr(expr.producer.prompt_expr),
            positional_args=(ctx_value, *producer_inputs),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=WccProduceOneOfPayload(
                ctx_expr=ctx_value,
                provider_name=_require_name_expr(expr.producer.provider_expr),
                prompt_name=_require_name_expr(expr.producer.prompt_expr),
                producer_inputs=producer_inputs,
                candidates=expr.candidates,
            ),
        )
    if isinstance(expr, ResumeOrStartExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:resume_or_start", **metadata_kwargs),
            perform_kind="resume_or_start",
            target_name=expr.resume_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=WccResumeOrStartPayload(
                resume_name=expr.resume_name,
                ctx_expr=_elaborate_atomic_value(
                    expr.ctx_expr,
                    scope=scope.child_scope("resume-or-start", authored_binding_name="ctx"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
                resume_from_expr=_elaborate_atomic_value(
                    expr.resume_from_expr,
                    scope=scope.child_scope("resume-or-start", authored_binding_name="resume-from"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
                valid_when=expr.valid_when,
                start_value=_elaborate_effect_expr_to_binding_value(
                    expr.start_expr,
                    scope=scope.child_scope("resume-or-start", authored_binding_name="start"),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                ),
                validation_spec=expr.validation_spec,
            ),
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:finalize_selected_item", **metadata_kwargs),
            perform_kind="finalize_selected_item",
            target_name="finalize-selected-item",
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=None,
            operation_payload=expr,
        )
    if isinstance(expr, BacklogDrainExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:backlog_drain", **metadata_kwargs),
            perform_kind="backlog_drain",
            target_name=expr.spec.drain_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=None,
            operation_payload=expr,
        )
    if isinstance(expr, ResourceTransitionExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:resource_transition", **metadata_kwargs),
            perform_kind="resource_transition",
            target_name=expr.spec.transition_ref_name or expr.spec.transition_name or "resource-transition",
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=None,
            operation_payload=expr,
        )
    if isinstance(expr, MaterializeViewExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:materialize_view", **metadata_kwargs),
            perform_kind="materialize_view",
            target_name=expr.view_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=(),
            returns_type_name=expr.returns_type_name,
            operation_payload=expr,
        )
    if isinstance(expr, CallExpr):
        return WccPerform(
            metadata=scope.value_metadata(role="perform:workflow_call", **metadata_kwargs),
            perform_kind="workflow_call",
            target_name=expr.callee_name,
            prompt_name=None,
            positional_args=(),
            keyword_args=tuple(
                (
                    binding_name,
                    _elaborate_workflow_call_binding_value(
                        binding_expr,
                        scope=scope.child_scope("workflow-binding", authored_binding_name=binding_name),
                        type_env=type_env,
                        value_env=value_env,
                        workflow_return_types=workflow_return_types,
                        procedure_return_types=procedure_return_types,
                        effect_summary=effect_summary,
                        procedure_edges_by_site=procedure_edges_by_site,
                        compile_time_bindings=compile_time_bindings,
                        active_phase_scope=active_phase_scope,
                    ),
                )
                for binding_name, binding_expr in expr.bindings
            ),
            returns_type_name=None,
        )
    if isinstance(expr, ProcedureCallExpr):
        specialized_name = procedure_edges_by_site.get((expr.span, expr.form_path), expr.callee_name)
        return WccCall(
            metadata=scope.value_metadata(role=f"call:{specialized_name}", **metadata_kwargs),
            callee_name=expr.callee_name,
            specialized_callee_name=specialized_name,
            args=tuple(
                _elaborate_atomic_value(
                    item,
                    scope=scope.child_scope("procedure-arg", authored_binding_name=str(index)),
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                    effect_summary=effect_summary,
                    procedure_edges_by_site=procedure_edges_by_site,
                    compile_time_bindings=compile_time_bindings,
                    active_phase_scope=active_phase_scope,
                )
                for index, item in enumerate(expr.args)
                if not (isinstance(item, NameExpr) and item.name in compile_time_bindings)
            ),
        )
    raise TypeError(f"unsupported WCC M2 effect node: {type(expr).__name__}")


def _elaborate_atomic_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccValue:
    prefix, value = _elaborate_expr_to_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )
    if prefix:
        raise TypeError(f"unsupported nested WCC M2 prefix for `{type(expr).__name__}`")
    return value


def _elaborate_workflow_call_binding_value(
    expr,
    *,
    scope: WccIdentityFactory,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
    effect_summary: EffectSummary,
    procedure_edges_by_site: Mapping[tuple[object, tuple[str, ...]], str],
    compile_time_bindings: Mapping[str, object],
    active_phase_scope: WccPhaseScope | None = None,
) -> WccValue:
    if isinstance(
        expr,
        (
            BacklogDrainExpr,
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            FinalizeSelectedItemExpr,
            ResourceTransitionExpr,
            CallExpr,
        ),
    ):
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="workflow_signature_mismatch",
                    message=(
                        "Stage 3 lowering requires same-file call bindings to resolve to workflow inputs"
                    ),
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                ),
            )
        )
    return _elaborate_atomic_value(
        expr,
        scope=scope,
        type_env=type_env,
        value_env=value_env,
        workflow_return_types=workflow_return_types,
        procedure_return_types=procedure_return_types,
        effect_summary=effect_summary,
        procedure_edges_by_site=procedure_edges_by_site,
        compile_time_bindings=compile_time_bindings,
        active_phase_scope=active_phase_scope,
    )


def _generated_effect_binding_name_from_scope(scope: WccIdentityFactory, *, role: str) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    return f"__wcc_effect_{safe_role}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _generated_value_binding_name_from_scope(scope: WccIdentityFactory, *, role: str) -> str:
    safe_role = "".join(char if char.isalnum() else "_" for char in role).strip("_")
    return f"__wcc_value_{safe_role}_{scope.scope_id.rsplit(':', 1)[-1]}"


def _require_record_type(expr: RecordExpr, *, type_env: FrontendTypeEnvironment) -> RecordTypeRef:
    resolved = type_env.resolve_type(
        expr.type_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not isinstance(resolved, RecordTypeRef):
        raise TypeError(f"expected record type for `{expr.type_name}`")
    return resolved


def _require_union_type(expr: UnionVariantExpr, *, type_env: FrontendTypeEnvironment) -> UnionTypeRef:
    resolved = type_env.resolve_type(
        expr.type_name,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    if not isinstance(resolved, UnionTypeRef):
        raise TypeError(f"expected union type for `{expr.type_name}`")
    return resolved


def _require_name_expr(expr) -> str:
    if not isinstance(expr, NameExpr):
        raise TypeError(f"expected name expression, found `{type(expr).__name__}`")
    return expr.name


def _infer_expr_type(
    expr,
    *,
    type_env: FrontendTypeEnvironment,
    value_env: Mapping[str, TypeRef],
    workflow_return_types: Mapping[str, TypeRef],
    procedure_return_types: Mapping[str, TypeRef],
) -> TypeRef:
    if isinstance(expr, LiteralExpr):
        return {
            "string": PrimitiveTypeRef(name="String"),
            "int": PrimitiveTypeRef(name="Int"),
            "bool": PrimitiveTypeRef(name="Bool"),
            "float": PrimitiveTypeRef(name="Float"),
        }[expr.literal_kind]
    if isinstance(expr, EnumMemberExpr):
        return type_env.resolve_type(
            expr.enum_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, NameExpr):
        return value_env[expr.name]
    if isinstance(expr, PhaseTargetExpr):
        return PrimitiveTypeRef(name="String")
    if isinstance(expr, GeneratedRelpathSeedExpr):
        return expr.target_type_ref
    if isinstance(expr, LoopStateSeedExpr):
        field_types = tuple(
            (
                field.name,
                _infer_expr_type(
                    field.value_expr,
                    type_env=type_env,
                    value_env=value_env,
                    workflow_return_types=workflow_return_types,
                    procedure_return_types=procedure_return_types,
                ),
            )
            for field in expr.fields
        )
        metadata = carrier_metadata_for_expr(
            expr,
            field_signature=tuple((field_name, field_type.name) for field_name, field_type in field_types),
            field_types=field_types,
        )
        if metadata is None:
            raise TypeError("loop-state seed metadata was unavailable during WCC inference")
        return type_env.resolve_type(
            metadata.generated_type_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, LoopStateUpdateExpr):
        return _infer_expr_type(
            expr.base_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, RecordUpdateExpr):
        return _infer_expr_type(
            expr.base_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, FieldAccessExpr):
        current: TypeRef = value_env[expr.base.name]
        for field_name in expr.fields:
            if not isinstance(current, (RecordTypeRef, VariantCaseTypeRef)):
                raise TypeError(f"expected record type while resolving `{expr.base.name}.{'.'.join(expr.fields)}`")
            current = type_env.record_field(
                current,
                field_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return current
    if isinstance(expr, RecordExpr):
        return _require_record_type(expr, type_env=type_env)
    if isinstance(expr, UnionVariantExpr):
        return _require_union_type(expr, type_env=type_env)
    if isinstance(expr, PureOpExpr):
        arg_types = tuple(
            _infer_expr_type(
                arg,
                type_env=type_env,
                value_env=value_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            )
            for arg in expr.args
        )
        operator = expr.operator
        if operator in {"=", "!=", "<", "<=", ">", ">=", "and", "or", "not", "some?"}:
            return PrimitiveTypeRef(name="Bool")
        if operator in {"+", "-", "*", "min", "max"}:
            if not arg_types:
                raise TypeError(f"pure operator `{operator}` requires arguments during WCC inference")
            return arg_types[0]
        if operator == "or-else":
            if len(arg_types) != 2:
                raise TypeError("pure operator `or-else` requires exactly two operands during WCC inference")
            if isinstance(arg_types[0], OptionalTypeRef):
                return arg_types[0].item_type_ref
            return arg_types[1]
        if operator in {"string/concat", "symbol/name"}:
            return PrimitiveTypeRef(name="String")
        if operator == "string/empty?":
            return PrimitiveTypeRef(name="Bool")
        raise TypeError(f"unsupported WCC pure operator inference `{operator}`")
    if isinstance(expr, ContinueExpr):
        state_type = _infer_expr_type(
            expr.state_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        return LoopControlTypeRef(state_type_ref=state_type, result_type_ref=None)
    if isinstance(expr, DoneExpr):
        result_type = _infer_expr_type(
            expr.result_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        return LoopControlTypeRef(state_type_ref=result_type, result_type_ref=result_type)
    if isinstance(expr, LoopRecurExpr):
        state_type = _infer_expr_type(
            expr.initial_state_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        loop_env = dict(value_env)
        loop_env[expr.binding_name] = state_type
        body_type = _infer_expr_type(
            expr.body_expr,
            type_env=type_env,
            value_env=loop_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        if isinstance(body_type, LoopControlTypeRef) and body_type.result_type_ref is not None:
            return body_type.result_type_ref
        if expr.on_exhausted_result_expr is not None:
            return _infer_expr_type(
                expr.on_exhausted_result_expr,
                type_env=type_env,
                value_env=loop_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            )
        raise TypeError("loop/recur body must expose a done result type")
    if isinstance(expr, LetStarExpr):
        local_env = dict(value_env)
        for binding_name, binding_expr in expr.bindings:
            local_env[binding_name] = _infer_expr_type(
                binding_expr,
                type_env=type_env,
                value_env=local_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            )
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=local_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, IfExpr):
        then_type = _infer_expr_type(
            expr.then_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        else_type = _infer_expr_type(
            expr.else_expr,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        if isinstance(then_type, LoopControlTypeRef) and isinstance(else_type, LoopControlTypeRef):
            return _merge_loop_control_types(then_type, else_type, owner="if")
        if not type_refs_compatible(then_type, else_type):
            raise TypeError("if branch types must match during WCC inference")
        return then_type
    if isinstance(expr, MatchExpr):
        subject_type = _infer_expr_type(
            expr.subject,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
        if not isinstance(subject_type, UnionTypeRef):
            raise TypeError("match subject must have a union type")
        inferred_type: TypeRef | LoopControlTypeRef | None = None
        for arm in expr.arms:
            arm_env = dict(value_env)
            arm_env[arm.binding_name] = type_env.union_variant(
                subject_type,
                arm.variant_name,
                span=arm.span,
                form_path=arm.form_path,
                expansion_stack=arm.expansion_stack,
            )
            arm_type = _infer_expr_type(
                arm.body,
                type_env=type_env,
                value_env=arm_env,
                workflow_return_types=workflow_return_types,
                procedure_return_types=procedure_return_types,
            )
            if inferred_type is None:
                inferred_type = arm_type
                continue
            if isinstance(inferred_type, LoopControlTypeRef) and isinstance(arm_type, LoopControlTypeRef):
                inferred_type = _merge_loop_control_types(inferred_type, arm_type, owner="match")
                continue
            if not type_refs_compatible(inferred_type, arm_type):
                raise TypeError("match arm types must match during WCC inference")
        assert inferred_type is not None
        return inferred_type
    if isinstance(expr, WithPhaseExpr):
        return _infer_expr_type(
            expr.body,
            type_env=type_env,
            value_env=value_env,
            workflow_return_types=workflow_return_types,
            procedure_return_types=procedure_return_types,
        )
    if isinstance(expr, ProviderBundlePathExpr):
        return _resolve_wcc_type_name(
            expr.target_type_name,
            type_env=type_env,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(
        expr,
        (
            ProviderResultExpr,
            CommandResultExpr,
            RunProviderPhaseExpr,
            ProduceOneOfExpr,
            ResumeOrStartExpr,
            MaterializeViewExpr,
        ),
    ):
        return _resolve_wcc_type_name(
            expr.returns_type_name,
            type_env=type_env,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, FinalizeSelectedItemExpr):
        return type_env.resolve_type(
            "SelectedItemResult",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, BacklogDrainExpr):
        return type_env.resolve_type(
            "DrainResult",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, ResourceTransitionExpr):
        if getattr(expr.spec, "mode", None) == "declared_transition":
            transition_def = type_env.resolve_transition_declaration(
                expr.spec.transition_ref_name or "",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
            return type_env.resolve_type(
                transition_def.result_type_name,
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        return type_env.resolve_type(
            "ResourceTransitionResult",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if isinstance(expr, CallExpr):
        return workflow_return_types[expr.callee_name]
    if isinstance(expr, ProcedureCallExpr):
        proc_ref_type = value_env.get(expr.callee_name)
        if isinstance(proc_ref_type, ProcRefTypeRef):
            return proc_ref_type.return_type_ref
        return procedure_return_types[expr.callee_name]
    if isinstance(expr, BindProcExpr):
        return value_env.get(expr.base_expr.target_name, PrimitiveTypeRef(name="String"))
    raise TypeError(f"unsupported WCC type inference node: {type(expr).__name__}")


def _merge_loop_control_types(
    left: LoopControlTypeRef,
    right: LoopControlTypeRef,
    *,
    owner: str,
) -> LoopControlTypeRef:
    if left.result_type_ref is None and right.result_type_ref is None:
        if not type_refs_compatible(left.state_type_ref, right.state_type_ref):
            raise TypeError(f"{owner} loop-control continue state types must match during WCC inference")
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=None,
        )
    if left.result_type_ref is not None and right.result_type_ref is not None:
        if not type_refs_compatible(left.result_type_ref, right.result_type_ref):
            raise TypeError(f"{owner} loop-control done result types must match during WCC inference")
        return LoopControlTypeRef(
            state_type_ref=left.state_type_ref,
            result_type_ref=left.result_type_ref,
        )
    result_type_ref = left.result_type_ref or right.result_type_ref
    state_type_ref = left.state_type_ref if left.result_type_ref is None else right.state_type_ref
    return LoopControlTypeRef(
        state_type_ref=state_type_ref,
        result_type_ref=result_type_ref,
    )


def _resolve_wcc_type_name(
    type_name: str,
    *,
    type_env: FrontendTypeEnvironment,
    span,
    form_path: tuple[str, ...],
    expansion_stack: tuple[object, ...],
) -> TypeRef:
    try:
        return type_env.resolve_type(
            type_name,
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
    except LispFrontendCompileError as exc:
        suffixes = (f"::{type_name}", f"/{type_name}")
        candidates: list[TypeRef] = []
        for name, candidate in type_env._type_refs.items():  # noqa: SLF001 - WCC consumes canonical import refs.
            if not any(name.endswith(suffix) for suffix in suffixes):
                continue
            if any(type_refs_compatible(existing, candidate) for existing in candidates):
                continue
            candidates.append(candidate)
        if len(candidates) == 1:
            return candidates[0]
        raise exc
