"""Shared semantic workflow IR derived from validated workflow bundle surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError

from .core_ast import (
    CoreForEach,
    CoreIf,
    CoreMatch,
    CoreRepeatUntil,
    CoreWorkflowAST,
    _surface_step_from_core_statement,
)
from .executable_ir import ExecutableWorkflow
from .runtime_plan import WorkflowRuntimePlan
from .state_projection import WorkflowStateProjection
from .surface_ast import SurfaceStep, SurfaceStepKind, SurfaceWorkflow, WorkflowProvenance, empty_frozen_mapping


WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION = "workflow_semantic_ir.v1"
_PROMOTED_ADAPTER_EFFECT_KINDS = frozenset({"resource_transition", "ledger_update"})
_PROMOTED_GENERATED_EFFECT_KINDS = frozenset({"snapshot_capture", "pointer_materialization"})


@dataclass(frozen=True)
class SemanticExecutableBridge:
    workflow_name: str
    node_ids: tuple[str, ...]
    presentation_keys: tuple[str, ...]
    resume_checkpoint_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticStatement:
    statement_id: str
    workflow_name: str
    step_id: str
    step_name: str
    step_kind: str
    executable_node_ids: tuple[str, ...] = ()
    presentation_keys: tuple[str, ...] = ()
    ref_ids: tuple[str, ...] = ()
    effect_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticTypeEntry:
    type_id: str
    workflow_name: str
    type_kind: str | None
    value_type: str | None
    definition: Mapping[str, Any]


@dataclass(frozen=True)
class SemanticContractEntry:
    contract_id: str
    workflow_name: str
    contract_name: str
    type_id: str
    contract_kind: str | None
    value_type: str | None
    definition: Mapping[str, Any]
    source_kind: str


@dataclass(frozen=True)
class SemanticRefEntry:
    ref_id: str
    workflow_name: str
    ref_kind: str
    subject_name: str
    contract_id: str | None = None
    statement_id: str | None = None
    target: str | None = None


@dataclass(frozen=True)
class SemanticEffectEntry:
    effect_id: str
    workflow_name: str
    statement_id: str
    effect_kind: str
    boundary_kind: str | None = None
    boundary_name: str | None = None
    call_target: str | None = None
    output_validation_surface: str | None = None
    source_map_behavior: str | None = None
    ref_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SemanticProofEntry:
    proof_id: str
    workflow_name: str
    proof_kind: str
    statement_id: str | None = None
    ref_ids: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SemanticStateLayoutEntry:
    layout_id: str
    workflow_name: str
    layout_kind: str
    node_id: str | None = None
    presentation_key: str | None = None
    details: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SemanticSourceMapBridgeEntry:
    bridge_id: str
    workflow_name: str
    bridge_kind: str
    subject_ref: ValidationSubjectRef | None = None
    origin_key: str | None = None
    coverage: str | None = None


@dataclass(frozen=True)
class SemanticCallEdge:
    edge_id: str
    workflow_name: str
    statement_id: str
    call_alias: str
    target_workflow_name: str | None = None


@dataclass(frozen=True)
class SemanticPromptSurface:
    prompt_surface_id: str
    workflow_name: str
    statement_id: str
    provider_name: str | None
    input_file: Any = None
    asset_file: Any = None
    prompt_consumes: tuple[Any, ...] = ()
    inject_output_contract: bool | None = None
    inject_consumes: bool | None = None


@dataclass(frozen=True)
class SemanticCommandBoundary:
    boundary_id: str
    workflow_name: str
    statement_id: str
    step_id: str
    boundary_kind: str
    boundary_name: str | None = None
    output_validation_surface: str | None = None
    source_map_behavior: str | None = None


@dataclass(frozen=True)
class SemanticWorkflow:
    workflow_name: str
    input_contract_ids: Mapping[str, str]
    output_contract_ids: Mapping[str, str]
    artifact_contract_ids: Mapping[str, str]
    authored_statement_ids: tuple[str, ...]
    statements: Mapping[str, SemanticStatement]
    call_edge_ids: tuple[str, ...] = ()
    prompt_surface_ids: tuple[str, ...] = ()
    command_boundary_ids: tuple[str, ...] = ()
    publication_ref_ids: tuple[str, ...] = ()
    executable_bridge: SemanticExecutableBridge = field(
        default_factory=lambda: SemanticExecutableBridge(workflow_name="", node_ids=(), presentation_keys=())
    )


@dataclass(frozen=True)
class SemanticWorkflowIR:
    schema_version: str
    workflows: Mapping[str, SemanticWorkflow]
    types: Mapping[str, SemanticTypeEntry]
    contracts: Mapping[str, SemanticContractEntry]
    refs: Mapping[str, SemanticRefEntry]
    effects: Mapping[str, SemanticEffectEntry]
    proofs: Mapping[str, SemanticProofEntry]
    state_layout: Mapping[str, SemanticStateLayoutEntry]
    source_map: Mapping[str, SemanticSourceMapBridgeEntry]
    call_edges: Mapping[str, SemanticCallEdge] = field(default_factory=empty_frozen_mapping)
    prompt_surfaces: Mapping[str, SemanticPromptSurface] = field(default_factory=empty_frozen_mapping)
    command_boundaries: Mapping[str, SemanticCommandBoundary] = field(default_factory=empty_frozen_mapping)


def derive_workflow_semantic_ir(
    *,
    core_workflow_ast: CoreWorkflowAST | None = None,
    surface: SurfaceWorkflow,
    ir: ExecutableWorkflow,
    projection: WorkflowStateProjection,
    runtime_plan: WorkflowRuntimePlan,
    imports: Mapping[str, Any],
    provenance: WorkflowProvenance,
) -> SemanticWorkflowIR:
    workflow_name = (
        core_workflow_ast.workflow_name
        if core_workflow_ast is not None
        else (surface.name or "")
    )
    input_catalog = core_workflow_ast.inputs if core_workflow_ast is not None else surface.inputs
    output_catalog = core_workflow_ast.outputs if core_workflow_ast is not None else surface.outputs
    artifact_catalog = core_workflow_ast.artifacts if core_workflow_ast is not None else surface.artifacts
    import_catalog = core_workflow_ast.imports if core_workflow_ast is not None else surface.imports
    statement_order: list[str] = []
    statements: dict[str, SemanticStatement] = {}
    surface_steps_by_step_id: dict[str, SurfaceStep] = {}
    statement_ids_by_step_id: dict[str, str] = {}
    statement_effect_ids_by_statement_id: dict[str, list[str]] = {}
    types: dict[str, SemanticTypeEntry] = {}
    contracts: dict[str, SemanticContractEntry] = {}
    refs: dict[str, SemanticRefEntry] = {}
    effects: dict[str, SemanticEffectEntry] = {}
    proofs: dict[str, SemanticProofEntry] = {}
    state_layout: dict[str, SemanticStateLayoutEntry] = {}
    source_map: dict[str, SemanticSourceMapBridgeEntry] = {}
    call_edges: dict[str, SemanticCallEdge] = {}
    prompt_surfaces: dict[str, SemanticPromptSurface] = {}
    command_boundaries: dict[str, SemanticCommandBoundary] = {}

    node_order = list(runtime_plan.ordered_node_ids)
    node_order.extend(sorted(set(runtime_plan.nodes) - set(node_order)))
    workflow_bridge = SemanticExecutableBridge(
        workflow_name=workflow_name,
        node_ids=tuple(node_order),
        presentation_keys=tuple(
            _dedupe(
                runtime_plan.nodes[node_id].presentation_key
                for node_id in node_order
                if node_id in runtime_plan.nodes
            )
        ),
        resume_checkpoint_ids=tuple(
            _resume_checkpoint_id(workflow_name, checkpoint)
            for checkpoint in runtime_plan.resume_checkpoints
        ),
    )

    for source_kind, catalog in (
        ("input", input_catalog),
        ("output", output_catalog),
        ("artifact", artifact_catalog),
    ):
        for name, contract in sorted(catalog.items()):
            contract_id = _contract_id(workflow_name, source_kind, name)
            type_id = _type_id(workflow_name, source_kind, name)
            types[type_id] = SemanticTypeEntry(
                type_id=type_id,
                workflow_name=workflow_name,
                type_kind=contract.kind,
                value_type=contract.value_type,
                definition=contract.definition,
            )
            contracts[contract_id] = SemanticContractEntry(
                contract_id=contract_id,
                workflow_name=workflow_name,
                contract_name=name,
                type_id=type_id,
                contract_kind=contract.kind,
                value_type=contract.value_type,
                definition=contract.definition,
                source_kind=source_kind,
            )
            refs[_ref_id(workflow_name, source_kind, name)] = SemanticRefEntry(
                ref_id=_ref_id(workflow_name, source_kind, name),
                workflow_name=workflow_name,
                ref_kind=f"workflow_{source_kind}",
                subject_name=name,
                contract_id=contract_id,
            )

    grouped_nodes = _statement_node_groups(runtime_plan)
    for statement_surface in _iter_semantic_statements(core_workflow_ast, surface):
        step = statement_surface.surface_step
        statement_id = _statement_id(workflow_name, statement_surface.surface_step_id)
        statement_order.append(statement_id)
        for alias in _step_id_aliases(statement_surface.surface_step_id):
            surface_steps_by_step_id.setdefault(alias, step)
            statement_ids_by_step_id.setdefault(alias, statement_id)
        statement_node_ids = tuple(grouped_nodes.get(statement_surface.surface_step_id, ()))
        statement_presentation_keys = tuple(
            _dedupe(
                runtime_plan.nodes[node_id].presentation_key
                for node_id in statement_node_ids
                if node_id in runtime_plan.nodes
            )
        )
        statement_effect_ids: list[str] = []
        statement_ref_id = _ref_id(workflow_name, "statement", statement_surface.surface_step_id)
        refs[statement_ref_id] = SemanticRefEntry(
            ref_id=statement_ref_id,
            workflow_name=workflow_name,
            ref_kind="statement",
            subject_name=statement_surface.surface_step_id,
            statement_id=statement_id,
            target=statement_surface.step_kind,
        )

        if step.kind is SurfaceStepKind.CALL:
            edge_id = _call_edge_id(workflow_name, statement_surface.surface_step_id)
            imported = imports.get(step.call_alias or "")
            imported_metadata = import_catalog.get(step.call_alias or "")
            call_edges[edge_id] = SemanticCallEdge(
                edge_id=edge_id,
                workflow_name=workflow_name,
                statement_id=statement_id,
                call_alias=step.call_alias or "",
                target_workflow_name=(
                    imported.surface.name
                    if imported is not None
                    else (
                        imported_metadata.workflow_name
                        if imported_metadata is not None
                        else step.call_alias
                    )
                ),
            )
            effect_id = _effect_id(workflow_name, statement_surface.surface_step_id, "workflow_call")
            effects[effect_id] = SemanticEffectEntry(
                effect_id=effect_id,
                workflow_name=workflow_name,
                statement_id=statement_id,
                effect_kind="workflow_call",
                call_target=step.call_alias,
            )
            statement_effect_ids.append(effect_id)

        if step.kind is SurfaceStepKind.PROVIDER:
            prompt_surface_id = _prompt_surface_id(workflow_name, statement_surface.surface_step_id)
            prompt_surfaces[prompt_surface_id] = SemanticPromptSurface(
                prompt_surface_id=prompt_surface_id,
                workflow_name=workflow_name,
                statement_id=statement_id,
                provider_name=step.provider,
                input_file=step.input_file,
                asset_file=step.asset_file,
                prompt_consumes=step.prompt_consumes or (),
                inject_output_contract=step.inject_output_contract,
                inject_consumes=step.inject_consumes,
            )
            effect_id = _effect_id(workflow_name, statement_surface.surface_step_id, "provider_call")
            effects[effect_id] = SemanticEffectEntry(
                effect_id=effect_id,
                workflow_name=workflow_name,
                statement_id=statement_id,
                effect_kind="provider_call",
                output_validation_surface=_output_validation_surface(step),
            )
            statement_effect_ids.append(effect_id)

        if step.kind is SurfaceStepKind.COMMAND:
            boundary_kind, boundary_name = _command_boundary_identity(
                step,
                grouped_nodes.get(statement_surface.surface_step_id, ()),
                runtime_plan,
            )
            boundary_id = _command_boundary_id(workflow_name, statement_surface.surface_step_id)
            command_boundaries[boundary_id] = SemanticCommandBoundary(
                boundary_id=boundary_id,
                workflow_name=workflow_name,
                statement_id=statement_id,
                step_id=statement_surface.surface_step_id,
                boundary_kind=boundary_kind,
                boundary_name=boundary_name,
                output_validation_surface=_output_validation_surface(step),
            )
            effect_id = _effect_id(workflow_name, statement_surface.surface_step_id, "command_call")
            effects[effect_id] = SemanticEffectEntry(
                effect_id=effect_id,
                workflow_name=workflow_name,
                statement_id=statement_id,
                effect_kind="command_call",
                boundary_kind=boundary_kind,
                boundary_name=boundary_name,
                output_validation_surface=_output_validation_surface(step),
            )
            statement_effect_ids.append(effect_id)

        if step.common.requires_variant is not None or step.common.variant_output is not None:
            proof_id = _proof_id(workflow_name, statement_surface.surface_step_id)
            proofs[proof_id] = SemanticProofEntry(
                proof_id=proof_id,
                workflow_name=workflow_name,
                proof_kind="variant_surface",
                statement_id=statement_id,
                details=MappingProxyType(
                    {
                        "requires_variant": step.common.requires_variant,
                        "variant_output": step.common.variant_output,
                    }
                ),
            )

        statements[statement_id] = SemanticStatement(
            statement_id=statement_id,
            workflow_name=workflow_name,
            step_id=statement_surface.step_id,
            step_name=step.name,
            step_kind=statement_surface.step_kind,
            executable_node_ids=statement_node_ids,
            presentation_keys=statement_presentation_keys,
            ref_ids=(statement_ref_id,),
            effect_ids=tuple(statement_effect_ids),
        )
        statement_effect_ids_by_statement_id[statement_id] = statement_effect_ids

    for alias, metadata in sorted(import_catalog.items()):
        ref_id = _ref_id(workflow_name, "import", alias)
        refs[ref_id] = SemanticRefEntry(
            ref_id=ref_id,
            workflow_name=workflow_name,
            ref_kind="import_alias",
            subject_name=alias,
            target=metadata.workflow_name or str(metadata.workflow_path),
        )

    publication_ref_ids: list[str] = []
    for artifact_plan in runtime_plan.artifacts:
        step_id = runtime_plan.nodes.get(artifact_plan.source_node_id).step_id if artifact_plan.source_node_id in runtime_plan.nodes else None
        statement_id = _statement_id(workflow_name, step_id) if isinstance(step_id, str) else None
        ref_id = _ref_id(workflow_name, "publication", artifact_plan.plan_key)
        refs[ref_id] = SemanticRefEntry(
            ref_id=ref_id,
            workflow_name=workflow_name,
            ref_kind="publication_plan",
            subject_name=artifact_plan.contract_name,
            contract_id=(
                _contract_id(workflow_name, "artifact", artifact_plan.contract_name)
                if artifact_plan.contract_name in artifact_catalog
                else None
            ),
            statement_id=statement_id,
            target=artifact_plan.publication_mode,
        )
        publication_ref_ids.append(ref_id)

    for node_id, node in sorted(runtime_plan.nodes.items()):
        state_layout[_state_layout_id(workflow_name, "presentation", node_id)] = SemanticStateLayoutEntry(
            layout_id=_state_layout_id(workflow_name, "presentation", node_id),
            workflow_name=workflow_name,
            layout_kind="presentation_key",
            node_id=node_id,
            presentation_key=node.presentation_key,
            details=MappingProxyType({"region": node.region, "kind": node.kind}),
        )
    for checkpoint in runtime_plan.resume_checkpoints:
        checkpoint_layout_id = _resume_checkpoint_id(workflow_name, checkpoint)
        state_layout[checkpoint_layout_id] = SemanticStateLayoutEntry(
            layout_id=checkpoint_layout_id,
            workflow_name=workflow_name,
            layout_kind="resume_checkpoint",
            node_id=checkpoint.node_id,
            presentation_key=checkpoint.presentation_key,
            details=MappingProxyType({"checkpoint_kind": checkpoint.checkpoint_kind}),
        )
    for input_name in provenance.managed_write_root_inputs:
        state_layout[_state_layout_id(workflow_name, "managed_write_root_input", input_name)] = SemanticStateLayoutEntry(
            layout_id=_state_layout_id(workflow_name, "managed_write_root_input", input_name),
            workflow_name=workflow_name,
            layout_kind="managed_write_root_input",
            details=MappingProxyType({"input_name": input_name}),
        )
    for input_name in provenance.runtime_context_inputs:
        state_layout[_state_layout_id(workflow_name, "runtime_context_input", input_name)] = SemanticStateLayoutEntry(
            layout_id=_state_layout_id(workflow_name, "runtime_context_input", input_name),
            workflow_name=workflow_name,
            layout_kind="runtime_context_input",
            details=MappingProxyType({"input_name": input_name}),
        )

    if provenance.frontend_source_map_coverage is not None:
        for key, value in sorted(provenance.frontend_source_map_coverage.items()):
            source_map[_source_map_id(workflow_name, "coverage", key)] = SemanticSourceMapBridgeEntry(
                bridge_id=_source_map_id(workflow_name, "coverage", key),
                workflow_name=workflow_name,
                bridge_kind="coverage",
                origin_key=key,
                coverage=value,
            )
    if isinstance(provenance.frontend_source_trace_path, Path) and provenance.frontend_source_trace_path.exists():
        workflow_payload = _load_frontend_source_map_workflow_payload(
            workflow_name,
            provenance.frontend_source_trace_path,
        )
        if workflow_payload is not None:
            source_map.update(_frontend_source_map_bridges_from_payload(workflow_name, workflow_payload))
            _promote_frontend_source_map_effects(
                workflow_name=workflow_name,
                workflow_payload=workflow_payload,
                statements=statements,
                surface_steps_by_step_id=surface_steps_by_step_id,
                statement_ids_by_step_id=statement_ids_by_step_id,
                statement_effect_ids_by_statement_id=statement_effect_ids_by_statement_id,
                effects=effects,
            )
            for statement_id, effect_ids in statement_effect_ids_by_statement_id.items():
                statements[statement_id] = replace(
                    statements[statement_id],
                    effect_ids=tuple(effect_ids),
                )

    semantic_ir = SemanticWorkflowIR(
        schema_version=WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION,
        workflows=MappingProxyType(
            {
                workflow_name: SemanticWorkflow(
                    workflow_name=workflow_name,
                    input_contract_ids=MappingProxyType({
                        name: _contract_id(workflow_name, "input", name)
                        for name in sorted(input_catalog)
                    }),
                    output_contract_ids=MappingProxyType({
                        name: _contract_id(workflow_name, "output", name)
                        for name in sorted(output_catalog)
                    }),
                    artifact_contract_ids=MappingProxyType({
                        name: _contract_id(workflow_name, "artifact", name)
                        for name in sorted(artifact_catalog)
                    }),
                    authored_statement_ids=tuple(statement_order),
                    statements=MappingProxyType(statements),
                    call_edge_ids=tuple(sorted(call_edges)),
                    prompt_surface_ids=tuple(sorted(prompt_surfaces)),
                    command_boundary_ids=tuple(sorted(command_boundaries)),
                    publication_ref_ids=tuple(publication_ref_ids),
                    executable_bridge=workflow_bridge,
                )
            }
        ),
        types=MappingProxyType(types),
        contracts=MappingProxyType(contracts),
        refs=MappingProxyType(refs),
        effects=MappingProxyType(effects),
        proofs=MappingProxyType(proofs),
        state_layout=MappingProxyType(state_layout),
        source_map=MappingProxyType(source_map),
        call_edges=MappingProxyType(call_edges),
        prompt_surfaces=MappingProxyType(prompt_surfaces),
        command_boundaries=MappingProxyType(command_boundaries),
    )
    validate_workflow_semantic_ir(
        semantic_ir,
        ir=ir,
        projection=projection,
        runtime_plan=runtime_plan,
    )
    return semantic_ir


def validate_workflow_semantic_ir(
    semantic_ir: SemanticWorkflowIR,
    *,
    ir: ExecutableWorkflow,
    projection: WorkflowStateProjection,
    runtime_plan: WorkflowRuntimePlan,
) -> None:
    workflow_name = ir.name or ""
    workflow = semantic_ir.workflows.get(workflow_name)

    if semantic_ir.schema_version != WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: unsupported semantic IR schema `{semantic_ir.schema_version}`",
            workflow_name=workflow_name,
        )
    if workflow is None:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: missing workflow entry `{workflow_name}`",
            workflow_name=workflow_name,
            subject_refs=(ValidationSubjectRef(subject_kind="workflow", subject_name=workflow_name),),
        )
    runtime_snapshot_operations = _runtime_snapshot_operations_by_step_id(runtime_plan)

    if len(set(workflow.authored_statement_ids)) != len(workflow.authored_statement_ids):
        _raise_semantic_ir_invalid(
            "semantic_ir_invalid: authored statement ids must be unique",
            workflow_name=workflow_name,
        )
    if set(workflow.statements) != set(workflow.authored_statement_ids):
        _raise_semantic_ir_invalid(
            "semantic_ir_invalid: workflow statement catalog must exactly match authored statement ids",
            workflow_name=workflow_name,
        )
    for edge_id in workflow.call_edge_ids:
        if edge_id not in semantic_ir.call_edges:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: missing call-edge catalog entry `{edge_id}`",
                workflow_name=workflow_name,
            )
    for prompt_surface_id in workflow.prompt_surface_ids:
        if prompt_surface_id not in semantic_ir.prompt_surfaces:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: missing prompt-surface catalog entry `{prompt_surface_id}`",
                workflow_name=workflow_name,
            )
    for command_boundary_id in workflow.command_boundary_ids:
        if command_boundary_id not in semantic_ir.command_boundaries:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: missing command-boundary catalog entry `{command_boundary_id}`",
                workflow_name=workflow_name,
            )
    for publication_ref_id in workflow.publication_ref_ids:
        publication_ref = semantic_ir.refs.get(publication_ref_id)
        if publication_ref is None or publication_ref.ref_kind != "publication_plan":
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: missing publication-plan ref `{publication_ref_id}`",
                workflow_name=workflow_name,
            )
    for input_name, contract_id in workflow.input_contract_ids.items():
        _validate_workflow_contract_binding(
            semantic_ir,
            workflow_name=workflow_name,
            subject_name=input_name,
            subject_kind="input",
            contract_id=contract_id,
        )
    for output_name, contract_id in workflow.output_contract_ids.items():
        _validate_workflow_contract_binding(
            semantic_ir,
            workflow_name=workflow_name,
            subject_name=output_name,
            subject_kind="output",
            contract_id=contract_id,
        )
    for artifact_name, contract_id in workflow.artifact_contract_ids.items():
        _validate_workflow_contract_binding(
            semantic_ir,
            workflow_name=workflow_name,
            subject_name=artifact_name,
            subject_kind="artifact",
            contract_id=contract_id,
        )

    expected_node_ids = set(ir.nodes)
    actual_node_ids = set(workflow.executable_bridge.node_ids)
    if actual_node_ids != expected_node_ids:
        missing_node_id = next(iter(sorted(expected_node_ids - actual_node_ids)), None)
        _raise_semantic_ir_invalid(
            "semantic_ir_invalid: executable bridge must cover every executable node id exactly once",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_node(workflow_name, missing_node_id, runtime_plan),
        )

    expected_presentation_keys = {node.presentation_key for node in runtime_plan.nodes.values()}
    actual_presentation_keys = set(workflow.executable_bridge.presentation_keys)
    if actual_presentation_keys != expected_presentation_keys:
        missing_key = next(iter(sorted(expected_presentation_keys - actual_presentation_keys)), None)
        _raise_semantic_ir_invalid(
            "semantic_ir_invalid: executable bridge must cover every runtime presentation key exactly once",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_presentation_key(workflow_name, missing_key, projection),
        )
    expected_checkpoints = {
        _resume_checkpoint_id(workflow_name, checkpoint): checkpoint
        for checkpoint in runtime_plan.resume_checkpoints
    }
    actual_checkpoint_ids = tuple(workflow.executable_bridge.resume_checkpoint_ids)
    if len(actual_checkpoint_ids) != len(expected_checkpoints) or set(actual_checkpoint_ids) != set(expected_checkpoints):
        unexpected_checkpoint_id = next(iter(sorted(set(actual_checkpoint_ids) - set(expected_checkpoints))), None)
        missing_checkpoint_id = next(iter(sorted(set(expected_checkpoints) - set(actual_checkpoint_ids))), None)
        checkpoint_id = unexpected_checkpoint_id or missing_checkpoint_id
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: executable bridge references unknown resume checkpoint `{checkpoint_id}`",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_checkpoint_id(
                workflow_name,
                expected_checkpoints,
                missing_checkpoint_id,
                projection,
                runtime_plan,
            ),
        )

    for statement in workflow.statements.values():
        unknown_nodes = [node_id for node_id in statement.executable_node_ids if node_id not in expected_node_ids]
        if unknown_nodes:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: statement `{statement.step_id}` references unknown executable node `{unknown_nodes[0]}`",
                workflow_name=workflow_name,
                subject_refs=(
                    ValidationSubjectRef(
                        subject_kind="step_id",
                        subject_name=statement.step_id,
                        workflow_name=workflow_name,
                    ),
                ),
            )
        if any(node_id not in workflow.executable_bridge.node_ids for node_id in statement.executable_node_ids):
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: statement `{statement.step_id}` references an executable node outside the workflow bridge",
                workflow_name=workflow_name,
                subject_refs=(
                    ValidationSubjectRef(
                        subject_kind="step_id",
                        subject_name=statement.step_id,
                        workflow_name=workflow_name,
                    ),
                ),
            )
        for ref_id in statement.ref_ids:
            ref = semantic_ir.refs.get(ref_id)
            if ref is None:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: statement `{statement.step_id}` references missing ref `{ref_id}`",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_statement(workflow_name, statement),
                )
        for effect_id in statement.effect_ids:
            effect = semantic_ir.effects.get(effect_id)
            if effect is None:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: statement `{statement.step_id}` references missing effect `{effect_id}`",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_statement(workflow_name, statement),
                )
            if effect.statement_id != statement.statement_id:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: effect `{effect_id}` is bound to the wrong statement",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_statement(workflow_name, statement),
                )

    for effect in semantic_ir.effects.values():
        if effect.statement_id not in workflow.statements:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: effect `{effect.effect_id}` references unknown statement `{effect.statement_id}`",
                workflow_name=workflow_name,
            )
        for ref_id in effect.ref_ids:
            ref = semantic_ir.refs.get(ref_id)
            if ref is None:
                step_id = workflow.statements[effect.statement_id].step_id
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: effect `{effect.effect_id}` references missing ref `{ref_id}`",
                    workflow_name=workflow_name,
                    subject_refs=(
                        ValidationSubjectRef(
                            subject_kind="step_id",
                            subject_name=step_id,
                            workflow_name=workflow_name,
                        ),
                    ),
                )

        if effect.boundary_kind == "certified_adapter" and not effect.boundary_name:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: certified adapter effect `{effect.effect_id}` requires a declared adapter name",
                workflow_name=workflow_name,
                subject_refs=(
                    ValidationSubjectRef(
                        subject_kind="step_id",
                        subject_name=workflow.statements[effect.statement_id].step_id,
                        workflow_name=workflow_name,
                    ),
                ),
            )
        if effect.effect_kind in _PROMOTED_ADAPTER_EFFECT_KINDS:
            _validate_promoted_adapter_effect(
                semantic_ir,
                workflow=workflow,
                workflow_name=workflow_name,
                effect=effect,
            )
        elif effect.effect_kind == "snapshot_capture":
            _validate_snapshot_capture_effect(
                workflow=workflow,
                workflow_name=workflow_name,
                effect=effect,
                runtime_snapshot_operations=runtime_snapshot_operations,
            )
        elif effect.effect_kind == "pointer_materialization":
            _validate_pointer_materialization_effect(
                workflow=workflow,
                workflow_name=workflow_name,
                effect=effect,
                runtime_snapshot_operations=runtime_snapshot_operations,
            )

    for proof in semantic_ir.proofs.values():
        if proof.statement_id is not None and proof.statement_id not in workflow.statements:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: proof `{proof.proof_id}` references unknown statement `{proof.statement_id}`",
                workflow_name=workflow_name,
            )
        for ref_id in proof.ref_ids:
            ref = semantic_ir.refs.get(ref_id)
            if ref is None:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: proof `{proof.proof_id}` references missing ref `{ref_id}`",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_statement_id(workflow_name, proof.statement_id, workflow),
                )

    state_layout_by_checkpoint = {
        layout.layout_id: layout
        for layout in semantic_ir.state_layout.values()
        if layout.layout_kind == "resume_checkpoint"
    }
    if len(state_layout_by_checkpoint) != len(expected_checkpoints) or set(state_layout_by_checkpoint) != set(expected_checkpoints):
        unexpected_checkpoint_id = next(iter(sorted(set(state_layout_by_checkpoint) - set(expected_checkpoints))), None)
        missing_checkpoint_id = next(iter(sorted(set(expected_checkpoints) - set(state_layout_by_checkpoint))), None)
        checkpoint_id = unexpected_checkpoint_id or missing_checkpoint_id
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: resume-checkpoint layout references unknown checkpoint `{checkpoint_id}`",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_layout_checkpoint(
                workflow_name,
                state_layout_by_checkpoint.get(unexpected_checkpoint_id),
                missing_checkpoint_id,
                expected_checkpoints,
                projection,
                runtime_plan,
            ),
        )
    for layout in semantic_ir.state_layout.values():
        if layout.layout_kind == "presentation_key":
            if layout.node_id not in runtime_plan.nodes:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: presentation layout `{layout.layout_id}` references unknown node `{layout.node_id}`",
                    workflow_name=workflow_name,
                )
            if layout.presentation_key != runtime_plan.nodes[layout.node_id].presentation_key:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: presentation layout `{layout.layout_id}` references inconsistent presentation key",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_node(workflow_name, layout.node_id, runtime_plan),
                )
        if layout.layout_kind == "resume_checkpoint":
            expected_checkpoint = expected_checkpoints.get(layout.layout_id)
            if expected_checkpoint is None:
                continue
            if layout.node_id != expected_checkpoint.node_id:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: resume-checkpoint layout `{layout.layout_id}` references inconsistent node `{layout.node_id}`",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_checkpoint_id(
                        workflow_name,
                        expected_checkpoints,
                        layout.layout_id,
                        projection,
                        runtime_plan,
                    ),
                )
            if layout.presentation_key != expected_checkpoint.presentation_key:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: resume-checkpoint layout `{layout.layout_id}` references inconsistent presentation key",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_checkpoint_id(
                        workflow_name,
                        expected_checkpoints,
                        layout.layout_id,
                        projection,
                        runtime_plan,
                    ),
                )
            checkpoint_kind = layout.details.get("checkpoint_kind") if isinstance(layout.details, Mapping) else None
            if checkpoint_kind != expected_checkpoint.checkpoint_kind:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: resume-checkpoint layout `{layout.layout_id}` references inconsistent checkpoint kind",
                    workflow_name=workflow_name,
                    subject_refs=_subject_refs_for_checkpoint_id(
                        workflow_name,
                        expected_checkpoints,
                        layout.layout_id,
                        projection,
                        runtime_plan,
                    ),
                )
        if layout.layout_kind == "managed_write_root_input":
            input_name = layout.details.get("input_name") if isinstance(layout.details, Mapping) else None
            if not isinstance(input_name, str) or input_name not in workflow.input_contract_ids:
                _raise_semantic_ir_invalid(
                    f"semantic_ir_invalid: managed-write-root layout `{layout.layout_id}` references unknown input `{input_name}`",
                    workflow_name=workflow_name,
                )


def workflow_semantic_ir_to_json(semantic_ir: SemanticWorkflowIR) -> dict[str, Any]:
    return _json_value(semantic_ir)


def _iter_surface_steps(surface: SurfaceWorkflow) -> tuple[SurfaceStep, ...]:
    steps: list[SurfaceStep] = []

    def visit(items: tuple[SurfaceStep, ...]) -> None:
        for step in items:
            steps.append(step)
            if step.then_branch is not None:
                visit(step.then_branch.steps)
            if step.else_branch is not None:
                visit(step.else_branch.steps)
            for case in step.match_cases.values():
                visit(case.steps)
            if step.for_each_steps:
                visit(step.for_each_steps)
            if step.repeat_until is not None:
                visit(step.repeat_until.steps)

    visit(surface.steps)
    if surface.finalization is not None:
        visit(surface.finalization.steps)
    return tuple(steps)


@dataclass(frozen=True)
class _SemanticStatementSurface:
    step_id: str
    surface_step_id: str
    step_kind: str
    surface_step: SurfaceStep


def _iter_semantic_statements(
    core_workflow_ast: CoreWorkflowAST | None,
    surface: SurfaceWorkflow,
) -> tuple[_SemanticStatementSurface, ...]:
    if core_workflow_ast is None:
        return tuple(
            _SemanticStatementSurface(
                step_id=step.step_id,
                surface_step_id=step.step_id,
                step_kind=step.kind.value,
                surface_step=step,
            )
            for step in _iter_surface_steps(surface)
        )

    statements: list[_SemanticStatementSurface] = []

    def visit(items: tuple[Any, ...]) -> None:
        for statement in items:
            meta = getattr(statement, "meta", None)
            if meta is not None:
                surface_step = _surface_step_from_core_statement(statement)
                statements.append(
                    _SemanticStatementSurface(
                        step_id=surface_step.step_id,
                        surface_step_id=surface_step.step_id,
                        step_kind=meta.step_kind,
                        surface_step=surface_step,
                    )
                )
            if isinstance(statement, CoreIf):
                visit(statement.then_branch.statements)
                if statement.else_branch is not None:
                    visit(statement.else_branch.statements)
            elif isinstance(statement, CoreMatch):
                for case in statement.cases.values():
                    visit(case.statements)
            elif isinstance(statement, CoreForEach):
                visit(statement.statements)
            elif isinstance(statement, CoreRepeatUntil):
                visit(statement.statements)

    visit(core_workflow_ast.body)
    if core_workflow_ast.finalization is not None:
        visit(core_workflow_ast.finalization.statements)
    return tuple(statements)


def _statement_node_groups(runtime_plan: WorkflowRuntimePlan) -> Mapping[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for node_id, node in runtime_plan.nodes.items():
        grouped.setdefault(node.step_id, []).append(node_id)
    order = {node_id: index for index, node_id in enumerate(runtime_plan.ordered_node_ids)}
    return {
        step_id: tuple(sorted(node_ids, key=lambda node_id: (order.get(node_id, len(order)), node_id)))
        for step_id, node_ids in grouped.items()
    }


def _dedupe(values: Any) -> tuple[Any, ...]:
    seen: list[Any] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return tuple(seen)


def _command_boundary_identity(
    step: SurfaceStep,
    node_ids: tuple[str, ...],
    runtime_plan: WorkflowRuntimePlan,
) -> tuple[str, str | None]:
    for node_id in node_ids:
        node = runtime_plan.nodes.get(node_id)
        if node is None:
            continue
        if node.command_boundary_kind:
            return node.command_boundary_kind, node.command_boundary_name
    return "external_tool", step.name


def _output_validation_surface(step: SurfaceStep) -> str | None:
    if step.common.variant_output is not None:
        return "variant_output"
    if step.common.output_bundle is not None:
        return "output_bundle"
    if step.common.expected_outputs:
        return "expected_outputs"
    return None


def _step_id_aliases(step_id: str) -> tuple[str, ...]:
    aliases = [step_id]
    leaf = step_id.split(".")[-1]
    if leaf not in aliases:
        aliases.append(leaf)
    return tuple(aliases)


def _load_frontend_source_map_workflow_payload(
    workflow_name: str,
    source_map_path: Path,
) -> Mapping[str, Any] | None:
    try:
        payload = json.loads(source_map_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    workflows = payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return None
    workflow_payload = workflows.get(workflow_name)
    if not isinstance(workflow_payload, Mapping):
        return None
    return workflow_payload


def _load_frontend_source_map_bridges(
    workflow_name: str,
    source_map_path: Path,
) -> dict[str, SemanticSourceMapBridgeEntry]:
    workflow_payload = _load_frontend_source_map_workflow_payload(workflow_name, source_map_path)
    if workflow_payload is None:
        return {}
    return _frontend_source_map_bridges_from_payload(workflow_name, workflow_payload)


def _frontend_source_map_bridges_from_payload(
    workflow_name: str,
    workflow_payload: Mapping[str, Any],
) -> dict[str, SemanticSourceMapBridgeEntry]:
    origin_keys = _source_map_origin_keys(workflow_payload)
    supported_subject_keys = _supported_source_map_subject_keys(workflow_name, workflow_payload)
    validation_subjects = workflow_payload.get("validation_subjects")
    if not isinstance(validation_subjects, list):
        return {}

    bridges: dict[str, SemanticSourceMapBridgeEntry] = {}
    for binding in validation_subjects:
        if not isinstance(binding, Mapping):
            continue
        subject_ref = binding.get("subject_ref")
        origin_key = binding.get("origin_key")
        if not isinstance(subject_ref, Mapping):
            continue
        subject_kind = subject_ref.get("subject_kind")
        subject_name = subject_ref.get("subject_name")
        if not isinstance(subject_kind, str) or not isinstance(subject_name, str):
            continue
        ref = ValidationSubjectRef(
            subject_kind=subject_kind,
            subject_name=subject_name,
            workflow_name=subject_ref.get("workflow_name")
            if isinstance(subject_ref.get("workflow_name"), str)
            else workflow_name,
        )
        if not isinstance(origin_key, str) or origin_key not in origin_keys:
            _raise_semantic_ir_invalid(
                "semantic_ir_invalid: source-map validation subject does not resolve to a declared source-map origin",
                workflow_name=workflow_name,
                subject_refs=(ref,),
            )
        if _validation_subject_key(ref, workflow_name) not in supported_subject_keys:
            _raise_semantic_ir_invalid(
                (
                    "semantic_ir_invalid: source-map validation subject "
                    f"`{subject_kind}:{subject_name}` references unsupported source-map subject"
                ),
                workflow_name=workflow_name,
                subject_refs=(ref,),
            )
        bridge_id = _source_map_id(workflow_name, subject_kind, subject_name)
        bridges[bridge_id] = SemanticSourceMapBridgeEntry(
            bridge_id=bridge_id,
            workflow_name=workflow_name,
            bridge_kind="validation_subject",
            subject_ref=ref,
            origin_key=origin_key,
        )
    return bridges


def _promote_frontend_source_map_effects(
    *,
    workflow_name: str,
    workflow_payload: Mapping[str, Any],
    statements: Mapping[str, SemanticStatement],
    surface_steps_by_step_id: Mapping[str, SurfaceStep],
    statement_ids_by_step_id: Mapping[str, str],
    statement_effect_ids_by_statement_id: Mapping[str, list[str]],
    effects: dict[str, SemanticEffectEntry],
) -> None:
    origin_keys = _source_map_origin_keys(workflow_payload)
    _promote_frontend_command_boundary_effects(
        workflow_name=workflow_name,
        workflow_payload=workflow_payload,
        origin_keys=origin_keys,
        statements=statements,
        surface_steps_by_step_id=surface_steps_by_step_id,
        statement_ids_by_step_id=statement_ids_by_step_id,
        statement_effect_ids_by_statement_id=statement_effect_ids_by_statement_id,
        effects=effects,
    )
    _promote_frontend_generated_semantic_effects(
        workflow_name=workflow_name,
        workflow_payload=workflow_payload,
        origin_keys=origin_keys,
        statements=statements,
        surface_steps_by_step_id=surface_steps_by_step_id,
        statement_ids_by_step_id=statement_ids_by_step_id,
        statement_effect_ids_by_statement_id=statement_effect_ids_by_statement_id,
        effects=effects,
    )


def _promote_frontend_command_boundary_effects(
    *,
    workflow_name: str,
    workflow_payload: Mapping[str, Any],
    origin_keys: set[str],
    statements: Mapping[str, SemanticStatement],
    surface_steps_by_step_id: Mapping[str, SurfaceStep],
    statement_ids_by_step_id: Mapping[str, str],
    statement_effect_ids_by_statement_id: Mapping[str, list[str]],
    effects: dict[str, SemanticEffectEntry],
) -> None:
    command_boundaries = workflow_payload.get("command_boundaries")
    if not isinstance(command_boundaries, list):
        return
    for boundary in command_boundaries:
        if not isinstance(boundary, Mapping):
            continue
        if boundary.get("boundary_kind") != "certified_adapter":
            continue
        declared_effects = tuple(
            effect_kind
            for effect_kind in boundary.get("declared_effects", ())
            if isinstance(effect_kind, str) and effect_kind in _PROMOTED_ADAPTER_EFFECT_KINDS
        )
        if not declared_effects:
            continue
        step_id = boundary.get("step_id")
        if not isinstance(step_id, str):
            continue
        origin_key = boundary.get("origin_key")
        statement_id = statement_ids_by_step_id.get(step_id)
        statement = statements.get(statement_id) if statement_id is not None else None
        if statement is None:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted certified-adapter effect references unknown statement `{step_id}`",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_frontend_step_id(
                    workflow_name,
                    step_id,
                    statements,
                    statement_ids_by_step_id,
                ),
            )
        if isinstance(origin_key, str) and origin_key not in origin_keys:
            _raise_semantic_ir_invalid(
                "semantic_ir_invalid: promoted certified-adapter effect does not resolve to a declared source-map origin",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        command_effect = _command_call_effect_for_statement(
            statement=statement,
            statement_effect_ids=statement_effect_ids_by_statement_id[statement.statement_id],
            effects=effects,
        )
        if command_effect is None or command_effect.boundary_kind != "certified_adapter":
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted certified-adapter effect for `{statement.step_id}` requires a matching generic command-call effect",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        surface_step = _surface_step_for_statement(statement, surface_steps_by_step_id)
        adapter_payload = _resource_transition_payload_for_step(
            workflow_name=workflow_name,
            statement=statement,
            surface_step=surface_step,
        )
        boundary_name = boundary.get("adapter_name") or boundary.get("command_name")
        if not isinstance(boundary_name, str) or not boundary_name:
            boundary_name = command_effect.boundary_name
        if not isinstance(boundary_name, str) or not boundary_name:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted certified-adapter effect for `{statement.step_id}` requires a boundary name",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        for effect_kind in declared_effects:
            details = _promoted_adapter_effect_details(
                workflow_name=workflow_name,
                statement=statement,
                effect_kind=effect_kind,
                adapter_payload=adapter_payload,
            )
            effect_id = _effect_id(workflow_name, statement.step_id, effect_kind)
            effects[effect_id] = SemanticEffectEntry(
                effect_id=effect_id,
                workflow_name=workflow_name,
                statement_id=statement.statement_id,
                effect_kind=effect_kind,
                boundary_kind="certified_adapter",
                boundary_name=boundary_name,
                details=details,
            )
            statement_effect_ids_by_statement_id[statement.statement_id].append(effect_id)


def _promote_frontend_generated_semantic_effects(
    *,
    workflow_name: str,
    workflow_payload: Mapping[str, Any],
    origin_keys: set[str],
    statements: Mapping[str, SemanticStatement],
    surface_steps_by_step_id: Mapping[str, SurfaceStep],
    statement_ids_by_step_id: Mapping[str, str],
    statement_effect_ids_by_statement_id: Mapping[str, list[str]],
    effects: dict[str, SemanticEffectEntry],
) -> None:
    generated_effects = workflow_payload.get("generated_semantic_effects")
    if not isinstance(generated_effects, list):
        return
    counts: dict[tuple[str, str], int] = {}
    for entry in generated_effects:
        if not isinstance(entry, Mapping):
            continue
        step_id = entry.get("step_id")
        effect_kind = entry.get("effect_kind")
        if isinstance(step_id, str) and isinstance(effect_kind, str) and effect_kind in _PROMOTED_GENERATED_EFFECT_KINDS:
            counts[(step_id, effect_kind)] = counts.get((step_id, effect_kind), 0) + 1
    for entry in generated_effects:
        if not isinstance(entry, Mapping):
            continue
        effect_kind = entry.get("effect_kind")
        if effect_kind not in _PROMOTED_GENERATED_EFFECT_KINDS:
            continue
        step_id = entry.get("step_id")
        effect_key = entry.get("effect_key")
        origin_key = entry.get("origin_key")
        details = entry.get("details")
        if not isinstance(step_id, str) or not isinstance(effect_key, str) or not isinstance(details, Mapping):
            continue
        statement_id = statement_ids_by_step_id.get(step_id)
        statement = statements.get(statement_id) if statement_id is not None else None
        if statement is None:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted effect references unknown statement `{step_id}`",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_frontend_step_id(
                    workflow_name,
                    step_id,
                    statements,
                    statement_ids_by_step_id,
                ),
            )
        if not isinstance(origin_key, str) or origin_key not in origin_keys:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted effect `{effect_key}` does not resolve to a declared source-map origin",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        surface_step = _surface_step_for_statement(statement, surface_steps_by_step_id)
        promoted_details = _generated_promoted_effect_details(
            workflow_name=workflow_name,
            statement=statement,
            surface_step=surface_step,
            effect_kind=effect_kind,
            effect_key=effect_key,
            details=details,
        )
        base_effect_id = _effect_id(workflow_name, statement.step_id, effect_kind)
        effect_id = (
            f"{base_effect_id}:{effect_key}"
            if counts.get((step_id, effect_kind), 0) > 1
            else base_effect_id
        )
        effects[effect_id] = SemanticEffectEntry(
            effect_id=effect_id,
            workflow_name=workflow_name,
            statement_id=statement.statement_id,
            effect_kind=effect_kind,
            details=promoted_details,
        )
        statement_effect_ids_by_statement_id[statement.statement_id].append(effect_id)


def _subject_refs_for_frontend_step_id(
    workflow_name: str,
    frontend_step_id: str,
    statements: Mapping[str, SemanticStatement],
    statement_ids_by_step_id: Mapping[str, str],
) -> tuple[ValidationSubjectRef, ...]:
    statement_id = statement_ids_by_step_id.get(frontend_step_id)
    if statement_id is None:
        return (
            ValidationSubjectRef(
                subject_kind="step_id",
                subject_name=frontend_step_id,
                workflow_name=workflow_name,
            ),
        )
    statement = statements.get(statement_id)
    if statement is None:
        return ()
    return _subject_refs_for_statement(workflow_name, statement)


def _surface_step_for_statement(
    statement: SemanticStatement,
    surface_steps_by_step_id: Mapping[str, SurfaceStep],
) -> SurfaceStep:
    step = surface_steps_by_step_id.get(statement.step_id)
    if step is not None:
        return step
    step = surface_steps_by_step_id.get(statement.step_id.split(".")[-1])
    if step is not None:
        return step
    raise AssertionError(f"missing surface step for statement {statement.statement_id}")


def _command_call_effect_for_statement(
    *,
    statement: SemanticStatement,
    statement_effect_ids: list[str],
    effects: Mapping[str, SemanticEffectEntry],
) -> SemanticEffectEntry | None:
    for effect_id in statement_effect_ids:
        effect = effects.get(effect_id)
        if effect is None:
            continue
        if effect.statement_id == statement.statement_id and effect.effect_kind == "command_call":
            return effect
    return None


def _resource_transition_payload_for_step(
    *,
    workflow_name: str,
    statement: SemanticStatement,
    surface_step: SurfaceStep,
) -> Mapping[str, Any]:
    command = surface_step.command
    if not isinstance(command, tuple) or len(command) < 4:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted certified-adapter effect for `{statement.step_id}` requires a structured adapter payload",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    payload_text = command[3]
    if not isinstance(payload_text, str):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted certified-adapter effect for `{statement.step_id}` requires a JSON adapter payload",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as error:
        _raise_semantic_ir_invalid(
            (
                "semantic_ir_invalid: promoted certified-adapter effect "
                f"for `{statement.step_id}` has an invalid JSON adapter payload: {error.msg}"
            ),
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if not isinstance(payload, Mapping):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted certified-adapter effect for `{statement.step_id}` requires an object payload",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    return payload


def _promoted_adapter_effect_details(
    *,
    workflow_name: str,
    statement: SemanticStatement,
    effect_kind: str,
    adapter_payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if effect_kind == "resource_transition":
        from_queue = adapter_payload.get("from")
        to_queue = adapter_payload.get("to")
        if not isinstance(from_queue, str) or not isinstance(to_queue, str):
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted resource-transition effect for `{statement.step_id}` requires `from` and `to` strings",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        return MappingProxyType({"from_queue": from_queue, "to_queue": to_queue})
    event_name = adapter_payload.get("event")
    if not isinstance(event_name, str):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted ledger-update effect for `{statement.step_id}` requires an `event` string",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    return MappingProxyType({"event_name": event_name})


def _generated_promoted_effect_details(
    *,
    workflow_name: str,
    statement: SemanticStatement,
    surface_step: SurfaceStep,
    effect_kind: str,
    effect_key: str,
    details: Mapping[str, Any],
) -> Mapping[str, Any]:
    if effect_kind == "snapshot_capture":
        pre_snapshot = surface_step.common.pre_snapshot
        if not isinstance(pre_snapshot, Mapping):
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted effect `{effect_key}` requires a matching pre_snapshot surface",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        snapshot_kind = details.get("snapshot_kind")
        candidate_names = details.get("candidate_names")
        candidates = pre_snapshot.get("candidates")
        if not isinstance(snapshot_kind, str) or not isinstance(candidate_names, (list, tuple)):
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted effect `{effect_key}` requires snapshot details",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        expected_snapshot_kind = pre_snapshot.get("name")
        if not isinstance(expected_snapshot_kind, str) or snapshot_kind != expected_snapshot_kind:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted effect `{effect_key}` has inconsistent snapshot lineage",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        normalized_candidate_names = tuple(name for name in candidate_names if isinstance(name, str))
        expected_candidate_names = (
            tuple(str(name) for name in candidates.keys())
            if isinstance(candidates, Mapping)
            else ()
        )
        if normalized_candidate_names != expected_candidate_names:
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted effect `{effect_key}` has inconsistent snapshot candidates",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
        return MappingProxyType(
            {
                "snapshot_kind": snapshot_kind,
                "candidate_names": normalized_candidate_names,
            }
        )

    if surface_step.kind is not SurfaceStepKind.MATERIALIZE_ARTIFACTS:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect_key}` requires a materialize_artifacts surface",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    pointer_path = details.get("pointer_path")
    representation_role = details.get("representation_role")
    value_name = details.get("value_name")
    if not isinstance(pointer_path, str) or not isinstance(representation_role, str):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect_key}` requires pointer details",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    values = surface_step.materialize_artifacts.get("values", ())
    pointer_matches = [
        value
        for value in values
        if isinstance(value, Mapping)
        and isinstance(value.get("pointer"), Mapping)
        and value["pointer"].get("path") == pointer_path
    ]
    if not pointer_matches:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect_key}` has no matching pointer surface",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if isinstance(value_name, str) and all(value.get("name") != value_name for value in pointer_matches):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect_key}` has inconsistent pointer lineage",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    return MappingProxyType(
        {
            "pointer_path": pointer_path,
            "representation_role": representation_role,
        }
    )


def _subject_refs_for_node(
    workflow_name: str,
    node_id: str | None,
    runtime_plan: WorkflowRuntimePlan,
) -> tuple[ValidationSubjectRef, ...]:
    if node_id is None:
        return ()
    node = runtime_plan.nodes.get(node_id)
    if node is None:
        return ()
    return (
        ValidationSubjectRef(
            subject_kind="step_id",
            subject_name=node.step_id,
            workflow_name=workflow_name,
        ),
    )


def _subject_refs_for_presentation_key(
    workflow_name: str,
    presentation_key: str | None,
    projection: WorkflowStateProjection,
) -> tuple[ValidationSubjectRef, ...]:
    if presentation_key is None:
        return ()
    for node_id, key in projection.presentation_key_by_node_id.items():
        if key != presentation_key:
            continue
        entry = projection.entries_by_node_id.get(node_id)
        if entry is None:
            break
        return (
            ValidationSubjectRef(
                subject_kind="step_id",
                subject_name=entry.step_id,
                workflow_name=workflow_name,
            ),
        )
    return ()


def _validate_workflow_contract_binding(
    semantic_ir: SemanticWorkflowIR,
    *,
    workflow_name: str,
    subject_name: str,
    subject_kind: str,
    contract_id: str,
) -> None:
    contract = semantic_ir.contracts.get(contract_id)
    if contract is None or contract.source_kind != subject_kind:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: {subject_kind} contract `{subject_name}` references missing contract `{contract_id}`",
            workflow_name=workflow_name,
            subject_refs=(
                ValidationSubjectRef(
                    subject_kind="workflow",
                    subject_name=workflow_name,
                    workflow_name=workflow_name,
                ),
            ),
        )
    if contract.type_id not in semantic_ir.types:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: contract `{contract_id}` references missing type `{contract.type_id}`",
            workflow_name=workflow_name,
        )


def _subject_refs_for_statement(
    workflow_name: str,
    statement: SemanticStatement,
) -> tuple[ValidationSubjectRef, ...]:
    return (
        ValidationSubjectRef(
            subject_kind="step_id",
            subject_name=statement.step_id,
            workflow_name=workflow_name,
        ),
    )


def _runtime_snapshot_operations_by_step_id(
    runtime_plan: WorkflowRuntimePlan,
) -> Mapping[str, tuple[str, ...]]:
    operations: dict[str, list[str]] = {}
    for snapshot in runtime_plan.snapshots:
        node = runtime_plan.nodes.get(snapshot.owner_node_id)
        if node is None:
            continue
        operations.setdefault(node.step_id, []).append(snapshot.operation_kind)
    return {
        step_id: tuple(operation_kinds)
        for step_id, operation_kinds in operations.items()
    }


def _validate_promoted_adapter_effect(
    semantic_ir: SemanticWorkflowIR,
    *,
    workflow: SemanticWorkflow,
    workflow_name: str,
    effect: SemanticEffectEntry,
) -> None:
    statement = workflow.statements[effect.statement_id]
    if effect.boundary_kind != "certified_adapter" or not effect.boundary_name:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted adapter effect `{effect.effect_id}` must reference a certified adapter boundary",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    command_effect = next(
        (
            semantic_ir.effects[effect_id]
            for effect_id in statement.effect_ids
            if effect_id in semantic_ir.effects
            and semantic_ir.effects[effect_id].effect_kind == "command_call"
        ),
        None,
    )
    if (
        command_effect is None
        or command_effect.boundary_kind != "certified_adapter"
        or command_effect.statement_id != statement.statement_id
    ):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted adapter effect `{effect.effect_id}` requires a matching command-call effect",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if effect.effect_kind == "resource_transition":
        if not (
            isinstance(effect.details.get("from_queue"), str)
            and isinstance(effect.details.get("to_queue"), str)
        ):
            _raise_semantic_ir_invalid(
                f"semantic_ir_invalid: promoted adapter effect `{effect.effect_id}` requires resource-transition details",
                workflow_name=workflow_name,
                subject_refs=_subject_refs_for_statement(workflow_name, statement),
            )
    if effect.effect_kind == "ledger_update" and not isinstance(effect.details.get("event_name"), str):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted adapter effect `{effect.effect_id}` requires ledger-update details",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )


def _validate_snapshot_capture_effect(
    *,
    workflow: SemanticWorkflow,
    workflow_name: str,
    effect: SemanticEffectEntry,
    runtime_snapshot_operations: Mapping[str, tuple[str, ...]],
) -> None:
    statement = workflow.statements[effect.statement_id]
    candidate_names = effect.details.get("candidate_names")
    if not isinstance(effect.details.get("snapshot_kind"), str) or not isinstance(candidate_names, (list, tuple)):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect.effect_id}` requires snapshot-capture details",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if any(not isinstance(name, str) for name in candidate_names):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect.effect_id}` requires string snapshot candidates",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if "pre_snapshot" not in runtime_snapshot_operations.get(statement.step_id, ()):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect.effect_id}` requires a matching pre_snapshot runtime surface",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )


def _validate_pointer_materialization_effect(
    *,
    workflow: SemanticWorkflow,
    workflow_name: str,
    effect: SemanticEffectEntry,
    runtime_snapshot_operations: Mapping[str, tuple[str, ...]],
) -> None:
    statement = workflow.statements[effect.statement_id]
    if statement.step_kind != SurfaceStepKind.MATERIALIZE_ARTIFACTS.value:
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect.effect_id}` requires a materialize-artifacts statement",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if not (
        isinstance(effect.details.get("pointer_path"), str)
        and isinstance(effect.details.get("representation_role"), str)
    ):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect.effect_id}` requires pointer-materialization details",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )
    if "materialize_artifacts" not in runtime_snapshot_operations.get(statement.step_id, ()):
        _raise_semantic_ir_invalid(
            f"semantic_ir_invalid: promoted effect `{effect.effect_id}` requires a matching materialize-artifacts runtime surface",
            workflow_name=workflow_name,
            subject_refs=_subject_refs_for_statement(workflow_name, statement),
        )


def _subject_refs_for_statement_id(
    workflow_name: str,
    statement_id: str | None,
    workflow: SemanticWorkflow,
) -> tuple[ValidationSubjectRef, ...]:
    if not isinstance(statement_id, str):
        return ()
    statement = workflow.statements.get(statement_id)
    if statement is None:
        return ()
    return _subject_refs_for_statement(workflow_name, statement)


def _subject_refs_for_layout_checkpoint(
    workflow_name: str,
    layout: SemanticStateLayoutEntry | None,
    missing_checkpoint_id: str | None,
    expected_checkpoints: Mapping[str, RuntimeResumeCheckpoint],
    projection: WorkflowStateProjection,
    runtime_plan: WorkflowRuntimePlan,
) -> tuple[ValidationSubjectRef, ...]:
    if layout is not None and isinstance(layout.presentation_key, str):
        subject_refs = _subject_refs_for_presentation_key(
            workflow_name,
            layout.presentation_key,
            projection,
        )
        if subject_refs:
            return subject_refs
    return _subject_refs_for_checkpoint_id(
        workflow_name,
        expected_checkpoints,
        missing_checkpoint_id,
        projection,
        runtime_plan,
    )


def _subject_refs_for_checkpoint_id(
    workflow_name: str,
    expected_checkpoints: Mapping[str, RuntimeResumeCheckpoint],
    checkpoint_id: str | None,
    projection: WorkflowStateProjection,
    runtime_plan: WorkflowRuntimePlan,
) -> tuple[ValidationSubjectRef, ...]:
    if not isinstance(checkpoint_id, str):
        return ()
    checkpoint = expected_checkpoints.get(checkpoint_id)
    if checkpoint is not None:
        subject_refs = _subject_refs_for_presentation_key(
            workflow_name,
            checkpoint.presentation_key,
            projection,
        )
        if subject_refs:
            return subject_refs
        return _subject_refs_for_node(workflow_name, checkpoint.node_id, runtime_plan)
    return ()


def _source_map_origin_keys(workflow_payload: Mapping[str, Any]) -> set[str]:
    origin_keys: set[str] = set()
    workflow_origin = workflow_payload.get("workflow_origin")
    if isinstance(workflow_origin, Mapping):
        origin_key = workflow_origin.get("origin_key")
        if isinstance(origin_key, str):
            origin_keys.add(origin_key)
    for section_name in (
        "step_ids",
        "generated_inputs",
        "generated_outputs",
        "generated_paths",
        "generated_internal_inputs",
    ):
        section = workflow_payload.get(section_name)
        if not isinstance(section, Mapping):
            continue
        for entry in section.values():
            if not isinstance(entry, Mapping):
                continue
            origin_key = entry.get("origin_key")
            if isinstance(origin_key, str):
                origin_keys.add(origin_key)
    return origin_keys


def _supported_source_map_subject_keys(
    workflow_name: str,
    workflow_payload: Mapping[str, Any],
) -> set[tuple[str, str, str]]:
    supported = {("workflow", workflow_name, workflow_name)}
    supported.update(
        ("step_id", name, workflow_name)
        for name in _mapping_string_keys(workflow_payload.get("step_ids"))
    )
    supported.update(
        ("generated_input", name, workflow_name)
        for name in _mapping_string_keys(workflow_payload.get("generated_inputs"))
    )
    supported.update(
        ("generated_input", name, workflow_name)
        for name in _mapping_string_keys(workflow_payload.get("generated_internal_inputs"))
    )
    supported.update(
        ("generated_output", name, workflow_name)
        for name in _mapping_string_keys(workflow_payload.get("generated_outputs"))
    )
    supported.update(
        ("generated_path", name, workflow_name)
        for name in _mapping_string_keys(workflow_payload.get("generated_paths"))
    )
    return supported


def _mapping_string_keys(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    return tuple(key for key in value if isinstance(key, str))


def _validation_subject_key(
    subject_ref: ValidationSubjectRef,
    workflow_name: str,
) -> tuple[str, str, str]:
    return (
        subject_ref.subject_kind,
        subject_ref.subject_name,
        subject_ref.workflow_name or workflow_name,
    )


def _raise_semantic_ir_invalid(
    message: str,
    *,
    workflow_name: str,
    subject_refs: tuple[ValidationSubjectRef, ...] = (),
) -> None:
    raise WorkflowValidationError(
        [
            ValidationError(
                message=message,
                subject_refs=subject_refs or (
                    ValidationSubjectRef(
                        subject_kind="workflow",
                        subject_name=workflow_name,
                        workflow_name=workflow_name or None,
                    ),
                ),
            )
        ]
    )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    return value


def _statement_id(workflow_name: str, step_id: str) -> str:
    return f"statement:{workflow_name}:{step_id}"


def _type_id(workflow_name: str, source_kind: str, name: str) -> str:
    return f"type:{workflow_name}:{source_kind}:{name}"


def _contract_id(workflow_name: str, source_kind: str, name: str) -> str:
    return f"contract:{workflow_name}:{source_kind}:{name}"


def _ref_id(workflow_name: str, ref_kind: str, name: str) -> str:
    return f"ref:{workflow_name}:{ref_kind}:{name}"


def _effect_id(workflow_name: str, step_id: str, effect_kind: str) -> str:
    return f"effect:{workflow_name}:{step_id}:{effect_kind}"


def _proof_id(workflow_name: str, step_id: str) -> str:
    return f"proof:{workflow_name}:{step_id}"


def _state_layout_id(workflow_name: str, layout_kind: str, name: str) -> str:
    return f"state:{workflow_name}:{layout_kind}:{name}"


def _resume_checkpoint_id(
    workflow_name: str,
    checkpoint: RuntimeResumeCheckpoint,
) -> str:
    parts = [
        checkpoint.checkpoint_kind,
        checkpoint.node_id,
        checkpoint.runtime_step_id_mode,
    ]
    if checkpoint.iteration_owner_node_id is not None:
        parts.append(checkpoint.iteration_owner_node_id)
    if checkpoint.iteration_step_id_suffix is not None:
        parts.append(checkpoint.iteration_step_id_suffix)
    return _state_layout_id(
        workflow_name,
        "checkpoint",
        "::".join(parts),
    )


def _source_map_id(workflow_name: str, bridge_kind: str, name: str) -> str:
    return f"source_map:{workflow_name}:{bridge_kind}:{name}"


def _call_edge_id(workflow_name: str, step_id: str) -> str:
    return f"call:{workflow_name}:{step_id}"


def _prompt_surface_id(workflow_name: str, step_id: str) -> str:
    return f"prompt:{workflow_name}:{step_id}"


def _command_boundary_id(workflow_name: str, step_id: str) -> str:
    return f"command:{workflow_name}:{step_id}"
