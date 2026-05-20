"""Helper records for currently supported phase/context library forms."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

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
class ResumeValidationSpec:
    """Compiled validation contract for `resume-or-start` reusable state."""

    resume_from_expr: "ExprNode"
    return_type_ref: RecordTypeRef | UnionTypeRef
    valid_variants: tuple[str, ...]
    required_artifact_fields: Mapping[str, tuple[str, ...]]
    validator_adapter_name: str
    decision_type_name: str
    source_map_behavior: str
