"""Workflow Lisp source-map schema and build-time lineage helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from orchestrator.exceptions import ValidationSubjectRef
from orchestrator.workflow.core_ast import CoreForEach, CoreIf, CoreMatch, CoreRepeatUntil, CoreWorkflowAST
from orchestrator.workflow.executable_ir import (
    ExecutableNodeBase,
    ProviderSupervisionStepConfig,
)
from orchestrator.workflow.prompt_dependency_contract import (
    CompilerPromptDependencyContract,
    PromptDependencyOriginKind,
)

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourcePosition, SourceSpan

if TYPE_CHECKING:
    from .compiler import LinkedStage3CompileResult
    from .lowering import LoweringOrigin, LoweredWorkflow
    from .workflows import CertifiedAdapterBinding, ExternalToolBinding


SOURCE_MAP_SCHEMA_VERSION = "workflow_lisp_source_map.v1"
SOURCE_MAP_COVERAGE = {
    "frontend_ast": "covered",
    "lowered_surface": "covered",
    "shared_validation_subjects": "covered",
    "executable_ir": "covered",
    "runtime_logs": "covered",
    "core_workflow_ast": "covered",
    "semantic_ir": "covered",
}
_VALID_COVERAGE_KEYS = frozenset(SOURCE_MAP_COVERAGE)
_VALID_COVERAGE_VALUES = frozenset({"covered"})
_PROVIDER_SUPERVISION_OWNER_ROLES = (
    "form",
    "worker_binding",
    "supervisor_binding",
    "observation",
    "settlement",
)
_PROVIDER_SUPERVISION_MEMBER_ROLES = ("worker", "supervisor")


@dataclass(frozen=True)
class SourceMapEntry:
    """One authored source origin serialized into the persisted sidecar."""

    origin_key: str
    entity_kind: str
    workflow_name: str
    path: str
    line: int
    column: int
    end_line: int
    end_column: int
    form_path: tuple[str, ...]
    module_name: str | None = None
    expansion_stack: tuple[object, ...] = ()
    notes: tuple[str, ...] = ()
    generated_name_origin: str | None = None


@dataclass(frozen=True)
class CommandBoundaryLineage:
    """Persisted command-boundary provenance for one lowered step."""

    step_id: str
    command_name: str
    boundary_kind: str
    origin_key: str
    adapter_name: str | None = None
    source_map_behavior: str | None = None
    declared_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class GeneratedSemanticEffectLineage:
    """Persisted lowering-owned promoted semantic effect lineage."""

    effect_key: str
    step_id: str
    effect_kind: str
    origin_key: str
    details: Mapping[str, Any]


@dataclass(frozen=True)
class ValidationSubjectBinding:
    """One generated validation subject mapped back to an authored origin."""

    subject_ref: ValidationSubjectRef
    origin_key: str


@dataclass(frozen=True)
class ExecutableNodeLineage:
    """One runtime-observable executable node mapped to authored provenance."""

    node_id: str
    step_id: str
    kind: str
    region: str
    origin_key: str
    presentation_name: str


@dataclass(frozen=True)
class CoreNodeLineage:
    """One serialized Core AST statement mapped to authored provenance."""

    statement_id: str
    step_id: str
    step_kind: str
    origin_key: str


@dataclass(frozen=True)
class GeneratedPathAllocationLineage:
    """Persisted allocator metadata tied back to one generated authored path."""

    allocation_id: str
    semantic_role: str
    privacy: str
    resume_scope: str
    stable_identity: str
    concrete_path_template: str
    generated_input_name: str | None
    path_safety_policy: str
    origin_key: str


@dataclass(frozen=True)
class PromptDependencyRowLineage:
    """One authored dependency row and its exact lowered binding ref."""

    role: str
    authored_index: int
    binding_ref: str
    origin: SourceMapEntry


@dataclass(frozen=True)
class PromptDependencyPolicyLineage:
    """One normalized injection-policy value and its authored origin."""

    value: str
    origin: SourceMapEntry


@dataclass(frozen=True)
class PromptDependencyContractLineage:
    """Clause, row, and policy lineage for one provider step."""

    step_id: str
    source_origin_key: str
    clause: SourceMapEntry
    rows: tuple[PromptDependencyRowLineage, ...]
    position: PromptDependencyPolicyLineage
    instruction: PromptDependencyPolicyLineage | None


@dataclass(frozen=True)
class ProviderSupervisionOwnerLineage:
    """One fixed provider-supervision source-owner role and its origin."""

    role: str
    source_origin_key: str
    origin: SourceMapEntry


@dataclass(frozen=True)
class ProviderSupervisionMemberPromptLineage:
    """One member's compiler-owned prompt contract and source lineage."""

    member_id: str
    source_origin_key: str
    origin_kind: str
    origin: SourceMapEntry
    rows: tuple[PromptDependencyRowLineage, ...]
    position: str
    position_origin: SourceMapEntry | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    instruction: str | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    instruction_origin: SourceMapEntry | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )


@dataclass(frozen=True)
class ProviderSupervisionLineage:
    """One generated supervision node and its closed nested provenance."""

    node_id: str
    step_id: str
    member_ids: Mapping[str, str]
    owners: Mapping[str, ProviderSupervisionOwnerLineage]
    member_prompt_dependencies: tuple[
        ProviderSupervisionMemberPromptLineage, ...
    ]


@dataclass(frozen=True)
class WorkflowSourceMap:
    """Per-workflow lineage sections nested under the top-level document."""

    display_name: str
    selected_entry_workflow: bool
    workflow_name: str
    workflow_origin: SourceMapEntry
    step_ids: Mapping[str, SourceMapEntry]
    generated_inputs: Mapping[str, SourceMapEntry]
    generated_outputs: Mapping[str, SourceMapEntry]
    contract_fields: Mapping[str, SourceMapEntry]
    generated_paths: Mapping[str, SourceMapEntry]
    generated_internal_inputs: Mapping[str, SourceMapEntry]
    generated_path_allocations: tuple[GeneratedPathAllocationLineage, ...]
    generated_semantic_effects: tuple[GeneratedSemanticEffectLineage, ...]
    core_nodes: tuple[CoreNodeLineage, ...]
    command_boundaries: tuple[CommandBoundaryLineage, ...]
    validation_subjects: tuple[ValidationSubjectBinding, ...]
    executable_nodes: tuple[ExecutableNodeLineage, ...]
    provider_supervision: tuple[ProviderSupervisionLineage, ...] | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    prompt_dependencies: tuple[PromptDependencyContractLineage, ...] | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )


@dataclass(frozen=True)
class WorkflowLispSourceMap:
    """Canonical persisted source-map sidecar for Workflow Lisp builds."""

    schema_version: str
    coverage: Mapping[str, str]
    workflows: Mapping[str, WorkflowSourceMap]


