"""Administrative-normal-form normalization for Workflow Core Calculus."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

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
    WccJump,
    WccLet,
    WccLiteralAtom,
    WccLoopContinue,
    WccLoopDone,
    WccNameAtom,
    WccNodeMetadata,
    WccOpaqueFrontendValue,
    WccPhaseTargetAtom,
    WccPerform,
    WccPureOp,
    WccRecJoin,
    WccRecordAtom,
    WccValue,
)


_WCC_ATOM_TYPES = (
    WccLiteralAtom,
    WccNameAtom,
    WccFieldAccessAtom,
    WccPhaseTargetAtom,
    WccRecordAtom,
    WccOpaqueFrontendValue,
)


@dataclass(frozen=True)
class _PendingLet:
    binding_name: str
    bound_type_ref: object
    bound_value: WccValue
    source_metadata: WccNodeMetadata


def _stable_generated_digest(*, source_node_id: str, purpose: str) -> str:
    payload = json.dumps(
        {"source_node_id": source_node_id, "purpose": purpose},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:10]


def _generated_binding_name(metadata: WccNodeMetadata, *, purpose: str) -> str:
    return f"__wcc_anf_{_stable_generated_digest(source_node_id=metadata.node_id, purpose=purpose)}"


def _generated_name_atom(metadata: WccNodeMetadata, *, purpose: str) -> WccNameAtom:
    binding_name = _generated_binding_name(metadata, purpose=purpose)
    factory = WccIdentityFactory(
        owner_name=metadata.node_id,
        lexical_owner_chain=(metadata.scope_id, "anf-ref", purpose),
        route_schema_version=_route_schema_version(metadata),
    )
    return WccNameAtom(
        metadata=factory.atom_metadata(
            role=f"generated-ref:{binding_name}",
            type_ref=metadata.type_ref,
            source_span=metadata.source_span,
            form_path=metadata.form_path,
            expansion_stack=metadata.expansion_stack,
        ),
        name=binding_name,
    )


def _generated_pending_let(value: WccValue, *, purpose: str) -> _PendingLet:
    metadata = value.metadata
    return _PendingLet(
        binding_name=_generated_binding_name(metadata, purpose=purpose),
        bound_type_ref=metadata.type_ref,
        bound_value=value,
        source_metadata=metadata,
    )


def _wrap_pending_lets(prefix: tuple[_PendingLet, ...], tail: WccBody) -> WccBody:
    current = tail
    for pending in reversed(prefix):
        factory = WccIdentityFactory(
            owner_name=pending.source_metadata.node_id,
            lexical_owner_chain=(pending.source_metadata.scope_id, "anf-let", pending.binding_name),
            route_schema_version=_route_schema_version(pending.source_metadata),
        )
        current = WccLet(
            metadata=factory.body_metadata(
                role=f"generated-let:{pending.binding_name}",
                type_ref=current.metadata.type_ref,
                source_span=pending.source_metadata.source_span,
                form_path=pending.source_metadata.form_path,
                expansion_stack=pending.source_metadata.expansion_stack,
            ),
            bound_name=pending.binding_name,
            bound_type_ref=pending.bound_type_ref,
            bound_value=pending.bound_value,
            body=current,
        )
    return current


def normalize_wcc_body_to_anf(body: WccBody) -> WccBody:
    """Normalize one WCC body so record/inject fields and terminal halts are atomic."""

    return _normalize_body(body)


def _normalize_body(body: WccBody) -> WccBody:
    if isinstance(body, WccLet):
        prefix, bound_value = _normalize_binding_value(body.bound_value)
        normalized_body = _normalize_body(body.body)
        let_node = replace(body, bound_value=bound_value, body=normalized_body)
        return _wrap_pending_lets(prefix, let_node)
    if isinstance(body, WccCase):
        subject_prefix, subject = _normalize_value(body.subject)
        normalized_arms = tuple(
            WccCaseArm(
                variant_name=arm.variant_name,
                binding_name=arm.binding_name,
                binding_type_ref=arm.binding_type_ref,
                body=_normalize_body(arm.body),
            )
            for arm in body.arms
        )
        if not isinstance(subject, _WCC_ATOM_TYPES):
            generated = _generated_pending_let(subject, purpose="case:subject")
            subject = _generated_name_atom(subject.metadata, purpose="case:subject")
            subject_prefix = (*subject_prefix, generated)
        return _wrap_pending_lets(subject_prefix, replace(body, subject=subject, arms=normalized_arms))
    if isinstance(body, WccJoin):
        return replace(
            body,
            body=_normalize_body(body.body),
            continuation=_normalize_body(body.continuation),
        )
    if isinstance(body, WccIf):
        condition_prefix, condition = _normalize_value(body.condition)
        if not _is_atomic_effect_arg(condition):
            generated = _generated_pending_let(condition, purpose="if:condition")
            condition = _generated_name_atom(condition.metadata, purpose="if:condition")
            condition_prefix = (*condition_prefix, generated)
        return _wrap_pending_lets(
            condition_prefix,
            replace(
                body,
                condition=condition,
                then_body=_normalize_body(body.then_body),
                else_body=_normalize_body(body.else_body),
            ),
        )
    if isinstance(body, WccJump):
        pending: list[_PendingLet] = []
        args: list[WccValue] = []
        for index, arg in enumerate(body.args):
            arg_prefix, normalized_arg = _normalize_value(arg)
            pending.extend(arg_prefix)
            if not _is_atomic_effect_arg(normalized_arg):
                generated = _generated_pending_let(normalized_arg, purpose=f"jump:{index}")
                pending.append(generated)
                normalized_arg = _generated_name_atom(normalized_arg.metadata, purpose=f"jump:{index}")
            args.append(normalized_arg)
        return _wrap_pending_lets(tuple(pending), replace(body, args=tuple(args)))
    if isinstance(body, WccRecJoin):
        pending: list[_PendingLet] = []
        budget_prefix, budget = _normalize_value(body.budget)
        pending.extend(budget_prefix)
        if not _is_atomic_effect_arg(budget):
            generated = _generated_pending_let(budget, purpose="loop:budget")
            pending.append(generated)
            budget = _generated_name_atom(budget.metadata, purpose="loop:budget")
        initial_state = body.initial_state
        if initial_state is not None:
            state_prefix, normalized_state = _normalize_value(initial_state)
            pending.extend(state_prefix)
            if not _is_atomic_effect_arg(normalized_state):
                generated = _generated_pending_let(normalized_state, purpose="loop:state")
                pending.append(generated)
                normalized_state = _generated_name_atom(normalized_state.metadata, purpose="loop:state")
            initial_state = normalized_state
        rec_join = replace(
            body,
            budget=budget,
            initial_state=initial_state,
            body=_normalize_body(body.body),
            exhaustion=_normalize_body(body.exhaustion) if body.exhaustion is not None else None,
        )
        return _wrap_pending_lets(tuple(pending), rec_join)
    if isinstance(body, WccLoopContinue):
        pending: list[_PendingLet] = []
        args: list[WccValue] = []
        for index, arg in enumerate(body.state_args):
            arg_prefix, normalized_arg = _normalize_value(arg)
            pending.extend(arg_prefix)
            if not _is_atomic_effect_arg(normalized_arg):
                generated = _generated_pending_let(normalized_arg, purpose=f"loop:continue:{index}")
                pending.append(generated)
                normalized_arg = _generated_name_atom(normalized_arg.metadata, purpose=f"loop:continue:{index}")
            args.append(normalized_arg)
        return _wrap_pending_lets(tuple(pending), replace(body, state_args=tuple(args)))
    if isinstance(body, WccLoopDone):
        prefix, result = _normalize_value(body.result)
        if _is_atomic_effect_arg(result):
            return _wrap_pending_lets(prefix, replace(body, result=result))
        generated = _generated_pending_let(result, purpose="loop:done")
        done_atom = _generated_name_atom(result.metadata, purpose="loop:done")
        done = replace(body, result=done_atom)
        return _wrap_pending_lets((*prefix, generated), done)
    prefix, result = _normalize_value(body.result)
    if isinstance(result, _WCC_ATOM_TYPES):
        return _wrap_pending_lets(prefix, replace(body, result=result))
    generated = _generated_pending_let(result, purpose="halt")
    halt_atom = _generated_name_atom(result.metadata, purpose="halt")
    halt = replace(body, result=halt_atom)
    return _wrap_pending_lets((*prefix, generated), halt)


def _normalize_binding_value(value) -> tuple[tuple[_PendingLet, ...], object]:
    if isinstance(value, WccPerform):
        return _normalize_perform(value)
    if isinstance(value, WccCall):
        return _normalize_call(value)
    return _normalize_value(value)


def _normalize_value(value: WccValue) -> tuple[tuple[_PendingLet, ...], WccValue]:
    if isinstance(value, (WccLiteralAtom, WccNameAtom, WccFieldAccessAtom, WccPhaseTargetAtom, WccOpaqueFrontendValue)):
        return (), value
    if isinstance(value, WccRecordAtom):
        pending: list[_PendingLet] = []
        normalized_fields: list[tuple[str, WccValue]] = []
        for field_name, field_value in value.fields:
            field_prefix, normalized_field = _normalize_value(field_value)
            pending.extend(field_prefix)
            if not isinstance(normalized_field, _WCC_ATOM_TYPES):
                generated = _generated_pending_let(normalized_field, purpose=f"record:{field_name}")
                pending.append(generated)
                normalized_field = _generated_name_atom(normalized_field.metadata, purpose=f"record:{field_name}")
            normalized_fields.append((field_name, normalized_field))
        return tuple(pending), replace(value, fields=tuple(normalized_fields))
    if isinstance(value, WccInject):
        pending: list[_PendingLet] = []
        normalized_fields: list[tuple[str, WccValue]] = []
        for field_name, field_value in value.fields:
            field_prefix, normalized_field = _normalize_value(field_value)
            pending.extend(field_prefix)
            if not isinstance(normalized_field, _WCC_ATOM_TYPES):
                generated = _generated_pending_let(normalized_field, purpose=f"inject:{field_name}")
                pending.append(generated)
                normalized_field = _generated_name_atom(normalized_field.metadata, purpose=f"inject:{field_name}")
            normalized_fields.append((field_name, normalized_field))
        return tuple(pending), replace(value, fields=tuple(normalized_fields))
    if isinstance(value, WccPureOp):
        pending: list[_PendingLet] = []
        normalized_args: list[WccValue] = []
        for index, arg in enumerate(value.args):
            arg_prefix, normalized_arg = _normalize_value(arg)
            pending.extend(arg_prefix)
            if not isinstance(normalized_arg, _WCC_ATOM_TYPES):
                generated = _generated_pending_let(normalized_arg, purpose=f"pure-op:{value.operator}:{index}")
                pending.append(generated)
                normalized_arg = _generated_name_atom(
                    normalized_arg.metadata,
                    purpose=f"pure-op:{value.operator}:{index}",
                )
            normalized_args.append(normalized_arg)
        return tuple(pending), replace(value, args=tuple(normalized_args))
    raise TypeError(f"unsupported WCC M1 ANF node: {type(value).__name__}")


def _normalize_perform(value: WccPerform) -> tuple[tuple[_PendingLet, ...], WccPerform]:
    pending: list[_PendingLet] = []
    positional_args: list[WccValue] = []
    keyword_args: list[tuple[str, WccValue]] = []
    for index, arg in enumerate(value.positional_args):
        arg_prefix, normalized_arg = _normalize_value(arg)
        pending.extend(arg_prefix)
        if not _is_atomic_effect_arg(normalized_arg):
            generated = _generated_pending_let(normalized_arg, purpose=f"{value.perform_kind}:arg:{index}")
            pending.append(generated)
            normalized_arg = _generated_name_atom(normalized_arg.metadata, purpose=f"{value.perform_kind}:arg:{index}")
        positional_args.append(normalized_arg)
    for field_name, arg in value.keyword_args:
        arg_prefix, normalized_arg = _normalize_value(arg)
        pending.extend(arg_prefix)
        if not _is_atomic_effect_arg(normalized_arg):
            generated = _generated_pending_let(normalized_arg, purpose=f"{value.perform_kind}:{field_name}")
            pending.append(generated)
            normalized_arg = _generated_name_atom(normalized_arg.metadata, purpose=f"{value.perform_kind}:{field_name}")
        keyword_args.append((field_name, normalized_arg))
    return tuple(pending), replace(value, positional_args=tuple(positional_args), keyword_args=tuple(keyword_args))


def _normalize_call(value: WccCall) -> tuple[tuple[_PendingLet, ...], WccCall]:
    pending: list[_PendingLet] = []
    args: list[WccValue] = []
    for index, arg in enumerate(value.args):
        arg_prefix, normalized_arg = _normalize_value(arg)
        pending.extend(arg_prefix)
        if not _is_atomic_effect_arg(normalized_arg):
            generated = _generated_pending_let(normalized_arg, purpose=f"call:{index}")
            pending.append(generated)
            normalized_arg = _generated_name_atom(normalized_arg.metadata, purpose=f"call:{index}")
        args.append(normalized_arg)
    return tuple(pending), replace(value, args=tuple(args))


def _is_atomic_effect_arg(value: WccValue) -> bool:
    return isinstance(value, (WccLiteralAtom, WccNameAtom, WccFieldAccessAtom))


def _route_schema_version(metadata: WccNodeMetadata) -> str:
    parts = metadata.node_id.split(":")
    if len(parts) >= 3:
        return parts[1]
    return WccIdentityFactory.route_schema_version
