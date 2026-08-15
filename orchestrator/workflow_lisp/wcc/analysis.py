"""Minimal scope and live-out analysis for WCC M3 control nodes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import IfExpr
from ..syntax import MAX_STATIC_LIVE_PROVIDER_PEERS
from ..type_env import TypeRef
from .model import (
    WccBody,
    WccCall,
    WccCase,
    WccFieldAccessAtom,
    WccHalt,
    WccIf,
    WccInject,
    WccJoin,
    WccJoinParam,
    WccJump,
    WccLet,
    WccLiteralAtom,
    WccLoopContinue,
    WccLoopDone,
    WccLoopRole,
    WccNameAtom,
    WccOpaqueFrontendValue,
    WccPerform,
    WccPhaseTargetAtom,
    WccProviderSupervision,
    WccProviderSupervisionMember,
    WccProviderPeerGroup,
    WccProviderPeerGroupMember,
    WccPureOp,
    WccRecJoin,
    WccRecordAtom,
    WccSelect,
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
            if isinstance(node.bound_value, WccProviderSupervision):
                validate_wcc_provider_supervision(node.bound_value)
            elif isinstance(node.bound_value, WccProviderPeerGroup):
                validate_wcc_provider_peer_group(node.bound_value)
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


_WCC_VALUE_TYPES = (
    WccLiteralAtom,
    WccNameAtom,
    WccFieldAccessAtom,
    WccPhaseTargetAtom,
    WccRecordAtom,
    WccOpaqueFrontendValue,
    WccInject,
    WccPureOp,
    WccSelect,
)


def validate_wcc_provider_supervision(
    group: WccProviderSupervision,
) -> WccProviderSupervision:
    """Validate and annotate one closed provider-supervision WCC term."""

    if len(group.members) != 2:
        _raise_supervision_diagnostic(
            code="provider_supervision_member_ineligible",
            message="provider supervision requires exactly two closed members",
            metadata=group.metadata,
        )
    member_names = tuple(member.binding_name for member in group.members)
    expected_names = {group.supervisor_name, group.worker_name}
    if (
        group.supervisor_name == group.worker_name
        or len(set(member_names)) != len(member_names)
        or set(member_names) != expected_names
    ):
        _raise_supervision_diagnostic(
            code="provider_supervision_member_ineligible",
            message=(
                "provider supervision member identities must match the "
                "distinct worker and supervisor bindings"
            ),
            metadata=group.metadata,
        )

    validated_members = tuple(
        _validate_wcc_provider_supervision_member(member)
        for member in group.members
    )
    supervisor_member = next(
        member
        for member in validated_members
        if member.binding_name == group.supervisor_name
    )
    projection_violation = (
        _nonidentity_supervisor_projection_metadata(supervisor_member)
    )
    if projection_violation is not None:
        _raise_member_ineligible(
            supervisor_member,
            metadata=projection_violation,
            reason=(
                "the supervisor provider must return its directive "
                "without a transforming projection"
            ),
        )
    _validate_wcc_provider_supervision_settlement(group.settlement_body)
    return replace(group, members=validated_members)


def validate_wcc_provider_peer_group(
    group: WccProviderPeerGroup,
) -> WccProviderPeerGroup:
    """Validate and annotate one closed provider-peer-group WCC term."""

    if not (
        2
        <= len(group.members)
        <= MAX_STATIC_LIVE_PROVIDER_PEERS
    ):
        _raise_peer_group_diagnostic(
            code="provider_peer_group_member_ineligible",
            message=(
                "provider peer groups require between two and eight "
                "closed members"
            ),
            metadata=group.metadata,
        )
    member_names = tuple(
        member.binding_name
        for member in group.members
    )
    if len(set(member_names)) != len(member_names):
        _raise_peer_group_diagnostic(
            code="provider_peer_group_member_ineligible",
            message="provider peer group member identities must be unique",
            metadata=group.metadata,
        )

    member_name_set = set(member_names)
    validated_members: list[WccProviderPeerGroupMember] = []
    for member in group.members:
        sibling_references = (
            _free_wcc_names_in_body(member.normalized_body)
            & (
                member_name_set
                - {member.binding_name}
                - set(member.lexical_capture_names)
            )
        )
        if sibling_references:
            _raise_member_ineligible(
                member,
                metadata=member.metadata,
                reason=(
                    "member references sibling result binding(s): "
                    + ", ".join(sorted(sibling_references))
                ),
            )
        validated_members.append(
            _validate_wcc_provider_peer_group_member(member)
        )

    settlement_free_names = _free_wcc_names_in_body(
        group.settlement_body
    )
    unsupported_settlement_names = (
        settlement_free_names - member_name_set
    )
    if unsupported_settlement_names:
        _raise_peer_group_diagnostic(
            code=(
                "provider_peer_group_settlement_"
                "environment_invalid"
            ),
            message=(
                "provider peer group settlement may reference only "
                "closed peer member results; found: "
                + ", ".join(sorted(unsupported_settlement_names))
            ),
            metadata=group.settlement_body.metadata,
        )
    _validate_wcc_provider_peer_group_settlement(
        group.settlement_body
    )
    return replace(group, members=tuple(validated_members))


def _validate_wcc_provider_supervision_member(
    member: WccProviderSupervisionMember,
) -> WccProviderSupervisionMember:
    return _validate_wcc_provider_region_member(member)


def _validate_wcc_provider_peer_group_member(
    member: WccProviderPeerGroupMember,
) -> WccProviderPeerGroupMember:
    return _validate_wcc_provider_region_member(member)


def _validate_wcc_provider_region_member(
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
) -> WccProviderSupervisionMember | WccProviderPeerGroupMember:
    bindings: list[WccLet] = []
    current = member.normalized_body
    seen_names: set[str] = set()
    all_local_names: set[str] = set()
    binding_probe = current
    while isinstance(binding_probe, WccLet):
        all_local_names.add(binding_probe.bound_name)
        binding_probe = binding_probe.body
    provider_binding_name: str | None = None
    provider_perform: WccPerform | None = None

    while isinstance(current, WccLet):
        if current.bound_name in seen_names:
            _raise_member_ineligible(
                member,
                metadata=current.metadata,
                reason=(
                    "member bindings must have unique normalized names"
                ),
            )
        seen_names.add(current.bound_name)
        bindings.append(current)
        bound_value = current.bound_value
        if isinstance(bound_value, WccCall):
            _raise_member_ineligible(
                member,
                metadata=bound_value.metadata,
                reason="member contains a residual procedure call",
            )
        forward_references = (
            _referenced_wcc_names(bound_value)
            & (all_local_names - seen_names)
        )
        if forward_references:
            _raise_member_ineligible(
                member,
                metadata=bound_value.metadata,
                reason=(
                    "member binding references later local binding(s): "
                    + ", ".join(sorted(forward_references))
                ),
            )
        disqualifying_control = _disqualifying_member_control_metadata(
            bound_value
        )
        if disqualifying_control is not None:
            _raise_member_ineligible(
                member,
                metadata=disqualifying_control,
                reason="member contains a conditional pure projection",
            )
        if isinstance(bound_value, WccPerform):
            if bound_value.perform_kind != "provider_result":
                _raise_member_ineligible(
                    member,
                    metadata=bound_value.metadata,
                    reason=(
                        "member contains a non-provider perform "
                        f"`{bound_value.perform_kind}`"
                    ),
                )
            if provider_perform is not None:
                _raise_member_ineligible(
                    member,
                    metadata=bound_value.metadata,
                    reason="member contains more than one provider perform",
                )
            provider_perform = bound_value
            provider_binding_name = current.bound_name
        elif not isinstance(bound_value, _WCC_VALUE_TYPES):
            _raise_member_ineligible(
                member,
                metadata=bound_value.metadata,
                reason=(
                    "member contains a control or effect binding outside "
                    "the canonical provider region"
                ),
            )
        current = current.body

    if not isinstance(current, WccHalt):
        _raise_member_ineligible(
            member,
            metadata=current.metadata,
            reason=(
                "member control spine must contain only WccLet nodes "
                "followed by WccHalt"
            ),
        )
    if not isinstance(current.result, _WCC_VALUE_TYPES):
        _raise_member_ineligible(
            member,
            metadata=current.metadata,
            reason="member terminal projection must be a WCC value",
        )
    disqualifying_control = _disqualifying_member_control_metadata(
        current.result
    )
    if disqualifying_control is not None:
        _raise_member_ineligible(
            member,
            metadata=disqualifying_control,
            reason="member contains a conditional pure projection",
        )
    if provider_perform is None or provider_binding_name is None:
        _raise_member_ineligible(
            member,
            metadata=member.metadata,
            reason="member must contain exactly one provider perform",
        )

    dependencies_by_name = {
        binding.bound_name: _referenced_wcc_names(binding.bound_value)
        for binding in bindings
    }
    terminal_dependencies = _transitive_local_dependencies(
        _referenced_wcc_names(current.result),
        dependencies_by_name=dependencies_by_name,
    )
    if provider_binding_name not in terminal_dependencies:
        _raise_member_ineligible(
            member,
            metadata=current.result.metadata,
            reason=(
                "member terminal projection does not depend on its "
                "provider result"
            ),
        )

    live_dependencies = _transitive_local_dependencies(
        {
            *_referenced_wcc_names(current.result),
            *_referenced_wcc_names(provider_perform),
        },
        dependencies_by_name=dependencies_by_name,
    )
    for binding in bindings:
        if (
            isinstance(binding.bound_value, _WCC_VALUE_TYPES)
            and binding.bound_name not in live_dependencies
        ):
            _raise_member_ineligible(
                member,
                metadata=binding.bound_value.metadata,
                reason=(
                    f"pure member binding `{binding.bound_name}` feeds "
                    "neither the provider perform nor the terminal result"
                ),
            )

    if (
        member.provider_binding_name is not None
        and member.provider_binding_name != provider_binding_name
    ):
        _raise_member_ineligible(
            member,
            metadata=member.metadata,
            reason=(
                "recorded provider binding does not match the canonical "
                "provider perform"
            ),
        )
    return replace(
        member,
        provider_binding_name=provider_binding_name,
    )


def _validate_wcc_provider_supervision_settlement(body: WccBody) -> None:
    current = body
    while isinstance(current, WccLet):
        if not isinstance(current.bound_value, _WCC_VALUE_TYPES):
            _raise_supervision_diagnostic(
                code="provider_supervision_settlement_effectful",
                message=(
                    "provider supervision settlement may contain only "
                    "WCC value bindings"
                ),
                metadata=current.bound_value.metadata,
            )
        current = current.body
    if not isinstance(current, WccHalt):
        _raise_supervision_diagnostic(
            code="provider_supervision_settlement_effectful",
            message=(
                "provider supervision settlement control spine must contain "
                "only WccLet nodes followed by WccHalt"
            ),
            metadata=current.metadata,
        )
    if not isinstance(current.result, _WCC_VALUE_TYPES):
        _raise_supervision_diagnostic(
            code="provider_supervision_settlement_effectful",
            message="provider supervision settlement result must be a WCC value",
            metadata=current.metadata,
        )


def _validate_wcc_provider_peer_group_settlement(
    body: WccBody,
) -> None:
    current = body
    while isinstance(current, WccLet):
        if not isinstance(current.bound_value, _WCC_VALUE_TYPES):
            _raise_peer_group_diagnostic(
                code="provider_peer_group_settlement_effectful",
                message=(
                    "provider peer group settlement may contain only "
                    "WCC value bindings"
                ),
                metadata=current.bound_value.metadata,
            )
        current = current.body
    if not isinstance(current, WccHalt):
        _raise_peer_group_diagnostic(
            code="provider_peer_group_settlement_effectful",
            message=(
                "provider peer group settlement control spine must contain "
                "only WccLet nodes followed by WccHalt"
            ),
            metadata=current.metadata,
        )
    if not isinstance(current.result, _WCC_VALUE_TYPES):
        _raise_peer_group_diagnostic(
            code="provider_peer_group_settlement_effectful",
            message=(
                "provider peer group settlement result must be a WCC value"
            ),
            metadata=current.metadata,
        )


def _nonidentity_supervisor_projection_metadata(
    member: WccProviderSupervisionMember,
):
    provider_binding_name = member.provider_binding_name
    assert provider_binding_name is not None
    aliases = {provider_binding_name}
    provider_seen = False
    current = member.normalized_body
    while isinstance(current, WccLet):
        if current.bound_name == provider_binding_name:
            provider_seen = True
        elif provider_seen:
            if (
                not isinstance(current.bound_value, WccNameAtom)
                or current.bound_value.name not in aliases
            ):
                return current.bound_value.metadata
            aliases.add(current.bound_name)
        current = current.body
    assert isinstance(current, WccHalt)
    if (
        not isinstance(current.result, WccNameAtom)
        or current.result.name not in aliases
    ):
        return current.result.metadata
    return None


def _transitive_local_dependencies(
    initial_names: set[str],
    *,
    dependencies_by_name: Mapping[str, set[str]],
) -> set[str]:
    dependencies = set(initial_names)
    pending = list(initial_names)
    while pending:
        name = pending.pop()
        for dependency in dependencies_by_name.get(name, ()):
            if dependency in dependencies:
                continue
            dependencies.add(dependency)
            pending.append(dependency)
    return dependencies


def _referenced_wcc_names(value: object) -> set[str]:
    if isinstance(value, WccNameAtom):
        return {value.name}
    if isinstance(value, WccFieldAccessAtom):
        return _referenced_wcc_names(value.base)
    if isinstance(value, (WccRecordAtom, WccInject)):
        return {
            name
            for _, field_value in value.fields
            for name in _referenced_wcc_names(field_value)
        }
    if isinstance(value, WccPureOp):
        return {
            name
            for arg in value.args
            for name in _referenced_wcc_names(arg)
        }
    if isinstance(value, WccSelect):
        return (
            _referenced_wcc_names(value.condition)
            | _referenced_wcc_names(value.then_value)
            | _referenced_wcc_names(value.else_value)
        )
    if isinstance(
        value,
        (
            WccLiteralAtom,
            WccPhaseTargetAtom,
            WccOpaqueFrontendValue,
        ),
    ):
        return set()
    if isinstance(value, WccPerform):
        referenced = {
            name
            for arg in value.positional_args
            for name in _referenced_wcc_names(arg)
        }
        referenced.update(
            name
            for _, arg in value.keyword_args
            for name in _referenced_wcc_names(arg)
        )
        referenced.update(
            _referenced_wcc_names_in_payload(value.operation_payload)
        )
        return referenced
    if isinstance(value, WccCall):
        referenced = {
            name
            for arg in value.args
            for name in _referenced_wcc_names(arg)
        }
        referenced.update(
            name
            for capture in value.specialization_captures
            for name in _referenced_wcc_names(capture.value)
        )
        return referenced
    return set()


def _free_wcc_names_in_body(
    body: WccBody,
    *,
    bound_names: frozenset[str] = frozenset(),
) -> set[str]:
    if isinstance(body, WccLet):
        return (
            _referenced_wcc_names(body.bound_value) - bound_names
        ) | _free_wcc_names_in_body(
            body.body,
            bound_names=bound_names | {body.bound_name},
        )
    if isinstance(body, WccCase):
        names = _referenced_wcc_names(body.subject) - bound_names
        for arm in body.arms:
            names.update(
                _free_wcc_names_in_body(
                    arm.body,
                    bound_names=(
                        bound_names | {arm.binding_name}
                    ),
                )
            )
        return names
    if isinstance(body, WccIf):
        return (
            _referenced_wcc_names(body.condition) - bound_names
        ) | _free_wcc_names_in_body(
            body.then_body,
            bound_names=bound_names,
        ) | _free_wcc_names_in_body(
            body.else_body,
            bound_names=bound_names,
        )
    if isinstance(body, WccJoin):
        join_bound_names = bound_names | {
            param.name
            for param in body.params
        }
        return _free_wcc_names_in_body(
            body.body,
            bound_names=bound_names,
        ) | _free_wcc_names_in_body(
            body.continuation,
            bound_names=join_bound_names,
        )
    if isinstance(body, WccJump):
        return {
            name
            for arg in body.args
            for name in _referenced_wcc_names(arg)
            if name not in bound_names
        }
    if isinstance(body, WccRecJoin):
        names = _referenced_wcc_names(body.budget) - bound_names
        if body.initial_state is not None:
            names.update(
                _referenced_wcc_names(body.initial_state)
                - bound_names
            )
        loop_bound_names = bound_names | {
            param.name
            for param in body.params
        }
        names.update(
            _free_wcc_names_in_body(
                body.body,
                bound_names=loop_bound_names,
            )
        )
        if body.exhaustion is not None:
            names.update(
                _free_wcc_names_in_body(
                    body.exhaustion,
                    bound_names=bound_names,
                )
            )
        return names
    if isinstance(body, WccLoopContinue):
        return {
            name
            for arg in body.state_args
            for name in _referenced_wcc_names(arg)
            if name not in bound_names
        }
    if isinstance(body, WccLoopDone):
        names = _referenced_wcc_names(body.result)
        if body.state is not None:
            names.update(_referenced_wcc_names(body.state))
        return names - bound_names
    if isinstance(body, WccHalt):
        return _referenced_wcc_names(body.result) - bound_names
    return set()


def _referenced_wcc_names_in_payload(value: object) -> set[str]:
    if isinstance(value, _WCC_VALUE_TYPES):
        return _referenced_wcc_names(value)
    if isinstance(value, Mapping):
        return {
            name
            for item in value.values()
            for name in _referenced_wcc_names_in_payload(item)
        }
    if isinstance(value, (tuple, list)):
        return {
            name
            for item in value
            for name in _referenced_wcc_names_in_payload(item)
        }
    if is_dataclass(value):
        return {
            name
            for field in fields(value)
            for name in _referenced_wcc_names_in_payload(
                getattr(value, field.name)
            )
        }
    return set()


def _disqualifying_member_control_metadata(value: object):
    if (
        isinstance(value, WccOpaqueFrontendValue)
        and isinstance(value.expr, IfExpr)
    ):
        return value.metadata
    if isinstance(value, WccFieldAccessAtom):
        return _disqualifying_member_control_metadata(value.base)
    if isinstance(value, (WccRecordAtom, WccInject)):
        for _, field_value in value.fields:
            metadata = _disqualifying_member_control_metadata(field_value)
            if metadata is not None:
                return metadata
        return None
    if isinstance(value, WccPureOp):
        for arg in value.args:
            metadata = _disqualifying_member_control_metadata(arg)
            if metadata is not None:
                return metadata
        return None
    if isinstance(value, WccSelect):
        for child in (value.condition, value.then_value, value.else_value):
            metadata = _disqualifying_member_control_metadata(child)
            if metadata is not None:
                return metadata
        return None
    if isinstance(value, WccPerform):
        for arg in value.positional_args:
            metadata = _disqualifying_member_control_metadata(arg)
            if metadata is not None:
                return metadata
        for _, arg in value.keyword_args:
            metadata = _disqualifying_member_control_metadata(arg)
            if metadata is not None:
                return metadata
        return _disqualifying_member_control_in_payload(
            value.operation_payload
        )
    return None


def _disqualifying_member_control_in_payload(value: object):
    if isinstance(value, _WCC_VALUE_TYPES):
        return _disqualifying_member_control_metadata(value)
    if isinstance(value, Mapping):
        for item in value.values():
            metadata = _disqualifying_member_control_in_payload(item)
            if metadata is not None:
                return metadata
        return None
    if isinstance(value, (tuple, list)):
        for item in value:
            metadata = _disqualifying_member_control_in_payload(item)
            if metadata is not None:
                return metadata
        return None
    if is_dataclass(value):
        for field in fields(value):
            metadata = _disqualifying_member_control_in_payload(
                getattr(value, field.name)
            )
            if metadata is not None:
                return metadata
    return None


def _raise_member_ineligible(
    member: WccProviderSupervisionMember | WccProviderPeerGroupMember,
    *,
    metadata,
    reason: str,
) -> None:
    is_peer_group = isinstance(
        member,
        WccProviderPeerGroupMember,
    )
    group_label = (
        "provider peer group"
        if is_peer_group
        else "provider supervision"
    )
    diagnostics = [
        LispFrontendDiagnostic(
            code=(
                "provider_peer_group_member_ineligible"
                if is_peer_group
                else "provider_supervision_member_ineligible"
            ),
            message=(
                f"{group_label} member `{member.binding_name}` is "
                f"ineligible: {reason}"
            ),
            span=member.metadata.source_span,
            form_path=member.metadata.form_path,
            expansion_stack=member.metadata.expansion_stack,
            phase="lowering",
        )
    ]
    if (
        metadata.source_span != member.metadata.source_span
        or metadata.form_path != member.metadata.form_path
    ):
        diagnostics.append(
            LispFrontendDiagnostic(
                code=(
                    "provider_peer_group_member_disqualifying_form"
                    if is_peer_group
                    else "provider_supervision_member_disqualifying_form"
                ),
                message="specialized member contains this disqualifying form",
                span=metadata.source_span,
                form_path=metadata.form_path,
                expansion_stack=metadata.expansion_stack,
                phase="lowering",
            )
        )
    raise LispFrontendCompileError(tuple(diagnostics))


def _raise_supervision_diagnostic(
    *,
    code: str,
    message: str,
    metadata,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=metadata.source_span,
                form_path=metadata.form_path,
                expansion_stack=metadata.expansion_stack,
                phase="lowering",
            ),
        )
    )


def _raise_peer_group_diagnostic(
    *,
    code: str,
    message: str,
    metadata,
) -> None:
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=metadata.source_span,
                form_path=metadata.form_path,
                expansion_stack=metadata.expansion_stack,
                phase="lowering",
            ),
        )
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