def _prompt_dependency_rows_policy_error(
    rows: object,
    *,
    position: object,
    require_rows: bool,
) -> str | None:
    """Return the shared persisted row/position contract violation, if any."""

    if not isinstance(rows, tuple):
        return "rows must be a tuple"
    if require_rows and not rows:
        return "at least one row is required"
    expected_indices = {"required": 0, "optional": 0}
    for row in rows:
        if not isinstance(row, PromptDependencyRowLineage):
            return "rows must use typed lineage entries"
        expected_index = expected_indices.get(row.role)
        if (
            expected_index is None
            or isinstance(row.authored_index, bool)
            or row.authored_index != expected_index
            or not isinstance(row.binding_ref, str)
            or not row.binding_ref
        ):
            return "row role, index, or binding ref is invalid"
        expected_indices[row.role] += 1
    if position not in {"prepend", "append"}:
        return "position policy is invalid"
    return None


def _provider_supervision_lineage_error(
    lineage: ProviderSupervisionLineage,
    *,
    executable_nodes_by_id: Mapping[str, ExecutableNodeLineage],
    origin_keys: set[str],
) -> str | None:
    executable_node = executable_nodes_by_id.get(lineage.node_id)
    if (
        executable_node is None
        or executable_node.kind != "provider_supervision"
        or executable_node.step_id != lineage.step_id
    ):
        return f"lineage `{lineage.node_id}` does not match its executable node"

    if set(lineage.owners) != set(_PROVIDER_SUPERVISION_OWNER_ROLES):
        return (
            f"lineage `{lineage.node_id}` must declare the five fixed "
            "source-owner roles"
        )
    owner_keys: list[str] = []
    for role in _PROVIDER_SUPERVISION_OWNER_ROLES:
        owner = lineage.owners[role]
        owner_keys.append(owner.source_origin_key)
        if (
            owner.role != role
            or owner.source_origin_key != owner.origin.origin_key
            or owner.origin.origin_key not in origin_keys
        ):
            return f"source owner `{lineage.node_id}:{role}` is dangling"
    if len(set(owner_keys)) != len(_PROVIDER_SUPERVISION_OWNER_ROLES):
        return f"lineage `{lineage.node_id}` must retain five distinct source owners"

    declared_member_ids = lineage.member_ids
    if (
        not isinstance(declared_member_ids, Mapping)
        or set(declared_member_ids) != set(_PROVIDER_SUPERVISION_MEMBER_ROLES)
        or any(
            not isinstance(member_id, str) or not member_id
            for member_id in declared_member_ids.values()
        )
        or len(set(declared_member_ids.values())) != 2
    ):
        return (
            f"lineage `{lineage.node_id}` has an invalid worker/supervisor "
            "member identity map"
        )
    member_lineages = lineage.member_prompt_dependencies
    if (
        len(member_lineages) != 2
        or any(
            not isinstance(member, ProviderSupervisionMemberPromptLineage)
            for member in member_lineages
        )
        or tuple(member.member_id for member in member_lineages)
        != tuple(
            declared_member_ids[role]
            for role in _PROVIDER_SUPERVISION_MEMBER_ROLES
        )
    ):
        return (
            f"lineage `{lineage.node_id}` must retain the exact "
            "worker/supervisor member prompt association"
        )

    implicit_origin_kind = (
        PromptDependencyOriginKind
        .WORKFLOW_LISP_PROVIDER_SUPERVISION_MEMBER_IMPLICIT_EMPTY
        .value
    )
    explicit_origin_kind = (
        PromptDependencyOriginKind
        .WORKFLOW_LISP_PROVIDER_RESULT_PROMPT_DEPENDENCIES
        .value
    )
    for member in member_lineages:
        member_ref = f"{lineage.node_id}:{member.member_id}"
        if (
            member.source_origin_key != member.origin.origin_key
            or member.origin.origin_key not in origin_keys
        ):
            return f"member prompt origin `{member_ref}` is dangling"
        implicit_empty = member.origin_kind == implicit_origin_kind
        rows_policy_error = _prompt_dependency_rows_policy_error(
            member.rows,
            position=member.position,
            require_rows=not implicit_empty,
        )
        if rows_policy_error is not None:
            return (
                f"member prompt lineage `{member_ref}` has invalid rows or "
                f"policy: {rows_policy_error}"
            )
        if implicit_empty:
            if (
                member.rows
                or member.position != "prepend"
                or member.position_origin is not None
                or member.instruction is not None
                or member.instruction_origin is not None
            ):
                return "implicit-empty member prompt lineage must stay empty"
            continue
        if member.origin_kind != explicit_origin_kind:
            return "member prompt lineage has an unsupported origin kind"
        if member.position_origin is None:
            return "authored member prompt lineage is incomplete"
        if (member.instruction is None) != (member.instruction_origin is None):
            return "member prompt instruction lineage is incomplete"
    return None


def build_source_map_document(
    compile_result: "LinkedStage3CompileResult",
    *,
    selected_name: str,
    display_name_resolver,
) -> WorkflowLispSourceMap:
    """Build and validate the persisted Workflow Lisp source-map document."""

    workflows: dict[str, WorkflowSourceMap] = {}
    for module_result in compile_result.compiled_results_by_name.values():
        bindings = module_result.command_boundary_environment.bindings_by_name
        for lowered in module_result.lowered_workflows:
            workflow_name = lowered.typed_workflow.definition.name
            workflow_origin = _entry_from_origin(
                lowered.origin_map.workflow_origin,
                workflow_name=workflow_name,
                entity_kind="workflow",
                subject_name=workflow_name,
            )
            step_ids = _step_entry_mapping(
                lowered=lowered,
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
            )
            generated_inputs = _entry_mapping(
                lowered.origin_map.authored_input_spans,
                workflow_name=workflow_name,
                entity_kind="generated_input",
            )
            generated_outputs = _entry_mapping(
                lowered.origin_map.generated_output_spans,
                workflow_name=workflow_name,
                entity_kind="generated_output",
            )
            contract_fields = _contract_field_entry_mapping(
                lowered=lowered,
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
            )
            generated_paths = _entry_mapping(
                lowered.origin_map.generated_path_spans,
                workflow_name=workflow_name,
                entity_kind="generated_path",
            )
            generated_internal_inputs = _entry_mapping(
                lowered.origin_map.internal_input_spans,
                workflow_name=workflow_name,
                entity_kind="generated_internal_input",
            )
            generated_path_allocations = _generated_path_allocations_for_workflow(
                lowered=lowered,
                generated_paths=generated_paths,
                workflow_origin=workflow_origin,
            )
            command_boundaries = _command_boundaries_for_workflow(
                lowered=lowered,
                step_ids=step_ids,
                bindings_by_name=bindings,
            )
            generated_semantic_effects = _generated_semantic_effects_for_workflow(
                lowered=lowered,
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
            )
            validation_subjects = _validation_subject_bindings(
                lowered=lowered,
                workflow_origin=workflow_origin,
                step_ids=step_ids,
                generated_inputs=generated_inputs,
                generated_outputs=generated_outputs,
                generated_paths=generated_paths,
                generated_internal_inputs=generated_internal_inputs,
            )
            validated_bundle = compile_result.validated_bundles_by_name.get(workflow_name)
            executable_nodes = _executable_nodes_for_workflow(
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
                step_ids=step_ids,
                validated_bundle=validated_bundle,
            )
            provider_supervision = (
                _provider_supervision_lineages_for_workflow(
                    lowered=lowered,
                    workflow_name=workflow_name,
                    workflow_origin=workflow_origin,
                    validated_bundle=validated_bundle,
                )
            )
            core_nodes = _core_nodes_for_workflow(
                lowered=lowered,
                workflow_origin=workflow_origin,
                step_ids=step_ids,
                validated_bundle=validated_bundle,
            )
            prompt_dependencies = _prompt_dependency_lineages_for_workflow(
                lowered=lowered,
                workflow_name=workflow_name,
            )
            workflows[workflow_name] = WorkflowSourceMap(
                display_name=display_name_resolver(workflow_name),
                selected_entry_workflow=workflow_name == selected_name,
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
                step_ids=step_ids,
                generated_inputs=generated_inputs,
                generated_outputs=generated_outputs,
                contract_fields=contract_fields,
                generated_paths=generated_paths,
                generated_internal_inputs=generated_internal_inputs,
                generated_path_allocations=generated_path_allocations,
                generated_semantic_effects=generated_semantic_effects,
                core_nodes=core_nodes,
                command_boundaries=command_boundaries,
                validation_subjects=validation_subjects,
                executable_nodes=executable_nodes,
                provider_supervision=provider_supervision or None,
                prompt_dependencies=prompt_dependencies or None,
            )

    document = WorkflowLispSourceMap(
        schema_version=SOURCE_MAP_SCHEMA_VERSION,
        coverage=dict(SOURCE_MAP_COVERAGE),
        workflows=workflows,
    )
    validate_source_map_document(document)
    return document


