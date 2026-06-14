"""Derived runtime-plan summaries for validated workflow bundles."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .executable_ir import (
    CallBoundaryNode,
    CommandStepConfig,
    ExecutableNode,
    ExecutableNodeKind,
    ExecutableWorkflow,
    ForEachNode,
    MaterializeArtifactsStepConfig,
    RepeatUntilFrameNode,
    SelectVariantOutputStepConfig,
    WorkflowRegion,
)
from .state_projection import WorkflowStateProjection
from .surface_ast import WorkflowProvenance, empty_frozen_mapping


WORKFLOW_RUNTIME_PLAN_SCHEMA_VERSION = "workflow_runtime_plan.v1"


@dataclass(frozen=True)
class RuntimePlanNode:
    """Runtime-facing summary for one executable node."""

    node_id: str
    step_id: str
    presentation_key: str
    display_name: str
    kind: str
    region: str
    execution_index: int | None
    lexical_scope: tuple[str, ...] = ()
    fallthrough_node_id: str | None = None
    routed_transfer_targets: Mapping[str, str] = field(default_factory=empty_frozen_mapping)
    dependency_node_ids: tuple[str, ...] = ()
    nested_body_node_ids: tuple[str, ...] = ()
    call_alias: str | None = None
    command_boundary_kind: str | None = None
    command_boundary_name: str | None = None


@dataclass(frozen=True)
class RuntimeArtifactPlan:
    """Publication-facing artifact or bundle field summary."""

    plan_key: str
    source_node_id: str
    contract_name: str
    contract_kind: str | None
    publication_mode: str


@dataclass(frozen=True)
class RuntimeSnapshotPlan:
    """Snapshot/materialization summary derived from executable config."""

    owner_node_id: str
    operation_kind: str
    related_surface: str | None = None
    selection_relevant: bool = False


@dataclass(frozen=True)
class RuntimeResumeCheckpoint:
    """Resume-facing checkpoint summary aligned to projection rules."""

    checkpoint_kind: str
    node_id: str
    step_id: str
    presentation_key: str
    runtime_step_id_mode: str
    iteration_owner_node_id: str | None = None
    iteration_step_id_suffix: str | None = None


@dataclass(frozen=True)
class RuntimeLexicalCheckpointPoint:
    """Future-restore checkpoint metadata derived from frontend lowering."""

    checkpoint_id: str
    program_point_id: str
    point_kind: str
    workflow_name: str
    step_id: str
    node_id: str
    presentation_key: str
    origin_key: str
    details: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class RuntimeObservabilityNode:
    """Compact per-node observability metadata."""

    node_id: str
    step_id: str
    presentation_key: str
    display_name: str
    kind: str
    region: str


@dataclass(frozen=True)
class RuntimeCommandBoundarySummary:
    """Runtime-visible command boundary hint."""

    node_id: str
    step_id: str
    boundary_kind: str
    boundary_name: str


@dataclass(frozen=True)
class RuntimeObservabilityPlan:
    """Observability-facing runtime metadata."""

    workflow_name: str
    top_level_ordered_node_ids: tuple[str, ...]
    has_compiled_frontend_lineage: bool = False
    nodes: Mapping[str, RuntimeObservabilityNode] = field(default_factory=empty_frozen_mapping)
    command_boundaries: tuple[RuntimeCommandBoundarySummary, ...] = ()


@dataclass(frozen=True)
class WorkflowRuntimePlan:
    """Derived runtime-facing plan over executable IR and projection."""

    schema_version: str
    workflow_name: str
    ordered_node_ids: tuple[str, ...]
    nodes: Mapping[str, RuntimePlanNode]
    artifacts: tuple[RuntimeArtifactPlan, ...]
    snapshots: tuple[RuntimeSnapshotPlan, ...]
    resume_checkpoints: tuple[RuntimeResumeCheckpoint, ...]
    observability: RuntimeObservabilityPlan
    lexical_checkpoint_points: tuple[RuntimeLexicalCheckpointPoint, ...] = ()


def derive_workflow_runtime_plan(
    ir: ExecutableWorkflow,
    projection: WorkflowStateProjection,
    provenance: WorkflowProvenance | None = None,
) -> WorkflowRuntimePlan:
    """Build one deterministic runtime-facing summary from validated runtime surfaces."""

    ordered_node_ids = projection.ordered_execution_node_ids()
    execution_indexes = {node_id: index for index, node_id in enumerate(ordered_node_ids)}
    dependencies = _derive_dependency_node_ids(ir, projection, ordered_node_ids)
    nodes = {
        node_id: _runtime_plan_node(
            ir.nodes[node_id],
            projection=projection,
            execution_index=execution_indexes.get(node_id),
            dependency_node_ids=dependencies.get(node_id, ()),
        )
        for node_id in ir.nodes
    }
    plan = WorkflowRuntimePlan(
        schema_version=WORKFLOW_RUNTIME_PLAN_SCHEMA_VERSION,
        workflow_name=ir.name or "",
        ordered_node_ids=ordered_node_ids,
        nodes=MappingProxyType(nodes),
        artifacts=_derive_artifact_plans(ir),
        snapshots=_derive_snapshot_plans(ir),
        resume_checkpoints=_derive_resume_checkpoints(ir, projection, ordered_node_ids),
        observability=_derive_observability_plan(
            workflow_name=ir.name or "",
            ordered_node_ids=ordered_node_ids,
            nodes=nodes,
        ),
        lexical_checkpoint_points=_derive_lexical_checkpoint_points(ir, provenance=provenance),
    )
    validate_workflow_runtime_plan(plan, ir, projection)
    return plan


def enrich_workflow_runtime_plan(
    plan: WorkflowRuntimePlan,
    *,
    command_boundary_metadata: Mapping[str, tuple[str, str]] | None = None,
    has_compiled_frontend_lineage: bool | None = None,
) -> WorkflowRuntimePlan:
    """Return one runtime plan with optional command-boundary and lineage hints."""

    metadata = command_boundary_metadata or {}
    updated_nodes: dict[str, RuntimePlanNode] = {}
    for node_id, node in plan.nodes.items():
        boundary = metadata.get(node.step_id)
        if boundary is None:
            updated_nodes[node_id] = node
            continue
        updated_nodes[node_id] = replace(
            node,
            command_boundary_kind=boundary[0],
            command_boundary_name=boundary[1],
        )

    observability_nodes = {
        node_id: RuntimeObservabilityNode(
            node_id=node.node_id,
            step_id=node.step_id,
            presentation_key=node.presentation_key,
            display_name=node.display_name,
            kind=node.kind,
            region=node.region,
        )
        for node_id, node in updated_nodes.items()
    }
    command_boundaries = tuple(
        RuntimeCommandBoundarySummary(
            node_id=node.node_id,
            step_id=node.step_id,
            boundary_kind=node.command_boundary_kind,
            boundary_name=node.command_boundary_name,
        )
        for node in updated_nodes.values()
        if isinstance(node.command_boundary_kind, str)
        and node.command_boundary_kind
        and isinstance(node.command_boundary_name, str)
        and node.command_boundary_name
    )
    observability = replace(
        plan.observability,
        has_compiled_frontend_lineage=(
            plan.observability.has_compiled_frontend_lineage
            if has_compiled_frontend_lineage is None
            else has_compiled_frontend_lineage
        ),
        nodes=MappingProxyType(observability_nodes),
        command_boundaries=command_boundaries,
    )
    return replace(
        plan,
        nodes=MappingProxyType(updated_nodes),
        observability=observability,
    )


def validate_workflow_runtime_plan(
    plan: WorkflowRuntimePlan,
    ir: ExecutableWorkflow,
    projection: WorkflowStateProjection,
) -> None:
    """Validate one derived runtime plan against its authoritative inputs."""

    if plan.schema_version != WORKFLOW_RUNTIME_PLAN_SCHEMA_VERSION:
        raise ValueError(f"Unsupported workflow runtime plan schema '{plan.schema_version}'")
    if plan.ordered_node_ids != projection.ordered_execution_node_ids():
        raise ValueError("Runtime plan ordering must exactly match projection ordering")

    node_ids = set(ir.nodes)
    ordered_node_ids = set(plan.ordered_node_ids)
    if set(plan.nodes) != node_ids:
        raise ValueError("Runtime plan nodes must cover every executable node id exactly once")
    if any(node_id not in node_ids for node_id in plan.ordered_node_ids):
        raise ValueError("Runtime plan ordering references unknown executable nodes")

    body_count = len(ir.body_region)
    seen_finalization = False
    for index, node_id in enumerate(plan.ordered_node_ids):
        if node_id in ir.finalization_region:
            seen_finalization = True
            if index < body_count:
                raise ValueError("Finalization nodes must appear only after body nodes")
        elif seen_finalization:
            raise ValueError("Body nodes cannot appear after finalization nodes")

    for node in plan.nodes.values():
        if any(dep not in node_ids for dep in node.dependency_node_ids):
            raise ValueError(f"Runtime plan node '{node.node_id}' references unknown dependencies")
        if any(nested_id not in node_ids for nested_id in node.nested_body_node_ids):
            raise ValueError(f"Runtime plan node '{node.node_id}' references unknown nested nodes")
        if node.fallthrough_node_id is not None and node.fallthrough_node_id not in node_ids:
            raise ValueError(f"Runtime plan node '{node.node_id}' references unknown fallthrough target")
        if any(target not in node_ids for target in node.routed_transfer_targets.values()):
            raise ValueError(f"Runtime plan node '{node.node_id}' references unknown routed transfer targets")
        if node.execution_index is not None and node.node_id not in ordered_node_ids:
            raise ValueError(f"Nested node '{node.node_id}' cannot claim a top-level execution index")

    for artifact in plan.artifacts:
        if artifact.source_node_id not in node_ids:
            raise ValueError(f"Artifact plan '{artifact.plan_key}' references unknown source node")

    for snapshot in plan.snapshots:
        if snapshot.owner_node_id not in node_ids:
            raise ValueError(f"Snapshot plan '{snapshot.operation_kind}' references unknown owner node")

    seen_checkpoints: set[tuple[str, str, str, str]] = set()
    for checkpoint in plan.resume_checkpoints:
        if checkpoint.node_id not in node_ids:
            raise ValueError(f"Checkpoint '{checkpoint.checkpoint_kind}' references unknown node")
        key = (
            checkpoint.checkpoint_kind,
            checkpoint.node_id,
            checkpoint.step_id,
            checkpoint.runtime_step_id_mode,
        )
        if key in seen_checkpoints:
            raise ValueError(f"Duplicate checkpoint tuple detected for '{checkpoint.node_id}'")
        seen_checkpoints.add(key)

    seen_lexical_checkpoint_ids: set[str] = set()
    seen_program_point_ids: set[str] = set()
    step_ids_by_node_id = {node.node_id: node.step_id for node in plan.nodes.values()}
    for checkpoint_point in plan.lexical_checkpoint_points:
        if checkpoint_point.node_id not in node_ids:
            raise ValueError(
                f"Lexical checkpoint point '{checkpoint_point.checkpoint_id}' references unknown node"
            )
        if step_ids_by_node_id[checkpoint_point.node_id] != checkpoint_point.step_id:
            raise ValueError(
                f"Lexical checkpoint point '{checkpoint_point.checkpoint_id}' does not match node step id"
            )
        if checkpoint_point.checkpoint_id in seen_lexical_checkpoint_ids:
            raise ValueError(f"Duplicate lexical checkpoint id '{checkpoint_point.checkpoint_id}'")
        if checkpoint_point.program_point_id in seen_program_point_ids:
            raise ValueError(f"Duplicate lexical program point id '{checkpoint_point.program_point_id}'")
        seen_lexical_checkpoint_ids.add(checkpoint_point.checkpoint_id)
        seen_program_point_ids.add(checkpoint_point.program_point_id)


def _runtime_plan_node(
    node: ExecutableNode,
    *,
    projection: WorkflowStateProjection,
    execution_index: int | None,
    dependency_node_ids: tuple[str, ...],
) -> RuntimePlanNode:
    entry = projection.entries_by_node_id.get(node.node_id)
    nested_body_node_ids = ()
    call_alias = None
    if isinstance(node, (ForEachNode, RepeatUntilFrameNode)):
        nested_body_node_ids = tuple(node.body_node_ids)
    if isinstance(node, CallBoundaryNode):
        call_alias = node.call_alias
    return RuntimePlanNode(
        node_id=node.node_id,
        step_id=node.step_id,
        presentation_key=(
            entry.presentation_key if entry is not None else node.presentation_name
        ),
        display_name=(
            entry.display_name if entry is not None else node.presentation_name
        ),
        kind=node.kind.value,
        region=node.region.value,
        execution_index=execution_index,
        lexical_scope=tuple(node.lexical_scope),
        fallthrough_node_id=node.fallthrough_node_id,
        routed_transfer_targets=MappingProxyType(
            {
                reason: transfer.target_node_id
                for reason, transfer in node.routed_transfers.items()
                if isinstance(transfer.target_node_id, str)
            }
        ),
        dependency_node_ids=dependency_node_ids,
        nested_body_node_ids=nested_body_node_ids,
        call_alias=call_alias,
    )


def _derive_dependency_node_ids(
    ir: ExecutableWorkflow,
    projection: WorkflowStateProjection,
    ordered_node_ids: tuple[str, ...],
) -> Mapping[str, tuple[str, ...]]:
    dependency_lists: dict[str, list[str]] = {node_id: [] for node_id in ir.nodes}

    def add_dependency(target_node_id: str | None, source_node_id: str | None) -> None:
        if not isinstance(target_node_id, str) or not isinstance(source_node_id, str):
            return
        if target_node_id not in dependency_lists or source_node_id not in dependency_lists:
            return
        bucket = dependency_lists[target_node_id]
        if source_node_id not in bucket:
            bucket.append(source_node_id)

    previous_top_level_node_id: str | None = None
    for node_id in ordered_node_ids:
        add_dependency(node_id, previous_top_level_node_id)
        previous_top_level_node_id = node_id

    for node in ir.nodes.values():
        add_dependency(node.fallthrough_node_id, node.node_id)
        for transfer in node.routed_transfers.values():
            add_dependency(transfer.target_node_id, node.node_id)
        if isinstance(node, (ForEachNode, RepeatUntilFrameNode)):
            add_dependency(node.body_entry_node_id, node.node_id)
            previous_nested_node_id: str | None = None
            for nested_node_id in node.body_node_ids:
                add_dependency(nested_node_id, previous_nested_node_id)
                previous_nested_node_id = nested_node_id
        if isinstance(node, CallBoundaryNode):
            call_boundary = projection.call_boundaries.get(node.node_id)
            if call_boundary is not None:
                add_dependency(node.node_id, call_boundary.iteration_owner_node_id)

    return MappingProxyType(
        {
            node_id: tuple(dependencies)
            for node_id, dependencies in dependency_lists.items()
        }
    )


def _derive_artifact_plans(ir: ExecutableWorkflow) -> tuple[RuntimeArtifactPlan, ...]:
    plans: list[RuntimeArtifactPlan] = []
    for node in ir.nodes.values():
        common = _step_common_config(node)
        if common is None:
            continue
        for item in common.publishes:
            if not isinstance(item, Mapping):
                continue
            contract_name = _artifact_contract_name(item, "artifact")
            if contract_name is None:
                continue
            plans.append(
                RuntimeArtifactPlan(
                    plan_key=f"{node.node_id}:publishes:{contract_name}",
                    source_node_id=node.node_id,
                    contract_name=contract_name,
                    contract_kind=_artifact_contract_kind(item),
                    publication_mode="publishes",
                )
            )
        for item in common.expected_outputs:
            if not isinstance(item, Mapping):
                continue
            contract_name = _artifact_contract_name(item, "name")
            if contract_name is None:
                continue
            plans.append(
                RuntimeArtifactPlan(
                    plan_key=f"{node.node_id}:expected_output:{contract_name}",
                    source_node_id=node.node_id,
                    contract_name=contract_name,
                    contract_kind=_artifact_contract_kind(item),
                    publication_mode="expected_output",
                )
            )
        output_bundle = common.output_bundle
        if isinstance(output_bundle, Mapping):
            for field in output_bundle.get("fields", ()):
                if not isinstance(field, Mapping):
                    continue
                contract_name = _artifact_contract_name(field, "name")
                if contract_name is None:
                    continue
                plans.append(
                    RuntimeArtifactPlan(
                        plan_key=f"{node.node_id}:output_bundle:{contract_name}",
                        source_node_id=node.node_id,
                        contract_name=contract_name,
                        contract_kind=_artifact_contract_kind(field),
                        publication_mode="output_bundle",
                    )
                )
        variant_output = common.variant_output
        if isinstance(variant_output, Mapping):
            discriminant = variant_output.get("discriminant")
            if isinstance(discriminant, Mapping):
                contract_name = _artifact_contract_name(discriminant, "name")
                if contract_name is not None:
                    plans.append(
                        RuntimeArtifactPlan(
                            plan_key=f"{node.node_id}:variant_output:{contract_name}",
                            source_node_id=node.node_id,
                            contract_name=contract_name,
                            contract_kind=_artifact_contract_kind(discriminant),
                            publication_mode="variant_output",
                        )
                    )
            variants = variant_output.get("variants")
            if isinstance(variants, Mapping):
                for variant in variants.values():
                    if not isinstance(variant, Mapping):
                        continue
                    for field in variant.get("fields", ()):
                        if not isinstance(field, Mapping):
                            continue
                        contract_name = _artifact_contract_name(field, "name")
                        if contract_name is None:
                            continue
                        plans.append(
                            RuntimeArtifactPlan(
                                plan_key=f"{node.node_id}:variant_output:{contract_name}",
                                source_node_id=node.node_id,
                                contract_name=contract_name,
                                contract_kind=_artifact_contract_kind(field),
                                publication_mode="variant_output",
                            )
                        )
    return tuple(plans)


def _derive_snapshot_plans(ir: ExecutableWorkflow) -> tuple[RuntimeSnapshotPlan, ...]:
    plans: list[RuntimeSnapshotPlan] = []
    for node in ir.nodes.values():
        if isinstance(node.execution_config, MaterializeArtifactsStepConfig):
            value_names = ()
            materialize = node.execution_config.materialize_artifacts
            if isinstance(materialize, Mapping):
                value_names = tuple(
                    str(item.get("name"))
                    for item in materialize.get("values", ())
                    if isinstance(item, Mapping) and isinstance(item.get("name"), str)
                )
            plans.append(
                RuntimeSnapshotPlan(
                    owner_node_id=node.node_id,
                    operation_kind="materialize_artifacts",
                    related_surface=", ".join(value_names) if value_names else None,
                    selection_relevant=False,
                )
            )

        common = _step_common_config(node)
        if common is not None and isinstance(common.pre_snapshot, Mapping):
            candidates = common.pre_snapshot.get("candidates")
            candidate_surface = None
            if isinstance(candidates, Mapping):
                candidate_surface = ", ".join(str(name) for name in candidates)
            plans.append(
                RuntimeSnapshotPlan(
                    owner_node_id=node.node_id,
                    operation_kind="pre_snapshot",
                    related_surface=candidate_surface,
                    selection_relevant=True,
                )
            )

        if isinstance(node.execution_config, SelectVariantOutputStepConfig):
            evidence = node.execution_config.select_variant_output.get("evidence")
            related_surface = None
            if isinstance(evidence, Mapping):
                snapshot = evidence.get("snapshot")
                if isinstance(snapshot, Mapping) and isinstance(snapshot.get("ref"), str):
                    related_surface = str(snapshot["ref"])
            plans.append(
                RuntimeSnapshotPlan(
                    owner_node_id=node.node_id,
                    operation_kind="select_variant_output",
                    related_surface=related_surface,
                    selection_relevant=True,
                )
            )
    return tuple(plans)


def _derive_resume_checkpoints(
    ir: ExecutableWorkflow,
    projection: WorkflowStateProjection,
    ordered_node_ids: tuple[str, ...],
) -> tuple[RuntimeResumeCheckpoint, ...]:
    checkpoints: list[RuntimeResumeCheckpoint] = []
    for node_id in ordered_node_ids:
        entry = projection.entries_by_node_id.get(node_id)
        if entry is None:
            continue
        if node_id in projection.repeat_until_nodes:
            checkpoint_kind = "repeat_until_frame"
        elif node_id in projection.for_each_nodes:
            checkpoint_kind = "for_each_frame"
        elif entry.region is WorkflowRegion.FINALIZATION:
            checkpoint_kind = "finalization_node"
        else:
            checkpoint_kind = "top_level_node"
        checkpoints.append(
            RuntimeResumeCheckpoint(
                checkpoint_kind=checkpoint_kind,
                node_id=node_id,
                step_id=entry.step_id,
                presentation_key=entry.presentation_key,
                runtime_step_id_mode="static",
            )
        )
    for call_boundary in projection.call_boundaries.values():
        checkpoints.append(
            RuntimeResumeCheckpoint(
                checkpoint_kind="call_boundary",
                node_id=call_boundary.node_id,
                step_id=call_boundary.step_id,
                presentation_key=call_boundary.presentation_key,
                runtime_step_id_mode=(
                    "qualified_iteration"
                    if call_boundary.iteration_owner_node_id is not None
                    else "static"
                ),
                iteration_owner_node_id=call_boundary.iteration_owner_node_id,
                iteration_step_id_suffix=call_boundary.iteration_step_id_suffix,
            )
        )
    return tuple(checkpoints)


def _derive_lexical_checkpoint_points(
    ir: ExecutableWorkflow,
    *,
    provenance: WorkflowProvenance | None,
) -> tuple[RuntimeLexicalCheckpointPoint, ...]:
    if provenance is None or not provenance.lexical_checkpoint_points:
        return ()

    nodes_by_step_id = {node.step_id: node for node in ir.nodes.values()}
    points: list[RuntimeLexicalCheckpointPoint] = []
    for payload in provenance.lexical_checkpoint_points:
        step_id = payload.get("step_id")
        checkpoint_id = payload.get("checkpoint_id")
        program_point_id = payload.get("program_point_id")
        point_kind = payload.get("point_kind")
        origin_key = payload.get("origin_key")
        if not all(
            isinstance(value, str) and value
            for value in (step_id, checkpoint_id, program_point_id, point_kind, origin_key)
        ):
            raise ValueError("Lexical checkpoint metadata requires non-empty string identifiers")
        node = nodes_by_step_id.get(step_id)
        if node is None:
            node = next(
                (
                    candidate
                    for candidate in ir.nodes.values()
                    if candidate.step_id == step_id or candidate.step_id.endswith(f".{step_id}")
                ),
                None,
            )
        if node is None:
            raise ValueError(f"Lexical checkpoint metadata references unknown step_id '{step_id}'")
        points.append(
            RuntimeLexicalCheckpointPoint(
                checkpoint_id=checkpoint_id,
                program_point_id=program_point_id,
                point_kind=point_kind,
                workflow_name=ir.name or "",
                step_id=node.step_id,
                node_id=node.node_id,
                presentation_key=getattr(node, "presentation_key", node.presentation_name),
                origin_key=origin_key,
                details=MappingProxyType(
                    {
                        key: value
                        for key, value in payload.items()
                        if key
                        not in {
                            "checkpoint_id",
                            "program_point_id",
                            "point_kind",
                            "workflow_name",
                            "step_id",
                            "origin_key",
                        }
                    }
                ),
            )
        )
    return tuple(points)


def _derive_observability_plan(
    *,
    workflow_name: str,
    ordered_node_ids: tuple[str, ...],
    nodes: Mapping[str, RuntimePlanNode],
) -> RuntimeObservabilityPlan:
    observability_nodes = MappingProxyType(
        {
            node_id: RuntimeObservabilityNode(
                node_id=node.node_id,
                step_id=node.step_id,
                presentation_key=node.presentation_key,
                display_name=node.display_name,
                kind=node.kind,
                region=node.region,
            )
            for node_id, node in nodes.items()
        }
    )
    return RuntimeObservabilityPlan(
        workflow_name=workflow_name,
        top_level_ordered_node_ids=ordered_node_ids,
        has_compiled_frontend_lineage=False,
        nodes=observability_nodes,
        command_boundaries=(),
    )


def _step_common_config(node: ExecutableNode) -> Any:
    config = node.execution_config
    return getattr(config, "common", None) if config is not None else None


def _artifact_contract_name(payload: Mapping[str, Any], preferred_key: str) -> Optional[str]:
    for key in (preferred_key, "artifact", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _artifact_contract_kind(payload: Mapping[str, Any]) -> Optional[str]:
    for key in ("kind", "type"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None
