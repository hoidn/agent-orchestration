"""Helper records for the bounded phase/context standard-library slice."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .type_env import RecordTypeRef, UnionTypeRef

if TYPE_CHECKING:
    from .expressions import ExprNode


@dataclass(frozen=True)
class ProduceOneOfProducerSpec:
    kind: str
    provider_expr: "ExprNode | None" = None
    prompt_expr: "ExprNode | None" = None
    inputs: tuple["ExprNode", ...] = ()


@dataclass(frozen=True)
class ProduceOneOfCandidateFieldSpec:
    field_name: str
    schema_type_name: str | None = None
    target_expr: "ExprNode | None" = None
    source_kind: str | None = None
    source_type_name: str | None = None


@dataclass(frozen=True)
class ProduceOneOfCandidateSpec:
    variant_name: str
    fields: tuple[ProduceOneOfCandidateFieldSpec, ...]


@dataclass(frozen=True)
class ResumeValidationSpec:
    resume_from_expr: "ExprNode"
    return_type_ref: RecordTypeRef | UnionTypeRef
    valid_variants: tuple[str, ...]
    required_artifact_fields: Mapping[str, tuple[str, ...]]
    validator_adapter_name: str
    decision_type_name: str
    source_map_behavior: str