def validate_source_map_document(document: WorkflowLispSourceMap) -> None:
    """Reject inconsistent lineage claims with deterministic frontend diagnostics."""

    diagnostics: list[LispFrontendDiagnostic] = []
    coverage = dict(document.coverage)
    if set(coverage) != _VALID_COVERAGE_KEYS:
        diagnostics.append(
            LispFrontendDiagnostic(
                code="source_map_invalid_coverage",
                message="source-map coverage claims must declare the full canonical key set",
                phase="lowering",
            )
        )
    elif any(value not in _VALID_COVERAGE_VALUES for value in coverage.values()):
        diagnostics.append(
            LispFrontendDiagnostic(
                code="source_map_invalid_coverage",
                message="source-map coverage claims must use only supported coverage states",
                phase="lowering",
            )
        )

    seen_origin_keys: dict[str, SourceMapEntry] = {}
    for workflow in document.workflows.values():
        origin_entries = list(_iter_origin_entries(workflow))
        workflow_origin = workflow.workflow_origin
        origin_keys = {entry.origin_key for entry in origin_entries}
        for entry in origin_entries:
            previous = seen_origin_keys.get(entry.origin_key)
            if previous is not None:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_duplicate_key",
                        message=f"duplicate source-map origin key `{entry.origin_key}`",
                    )
                )
                break
            seen_origin_keys[entry.origin_key] = entry
        for subject in workflow.validation_subjects:
            if subject.origin_key not in origin_keys:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_validation_ref_missing",
                        message=(
                            "validation subject "
                            f"`{subject.subject_ref.subject_kind}:{subject.subject_ref.subject_name}` "
                            "does not resolve to a declared origin"
                        ),
                    )
                )
        for subject_name, entry in workflow.contract_fields.items():
            matching_subjects = [
                subject
                for subject in workflow.validation_subjects
                if _validation_subject_key(subject.subject_ref, workflow.workflow_name)
                == (entry.entity_kind, subject_name, workflow.workflow_name)
                and subject.origin_key == entry.origin_key
            ]
            if len(matching_subjects) != 1:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_validation_subject_missing",
                        message=(
                            "contract field "
                            f"`{subject_name}` must have exactly one matching validation subject"
                        ),
                    )
                )
        required_subject_keys = _required_validation_subject_keys(workflow)
        actual_subject_keys = {
            _validation_subject_key(subject.subject_ref, workflow.workflow_name)
            for subject in workflow.validation_subjects
        }
        for subject_kind, subject_name, workflow_name in sorted(required_subject_keys - actual_subject_keys):
            diagnostics.append(
                _diagnostic_for_entry(
                    workflow_origin,
                    code="source_map_validation_subject_missing",
                    message=(
                        "required validation subject "
                        f"`{subject_kind}:{subject_name}` missing for workflow `{workflow_name}`"
                    ),
                    )
                )
        if workflow.step_ids and not workflow.core_nodes:
            diagnostics.append(
                _diagnostic_for_entry(
                    workflow_origin,
                    code="source_map_core_node_missing",
                    message=(
                        "core-workflow-ast coverage is declared but workflow "
                        f"`{workflow.workflow_name}` has no persisted core node lineage"
                    ),
                )
            )
        for node in workflow.core_nodes:
            if node.origin_key not in origin_keys:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_core_node_missing",
                        message=(
                            "core-workflow-ast lineage entry "
                            f"`{node.statement_id}` does not resolve to a declared origin"
                        ),
                    )
                )
            if node.step_id not in workflow.step_ids:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_core_node_missing",
                        message=(
                            "core-workflow-ast lineage entry "
                            f"`{node.statement_id}` references unknown step `{node.step_id}`"
                        ),
                    )
                )
        for node in workflow.executable_nodes:
            if node.origin_key not in origin_keys:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_executable_node_unmapped",
                        message=f"executable node `{node.node_id}` does not resolve to a declared origin",
                    )
                )
        provider_node_ids = {
            node.node_id
            for node in workflow.executable_nodes
            if node.kind == "provider_supervision"
        }
        provider_lineages = workflow.provider_supervision or ()
        lineage_node_ids = {
            lineage.node_id
            for lineage in provider_lineages
        }
        if (
            len(lineage_node_ids) != len(provider_lineages)
            or lineage_node_ids != provider_node_ids
        ):
            diagnostics.append(
                _diagnostic_for_entry(
                    workflow_origin,
                    code="source_map_provider_supervision_invalid",
                    message=(
                        "provider-supervision lineage must match the exact "
                        "executable provider-supervision node set"
                    ),
                )
            )
        executable_nodes_by_id = {
            node.node_id: node
            for node in workflow.executable_nodes
        }
        for lineage in provider_lineages:
            lineage_error = _provider_supervision_lineage_error(
                lineage,
                executable_nodes_by_id=executable_nodes_by_id,
                origin_keys=origin_keys,
            )
            if lineage_error is not None:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_provider_supervision_invalid",
                        message=f"provider-supervision {lineage_error}",
                    )
                )
        seen_effect_keys: set[str] = set()
        for effect in workflow.generated_semantic_effects:
            if effect.effect_key in seen_effect_keys:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_generated_effect_invalid",
                        message=f"generated semantic effect `{effect.effect_key}` is duplicated",
                    )
                )
                continue
            seen_effect_keys.add(effect.effect_key)
            if effect.origin_key not in origin_keys:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_generated_effect_invalid",
                        message=(
                            f"generated semantic effect `{effect.effect_key}` "
                            "does not resolve to a declared origin"
                        ),
                    )
                )
            if effect.step_id not in workflow.step_ids:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_generated_effect_invalid",
                        message=(
                            f"generated semantic effect `{effect.effect_key}` "
                            f"references unknown step `{effect.step_id}`"
                        ),
                    )
                )
        seen_prompt_dependency_steps: set[str] = set()
        for lineage in workflow.prompt_dependencies or ():
            if lineage.step_id in seen_prompt_dependency_steps:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_prompt_dependency_invalid",
                        message=(
                            f"prompt dependency lineage for step `{lineage.step_id}` is duplicated"
                        ),
                    )
                )
                continue
            seen_prompt_dependency_steps.add(lineage.step_id)
            if lineage.step_id not in workflow.step_ids:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_prompt_dependency_invalid",
                        message=(
                            f"prompt dependency lineage references unknown step `{lineage.step_id}`"
                        ),
                    )
                )
            if lineage.source_origin_key != lineage.clause.origin_key:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_prompt_dependency_invalid",
                        message="prompt dependency contract origin does not resolve to its clause",
                    )
                )
            rows_policy_error = _prompt_dependency_rows_policy_error(
                lineage.rows,
                position=lineage.position.value,
                require_rows=True,
            )
            if rows_policy_error is not None:
                diagnostics.append(
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_prompt_dependency_invalid",
                        message=(
                            f"prompt dependency lineage for step `{lineage.step_id}` "
                            f"has invalid rows or policy: {rows_policy_error}"
                        ),
                    )
                )
    if diagnostics:
        raise LispFrontendCompileError(tuple(diagnostics))


