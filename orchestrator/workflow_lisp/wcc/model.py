"""Workflow Core Calculus data model and identity helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from ..spans import SourceSpan
from ..type_env import TypeRef


WCC_M1_ROUTE_SCHEMA_VERSION = "wcc_m1"
WCC_M2_ROUTE_SCHEMA_VERSION = "wcc_m2"


def _stable_identity_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


@dataclass(frozen=True)
class WccNodeMetadata:
    """Stable semantic identity and provenance attached to every WCC node."""

    node_id: str
    type_ref: TypeRef
    scope_id: str
    source_span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY
    proof_context: tuple[object, ...] = ()
    allocation_requests: tuple[object, ...] = ()
    phase_scope: "WccPhaseScope | None" = None


@dataclass(frozen=True)
class WccPhaseScope:
    """Authored `with-phase` lowering context carried transparently through WCC."""

    ctx_expr: object
    phase_name: str
    source_span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()


@dataclass(frozen=True)
class WccIdentityFactory:
    """Deterministic semantic identity generator for one lexical WCC scope."""

    owner_name: str
    lexical_owner_chain: tuple[str, ...] = ()
    route_schema_version: str = WCC_M1_ROUTE_SCHEMA_VERSION

    @property
    def scope_id(self) -> str:
        digest = _stable_identity_digest(
            {
                "route_schema_version": self.route_schema_version,
                "owner_name": self.owner_name,
                "lexical_owner_chain": self.lexical_owner_chain,
            }
        )
        return f"wcc-scope:{self.route_schema_version}:{digest}"

    def child_scope(self, scope_role: str, *, authored_binding_name: str | None = None) -> "WccIdentityFactory":
        segment = scope_role if authored_binding_name is None else f"{scope_role}:{authored_binding_name}"
        return WccIdentityFactory(
            owner_name=self.owner_name,
            lexical_owner_chain=(*self.lexical_owner_chain, segment),
            route_schema_version=self.route_schema_version,
        )

    def _metadata(
        self,
        *,
        node_kind: str,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        digest = _stable_identity_digest(
            {
                "route_schema_version": self.route_schema_version,
                "owner_name": self.owner_name,
                "lexical_owner_chain": self.lexical_owner_chain,
                "node_kind": node_kind,
                "role": role,
            }
        )
        return WccNodeMetadata(
            node_id=f"wcc-node:{self.route_schema_version}:{digest}",
            type_ref=type_ref,
            scope_id=self.scope_id,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )

    def atom_metadata(
        self,
        *,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        return self._metadata(
            node_kind="atom",
            role=role,
            type_ref=type_ref,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )

    def value_metadata(
        self,
        *,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        return self._metadata(
            node_kind="value",
            role=role,
            type_ref=type_ref,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )

    def body_metadata(
        self,
        *,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        return self._metadata(
            node_kind="body",
            role=role,
            type_ref=type_ref,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )


@dataclass(frozen=True)
class WccLiteralAtom:
    metadata: WccNodeMetadata
    value: str | int | bool
    literal_kind: str


@dataclass(frozen=True)
class WccNameAtom:
    metadata: WccNodeMetadata
    name: str


@dataclass(frozen=True)
class WccFieldAccessAtom:
    metadata: WccNodeMetadata
    base: "WccAtom"
    fields: tuple[str, ...]


@dataclass(frozen=True)
class WccRecordAtom:
    metadata: WccNodeMetadata
    type_name: str
    fields: tuple[tuple[str, "WccValue"], ...]


WccAtom = WccLiteralAtom | WccNameAtom | WccFieldAccessAtom | WccRecordAtom


@dataclass(frozen=True)
class WccInject:
    metadata: WccNodeMetadata
    union_name: str
    variant_name: str
    fields: tuple[tuple[str, WccValue], ...]


WccValue = WccAtom | WccInject


@dataclass(frozen=True)
class WccPerform:
    metadata: WccNodeMetadata
    perform_kind: str
    target_name: str
    prompt_name: str | None
    positional_args: tuple[WccValue, ...]
    keyword_args: tuple[tuple[str, WccValue], ...]
    returns_type_name: str | None


@dataclass(frozen=True)
class WccCall:
    metadata: WccNodeMetadata
    callee_name: str
    specialized_callee_name: str
    args: tuple[WccValue, ...]


WccBindingValue = WccValue | WccPerform | WccCall


@dataclass(frozen=True)
class WccHalt:
    metadata: WccNodeMetadata
    result: WccValue


@dataclass(frozen=True)
class WccLet:
    metadata: WccNodeMetadata
    bound_name: str
    bound_type_ref: TypeRef
    bound_value: WccBindingValue
    body: "WccBody"


WccBody = WccLet | WccHalt
WccProgram = WccBody
