"""Phase-family public/private boundary classification for selected migrations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from typing import Any

from .context_classification import (
    _bootstrap_role_for_field,
    classify_structural_private_exec_context,
)
from .contracts import FlattenedContractField, derive_workflow_boundary_fields
from .effects import CallsWorkflowEffect, EffectSummary
from .family_profiles import WorkflowFamilyProfileCatalog
from .phase import private_exec_context_capabilities
from .type_env import PathTypeRef, RecordTypeRef, TypeRef
from orchestrator.workflow.surface_ast import PrivateExecContextBinding


PHASE_CONTEXT_TYPE_NAME = "PhaseCtx"
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
        "selection_bundle_path",
        "manifest_path",
        "architecture_bundle_path",
        "progress_ledger_path",
        "run_state_path",
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


def apply_phase_family_boundary_classification(
    *,
    workflow_name: str,
    params: Iterable[tuple[str, TypeRef]],
    hidden_context_requirements: Mapping[str, Any] | None = None,
    boundary_projection: Any,
    context: Any,
) -> PhaseFamilyBoundaryClassification:
    classification = classify_phase_family_boundary(
        workflow_name=workflow_name,
        params=params,
        flattened_inputs=boundary_projection.flattened_inputs,
        family_profile_catalog=context.workflow_catalog.family_profile_catalog,
        hidden_context_requirements=hidden_context_requirements,
    )
    for name in classification.runtime_owned_context_inputs:
        context.internal_generated_input_reasons[name] = "runtime_owned_context"
        context.authored_generated_inputs.discard(name)
    for name in classification.compatibility_bridge_inputs:
        context.internal_generated_input_reasons[name] = "compatibility_bridge"
        context.authored_generated_inputs.discard(name)
    return classification


def record_direct_entry_phase_context_binding(
    *,
    context: Any,
    typed_workflow: Any,
    generated_input_names: tuple[str, ...],
) -> None:
    if not generated_input_names:
        return
    generated_input_name_set = set(generated_input_names)
    params_by_name = dict(typed_workflow.signature.params)
    for (
        source_param_name,
        requirement,
    ) in typed_workflow.signature.hidden_context_requirements.items():
        type_ref = params_by_name.get(source_param_name)
        if not isinstance(type_ref, RecordTypeRef):
            continue
        structural_classification = classify_structural_private_exec_context(type_ref)
        flattened_fields = tuple(
            field
            for field in derive_workflow_boundary_fields(
                type_ref,
                generated_name=source_param_name,
                source_path=(source_param_name,),
                span=typed_workflow.definition.span,
                form_path=typed_workflow.definition.form_path,
            )
            if field.generated_name in generated_input_name_set
        )
        if not flattened_fields:
            continue
        origin = context.generated_input_spans.get(flattened_fields[0].generated_name)
        provenance: dict[str, Any] = {
            "workflow_name": typed_workflow.definition.name,
        }
        if origin is not None:
            provenance.update(
                {
                    "path": str(origin.span.start.path),
                    "line": origin.span.start.line,
                    "form_path": list(origin.form_path),
                }
            )
        input_roles: dict[str, str] = {}
        carried_input_sources: dict[str, tuple[str, ...]] = {}
        has_non_bootstrap_leaf = False
        entry_phase_identity = phase_family_entry_phase_identity(
            typed_workflow.definition.name,
            family_profile_catalog=context.workflow_catalog.family_profile_catalog,
        )
        if structural_classification is not None:
            for field in flattened_fields:
                contract_definition = dict(field.contract_definition)
                if (
                    requirement.context_kind == PHASE_CONTEXT_TYPE_NAME
                    and entry_phase_identity is not None
                ):
                    relative_path = field.source_path[1:]
                    if relative_path == ("phase-name",):
                        contract_definition["default"] = entry_phase_identity
                    elif relative_path == ("state-root",):
                        contract_definition["default"] = f"state/{entry_phase_identity}"
                    elif relative_path == ("artifact-root",):
                        contract_definition["default"] = (
                            f"artifacts/{entry_phase_identity}"
                        )
                role = _bootstrap_role_for_field(
                    source_path=field.source_path,
                    contract_definition=contract_definition,
                    anchors=structural_classification.anchors,
                )
                if role is not None:
                    input_roles[field.generated_name] = role
                    if role.startswith("run_anchor:"):
                        carried_input_sources[field.generated_name] = field.source_path
                    continue
                carried_input_sources[field.generated_name] = field.source_path
                has_non_bootstrap_leaf = True
        projection_hints: dict[str, Any] = {"context_binding_schema_version": 1}
        if input_roles:
            projection_hints["context_input_roles"] = input_roles
        if carried_input_sources:
            projection_hints["carried_input_sources"] = carried_input_sources
        binding = PrivateExecContextBinding(
            binding_id=source_param_name,
            source_param_name=source_param_name,
            context_family=requirement.context_kind,
            bridge_class=(
                "imported_adapter_carried_context"
                if has_non_bootstrap_leaf
                else "runtime_owned_context"
            ),
            generated_input_names=tuple(
                field.generated_name for field in flattened_fields
            ),
            required_capabilities=(
                structural_classification.derived_capabilities
                if structural_classification is not None
                else private_exec_context_capabilities(requirement.context_kind)
            ),
            derived_phase_identity=phase_family_entry_phase_identity(
                typed_workflow.definition.name,
                family_profile_catalog=context.workflow_catalog.family_profile_catalog,
            ),
            projection_hints=projection_hints,
            source_provenance=provenance,
        )
        if binding not in context.private_exec_context_bindings:
            context.private_exec_context_bindings.append(binding)


def _phase_context_capabilities(typed_workflow: Any) -> tuple[str, ...]:
    for param_name, type_ref in typed_workflow.signature.params:
        if param_name != "phase-ctx":
            continue
        classification = classify_structural_private_exec_context(type_ref)
        if classification is not None:
            return classification.derived_capabilities
    return ()


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


def checked_design_delta_public_input_names(
    workflow_name: str,
    *,
    boundary_authority_registry: Mapping[str, object] | None = None,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> frozenset[str]:
    """Return checked public-authored inputs for one Design Delta workflow."""

    if family_profile_catalog is None or not is_design_delta_parent_drain_target_workflow(
        workflow_name,
        family_profile_catalog=family_profile_catalog,
    ):
        return frozenset()
    registry_payload = boundary_authority_registry
    if isinstance(registry_payload, Mapping):
        return frozenset(
            str(row.get("field_name"))
            for row in registry_payload.get("rows", [])
            if isinstance(row, Mapping)
            and row.get("workflow_name") == workflow_name
            and row.get("surface_kind") == "public_input"
            and row.get("authority_class") == "public_authored"
            and isinstance(row.get("field_name"), str)
        )
    return family_profile_catalog.checked_public_inputs(workflow_name)


def build_design_delta_boundary_authority_expected_rows(
    boundary_projection_payload: dict[str, object],
    *,
    boundary_authority_registry: Mapping[str, object] | None = None,
    family_profile_catalog: WorkflowFamilyProfileCatalog | None = None,
) -> dict[tuple[str, str], dict[str, object]]:
    workflows = boundary_projection_payload.get("workflows")
    if not isinstance(workflows, list):
        return {}
    if family_profile_catalog is None:
        return {}
    registry_payload = boundary_authority_registry
    if registry_payload is None:
        profile = next(
            (
                family
                for family in family_profile_catalog.profiles
                if family.boundary_authority_registry_path is not None
            ),
            None,
        )
        if profile is not None:
            registry_payload = load_design_delta_boundary_authority_registry(
                profile.boundary_authority_registry_path,
                target_workflows=profile.target_workflows,
            )
    registry_target_workflows = (
        frozenset(
            str(row.get("workflow_name"))
            for row in registry_payload.get("rows", [])
            if isinstance(row, Mapping) and isinstance(row.get("workflow_name"), str)
        )
        if isinstance(registry_payload, Mapping)
        else None
    )
    target_workflows = frozenset(
        str(workflow.get("workflow_name"))
        for workflow in workflows
        if isinstance(workflow, Mapping)
        and isinstance(workflow.get("workflow_name"), str)
        and is_design_delta_parent_drain_target_workflow(
            str(workflow.get("workflow_name")),
            family_profile_catalog=family_profile_catalog,
        )
        and (
            registry_target_workflows is None
            or str(workflow.get("workflow_name")) in registry_target_workflows
        )
    )
    checked_public_inputs = {
        (workflow_name, field_name)
        for workflow_name in target_workflows
        for field_name in checked_design_delta_public_input_names(
            workflow_name,
            boundary_authority_registry=registry_payload,
            family_profile_catalog=family_profile_catalog,
        )
    }
    expected: dict[tuple[str, str], dict[str, object]] = {}
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        workflow_name = workflow.get("workflow_name")
        if not isinstance(workflow_name, str) or not is_design_delta_parent_drain_target_workflow(
            workflow_name,
            family_profile_catalog=family_profile_catalog,
        ):
            continue
        boundary = workflow.get("boundary")
        if not isinstance(boundary, dict):
            continue
        runtime_context_generated_names = {
            field_name
            for binding in boundary.get("private_runtime_context_bindings", [])
            if isinstance(binding, dict)
            for field_name in binding.get("generated_input_names", [])
            if isinstance(field_name, str)
        }
        compatibility_bridge_inputs = {
            field_name
            for field_name in boundary.get("private_compatibility_bridge_inputs", [])
            if isinstance(field_name, str)
        }
        overlapping_checked_public_inputs = {
            field_name
            for field_name in compatibility_bridge_inputs
            if (workflow_name, field_name) in checked_public_inputs
        }
        managed_write_root_inputs = {
            field_name
            for field_name in boundary.get("private_managed_write_root_inputs", [])
            if isinstance(field_name, str)
        }
        flattened_inputs = {
            item.get("generated_name"): item
            for item in workflow.get("flattened_inputs", [])
            if isinstance(item, dict) and isinstance(item.get("generated_name"), str)
        }
        generated_internal_inputs = {
            item.get("generated_name"): item
            for item in workflow.get("generated_internal_inputs", [])
            if isinstance(item, dict) and isinstance(item.get("generated_name"), str)
        }
        flattened_outputs = workflow.get("flattened_outputs", [])
        public_input_names = (
            checked_design_delta_public_input_names(
                workflow_name,
                boundary_authority_registry=registry_payload,
                family_profile_catalog=family_profile_catalog,
            )
            if registry_payload is not None
            else tuple(
                field_name
                for field_name in boundary.get("public_input_names", [])
                if isinstance(field_name, str)
            )
        )
        for field_name in public_input_names:
            field = flattened_inputs.get(field_name)
            if not isinstance(field, dict) or not _is_path_like_contract(field.get("contract_definition")):
                continue
            expected[(workflow_name, field_name)] = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": "public_input",
                "path_like": True,
            }
        for field_name in overlapping_checked_public_inputs:
            field = flattened_inputs.get(field_name)
            if not isinstance(field, dict) or not _is_path_like_contract(field.get("contract_definition")):
                continue
            expected[(workflow_name, field_name)] = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": "public_input",
                "path_like": True,
            }
        for field in flattened_outputs:
            if not isinstance(field, dict):
                continue
            field_name = field.get("generated_name")
            if not isinstance(field_name, str) or not _is_path_like_contract(field.get("contract_definition")):
                continue
            expected[(workflow_name, field_name)] = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": "flattened_output",
                "path_like": True,
            }
        for field in workflow.get("generated_internal_inputs", []):
            if not isinstance(field, dict):
                continue
            field_name = field.get("generated_name")
            if (
                not isinstance(field_name, str)
                or (workflow_name, field_name) in expected
                or field_name in runtime_context_generated_names
                or field_name in compatibility_bridge_inputs
                or field_name in managed_write_root_inputs
                or not _is_path_like_generated_internal_field(
                    field_name,
                    field,
                    flattened_inputs=flattened_inputs,
                )
            ):
                continue
            expected[(workflow_name, field_name)] = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": "generated_internal_input",
                "path_like": True,
            }
        for field_name in boundary.get("private_compatibility_bridge_inputs", []):
            field = flattened_inputs.get(field_name) or generated_internal_inputs.get(field_name)
            if (
                not isinstance(field_name, str)
                or (workflow_name, field_name) in expected
                or field_name in overlapping_checked_public_inputs
                or not isinstance(field, dict)
                or not _is_path_like_generated_internal_field(
                    field_name,
                    field,
                    flattened_inputs=flattened_inputs,
                )
            ):
                continue
            expected[(workflow_name, field_name)] = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": "compatibility_bridge_input",
                "path_like": True,
            }
        for field_name in boundary.get("private_managed_write_root_inputs", []):
            field = flattened_inputs.get(field_name) or generated_internal_inputs.get(field_name)
            if (
                not isinstance(field_name, str)
                or (workflow_name, field_name) in expected
                or not isinstance(field, dict)
                or not _is_path_like_generated_internal_field(
                    field_name,
                    field,
                    flattened_inputs=flattened_inputs,
                )
            ):
                continue
            expected[(workflow_name, field_name)] = {
                "workflow_name": workflow_name,
                "field_name": field_name,
                "surface_kind": "managed_write_root",
                "path_like": True,
            }
        for binding in boundary.get("private_runtime_context_bindings", []):
            if not isinstance(binding, dict):
                continue
            for field_name in binding.get("generated_input_names", []):
                field = flattened_inputs.get(field_name) or generated_internal_inputs.get(field_name)
                if (
                    not isinstance(field_name, str)
                    or (workflow_name, field_name) in expected
                    or not isinstance(field, dict)
                    or not _is_path_like_generated_internal_field(
                        field_name,
                        field,
                        flattened_inputs=flattened_inputs,
                    )
                ):
                    continue
                expected[(workflow_name, field_name)] = {
                    "workflow_name": workflow_name,
                    "field_name": field_name,
                    "surface_kind": "runtime_context_input",
                    "path_like": True,
                }
    return expected


def _is_path_like_contract(contract_definition: object) -> bool:
    return isinstance(contract_definition, dict) and contract_definition.get("type") == "relpath"


def _is_path_like_generated_internal_field(
    field_name: str,
    field: dict[str, object],
    *,
    flattened_inputs: dict[str, dict[str, object]],
) -> bool:
    flattened_input = flattened_inputs.get(field_name)
    if isinstance(flattened_input, dict) and _is_path_like_contract(
        flattened_input.get("contract_definition")
    ):
        return True
    return field.get("reason") in {"managed_write_root", "compatibility_bridge"}


def _require_registry_string(row: dict[str, object], field_name: str, *, index: int) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"boundary authority row {index} must declare non-empty `{field_name}`")
    return value