def _entry_mapping(
    origins: Mapping[str, "LoweringOrigin"],
    *,
    workflow_name: str,
    entity_kind: str,
) -> Mapping[str, SourceMapEntry]:
    return {
        name: _entry_from_origin(
            origin,
            workflow_name=workflow_name,
            entity_kind=entity_kind,
            subject_name=name,
        )
        for name, origin in sorted(origins.items())
    }


def _step_entry_mapping(
    *,
    lowered: "LoweredWorkflow",
    workflow_name: str,
    workflow_origin: SourceMapEntry,
) -> Mapping[str, SourceMapEntry]:
    entries = _entry_mapping(
        lowered.origin_map.step_spans,
        workflow_name=workflow_name,
        entity_kind="step_id",
    )
    augmented = dict(entries)
    _augment_missing_step_entries(
        lowered.authored_mapping.get("steps"),
        workflow_name=workflow_name,
        workflow_origin=workflow_origin,
        entries=augmented,
        parent_origin=workflow_origin,
    )
    return augmented


def _contract_field_entry_mapping(
    *,
    lowered: "LoweredWorkflow",
    workflow_name: str,
    workflow_origin: SourceMapEntry,
) -> Mapping[str, SourceMapEntry]:
    entries: dict[str, SourceMapEntry] = {}
    for binding in lowered.origin_map.validation_subject_bindings:
        if binding.subject_ref.subject_kind not in (
            "variant_output_field",
            "output_bundle_field",
        ):
            continue
        subject_name = binding.subject_ref.subject_name
        entry = _entry_from_origin(
            binding.origin,
            workflow_name=workflow_name,
            entity_kind=binding.subject_ref.subject_kind,
            subject_name=subject_name,
        )
        existing = entries.get(subject_name)
        if existing is not None and existing == entry:
            continue
        if existing is not None:
            raise LispFrontendCompileError(
                (
                    _diagnostic_for_entry(
                        workflow_origin,
                        code="source_map_duplicate_key",
                        message=(
                            "contract field subject "
                            f"`{subject_name}` has conflicting source-map entries"
                        ),
                    ),
                )
            )
        entries[subject_name] = entry
    return entries


def _augment_missing_step_entries(
    raw_steps: Any,
    *,
    workflow_name: str,
    workflow_origin: SourceMapEntry,
    entries: dict[str, SourceMapEntry],
    parent_origin: SourceMapEntry,
) -> None:
    if not isinstance(raw_steps, list):
        return
    for step in raw_steps:
        if not isinstance(step, Mapping):
            continue
        current_origin = parent_origin
        step_id = step.get("id")
        if isinstance(step_id, str) and step_id:
            current_origin = entries.setdefault(
                step_id,
                _derived_entry_from_entry(
                    parent_origin,
                    workflow_name=workflow_name,
                    entity_kind="step_id",
                    subject_name=step_id,
                ),
            )
        step_name = step.get("name")
        if isinstance(step_name, str) and step_name:
            current_origin = entries.setdefault(
                step_name,
                _derived_entry_from_entry(
                    current_origin,
                    workflow_name=workflow_name,
                    entity_kind="step_id",
                    subject_name=step_name,
                ),
            )
        match = step.get("match")
        if isinstance(match, Mapping):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, Mapping):
                    _augment_missing_step_entries(
                        case.get("steps"),
                        workflow_name=workflow_name,
                        workflow_origin=workflow_origin,
                        entries=entries,
                        parent_origin=current_origin,
                    )
        repeat = step.get("repeat_until")
        if isinstance(repeat, Mapping):
            _augment_missing_step_entries(
                repeat.get("steps"),
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
                entries=entries,
                parent_origin=current_origin,
            )
        branch = step.get("if")
        if isinstance(branch, Mapping):
            _augment_missing_step_entries(
                branch.get("then"),
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
                entries=entries,
                parent_origin=current_origin,
            )
            _augment_missing_step_entries(
                branch.get("else"),
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
                entries=entries,
                parent_origin=current_origin,
            )
        for_each = step.get("for_each")
        if isinstance(for_each, Mapping):
            _augment_missing_step_entries(
                for_each.get("steps"),
                workflow_name=workflow_name,
                workflow_origin=workflow_origin,
                entries=entries,
                parent_origin=current_origin,
            )


def _entry_from_origin(
    origin: "LoweringOrigin",
    *,
    workflow_name: str,
    entity_kind: str,
    subject_name: str,
) -> SourceMapEntry:
    span = origin.span
    return SourceMapEntry(
        origin_key=getattr(origin, "origin_key", "")
        or _origin_key(
            workflow_name=workflow_name,
            entity_kind=entity_kind,
            subject_name=subject_name,
        ),
        entity_kind=entity_kind,
        workflow_name=workflow_name,
        path=span.start.path,
        line=span.start.line,
        column=span.start.column,
        end_line=span.end.line,
        end_column=span.end.column,
        form_path=tuple(getattr(origin, "form_path", ()) or ()),
        module_name=workflow_name.split("::", 1)[0] if "::" in workflow_name else None,
        expansion_stack=tuple(getattr(origin, "expansion_stack", ()) or ()),
        notes=tuple(getattr(origin, "notes", ()) or ()),
        generated_name_origin=subject_name,
    )


def _origin_key(*, workflow_name: str, entity_kind: str, subject_name: str) -> str:
    return f"{workflow_name}::{entity_kind}::{subject_name}"


def _derived_entry_from_entry(
    entry: SourceMapEntry,
    *,
    workflow_name: str,
    entity_kind: str,
    subject_name: str,
) -> SourceMapEntry:
    return SourceMapEntry(
        origin_key=_origin_key(
            workflow_name=workflow_name,
            entity_kind=entity_kind,
            subject_name=subject_name,
        ),
        entity_kind=entity_kind,
        workflow_name=workflow_name,
        path=entry.path,
        line=entry.line,
        column=entry.column,
        end_line=entry.end_line,
        end_column=entry.end_column,
        form_path=entry.form_path,
        module_name=entry.module_name,
        expansion_stack=entry.expansion_stack,
        notes=entry.notes,
        generated_name_origin=subject_name,
    )


