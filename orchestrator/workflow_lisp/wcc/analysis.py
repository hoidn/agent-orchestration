"""Minimal scope and live-out analysis for WCC M3 control nodes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from ..type_env import TypeRef
from .model import WccBody, WccCase, WccCaseArm, WccHalt, WccJoin, WccJoinParam, WccJump, WccLet


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
class WccScopeAnalysis:
    arm_scopes: tuple[WccArmScope, ...]
    joins_by_name: Mapping[str, WccJoinSite]


def analyze_wcc_body(body: WccBody) -> WccScopeAnalysis:
    """Collect branch-local arm scopes and explicit join live-outs."""

    arm_scopes: list[WccArmScope] = []
    jump_args_by_join: dict[str, list[tuple[object, ...]]] = defaultdict(list)
    joins_by_name: dict[str, WccJoin] = {}

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
        if isinstance(node, WccJump):
            jump_args_by_join[node.join_name].append(tuple(node.args))
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
