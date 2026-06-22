"""Phase-family public/private boundary classification for selected migrations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from .context_classification import (
    _bootstrap_role_for_field,
    classify_structural_private_exec_context,
)
from .contracts import FlattenedContractField, derive_workflow_boundary_fields
from .effects import CallsWorkflowEffect, EffectSummary
from .phase import private_exec_context_capabilities
from .type_env import PathTypeRef, RecordTypeRef, TypeRef
from orchestrator.workflow.surface_ast import PrivateExecContextBinding


PHASE_FAMILY_MODULE_PREFIX = "lisp_frontend_design_delta/"
PHASE_CONTEXT_TYPE_NAME = "PhaseCtx"
PHASE_FAMILY_PARENT_WORKFLOW_NAMES = frozenset(
    {
        "design_delta_parent_calls_implementation_phase::run-implementation-phase",
        "design_delta_parent_calls_work_item::run-parent-work-item",
    }
)
DESIGN_DELTA_PARENT_DRAIN_TARGET_WORKFLOW_NAMES = frozenset(
    {
        "lisp_frontend_design_delta/drain::drain",
        "lisp_frontend_design_delta/selector::select-next-work",
        "lisp_frontend_design_delta/work_item::run-work-item",
        "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "lisp_frontend_design_delta/implementation_phase::implementation-phase",
        "lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture",
        "lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture",
    }
)
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
DESIGN_DELTA_BOUNDARY_AUTHORITY_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.boundary_authority.json"
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


def is_selected_phase_family_workflow(workflow_name: str) -> bool:
    return workflow_name.startswith(PHASE_FAMILY_MODULE_PREFIX) or workflow_name in PHASE_FAMILY_PARENT_WORKFLOW_NAMES


def is_design_delta_parent_drain_target_workflow(workflow_name: str) -> bool:
    return workflow_name in DESIGN_DELTA_PARENT_DRAIN_TARGET_WORKFLOW_NAMES


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
) -> PhaseFamilyBoundaryClassification:
    selected_phase_family = is_selected_phase_family_workflow(workflow_name)
    params_by_name = dict(params)
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
            if selected_phase_family:
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


def phase_family_entry_phase_identity(workflow_name: str) -> str | None:
    if not is_selected_phase_family_workflow(workflow_name):
        return None
    entry_name = workflow_name.rsplit("::", 1)[-1]
    return {
        "run-plan-phase": "plan",
        "run-implementation-phase": "implementation",
        "implementation-phase": "implementation",
        "run-work-item": "work-item",
    }.get(entry_name)


def apply_phase_family_boundary_classification(
    *,
    workflow_name: str,
    params: Iterable[tuple[str, TypeRef]],
    boundary_projection: Any,
    context: Any,
) -> PhaseFamilyBoundaryClassification:
    classification = classify_phase_family_boundary(
        workflow_name=workflow_name,
        params=params,
        flattened_inputs=boundary_projection.flattened_inputs,
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
            typed_workflow.definition.name
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
                if role is None:
                    carried_input_sources[field.generated_name] = field.source_path
                    has_non_bootstrap_leaf = True
                    continue
                input_roles[field.generated_name] = role
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
                typed_workflow.definition.name
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


def load_design_delta_boundary_authority_registry(path: Path) -> dict[str, object]:
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
        if not is_design_delta_parent_drain_target_workflow(workflow_name):
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


@lru_cache(maxsize=1)
def _checked_design_delta_boundary_authority_registry() -> dict[str, object]:
    return load_design_delta_boundary_authority_registry(
        DESIGN_DELTA_BOUNDARY_AUTHORITY_REGISTRY_PATH
    )


def checked_design_delta_compatibility_bridge_inputs(workflow_name: str) -> frozenset[str]:
    if not is_design_delta_parent_drain_target_workflow(workflow_name):
        return frozenset()
    payload = _checked_design_delta_boundary_authority_registry()
    return frozenset(
        str(row["field_name"])
        for row in payload["rows"]
        if row.get("workflow_name") == workflow_name
        and row.get("surface_kind") == "compatibility_bridge_input"
        and row.get("authority_class") == "compatibility_bridge"
    )


def build_design_delta_boundary_authority_expected_rows(
    boundary_projection_payload: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    workflows = boundary_projection_payload.get("workflows")
    if not isinstance(workflows, list):
        return {}
    expected: dict[tuple[str, str], dict[str, object]] = {}
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        workflow_name = workflow.get("workflow_name")
        if not isinstance(workflow_name, str) or not is_design_delta_parent_drain_target_workflow(workflow_name):
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
        for field_name in boundary.get("public_input_names", []):
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