def _iter_origin_entries(workflow: WorkflowSourceMap) -> Iterable[SourceMapEntry]:
    yield workflow.workflow_origin
    yield from workflow.step_ids.values()
    yield from workflow.generated_inputs.values()
    yield from workflow.generated_outputs.values()
    yield from workflow.contract_fields.values()
    yield from workflow.generated_paths.values()
    yield from workflow.generated_internal_inputs.values()
    for lineage in workflow.provider_supervision or ():
        for owner in lineage.owners.values():
            yield owner.origin
        for member in lineage.member_prompt_dependencies:
            yield member.origin
            for row in member.rows:
                yield row.origin
            if member.position_origin is not None:
                yield member.position_origin
            if member.instruction_origin is not None:
                yield member.instruction_origin
    for lineage in workflow.prompt_dependencies or ():
        yield lineage.clause
        for row in lineage.rows:
            yield row.origin
        yield lineage.position.origin
        if lineage.instruction is not None:
            yield lineage.instruction.origin


def _provider_supervision_lineages_for_workflow(
    *,
    lowered: "LoweredWorkflow",
    workflow_name: str,
    workflow_origin: SourceMapEntry,
    validated_bundle,
) -> tuple[ProviderSupervisionLineage, ...]:
    retained_origins = dict(
        getattr(
            lowered.origin_map,
            "provider_supervision_origins",
            {},
        )
        or {}
    )
    retained_prompt_lineages = tuple(
        getattr(
            lowered.origin_map,
            "provider_supervision_prompt_dependency_lineages",
            (),
        )
        or ()
    )
    if validated_bundle is None:
        # Source maps are constructed once during lowering, before validated
        # bundles exist, and again for public build artifacts. The first pass
        # cannot authoritatively project provider-supervision node lineage yet.
        return ()

    prompt_lineages_by_origin: dict[str, object] = {}
    for lineage in retained_prompt_lineages:
        source_origin_key = lineage.source_origin_key
        if source_origin_key in prompt_lineages_by_origin:
            _raise_provider_supervision_source_map_error(
                workflow_origin,
                "provider-supervision member prompt lineage is duplicated",
            )
        prompt_lineages_by_origin[source_origin_key] = lineage

    projected: list[ProviderSupervisionLineage] = []
    claimed_origin_keys: set[str] = set()
    claimed_prompt_lineage_keys: set[str] = set()
    for node in sorted(
        validated_bundle.ir.nodes.values(),
        key=lambda candidate: candidate.node_id,
    ):
        config = node.execution_config
        if not isinstance(config, ProviderSupervisionStepConfig):
            continue
        owners: dict[str, ProviderSupervisionOwnerLineage] = {}
        source_ownership = config.source_ownership.to_dict()
        if set(source_ownership) != set(
            _PROVIDER_SUPERVISION_OWNER_ROLES
        ):
            _raise_provider_supervision_source_map_error(
                workflow_origin,
                "provider-supervision config has incomplete source ownership",
            )
        for role in _PROVIDER_SUPERVISION_OWNER_ROLES:
            source_origin_key = source_ownership[role]
            origin = retained_origins.get(source_origin_key)
            if origin is None:
                _raise_provider_supervision_source_map_error(
                    workflow_origin,
                    (
                        "provider-supervision source owner "
                        f"`{node.node_id}:{role}` has no retained origin"
                    ),
                )
            claimed_origin_keys.add(source_origin_key)
            owners[role] = ProviderSupervisionOwnerLineage(
                role=role,
                source_origin_key=source_origin_key,
                origin=_entry_from_origin(
                    origin,
                    workflow_name=workflow_name,
                    entity_kind="provider_supervision_owner",
                    subject_name=f"{node.node_id}:{role}",
                ),
            )

        member_prompt_dependencies: list[
            ProviderSupervisionMemberPromptLineage
        ] = []
        members_by_role = (
            ("worker", config.worker),
            ("supervisor", config.supervisor),
        )
        member_ids = {
            member_role: member.member_id
            for member_role, member in members_by_role
        }
        for member_role, member in members_by_role:
            contract = (
                member.provider_config
                .compiler_prompt_dependency_contract
            )
            if not isinstance(
                contract,
                CompilerPromptDependencyContract,
            ):
                _raise_provider_supervision_source_map_error(
                    workflow_origin,
                    (
                        "provider-supervision member "
                        f"`{node.node_id}:{member.member_id}` has no typed "
                        "prompt dependency contract"
                    ),
                )
            source_origin_key = contract.source_origin_key
            origin = retained_origins.get(source_origin_key)
            if origin is None:
                _raise_provider_supervision_source_map_error(
                    workflow_origin,
                    (
                        "provider-supervision member prompt contract "
                        f"`{node.node_id}:{member.member_id}` has no retained "
                        "origin"
                    ),
                )
            claimed_origin_keys.add(source_origin_key)
            authored_lineage = prompt_lineages_by_origin.get(
                source_origin_key
            )
            implicit_empty = contract.origin_kind is (
                PromptDependencyOriginKind
                .WORKFLOW_LISP_PROVIDER_SUPERVISION_MEMBER_IMPLICIT_EMPTY
            )
            if implicit_empty and authored_lineage is not None:
                _raise_provider_supervision_source_map_error(
                    workflow_origin,
                    "implicit-empty member prompt contract has authored lineage",
                )
            if not implicit_empty and authored_lineage is None:
                _raise_provider_supervision_source_map_error(
                    workflow_origin,
                    "authored member prompt contract has no retained lineage",
                )

            rows: tuple[PromptDependencyRowLineage, ...] = ()
            position_origin: SourceMapEntry | None = None
            instruction: str | None = None
            instruction_origin: SourceMapEntry | None = None
            if authored_lineage is not None:
                claimed_prompt_lineage_keys.add(source_origin_key)
                expected_rows = (
                    *(
                        ("required", index, binding_ref)
                        for index, binding_ref in enumerate(
                            contract.required_binding_refs
                        )
                    ),
                    *(
                        ("optional", index, binding_ref)
                        for index, binding_ref in enumerate(
                            contract.optional_binding_refs
                        )
                    ),
                )
                actual_rows = tuple(
                    (
                        row.role,
                        row.authored_index,
                        row.binding_ref,
                    )
                    for row in authored_lineage.rows
                )
                if (
                    actual_rows != expected_rows
                    or authored_lineage.position.value
                    != contract.position.value
                ):
                    _raise_provider_supervision_source_map_error(
                        workflow_origin,
                        (
                            "provider-supervision member prompt lineage "
                            "contradicts its typed compiler contract"
                        ),
                    )
                rows = tuple(
                    PromptDependencyRowLineage(
                        role=row.role,
                        authored_index=row.authored_index,
                        binding_ref=row.binding_ref,
                        origin=_entry_from_origin(
                            row.origin,
                            workflow_name=workflow_name,
                            entity_kind="prompt_dependency_row",
                            subject_name=(
                                f"{authored_lineage.step_id}:"
                                f"{row.role}:{row.authored_index}"
                            ),
                        ),
                    )
                    for row in authored_lineage.rows
                )
                position_origin = _entry_from_origin(
                    authored_lineage.position.origin,
                    workflow_name=workflow_name,
                    entity_kind="prompt_dependency_position",
                    subject_name=authored_lineage.step_id,
                )
                if authored_lineage.instruction is not None:
                    instruction = authored_lineage.instruction.value
                    observed_digest = (
                        "sha256:"
                        + hashlib.sha256(
                            instruction.encode("utf-8")
                        ).hexdigest()
                    )
                    if (
                        observed_digest
                        != contract.instruction_utf8_sha256_or_null
                    ):
                        _raise_provider_supervision_source_map_error(
                            workflow_origin,
                            (
                                "provider-supervision member prompt "
                                "instruction contradicts its typed contract"
                            ),
                        )
                    instruction_origin = _entry_from_origin(
                        authored_lineage.instruction.origin,
                        workflow_name=workflow_name,
                        entity_kind="prompt_dependency_instruction",
                        subject_name=authored_lineage.step_id,
                    )
                elif (
                    contract.instruction_utf8_sha256_or_null
                    is not None
                ):
                    _raise_provider_supervision_source_map_error(
                        workflow_origin,
                        (
                            "provider-supervision member prompt instruction "
                            "lineage is missing"
                        ),
                    )
            member_prompt_dependencies.append(
                ProviderSupervisionMemberPromptLineage(
                    member_id=member.member_id,
                    source_origin_key=source_origin_key,
                    origin_kind=contract.origin_kind.value,
                    origin=_entry_from_origin(
                        origin,
                        workflow_name=workflow_name,
                        entity_kind=(
                            "provider_supervision_member_prompt_dependencies"
                        ),
                        subject_name=(
                            f"{node.node_id}:{member.member_id}"
                        ),
                    ),
                    rows=rows,
                    position=contract.position.value,
                    position_origin=position_origin,
                    instruction=instruction,
                    instruction_origin=instruction_origin,
                )
            )
        projected.append(
            ProviderSupervisionLineage(
                node_id=node.node_id,
                step_id=node.step_id,
                member_ids=member_ids,
                owners=owners,
                member_prompt_dependencies=tuple(
                    member_prompt_dependencies
                ),
            )
        )

    if set(retained_origins) != claimed_origin_keys:
        _raise_provider_supervision_source_map_error(
            workflow_origin,
            "provider-supervision retained origin catalog is not exact",
        )
    if (
        set(prompt_lineages_by_origin)
        != claimed_prompt_lineage_keys
    ):
        _raise_provider_supervision_source_map_error(
            workflow_origin,
            "provider-supervision retained member prompt lineage is not exact",
        )
    return tuple(projected)


