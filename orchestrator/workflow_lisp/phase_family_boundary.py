"""Phase-family public/private boundary classification for selected migrations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .context_classification import (
    classify_structural_private_exec_context,
)
from .contracts import FlattenedContractField
from .effects import CallsWorkflowEffect, EffectSummary
from .family_profiles import WorkflowFamilyProfileCatalog
from .type_env import PathTypeRef, RecordTypeRef, TypeRef


DESIGN_DELTA_BOUNDARY_AUTHORITY_SCHEMA_VERSION = (
    "workflow_lisp_design_delta_boundary_authority.v1"
)
DESIGN_DELTA_BOUNDARY_AUTHORITY_CLASSES = frozenset(
    {
        "public_authored",
        "compatibility_bridge",
        "runtime_derived",
        "generated_internal",
        "materialized_view",
        "public_artifact",
    }
)
DESIGN_DELTA_BOUNDARY_SURFACE_KINDS = frozenset(
    {
        "public_input",
        "flattened_output",
        "generated_internal_input",
        "compatibility_bridge_input",
        "managed_write_root",
        "runtime_context_input",
    }
)

COMPATIBILITY_BRIDGE_TYPE_NAMES = frozenset(
    {
        "SelectionBundlePath",
        "ProgressLedger",
        "RunStatePath",
        "StateFile",
        "StateFileExisting",
    }
)

COMPATIBILITY_BRIDGE_PARAM_NAMES = frozenset(
    {
        "run_state_path",
        "selection_bundle_path",
        "manifest_path",
        "architecture_bundle_path",
        "progress_ledger",
        "progress_ledger_path",
    }
)


@dataclass(frozen=True)
class PhaseFamilyBoundaryClassification:
    runtime_owned_context_inputs: tuple[str, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    public_authored_inputs: tuple[str, ...] = ()
    unclassified_low_level_inputs: tuple[str, ...] = ()


def is_structural_pure_projection_effect_summary(effect_summary: EffectSummary) -> bool:
    """Return whether a workflow boundary is effect-free apart from pure calls."""

    allowed_effect_type = CallsWorkflowEffect
    all_effects = set(effect_summary.direct_effects)
    all_effects.update(effect_summary.transitive_effects)
    return all(isinstance(effect, allowed_effect_type) for effect in all_effects)


def is_selected_phase_family_workflow(
    workflow_name: str,
    *,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> bool:
    if family_profile_catalog is None:
        return False
    return family_profile_catalog.workflow_in_profile(workflow_name)


def is_design_delta_parent_drain_target_workflow(
    workflow_name: str,
    *,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> bool:
    if family_profile_catalog is None:
        return False
    profile = family_profile_catalog.profile_for_workflow(workflow_name)
    if profile is None:
        return False
    return workflow_name in profile.target_workflows


def short_type_name(type_ref: TypeRef) -> str:
    name = getattr(type_ref, "name", "")
    return str(name).rsplit("::", 1)[-1].rsplit("/", 1)[-1]


def is_phase_context_type(type_ref: TypeRef) -> bool:
    return isinstance(type_ref, RecordTypeRef) and (
        classify_structural_private_exec_context(type_ref) is not None
    )


def is_compatibility_bridge_param(param_name: str, type_ref: TypeRef) -> bool:
    if param_name not in COMPATIBILITY_BRIDGE_PARAM_NAMES:
        return False
    if short_type_name(type_ref) in COMPATIBILITY_BRIDGE_TYPE_NAMES:
        return True
    return isinstance(type_ref, PathTypeRef) and type_ref.definition.under == "state"


def classify_phase_family_boundary(
    *,
    workflow_name: str,
    params: Iterable[tuple[str, TypeRef]],
    flattened_inputs: Iterable[FlattenedContractField],
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
    hidden_context_requirements: Mapping[str, Any] | None = None,
) -> PhaseFamilyBoundaryClassification:
    selected_phase_family = is_selected_phase_family_workflow(
        workflow_name,
        family_profile_catalog=family_profile_catalog,
    )
    params_by_name = dict(params)
    hidden_context_names = set(hidden_context_requirements or ())
    runtime_names: list[str] = []
    bridge_names: list[str] = []
    public_names: list[str] = []
    unclassified_low_level_names: list[str] = []
    for field in flattened_inputs:
        root_param = field.source_path[0] if field.source_path else field.generated_name
        type_ref = params_by_name.get(root_param)
        if type_ref is None:
            public_names.append(field.generated_name)
            continue
        if is_phase_context_type(type_ref):
            if selected_phase_family or root_param in hidden_context_names:
                runtime_names.append(field.generated_name)
            else:
                public_names.append(field.generated_name)
        elif is_compatibility_bridge_param(root_param, type_ref):
            bridge_names.append(field.generated_name)
        else:
            public_names.append(field.generated_name)
            if field.contract_definition.get("type") == "relpath" and field.contract_definition.get("under") == "state":
                unclassified_low_level_names.append(field.generated_name)
    return PhaseFamilyBoundaryClassification(
        runtime_owned_context_inputs=tuple(sorted(set(runtime_names))),
        compatibility_bridge_inputs=tuple(sorted(set(bridge_names))),
        public_authored_inputs=tuple(sorted(set(public_names))),
        unclassified_low_level_inputs=tuple(sorted(set(unclassified_low_level_names))),
    )


def phase_family_entry_phase_identity(
    workflow_name: str,
    *,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> str | None:
    if family_profile_catalog is None:
        return None
    return family_profile_catalog.entry_phase_identity(workflow_name)


def load_design_delta_boundary_authority_registry(
    path: Path,
    *,
    target_workflows: frozenset[str] | None = None,
) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("boundary authority registry must be a JSON object")
    if payload.get("schema_version") != DESIGN_DELTA_BOUNDARY_AUTHORITY_SCHEMA_VERSION:
        raise ValueError(
            f"boundary authority registry schema_version must be {DESIGN_DELTA_BOUNDARY_AUTHORITY_SCHEMA_VERSION}"
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("boundary authority registry must declare non-empty `rows`")
    seen: set[tuple[str, str]] = set()
    normalized_rows: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"boundary authority row {index} must be an object")
        workflow_name = _require_registry_string(row, "workflow_name", index=index)
        if target_workflows is not None and workflow_name not in target_workflows:
            raise ValueError(
                f"boundary authority row {index} uses unknown target workflow `{workflow_name}`"
            )
        field_name = _require_registry_string(row, "field_name", index=index)
        surface_kind = _require_registry_string(row, "surface_kind", index=index)
        if surface_kind not in DESIGN_DELTA_BOUNDARY_SURFACE_KINDS:
            raise ValueError(
                f"boundary authority row {index} uses unknown surface_kind `{surface_kind}`"
            )
        authority_class = _require_registry_string(row, "authority_class", index=index)
        if authority_class not in DESIGN_DELTA_BOUNDARY_AUTHORITY_CLASSES:
            raise ValueError(
                f"boundary authority row {index} uses unknown authority_class `{authority_class}`"
            )
        path_like = row.get("path_like")
        parity_constrained = row.get("parity_constrained")
        if not isinstance(path_like, bool) or not isinstance(parity_constrained, bool):
            raise ValueError(
                f"boundary authority row {index} must declare boolean `path_like` and `parity_constrained`"
            )
        _require_registry_string(row, "owner", index=index)
        _require_registry_string(row, "justification", index=index)
        _require_registry_string(row, "replacement_tranche", index=index)
        key = (workflow_name, field_name)
        if key in seen:
            raise ValueError(
                f"boundary authority registry duplicates `{workflow_name}` / `{field_name}`"
            )
        seen.add(key)
        normalized_rows.append(dict(row))
    return {
        "schema_version": DESIGN_DELTA_BOUNDARY_AUTHORITY_SCHEMA_VERSION,
        "rows": normalized_rows,
    }


def _require_registry_string(
    row: dict[str, object],
    field_name: str,
    *,
    index: int,
) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"boundary authority row {index} must declare non-empty `{field_name}`"
        )
    return value
