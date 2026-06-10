"""Phase-family public/private boundary classification for selected migrations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .contracts import FlattenedContractField
from .phase import private_exec_context_capabilities
from .type_env import PathTypeRef, RecordTypeRef, TypeRef
from orchestrator.workflow.surface_ast import PrivateExecContextBinding


PHASE_FAMILY_MODULE_PREFIX = "lisp_frontend_design_delta/"
PHASE_CONTEXT_TYPE_NAME = "PhaseCtx"
PHASE_FAMILY_PARENT_WORKFLOW_NAMES = frozenset(
    {
        "design_delta_parent_calls_work_item::run-parent-work-item",
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


def is_selected_phase_family_workflow(workflow_name: str) -> bool:
    return workflow_name.startswith(PHASE_FAMILY_MODULE_PREFIX) or workflow_name in PHASE_FAMILY_PARENT_WORKFLOW_NAMES


def short_type_name(type_ref: TypeRef) -> str:
    name = getattr(type_ref, "name", "")
    return str(name).rsplit("::", 1)[-1].rsplit("/", 1)[-1]


def is_phase_context_type(type_ref: TypeRef) -> bool:
    return (
        isinstance(type_ref, RecordTypeRef)
        and short_type_name(type_ref) == PHASE_CONTEXT_TYPE_NAME
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
    if not is_selected_phase_family_workflow(workflow_name):
        return PhaseFamilyBoundaryClassification()

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
            runtime_names.append(field.generated_name)
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
    source_param_name = "phase-ctx"
    origin = context.generated_input_spans.get(generated_input_names[0])
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
    binding = PrivateExecContextBinding(
        binding_id=source_param_name,
        source_param_name=source_param_name,
        context_family=PHASE_CONTEXT_TYPE_NAME,
        bridge_class="runtime_owned_context",
        generated_input_names=generated_input_names,
        required_capabilities=private_exec_context_capabilities(PHASE_CONTEXT_TYPE_NAME),
        derived_phase_identity=phase_family_entry_phase_identity(
            typed_workflow.definition.name
        ),
        source_provenance=provenance,
    )
    if binding not in context.private_exec_context_bindings:
        context.private_exec_context_bindings.append(binding)