def _raise_provider_supervision_source_map_error(
    workflow_origin: SourceMapEntry,
    message: str,
) -> None:
    raise LispFrontendCompileError(
        (
            _diagnostic_for_entry(
                workflow_origin,
                code="source_map_provider_supervision_invalid",
                message=message,
            ),
        )
    )


def _prompt_dependency_lineages_for_workflow(
    *,
    lowered: "LoweredWorkflow",
    workflow_name: str,
) -> tuple[PromptDependencyContractLineage, ...]:
    lineages: list[PromptDependencyContractLineage] = []
    contracts = lowered.compiler_prompt_dependency_contracts
    for lineage in lowered.origin_map.prompt_dependency_lineages:
        contract = contracts.get(lineage.step_id)
        if contract is None or contract.source_origin_key != lineage.source_origin_key:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="source_map_prompt_dependency_invalid",
                        message=(
                            f"prompt dependency lineage for step `{lineage.step_id}` "
                            "has no matching typed compiler contract"
                        ),
                        span=lineage.clause_origin.span,
                        form_path=lineage.clause_origin.form_path,
                        expansion_stack=lineage.clause_origin.expansion_stack,
                    ),
                )
            )
        lineages.append(
            PromptDependencyContractLineage(
                step_id=lineage.step_id,
                source_origin_key=lineage.source_origin_key,
                clause=_entry_from_origin(
                    lineage.clause_origin,
                    workflow_name=workflow_name,
                    entity_kind="prompt_dependency_clause",
                    subject_name=lineage.step_id,
                ),
                rows=tuple(
                    PromptDependencyRowLineage(
                        role=row.role,
                        authored_index=row.authored_index,
                        binding_ref=row.binding_ref,
                        origin=_entry_from_origin(
                            row.origin,
                            workflow_name=workflow_name,
                            entity_kind="prompt_dependency_row",
                            subject_name=(
                                f"{lineage.step_id}:{row.role}:{row.authored_index}"
                            ),
                        ),
                    )
                    for row in lineage.rows
                ),
                position=PromptDependencyPolicyLineage(
                    value=lineage.position.value,
                    origin=_entry_from_origin(
                        lineage.position.origin,
                        workflow_name=workflow_name,
                        entity_kind="prompt_dependency_position",
                        subject_name=lineage.step_id,
                    ),
                ),
                instruction=(
                    PromptDependencyPolicyLineage(
                        value=lineage.instruction.value,
                        origin=_entry_from_origin(
                            lineage.instruction.origin,
                            workflow_name=workflow_name,
                            entity_kind="prompt_dependency_instruction",
                            subject_name=lineage.step_id,
                        ),
                    )
                    if lineage.instruction is not None
                    else None
                ),
            )
        )
    extra_contracts = set(contracts) - {lineage.step_id for lineage in lineages}
    if extra_contracts:
        first = sorted(extra_contracts)[0]
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="source_map_prompt_dependency_invalid",
                    message=f"typed compiler prompt dependency contract `{first}` has no lineage",
                    span=lowered.origin_map.workflow_span,
                ),
            )
        )
    return tuple(lineages)


def _command_boundaries_for_workflow(
    *,
    lowered: "LoweredWorkflow",
    step_ids: Mapping[str, SourceMapEntry],
    bindings_by_name: Mapping[str, "ExternalToolBinding | CertifiedAdapterBinding"],
) -> tuple[CommandBoundaryLineage, ...]:
    command_boundaries: list[CommandBoundaryLineage] = []
    for step in _walk_steps(lowered.authored_mapping.get("steps")):
        step_id = step.get("id")
        if not isinstance(step_id, str):
            continue
        binding = _match_command_binding(step, bindings_by_name)
        if binding is None:
            continue
        origin = step_ids.get(step_id)
        if origin is None:
            continue
        boundary_kind = (
            "certified_adapter"
            if hasattr(binding, "source_map_behavior")
            else "external_tool"
        )
        command_boundaries.append(
            CommandBoundaryLineage(
                step_id=step_id,
                command_name=binding.name,
                boundary_kind=boundary_kind,
                origin_key=origin.origin_key,
                adapter_name=(binding.name if boundary_kind == "certified_adapter" else None),
                source_map_behavior=getattr(binding, "source_map_behavior", None),
                declared_effects=tuple(getattr(binding, "effects", ()) or ()),
            )
        )
    command_boundaries.sort(key=lambda entry: (entry.step_id, entry.command_name))
    return tuple(command_boundaries)


