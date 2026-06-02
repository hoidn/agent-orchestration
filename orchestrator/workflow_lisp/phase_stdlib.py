"""Helper records for currently supported phase/context library forms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .type_env import RecordTypeRef, UnionTypeRef

if TYPE_CHECKING:
    from .expressions import ExprNode


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
