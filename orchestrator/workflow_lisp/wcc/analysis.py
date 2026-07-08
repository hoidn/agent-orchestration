"""Minimal scope and live-out analysis for WCC M3 control nodes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from ..type_env import TypeRef
from .model import (
    WccBody,
    WccCase,
    WccHalt,
    WccIf,
    WccJoin,
    WccJoinParam,
    WccJump,
    WccLet,
    WccLoopContinue,
    WccLoopDone,
    WccLoopRole,
    WccRecJoin,
)


@dataclass(frozen=True)
class WccArmScope:
    scope_id: str
    variant_name: str
    binding_name: str
    binding_type_ref: TypeRef
    proof_context: tuple[object, ...]


@dataclass(frozen=True)
class WccJoinSite:
    join_name: str
    params: tuple[WccJoinParam, ...]
    live_out_names: tuple[str, ...]
    jump_args: tuple[tuple[object, ...], ...]


@dataclass(frozen=True)
class WccLoopSite:
    loop_name: str
    scope_id: str
    state_params: tuple[WccJoinParam, ...]
    budget_source: object
    body_proof_scopes: tuple[object, ...]
    live_in_names: tuple[str, ...]
    live_out_names: tuple[str, ...]
    terminal_type: TypeRef | object
    exhaustion_type: TypeRef | object | None
    roles: WccLoopRole


@dataclass(frozen=True)
class WccScopeAnalysis:
    arm_scopes: tuple[WccArmScope, ...]
    joins_by_name: Mapping[str, WccJoinSite]
    loop_sites: tuple[WccLoopSite, ...] = ()


def analyze_wcc_body(body: WccBody) -> WccScopeAnalysis:
    """Collect branch-local arm scopes and explicit join live-outs."""

    arm_scopes: list[WccArmScope] = []
    jump_args_by_join: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    joins_by_name: dict[str, WccJoin] = {}
    loop_sites: list[WccLoopSite] = []

    def walk(node: WccBody) -> None:
        if isinstance(node, WccLet):
            walk(node.body)
            return
        if isinstance(node, WccCase):
            _record_case(node, arm_scopes)
            for arm in node.arms:
                walk(arm.body)
            return
        if isinstance(node, WccJoin):
            joins_by_name[node.join_name] = node
            walk(node.body)
            walk(node.continuation)
            return
        if isinstance(node, WccIf):
            walk(node.then_body)
            walk(node.else_body)
            return
        if isinstance(node, WccJump):
            jump_args_by_join[node.join_name].append(tuple(node.args))
            return
        if isinstance(node, WccRecJoin):
            loop_sites.append(
                WccLoopSite(
                    loop_name=node.loop_name,
                    scope_id=node.metadata.scope_id,
                    state_params=node.params,
                    budget_source=node.budget,
                    body_proof_scopes=_proof_scopes(node.body),
                    live_in_names=tuple(param.name for param in node.params),
                    live_out_names=tuple(param.name for param in node.params),
                    terminal_type=node.metadata.type_ref,
                    exhaustion_type=node.exhaustion.metadata.type_ref if node.exhaustion is not None else None,
                    roles=node.roles,
                )
            )
            walk(node.body)
            if node.exhaustion is not None:
                walk(node.exhaustion)
            return
        if isinstance(node, (WccLoopContinue, WccLoopDone)):
            return
        if isinstance(node, WccHalt):
            return
        raise TypeError(f"unsupported WCC analysis node: {type(node).__name__}")

    walk(body)
    return WccScopeAnalysis(
        arm_scopes=tuple(arm_scopes),
        joins_by_name={
            join_name: WccJoinSite(
                join_name=join_name,
                params=join.params,
                live_out_names=tuple(param.name for param in join.params),
                jump_args=tuple(jump_args_by_join.get(join_name, ())),
            )
            for join_name, join in joins_by_name.items()
        },
        loop_sites=tuple(loop_sites),
    )


def _record_case(case: WccCase, arm_scopes: list[WccArmScope]) -> None:
    for arm in case.arms:
        arm_scopes.append(
            WccArmScope(
                scope_id=arm.body.metadata.scope_id,
                variant_name=arm.variant_name,
                binding_name=arm.binding_name,
                binding_type_ref=arm.binding_type_ref,
                proof_context=arm.body.metadata.proof_context,
            )
        )


def _proof_scopes(body: WccBody) -> tuple[object, ...]:
    scopes: list[object] = []

    def walk(node: WccBody) -> None:
        if isinstance(node, WccLet):
            walk(node.body)
            return
        if isinstance(node, WccCase):
            scopes.extend(arm.body.metadata.proof_context for arm in node.arms)
            for arm in node.arms:
                walk(arm.body)
            return
        if isinstance(node, WccJoin):
            walk(node.body)
            walk(node.continuation)
            return
        if isinstance(node, WccIf):
            walk(node.then_body)
            walk(node.else_body)
            return
        if isinstance(node, WccRecJoin):
            walk(node.body)
            if node.exhaustion is not None:
                walk(node.exhaustion)

    walk(body)
    return tuple(scopes)