def _generated_path_allocations_for_workflow(
    *,
    lowered: "LoweredWorkflow",
    generated_paths: Mapping[str, SourceMapEntry],
    workflow_origin: SourceMapEntry,
) -> tuple[GeneratedPathAllocationLineage, ...]:
    entries: list[GeneratedPathAllocationLineage] = []
    for allocation in lowered.generated_path_allocations:
        generated_path_entry = generated_paths.get(allocation.concrete_path_template)
        origin_key = generated_path_entry.origin_key if generated_path_entry is not None else workflow_origin.origin_key
        entries.append(
            GeneratedPathAllocationLineage(
                allocation_id=allocation.allocation_id,
                semantic_role=allocation.semantic_role.value,
                privacy=allocation.privacy.value,
                resume_scope=allocation.resume_scope.value,
                stable_identity=allocation.stable_identity,
                concrete_path_template=allocation.concrete_path_template,
                generated_input_name=allocation.generated_input_name,
                path_safety_policy=allocation.path_safety_policy,
                origin_key=origin_key,
            )
        )
    return tuple(entries)


def _generated_semantic_effects_for_workflow(
    *,
    lowered: "LoweredWorkflow",
    workflow_name: str,
    workflow_origin: SourceMapEntry,
) -> tuple[GeneratedSemanticEffectLineage, ...]:
    entries: list[GeneratedSemanticEffectLineage] = []
    for effect in getattr(lowered.origin_map, "generated_semantic_effects", ()) or ():
        if effect.effect_kind == "pointer_materialization":
            entity_kind = "generated_path"
            subject_name = effect.details.get("pointer_path", effect.step_id)
        elif effect.effect_kind == "provider_bundle_path_projection":
            entity_kind = "generated_output"
            subject_name = effect.details.get("projected_output_name", effect.step_id)
        else:
            entity_kind = "step_id"
            subject_name = effect.step_id
        origin_entry = _entry_from_origin(
            effect.origin,
            workflow_name=workflow_name,
            entity_kind=entity_kind,
            subject_name=subject_name,
        )
        entries.append(
            GeneratedSemanticEffectLineage(
                effect_key=effect.effect_key,
                step_id=effect.step_id,
                effect_kind=effect.effect_kind,
                origin_key=origin_entry.origin_key or workflow_origin.origin_key,
                details=dict(effect.details),
            )
        )
    entries.sort(key=lambda entry: (entry.effect_kind, entry.step_id, entry.effect_key))
    return tuple(entries)


def _match_command_binding(
    step: Mapping[str, Any],
    bindings_by_name: Mapping[str, "ExternalToolBinding | CertifiedAdapterBinding"],
):
    command = step.get("command")
    if not isinstance(command, list):
        return None
    rendered = tuple(str(part) for part in command)
    matches = []
    for binding in bindings_by_name.values():
        prefix = tuple(binding.stable_command)
        if rendered[: len(prefix)] == prefix:
            matches.append((len(prefix), binding))
    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _validation_subject_bindings(
    *,
    lowered: "LoweredWorkflow",
    workflow_origin: SourceMapEntry,
    step_ids: Mapping[str, SourceMapEntry],
    generated_inputs: Mapping[str, SourceMapEntry],
    generated_outputs: Mapping[str, SourceMapEntry],
    generated_paths: Mapping[str, SourceMapEntry],
    generated_internal_inputs: Mapping[str, SourceMapEntry],
) -> tuple[ValidationSubjectBinding, ...]:
    bindings: list[ValidationSubjectBinding] = [
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="workflow",
                subject_name=lowered.typed_workflow.definition.name,
                workflow_name=lowered.typed_workflow.definition.name,
            ),
            origin_key=workflow_origin.origin_key,
        )
    ]
    origin_map_bindings = tuple(getattr(lowered.origin_map, "validation_subject_bindings", ()) or ())
    if origin_map_bindings:
        bindings.extend(
            ValidationSubjectBinding(
                subject_ref=binding.subject_ref,
                origin_key=binding.origin.origin_key,
            )
            for binding in origin_map_bindings
        )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="step_id",
                subject_name=name,
                workflow_name=lowered.typed_workflow.definition.name,
            ),
            origin_key=entry.origin_key,
        )
        for name, entry in step_ids.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_input",
                subject_name=name,
                workflow_name=lowered.typed_workflow.definition.name,
            ),
            origin_key=entry.origin_key,
        )
        for name, entry in generated_inputs.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_input",
                subject_name=name,
                workflow_name=lowered.typed_workflow.definition.name,
            ),
            origin_key=entry.origin_key,
        )
        for name, entry in generated_internal_inputs.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_output",
                subject_name=name,
                workflow_name=lowered.typed_workflow.definition.name,
            ),
            origin_key=entry.origin_key,
        )
        for name, entry in generated_outputs.items()
    )
    bindings.extend(
        ValidationSubjectBinding(
            subject_ref=ValidationSubjectRef(
                subject_kind="generated_path",
                subject_name=name,
                workflow_name=lowered.typed_workflow.definition.name,
            ),
            origin_key=entry.origin_key,
        )
        for name, entry in generated_paths.items()
    )
    deduped: dict[tuple[str, str, str], ValidationSubjectBinding] = {}
    for binding in bindings:
        key = (
            binding.subject_ref.subject_kind,
            binding.subject_ref.subject_name,
            binding.origin_key,
        )
        deduped.setdefault(key, binding)
    ordered = sorted(
        deduped.values(),
        key=lambda binding: (
            binding.subject_ref.subject_kind,
            binding.subject_ref.subject_name,
            binding.origin_key,
        ),
    )
    return tuple(ordered)


def _required_validation_subject_keys(
    workflow: WorkflowSourceMap,
) -> set[tuple[str, str, str]]:
    required = {
        ("workflow", workflow.workflow_name, workflow.workflow_name),
    }
    required.update(
        ("step_id", name, workflow.workflow_name)
        for name in workflow.step_ids
    )
    required.update(
        ("generated_input", name, workflow.workflow_name)
        for name in workflow.generated_inputs
    )
    required.update(
        ("generated_input", name, workflow.workflow_name)
        for name in workflow.generated_internal_inputs
    )
    required.update(
        ("generated_output", name, workflow.workflow_name)
        for name in workflow.generated_outputs
    )
    required.update(
        ("generated_path", name, workflow.workflow_name)
        for name in workflow.generated_paths
    )
    return required


def _validation_subject_key(
    subject_ref: ValidationSubjectRef,
    workflow_name: str,
) -> tuple[str, str, str]:
    return (
        subject_ref.subject_kind,
        subject_ref.subject_name,
        subject_ref.workflow_name or workflow_name,
    )


def _executable_nodes_for_workflow(
    *,
    workflow_name: str,
    workflow_origin: SourceMapEntry,
    step_ids: Mapping[str, SourceMapEntry],
    validated_bundle,
) -> tuple[ExecutableNodeLineage, ...]:
    if validated_bundle is None:
        return ()
    entries: list[ExecutableNodeLineage] = []
    for node in validated_bundle.ir.nodes.values():
        if not isinstance(node, ExecutableNodeBase):
            continue
        origin = _origin_for_node(node, step_ids=step_ids, workflow_origin=workflow_origin)
        entries.append(
            ExecutableNodeLineage(
                node_id=node.node_id,
                step_id=node.step_id,
                kind=node.kind.value,
                region=node.region.value,
                origin_key=origin.origin_key,
                presentation_name=node.presentation_name,
            )
        )
    entries.sort(key=lambda entry: entry.node_id)
    return tuple(entries)


