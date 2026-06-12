"""Shared structural traversal for Workflow Lisp expressions."""

from __future__ import annotations

from collections.abc import Iterator

from .drain_stdlib import BacklogDrainSpec
from .expressions import (
    BacklogDrainExpr,
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    ContinueExpr,
    DoneExpr,
    ExprNode,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    FunctionCallExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetProcExpr,
    LetStarExpr,
    LiteralExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PhaseTargetExpr,
    PureOpExpr,
    ProcedureCallExpr,
    ProcRefLiteralExpr,
    ProduceOneOfExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    RecordUpdateExpr,
    RecordExpr,
    ResourceTransitionExpr,
    ResumeOrStartExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from .phase_stdlib import ProduceOneOfCandidateSpec, ProduceOneOfProducerSpec
from .resource_stdlib import FinalizeSelectedItemSpec, ResourceTransitionSpec


def _produce_one_of_children(
    producer: ProduceOneOfProducerSpec,
    candidates: tuple[ProduceOneOfCandidateSpec, ...],
) -> tuple[ExprNode, ...]:
    children: list[ExprNode] = []
    if producer.provider_expr is not None:
        children.append(producer.provider_expr)
    if producer.prompt_expr is not None:
        children.append(producer.prompt_expr)
    children.extend(producer.inputs)
    for candidate in candidates:
        for field in candidate.fields:
            if field.target_expr is not None:
                children.append(field.target_expr)
    return tuple(children)


def _resource_transition_children(spec: ResourceTransitionSpec) -> tuple[ExprNode, ...]:
    children: list[ExprNode] = [spec.ctx_expr]
    if spec.when_expr is not None:
        children.append(spec.when_expr)
    children.extend((spec.resource_expr, spec.ledger_expr))
    return tuple(children)


def _finalize_selected_item_children(spec: FinalizeSelectedItemSpec) -> tuple[ExprNode, ...]:
    return (
        spec.ctx_expr,
        spec.selected_expr,
        spec.queue_transition_expr,
        spec.roadmap_expr,
        spec.plan_expr,
        spec.implementation_expr,
    )


def _backlog_drain_children(spec: BacklogDrainSpec) -> tuple[ExprNode, ...]:
    children: list[ExprNode] = [spec.ctx_expr]
    if spec.providers_expr is not None:
        children.append(spec.providers_expr)
    children.append(spec.max_iterations_expr)
    return tuple(children)


def iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]:
    """Return the direct child expressions for one authored expression node."""

    if isinstance(
        expr,
        (
            NameExpr,
            LiteralExpr,
            FieldAccessExpr,
            PhaseTargetExpr,
            GeneratedRelpathSeedExpr,
            WorkflowRefLiteralExpr,
            ProcRefLiteralExpr,
        ),
    ):
        return ()
    if isinstance(expr, RecordExpr):
        return tuple(field_expr for _, field_expr in expr.fields)
    if isinstance(expr, PureOpExpr):
        return expr.args
    if isinstance(expr, RecordUpdateExpr):
        return (expr.base_expr,) + tuple(field_expr for _, field_expr in expr.overrides)
    if isinstance(expr, LoopStateSeedExpr):
        return tuple(field.value_expr for field in expr.fields)
    if isinstance(expr, LoopStateUpdateExpr):
        return (expr.base_expr,) + tuple(field_expr for _, field_expr in expr.overrides)
    if isinstance(expr, UnionVariantExpr):
        return tuple(field_expr for _, field_expr in expr.fields)
    if isinstance(expr, LetStarExpr):
        return tuple(binding_expr for _, binding_expr in expr.bindings) + (expr.body,)
    if isinstance(expr, IfExpr):
        return (expr.condition_expr, expr.then_expr, expr.else_expr)
    if isinstance(expr, MatchExpr):
        return (expr.subject,) + tuple(arm.body for arm in expr.arms)
    if isinstance(expr, CallExpr):
        return tuple(binding_expr for _, binding_expr in expr.bindings)
    if isinstance(expr, FunctionCallExpr):
        return expr.args
    if isinstance(expr, ProcedureCallExpr):
        return expr.args
    if isinstance(expr, WithPhaseExpr):
        return (expr.ctx_expr, expr.body)
    if isinstance(expr, BindProcExpr):
        return (expr.base_expr,) + tuple(binding.value_expr for binding in expr.bindings)
    if isinstance(expr, LetProcExpr):
        return (expr.binding.local_body, expr.body)
    if isinstance(expr, ProviderResultExpr):
        return (expr.provider, expr.prompt) + expr.inputs
    if isinstance(expr, ProviderBundlePathExpr):
        return (expr.source_expr,)
    if isinstance(expr, CommandResultExpr):
        return expr.argv
    if isinstance(expr, ContinueExpr):
        return (expr.state_expr,)
    if isinstance(expr, DoneExpr):
        return (expr.result_expr,)
    if isinstance(expr, LoopRecurExpr):
        children: list[ExprNode] = [
            expr.max_iterations_expr,
            expr.initial_state_expr,
            expr.body_expr,
        ]
        if expr.on_exhausted_result_expr is not None:
            children.append(expr.on_exhausted_result_expr)
        return tuple(children)
    if isinstance(expr, RunProviderPhaseExpr):
        return (expr.ctx_expr, expr.inputs_expr, expr.provider, expr.prompt)
    if isinstance(expr, ProduceOneOfExpr):
        return (expr.ctx_expr,) + _produce_one_of_children(expr.producer, expr.candidates)
    if isinstance(expr, ResumeOrStartExpr):
        return (expr.ctx_expr, expr.resume_from_expr, expr.start_expr)
    if isinstance(expr, ResourceTransitionExpr):
        return _resource_transition_children(expr.spec)
    if isinstance(expr, FinalizeSelectedItemExpr):
        return _finalize_selected_item_children(expr.spec)
    if isinstance(expr, BacklogDrainExpr):
        return _backlog_drain_children(expr.spec)
    raise TypeError(f"unsupported expression traversal node: {type(expr)!r}")


def walk_expr(expr: ExprNode) -> Iterator[ExprNode]:
    """Yield one expression tree in deterministic pre-order."""

    yield expr
    for child in iter_child_exprs(expr):
        yield from walk_expr(child)
