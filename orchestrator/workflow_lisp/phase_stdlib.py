"""Helper records for currently supported phase/context library forms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourceSpan
from .type_env import RecordTypeRef, UnionTypeRef

if TYPE_CHECKING:
    from .syntax import ExpansionStack
    from .expressions import ExprNode


ReviewLoopLegacyBridgePolicy = Literal["allow", "deny"]

REVIEW_LOOP_LEGACY_BRIDGE_POLICY_ALLOW: ReviewLoopLegacyBridgePolicy = "allow"
REVIEW_LOOP_LEGACY_BRIDGE_POLICY_DENY: ReviewLoopLegacyBridgePolicy = "deny"
DEFAULT_REVIEW_LOOP_LEGACY_BRIDGE_POLICY: ReviewLoopLegacyBridgePolicy = (
    REVIEW_LOOP_LEGACY_BRIDGE_POLICY_ALLOW
)
REVIEW_LOOP_STDLIB_REQUEST_KIND = "phase-review-loop"


@dataclass(frozen=True)
class ProduceOneOfProducerSpec:
    """Producer clause for `produce-one-of` variant selection."""

    kind: str
    provider_expr: "ExprNode | None" = None
    prompt_expr: "ExprNode | None" = None
    inputs: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class ProduceOneOfCandidateFieldSpec:
    """One candidate artifact or structured sidecar field."""

    field_name: str
    schema_type_name: str | None = None
    target_expr: "ExprNode | None" = None
    source_kind: str | None = None
    source_type_name: str | None = None


@dataclass(frozen=True)
class ProduceOneOfCandidateSpec:
    """One variant candidate and the fields it may produce."""

    variant_name: str
    fields: tuple[ProduceOneOfCandidateFieldSpec, ...]


@dataclass(frozen=True)
class ReusableArtifactRequirement:
    """One compiler-derived reusable artifact existence requirement."""

    field_path: tuple[str, ...]
    under: str


@dataclass(frozen=True)
class ReusableStateValidationSpec:
    """Compiled validation contract for `resume-or-start` reusable state."""

    resume_from_expr: "ExprNode"
    return_type_ref: RecordTypeRef | UnionTypeRef
    summary_schema: str
    summary_version: str
    sidecar_suffix: str
    structured_contract_kind: str
    expected_contract_fingerprint: str
    reusable_variants: tuple[str, ...]
    public_input_hash_basis: tuple[str, ...]
    producer_fingerprint_basis: Mapping[str, Any]
    artifact_requirements: Mapping[str, tuple[ReusableArtifactRequirement, ...]]
    canonical_bundle_digest_field: str
    validator_binding_name: str
    writer_binding_name: str
    loader_binding_name: str
    source_map_behavior: str


def is_review_loop_request_kind(request_kind: str) -> bool:
    """Return whether one stdlib specialization request targets the review loop bridge."""

    return request_kind == REVIEW_LOOP_STDLIB_REQUEST_KIND


def review_loop_legacy_bridge_disallowed(
    *,
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy,
    request_kind: str,
) -> bool:
    """Return whether the current compile policy forbids the legacy review-loop bridge."""

    return (
        review_loop_legacy_bridge_policy == REVIEW_LOOP_LEGACY_BRIDGE_POLICY_DENY
        and is_review_loop_request_kind(request_kind)
    )


def raise_review_loop_legacy_bridge_disallowed(
    *,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack" = (),
    message: str | None = None,
) -> None:
    """Raise the stable promoted-route diagnostic for the legacy review-loop bridge."""

    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="stdlib_special_form_disallowed",
                message=message
                or (
                    "promoted mode cannot use the legacy `review-revise-loop` compatibility bridge; "
                    "compile with explicit legacy allow mode only for compatibility"
                ),
                span=span,
                form_path=form_path,
                expansion_stack=expansion_stack,
            ),
        )
    )


def ensure_review_loop_legacy_bridge_allowed(
    *,
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy,
    request_kind: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
    expansion_stack: "ExpansionStack" = (),
) -> None:
    """Fail closed when promoted-mode compilation reaches the legacy review-loop bridge."""

    if review_loop_legacy_bridge_disallowed(
        review_loop_legacy_bridge_policy=review_loop_legacy_bridge_policy,
        request_kind=request_kind,
    ):
        raise_review_loop_legacy_bridge_disallowed(
            span=span,
            form_path=form_path,
            expansion_stack=expansion_stack,
        )
