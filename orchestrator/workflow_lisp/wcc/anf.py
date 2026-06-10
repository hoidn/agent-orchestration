"""Administrative-normal-form normalization for the WCC M1 pure subset."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace

from .model import (
    WCC_M1_ROUTE_SCHEMA_VERSION,
    WccBody,
    WccFieldAccessAtom,
    WccHalt,
    WccIdentityFactory,
    WccInject,
    WccLet,
    WccLiteralAtom,
    WccNameAtom,
    WccNodeMetadata,
    WccRecordAtom,
    WccValue,
)


_WCC_ATOM_TYPES = (
    WccLiteralAtom,
    WccNameAtom,
    WccFieldAccessAtom,
    WccRecordAtom,
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
        route_schema_version=WCC_M1_ROUTE_SCHEMA_VERSION,
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
            route_schema_version=WCC_M1_ROUTE_SCHEMA_VERSION,
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
        prefix, bound_value = _normalize_value(body.bound_value)
        normalized_body = _normalize_body(body.body)
        let_node = replace(body, bound_value=bound_value, body=normalized_body)
        return _wrap_pending_lets(prefix, let_node)

    prefix, result = _normalize_value(body.result)
    if isinstance(result, _WCC_ATOM_TYPES):
        return _wrap_pending_lets(prefix, replace(body, result=result))
    generated = _generated_pending_let(result, purpose="halt")
    halt_atom = _generated_name_atom(result.metadata, purpose="halt")
    halt = replace(body, result=halt_atom)
    return _wrap_pending_lets((*prefix, generated), halt)


def _normalize_value(value: WccValue) -> tuple[tuple[_PendingLet, ...], WccValue]:
    if isinstance(value, (WccLiteralAtom, WccNameAtom, WccFieldAccessAtom)):
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
    raise TypeError(f"unsupported WCC M1 ANF node: {type(value).__name__}")