def _core_nodes_for_workflow(
    *,
    lowered: "LoweredWorkflow",
    workflow_origin: SourceMapEntry,
    step_ids: Mapping[str, SourceMapEntry],
    validated_bundle,
) -> tuple[CoreNodeLineage, ...]:
    if validated_bundle is None:
        return _core_nodes_from_authored_mapping(
            lowered=lowered,
            workflow_origin=workflow_origin,
            step_ids=step_ids,
        )
    core_workflow_ast = getattr(validated_bundle, "core_workflow_ast", None)
    if not isinstance(core_workflow_ast, CoreWorkflowAST):
        return _core_nodes_from_authored_mapping(
            lowered=lowered,
            workflow_origin=workflow_origin,
            step_ids=step_ids,
        )
    entries: list[CoreNodeLineage] = []
    for statement in _iter_core_statements(core_workflow_ast):
        meta = getattr(statement, "meta", None)
        if meta is None:
            continue
        origin = _origin_for_core_statement(
            statement,
            step_ids=step_ids,
            workflow_origin=workflow_origin,
        )
        entries.append(
            CoreNodeLineage(
                statement_id=meta.id,
                step_id=origin.generated_name_origin or meta.step_id,
                step_kind=meta.step_kind,
                origin_key=origin.origin_key,
            )
        )
    entries.sort(key=lambda entry: entry.statement_id)
    return tuple(entries)


def _core_nodes_from_authored_mapping(
    *,
    lowered: "LoweredWorkflow",
    workflow_origin: SourceMapEntry,
    step_ids: Mapping[str, SourceMapEntry],
) -> tuple[CoreNodeLineage, ...]:
    entries: list[CoreNodeLineage] = []
    for step in _walk_steps(lowered.authored_mapping.get("steps")):
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id:
            continue
        origin = _lookup_step_origin(step_id, step_ids=step_ids) or workflow_origin
        entries.append(
            CoreNodeLineage(
                statement_id=step_id,
                step_id=origin.generated_name_origin or step_id,
                step_kind=_step_kind_from_mapping(step),
                origin_key=origin.origin_key,
            )
        )
    entries.sort(key=lambda entry: entry.statement_id)
    return tuple(entries)


def _origin_for_node(
    node: ExecutableNodeBase,
    *,
    step_ids: Mapping[str, SourceMapEntry],
    workflow_origin: SourceMapEntry,
) -> SourceMapEntry:
    candidates = [
        node.node_id,
        node.step_id,
        node.presentation_name,
        _strip_root_prefix(node.node_id),
        _strip_root_prefix(node.step_id),
        _strip_root_prefix(node.presentation_name),
    ]
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        matched = _lookup_step_origin(candidate, step_ids=step_ids)
        if matched is not None:
            return matched
    return workflow_origin


def _origin_for_core_statement(
    statement: Any,
    *,
    step_ids: Mapping[str, SourceMapEntry],
    workflow_origin: SourceMapEntry,
) -> SourceMapEntry:
    meta = getattr(statement, "meta", None)
    if meta is None:
        return workflow_origin
    candidates = [
        meta.step_id,
        meta.id,
        meta.id.split(".")[-1],
    ]
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        matched = _lookup_step_origin(candidate, step_ids=step_ids)
        if matched is not None:
            return matched
    if isinstance(meta.origin_key, str) and meta.origin_key:
        for entry in step_ids.values():
            if entry.origin_key == meta.origin_key:
                return entry
        if workflow_origin.origin_key == meta.origin_key:
            return workflow_origin
    return workflow_origin


def _lookup_step_origin(
    candidate: str,
    *,
    step_ids: Mapping[str, SourceMapEntry],
) -> SourceMapEntry | None:
    current = candidate
    while current:
        matched = step_ids.get(current)
        if matched is not None:
            return matched
        if "." not in current:
            return None
        current = current.rsplit(".", 1)[0]
    return None


def _strip_root_prefix(value: str) -> str:
    return value.removeprefix("root.") if value.startswith("root.") else value


def _step_kind_from_mapping(step: Mapping[str, Any]) -> str:
    for key in (
        "command",
        "provider",
        "adjudicated_provider",
        "resource_transition",
        "wait_for",
        "assert",
        "set_scalar",
        "increment_scalar",
        "materialize_artifacts",
        "materialize_view",
        "select_variant_output",
        "call",
        "if",
        "match",
        "for_each",
        "repeat_until",
    ):
        if key in step:
            return key
    return "step"


def _iter_core_statements(core_workflow_ast: CoreWorkflowAST) -> Iterable[Any]:
    yield from _iter_nested_core_statements(core_workflow_ast.body)
    if core_workflow_ast.finalization is not None:
        yield from _iter_nested_core_statements(core_workflow_ast.finalization.statements)


def _iter_nested_core_statements(statements: Sequence[Any]) -> Iterable[Any]:
    for statement in statements:
        yield statement
        if isinstance(statement, CoreIf):
            yield from _iter_nested_core_statements(statement.then_branch.statements)
            if statement.else_branch is not None:
                yield from _iter_nested_core_statements(statement.else_branch.statements)
        elif isinstance(statement, CoreMatch):
            for case in statement.cases.values():
                yield from _iter_nested_core_statements(case.statements)
        elif isinstance(statement, CoreForEach):
            yield from _iter_nested_core_statements(statement.statements)
        elif isinstance(statement, CoreRepeatUntil):
            yield from _iter_nested_core_statements(statement.statements)


def _walk_steps(raw_steps: Any) -> Iterable[Mapping[str, Any]]:
    if not isinstance(raw_steps, list):
        return ()
    steps: list[Mapping[str, Any]] = []
    for step in raw_steps:
        if not isinstance(step, Mapping):
            continue
        steps.append(step)
        match = step.get("match")
        if isinstance(match, Mapping):
            for case in (match.get("cases") or {}).values():
                if isinstance(case, Mapping):
                    steps.extend(_walk_steps(case.get("steps")))
        repeat = step.get("repeat_until")
        if isinstance(repeat, Mapping):
            steps.extend(_walk_steps(repeat.get("steps")))
        branch = step.get("if")
        if isinstance(branch, Mapping):
            steps.extend(_walk_steps(branch.get("then")))
            steps.extend(_walk_steps(branch.get("else")))
        for_each = step.get("for_each")
        if isinstance(for_each, Mapping):
            steps.extend(_walk_steps(for_each.get("steps")))
    return tuple(steps)


def _diagnostic_for_entry(
    entry: SourceMapEntry,
    *,
    code: str,
    message: str,
) -> LispFrontendDiagnostic:
    return LispFrontendDiagnostic(
        code=code,
        message=message,
        span=SourceSpan(
            start=SourcePosition(
                path=entry.path,
                line=entry.line,
                column=entry.column,
                offset=0,
            ),
            end=SourcePosition(
                path=entry.path,
                line=entry.end_line,
                column=entry.end_column,
                offset=0,
            ),
        ),
        phase="lowering",
        form_path=entry.form_path,
        expansion_stack=entry.expansion_stack,
        notes=entry.notes,
    )
