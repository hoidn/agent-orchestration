"""Structural private-exec-context classification and bootstrap planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from .type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, TypeRef

if TYPE_CHECKING:
    from .contracts import FlattenedContractField


CONTEXT_BINDING_SCHEMA_VERSION = 1

RUN_CONTEXT_NAME = "RunCtx"
PHASE_CONTEXT_NAME = "PhaseCtx"
ITEM_CONTEXT_NAME = "ItemCtx"
DRAIN_CONTEXT_NAME = "DrainCtx"
SELECTION_CONTEXT_NAME = "SelectionCtx"
RECOVERY_CONTEXT_NAME = "RecoveryCtx"
RUN_CTX_ANCHORED_CONTEXT_FAMILY = "RunCtxAnchored"


class ContextAnchorKind(str, Enum):
    """Implemented and reserved anchor families for structural contexts."""

    RUN_CTX = "run_ctx"
    RESOURCE_HANDLE = "resource_handle"
    RUNTIME_ALLOCATION = "runtime_allocation"


@dataclass(frozen=True)
class ContextAnchor:
    """One runtime-owned anchor discovered within a structured context type."""

    kind: ContextAnchorKind
    field_path: tuple[str, ...]


@dataclass(frozen=True)
class StructuralContextClassification:
    """Structural context facts derived from a type reference alone."""

    anchors: tuple[ContextAnchor, ...]
    derived_capabilities: tuple[str, ...]
    legacy_family: str | None


@dataclass(frozen=True)
class ContextBootstrapPlan:
    """Per-input bootstrap roles for one hidden structural context binding."""

    input_roles: Mapping[str, str]

_RUN_ANCHOR_ROLE_BY_SUFFIX = {
    ("run-id",): "run_anchor:run-id",
    ("state-root",): "run_anchor:state-root",
    ("artifact-root",): "run_anchor:artifact-root",
}


def legacy_private_exec_context_kind(type_ref: TypeRef) -> str | None:
    """Classify one record boundary by the legacy private context families."""

    if _is_run_context_shape(type_ref):
        return RUN_CONTEXT_NAME
    if _is_phase_context_shape(type_ref):
        return PHASE_CONTEXT_NAME
    if _is_item_context_shape(type_ref):
        return ITEM_CONTEXT_NAME
    if _is_drain_context_shape(type_ref):
        return DRAIN_CONTEXT_NAME
    if _is_selection_context_shape(type_ref):
        return SELECTION_CONTEXT_NAME
    if _is_recovery_context_shape(type_ref):
        return RECOVERY_CONTEXT_NAME
    return None


def classify_structural_private_exec_context(
    type_ref: TypeRef,
) -> StructuralContextClassification | None:
    """Return structural context facts for records anchored on `RunCtx`."""

    anchors = _collect_run_ctx_anchors(type_ref, field_path=(), visited=frozenset())
    if not anchors:
        return None
    return StructuralContextClassification(
        anchors=anchors,
        derived_capabilities=("run",),
        legacy_family=legacy_private_exec_context_kind(type_ref),
    )


def structural_bootstrap_plan(
    flattened_fields: Sequence["FlattenedContractField"],
    classification: StructuralContextClassification | None,
) -> ContextBootstrapPlan | None:
    """Assign bootstrap roles for generated hidden inputs or fail closed."""

    if classification is None:
        return None
    input_roles: dict[str, str] = {}
    for flattened_field in flattened_fields:
        role = _bootstrap_role_for_field(
            source_path=flattened_field.source_path,
            contract_definition=flattened_field.contract_definition,
            anchors=classification.anchors,
        )
        if role is None:
            return None
        input_roles[flattened_field.generated_name] = role
    return ContextBootstrapPlan(input_roles=input_roles)


def _collect_run_ctx_anchors(
    type_ref: TypeRef,
    *,
    field_path: tuple[str, ...],
    visited: frozenset[object],
) -> tuple[ContextAnchor, ...]:
    if not isinstance(type_ref, RecordTypeRef):
        return ()

    visited_key = type_ref.definition
    if visited_key in visited:
        return ()
    next_visited = visited | {visited_key}

    anchors: list[ContextAnchor] = []
    if _is_run_context_shape(type_ref):
        anchors.append(ContextAnchor(kind=ContextAnchorKind.RUN_CTX, field_path=field_path))

    for field_name, field_type in type_ref.field_types.items():
        if isinstance(field_type, RecordTypeRef):
            anchors.extend(
                _collect_run_ctx_anchors(
                    field_type,
                    field_path=field_path + (field_name,),
                    visited=next_visited,
                )
            )
    return tuple(anchors)


def _bootstrap_role_for_field(
    *,
    source_path: tuple[str, ...],
    contract_definition: Mapping[str, object],
    anchors: Sequence[ContextAnchor],
) -> str | None:
    relative_path = source_path[1:] if source_path else ()
    for anchor in anchors:
        role = _role_for_anchor_path(relative_path, anchor)
        if role is not None:
            return role
    if "default" in contract_definition:
        return "compile_time_default"
    return None


def _role_for_anchor_path(relative_path: tuple[str, ...], anchor: ContextAnchor) -> str | None:
    if anchor.kind == ContextAnchorKind.RESOURCE_HANDLE:
        raise NotImplementedError("resource_handle anchors are deferred in this tranche")
    if anchor.kind == ContextAnchorKind.RUNTIME_ALLOCATION:
        raise NotImplementedError("runtime_allocation anchors are deferred in this tranche")
    if anchor.kind != ContextAnchorKind.RUN_CTX:
        return None
    for suffix, role in _RUN_ANCHOR_ROLE_BY_SUFFIX.items():
        if relative_path == anchor.field_path + suffix:
            return role
    return None


def _record_definition_name(type_ref: RecordTypeRef) -> str:
    return type_ref.definition.name


def _record_field_is_primitive(record_type: RecordTypeRef, field_name: str, expected_name: str) -> bool:
    field_type = record_type.field_types.get(field_name)
    return isinstance(field_type, PrimitiveTypeRef) and field_type.name == expected_name


def _record_field_is_path_under(record_type: RecordTypeRef, field_name: str, expected_under: str) -> bool:
    field_type = record_type.field_types.get(field_name)
    return isinstance(field_type, PathTypeRef) and field_type.definition.under == expected_under


def _is_run_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    return (
        _record_field_is_primitive(type_ref, "run-id", "RunId")
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _is_phase_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _is_run_context_shape(run_field)
        and _record_field_is_primitive(type_ref, "phase-name", "Symbol")
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _is_item_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _is_run_context_shape(run_field)
        and _record_field_is_primitive(type_ref, "item-id", "String")
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
        and _record_field_is_path_under(type_ref, "ledger", "state")
    )


def _is_drain_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _is_run_context_shape(run_field)
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "manifest", "state")
        and _record_field_is_path_under(type_ref, "ledger", "state")
    )


def _is_selection_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _record_definition_name(type_ref) == SELECTION_CONTEXT_NAME
        and _is_run_context_shape(run_field)
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )


def _is_recovery_context_shape(type_ref: TypeRef) -> bool:
    if not isinstance(type_ref, RecordTypeRef):
        return False
    run_field = type_ref.field_types.get("run")
    return (
        _record_definition_name(type_ref) == RECOVERY_CONTEXT_NAME
        and _is_run_context_shape(run_field)
        and _record_field_is_path_under(type_ref, "state-root", "state")
        and _record_field_is_path_under(type_ref, "artifact-root", "artifacts")
    )
