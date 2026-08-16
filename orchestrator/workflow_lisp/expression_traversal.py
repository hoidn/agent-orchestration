"""Shared structural traversal for Workflow Lisp expressions."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import fields as dataclass_fields, is_dataclass, replace
from typing import cast

from .expressions import (
    BindProcExpr,
    CallExpr,
    CommandResultExpr,
    CompilerListNonemptyHeadExpr,
    ContinueExpr,
    DoneExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    FinalizeSelectedItemExpr,
    CondExpr,
    FunctionCallExpr,
    GeneratedRelpathSeedExpr,
    IfExpr,
    LetProcExpr,
    LetStarExpr,
    ListExpr,
    ListMapEffectExpr,
    ListMapExpr,
    LiteralExpr,
    MaterializeViewExpr,
    LoopBodyFnExpr,
    LoopStateSeedExpr,
    LoopStateUpdateExpr,
    LoopRecurExpr,
    MatchExpr,
    NameExpr,
    PathJoinUnderExpr,
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
    RunRefExpr,
    TrialExpr,
    RunProviderPhaseExpr,
    UnionVariantExpr,
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
    WithPhaseExpr,
    WorkflowRefLiteralExpr,
)
from .phase_stdlib import ProduceOneOfCandidateSpec, ProduceOneOfProducerSpec
from .prompts import PromptApplicationExpr
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
    if spec.mode == "declared_transition":
        children: list[ExprNode] = []
        if spec.expected_version_expr is not None:
            children.append(spec.expected_version_expr)
        if spec.request_expr is not None:
            children.append(spec.request_expr)
        return tuple(children)
    children = [spec.ctx_expr]
    if spec.when_expr is not None:
        children.append(spec.when_expr)
    if spec.resource_expr is not None:
        children.append(spec.resource_expr)
    if spec.ledger_expr is not None:
        children.append(spec.ledger_expr)
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


def iter_child_exprs(expr: ExprNode) -> tuple[ExprNode, ...]:
    """Return the direct child expressions for one authored expression node."""

    if isinstance(
        expr,
        (
            NameExpr,
            LiteralExpr,
            EnumMemberExpr,
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
    if isinstance(expr, ListExpr):
        return expr.items
    if isinstance(expr, ListMapExpr):
        return (expr.source_expr, expr.body_expr)
    if isinstance(expr, ListMapEffectExpr):
        return (expr.source_expr, expr.body_expr)
    if isinstance(expr, CompilerListNonemptyHeadExpr):
        return (expr.source_expr,)
    if isinstance(expr, PathJoinUnderExpr):
        return (expr.child_expr,)
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
    if isinstance(expr, CondExpr):
        children: list[ExprNode] = []
        for clause in expr.clauses:
            if clause.condition_expr is not None:
                children.append(clause.condition_expr)
            children.append(clause.result_expr)
        return tuple(children)
    if isinstance(expr, MatchExpr):
        return (expr.subject,) + tuple(arm.body for arm in expr.arms)
    if isinstance(expr, CallExpr):
        return tuple(binding_expr for _, binding_expr in expr.bindings)
    if isinstance(expr, RunRefExpr):
        return tuple(value_expr for _, value_expr in expr.inputs)
    if isinstance(expr, TrialExpr):
        return tuple(arm.run_ref for arm in expr.arms)
    if isinstance(expr, FunctionCallExpr):
        return expr.args
    if isinstance(expr, ProcedureCallExpr):
        return expr.args
    if isinstance(expr, WithPhaseExpr):
        return (expr.ctx_expr, expr.body)
    if isinstance(expr, WithLiveProvidersExpr):
        return tuple(binding.value_expr for binding in expr.bindings) + (expr.body,)
    if isinstance(expr, WithLiveProviderPeersExpr):
        return tuple(
            binding.value_expr for binding in expr.bindings
        ) + (expr.body,)
    if isinstance(expr, BindProcExpr):
        return (expr.base_expr,) + tuple(binding.value_expr for binding in expr.bindings)
    if isinstance(expr, LetProcExpr):
        return (expr.binding.local_body, expr.body)
    if isinstance(expr, ProviderResultExpr):
        prompt_children = (
            [fill.value_expr for fill in expr.prompt.fills]
            if isinstance(expr.prompt, PromptApplicationExpr)
            else [expr.prompt]
        )
        children = [expr.provider, *prompt_children, *expr.inputs]
        if expr.prompt_dependencies is not None:
            children.extend(expr.prompt_dependencies.required)
            children.extend(expr.prompt_dependencies.optional)
        if expr.model is not None:
            children.append(expr.model)
        if expr.effort is not None:
            children.append(expr.effort)
        return tuple(children)
    if isinstance(expr, ProviderBundlePathExpr):
        return (expr.source_expr,)
    if isinstance(expr, CommandResultExpr):
        return expr.argv + tuple(
            value_expr for _, value_expr in expr.adapter_inputs
        )
    if isinstance(expr, ContinueExpr):
        return (expr.state_expr,)
    if isinstance(expr, DoneExpr):
        return (
            (expr.result_expr,)
            if expr.terminal_state_expr is None
            else (expr.result_expr, expr.terminal_state_expr)
        )
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
    if isinstance(expr, MaterializeViewExpr):
        children: list[ExprNode] = [expr.value_expr]
        if expr.target_expr is not None:
            children.append(expr.target_expr)
        return tuple(children)
    if isinstance(expr, FinalizeSelectedItemExpr):
        return _finalize_selected_item_children(expr.spec)
    raise TypeError(f"unsupported expression traversal node: {type(expr)!r}")


def walk_expr(expr: ExprNode) -> Iterator[ExprNode]:
    """Yield one expression tree in deterministic pre-order."""

    yield expr
    for child in iter_child_exprs(expr):
        yield from walk_expr(child)


def map_expr(
    expr: object,
    on_name: Callable[[NameExpr], ExprNode],
    *,
    bound: frozenset[str] = frozenset(),
) -> object:
    """Rebuild one expression, applying ``on_name`` to each free ``NameExpr``.

    ``on_name`` receives every ``NameExpr`` whose name is not locally bound
    and returns its replacement expression.  Binder forms thread their bound
    names so locally-scoped references are left untouched: sequential
    ``let*`` bindings, ``list/map`` binder names, per-arm ``match`` binding
    names, loop body binders, and local procedure parameter scopes all shadow
    outer references independently.  Nested containers and dataclass fields
    are traversed structurally; the original node is returned unchanged
    whenever no child was rewritten.
    """

    if isinstance(expr, NameExpr):
        if expr.name in bound:
            return expr
        return on_name(expr)
    if isinstance(expr, FieldAccessExpr):
        rewritten_base = map_expr(expr.base, on_name, bound=bound)
        if rewritten_base is expr.base:
            return expr
        if isinstance(rewritten_base, FieldAccessExpr):
            return replace(
                expr,
                base=rewritten_base.base,
                fields=(*rewritten_base.fields, *expr.fields),
            )
        if isinstance(rewritten_base, NameExpr):
            return replace(expr, base=rewritten_base)
        # A field access is only ever name-rooted. When the base resolved to a
        # non-name value, keep the original NameExpr base rather than emitting
        # an invalid non-Name-rooted FieldAccessExpr; the caller owns how a
        # non-name substitution is handled.
        return expr
    if isinstance(expr, LetStarExpr):
        local_bound = set(bound)
        rewritten_bindings: list[tuple[str, ExprNode]] = []
        changed = False
        for binding_name, binding_expr in expr.bindings:
            rewritten_binding = map_expr(
                binding_expr,
                on_name,
                bound=frozenset(local_bound),
            )
            rewritten_bindings.append((binding_name, cast(ExprNode, rewritten_binding)))
            changed = changed or rewritten_binding is not binding_expr
            local_bound.add(binding_name)
        rewritten_body = map_expr(
            expr.body,
            on_name,
            bound=frozenset(local_bound),
        )
        changed = changed or rewritten_body is not expr.body
        if not changed:
            return expr
        return replace(
            expr,
            bindings=tuple(rewritten_bindings),
            body=rewritten_body,
        )
    if isinstance(expr, (ListMapExpr, ListMapEffectExpr)):
        rewritten_source = map_expr(expr.source_expr, on_name, bound=bound)
        rewritten_body = map_expr(
            expr.body_expr,
            on_name,
            bound=bound | {expr.binder_name},
        )
        if (
            rewritten_source is expr.source_expr
            and rewritten_body is expr.body_expr
        ):
            return expr
        return replace(
            expr,
            source_expr=rewritten_source,
            body_expr=rewritten_body,
        )
    if isinstance(expr, MatchExpr):
        rewritten_subject = map_expr(expr.subject, on_name, bound=bound)
        changed = rewritten_subject is not expr.subject
        rewritten_arms: list[object] = []
        for arm in expr.arms:
            rewritten_arm_body = map_expr(
                arm.body,
                on_name,
                bound=bound | {arm.binding_name},
            )
            changed = changed or rewritten_arm_body is not arm.body
            if rewritten_arm_body is arm.body:
                rewritten_arms.append(arm)
            else:
                rewritten_arms.append(replace(arm, body=rewritten_arm_body))
        if not changed:
            return expr
        return replace(
            expr,
            subject=rewritten_subject,
            arms=tuple(rewritten_arms),
        )
    if isinstance(expr, LoopBodyFnExpr):
        rewritten_body = map_expr(
            expr.body_expr,
            on_name,
            bound=bound | {expr.binding_name},
        )
        if rewritten_body is expr.body_expr:
            return expr
        return replace(expr, body_expr=rewritten_body)
    if isinstance(expr, LoopRecurExpr):
        rewritten_body = map_expr(
            expr.body_expr,
            on_name,
            bound=bound | {expr.binding_name},
        )
        changed = rewritten_body is not expr.body_expr
        changed_updates: dict[str, object] = {}
        if changed:
            changed_updates["body_expr"] = rewritten_body
        for field_name in ("max_iterations_expr", "initial_state_expr"):
            current = getattr(expr, field_name)
            rewritten = map_expr(current, on_name, bound=bound)
            changed = changed or rewritten is not current
            if rewritten is not current:
                changed_updates[field_name] = rewritten
        if expr.on_exhausted_result_expr is not None:
            current = expr.on_exhausted_result_expr
            rewritten = map_expr(current, on_name, bound=bound)
            changed = changed or rewritten is not current
            if rewritten is not current:
                changed_updates["on_exhausted_result_expr"] = rewritten
        if not changed:
            return expr
        return replace(expr, **changed_updates)
    if isinstance(expr, LetProcExpr):
        proc_bound = bound | {expr.binding.local_name} | {
            param.name for param in expr.binding.params
        }
        rewritten_local_body = map_expr(
            expr.binding.local_body,
            on_name,
            bound=frozenset(proc_bound),
        )
        rewritten_body = map_expr(
            expr.body,
            on_name,
            bound=bound | {expr.binding.local_name},
        )
        if (
            rewritten_local_body is expr.binding.local_body
            and rewritten_body is expr.body
        ):
            return expr
        return replace(
            expr,
            binding=replace(expr.binding, local_body=rewritten_local_body),
            body=rewritten_body,
        )
    if isinstance(expr, tuple):
        rewritten_items = tuple(
            map_expr(item, on_name, bound=bound) for item in expr
        )
        if all(
            rewritten is original
            for rewritten, original in zip(
                rewritten_items,
                expr,
                strict=True,
            )
        ):
            return expr
        return rewritten_items
    if isinstance(expr, list):
        rewritten_items = [
            map_expr(item, on_name, bound=bound) for item in expr
        ]
        if all(
            rewritten is original
            for rewritten, original in zip(
                rewritten_items,
                expr,
                strict=True,
            )
        ):
            return expr
        return rewritten_items
    if isinstance(expr, Mapping):
        rewritten_items = {
            key: map_expr(item, on_name, bound=bound)
            for key, item in expr.items()
        }
        if all(
            rewritten_items[key] is item
            for key, item in expr.items()
        ):
            return expr
        return rewritten_items
    if is_dataclass(expr) and not isinstance(expr, type):
        changed_updates: dict[str, object] = {}
        for field in dataclass_fields(expr):
            if not field.init:
                continue
            current = getattr(expr, field.name)
            rewritten = map_expr(current, on_name, bound=bound)
            if rewritten is not current:
                changed_updates[field.name] = rewritten
        if changed_updates:
            return replace(expr, **changed_updates)
        return expr
    return expr


def free_expr_names(
    expr: object,
    *,
    bound: frozenset[str] = frozenset(),
) -> set[str]:
    """Return the free ``NameExpr`` names referenced by one expression."""

    names: set[str] = set()

    def collect(node: NameExpr) -> NameExpr:
        names.add(node.name)
        return node

    map_expr(expr, collect, bound=bound)
    return names
