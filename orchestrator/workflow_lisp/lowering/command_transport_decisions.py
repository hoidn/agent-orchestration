"""Pure legacy binding decisions; emission stays with each lowering owner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any, Literal

from ..expressions import (
    BindProcExpr, FieldAccessExpr, IfExpr, LiteralExpr, LoopStateSeedExpr,
    LoopStateUpdateExpr, MatchExpr, NameExpr, PhaseTargetExpr, ProcRefLiteralExpr,
    ProviderBundlePathExpr, PureOpExpr, RecordExpr, RecordUpdateExpr, UnionVariantExpr,
)
from ..wcc.model import (
    WccBody, WccCase, WccHalt, WccIf, WccJoin, WccJump, WccLet,
    WccLoopContinue, WccLoopDone, WccNameAtom, WccPerform, WccRecJoin,
)
from .pure_projection import is_pure_projection_expr


WccBindingKind = Literal["alias", "expansion_projection", "whole_value", "request_projection", "if_projection"]
SurfaceBindingKind = Literal["match", "projection", "expression"]


def is_inline_let_binding_expr(expr: Any) -> bool:
    return isinstance(expr, (
        NameExpr, FieldAccessExpr, PhaseTargetExpr, LiteralExpr, RecordExpr,
        RecordUpdateExpr, LoopStateSeedExpr, LoopStateUpdateExpr, UnionVariantExpr,
        ProviderBundlePathExpr, ProcRefLiteralExpr, BindProcExpr, PureOpExpr,
    ))


def pure_projection_binding_candidate(resolved_binding: Any) -> Any | None:
    if resolved_binding is None or isinstance(resolved_binding, (str, Mapping)):
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
        if isinstance(expr, NameExpr) and isinstance(existing_ref, str):
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
            if isinstance(resolved_binding, (str, LiteralExpr)):
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
            return (referenced_names(value.keyword_args), frozenset(), frozenset())
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
        if isinstance(value, (WccLet, WccCase, WccIf, WccJoin, WccRecJoin, WccHalt, WccJump, WccLoopContinue, WccLoopDone)):
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
