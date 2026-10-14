"""Shared semantic workflow IR derived from validated workflow bundle surfaces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError
from orchestrator.providers.types import validate_phased_delivery_carriage
from ..contracts.prompt_contract import normalize_consume_prompt_policy

from .core_ast import (
    CoreForEach,
    CoreIf,
    CoreMatch,
    CoreRepeatUntil,
    CoreWorkflowAST,
    _surface_step_from_core_statement,
)
from .executable_ir import (
    ExecutableNodeKind,
    ExecutableWorkflow,
    FinalizationStepNode,
    ProviderPeerGroupStepConfig,
    ProviderStepConfig,
    ProviderSupervisionStepConfig,
    RequestInputStepConfig,
    RunRefStepConfig,
    TrialStepConfig,
    provider_peer_group_config_to_runtime_dict,
)
from .prompt_dependency_contract import (
    CompilerPromptDependencyContract,
    serialize_compiler_prompt_dependency_contract,
)
from .prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    CompilerPromptFragmentContractCarrier,
    CompilerPromptFragmentContractV2,
    serialize_compiler_prompt_attempt_binding_plan,
    serialize_compiler_prompt_fragment_contract,
    validate_compiler_prompt_attempt_pair,
    validate_compiler_prompt_fragment_pair,
)
from .references import ReferenceResolutionError, StructuredStepReference, parse_structured_ref
from .runtime_plan import WorkflowRuntimePlan
from .run_ref.config import (
    RunRefStaticConfig,
    validate_run_ref_static_config_authority,
)
from .trial.config import (
    TrialStaticConfig,
    validate_trial_static_config_authority,
)
from .state_layout import (
    GeneratedPathAllocationRequest,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
    StateLayout,
)
from .state_projection import WorkflowStateProjection
from .surface_ast import (
    SurfaceStep,
    SurfaceStepKind,
    SurfaceWorkflow,
    WorkflowProvenance,
    empty_frozen_mapping,
    freeze_mapping,
)
from .transition_contract import ValidatedTransitionDeclaration
from .view_renderer import VIEW_RENDERER_SCHEMA_VERSION


WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION = "workflow_semantic_ir.v1"
_PROMOTED_ADAPTER_EFFECT_KINDS = frozenset({"resource_transition", "ledger_update"})
_PROMOTED_GENERATED_EFFECT_KINDS = frozenset(
    {
        "snapshot_capture",
        "pointer_materialization",
        "pure_projection",
        "materialize_view",
        "run_ref",
        "trial",
    }
)
_PROVIDER_BUNDLE_PATH_PROJECTION_KIND = "provider_bundle_path_projection"


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
    provider_call_policy: Mapping[str, object] | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    provider_context: Mapping[str, Any] | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    input_file: Any = None
    asset_file: Any = None
    prompt_consumes: tuple[Any, ...] = ()
    consumed_prompt_policies: tuple[Any, ...] = ()
    typed_prompt_inputs: tuple[Any, ...] = ()
    inject_output_contract: bool | None = None
    inject_consumes: bool | None = None
    compiler_prompt_dependency_contract: CompilerPromptDependencyContract | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": serialize_compiler_prompt_dependency_contract,
        },
    )
    compiler_prompt_fragment_contract: CompilerPromptFragmentContractCarrier | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": serialize_compiler_prompt_fragment_contract,
        },
    )
    compiled_prompt_fragment_identity: str | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    prompt_attempt_identity_version: str | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    compiler_prompt_attempt_binding_plan: (
        CompilerPromptAttemptBindingPlan | None
    ) = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": serialize_compiler_prompt_attempt_binding_plan,
        },
    )

    def __post_init__(self) -> None:
        validate_compiler_prompt_fragment_pair(
            self.compiler_prompt_fragment_contract,
            self.compiled_prompt_fragment_identity,
            tuple(
                row.expected_output
                for row in getattr(
                    self.compiler_prompt_fragment_contract,
                    "output_positions",
                    (),
                )
            ),
        )
        validate_compiler_prompt_attempt_pair(
            self.prompt_attempt_identity_version,
            self.compiler_prompt_attempt_binding_plan,
            fragment_contract=self.compiler_prompt_fragment_contract,
            dependency_contract=self.compiler_prompt_dependency_contract,
            typed_prompt_inputs=self.typed_prompt_inputs,
        )
        validate_phased_delivery_carriage(
            self.provider_call_policy,
            prompt_attempt_identity_version=(
                self.prompt_attempt_identity_version
            ),
        )


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
    result_guidance: Mapping[str, Any] | None = None
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






def workflow_semantic_ir_to_json(semantic_ir: SemanticWorkflowIR) -> dict[str, Any]:
    payload = _json_value(semantic_ir)
    workflows = payload.get("workflows")
    if isinstance(workflows, Mapping):
        for workflow in workflows.values():
            if isinstance(workflow, dict) and workflow.get("result_guidance") is None:
                workflow.pop("result_guidance", None)
    generated_compatibility_bridges = _generated_compatibility_bridges_from_payload(
        payload
    )
    if generated_compatibility_bridges:
        payload["generated_compatibility_bridges"] = generated_compatibility_bridges
    return payload


def _generated_compatibility_bridges_from_payload(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    effects = payload.get("effects")
    if not isinstance(effects, Mapping):
        return []
    generated: list[dict[str, Any]] = []
    for effect_id, effect in sorted(effects.items()):
        if not isinstance(effect, Mapping):
            continue
        if effect.get("effect_kind") != "materialize_view":
            continue
        details = effect.get("details")
        if not isinstance(details, Mapping):
            continue
        if details.get("authority_class") != "compatibility_bridge":
            continue
        bridge_id = details.get("bridge_id")
        if not isinstance(bridge_id, str) or not bridge_id:
            continue
        generated.append(
                {
                    "bridge_id": bridge_id,
                    "c0_row_id": details.get("c0_row_id"),
                    "workflow_name": effect.get("workflow_name"),
                    "step_id": effect.get("statement_id"),
                    "effect_id": effect_id,
                    "effect_kind": "materialize_view",
                    "renderer_id": details.get("renderer_id"),
                "renderer_version": details.get("renderer_version"),
                "target_path": details.get("target_path"),
                "target_allocation_id": details.get("target_allocation_id"),
                "authority_class": "compatibility_bridge",
                "value_type": _json_value(details.get("value_type")),
            }
        )
    return generated




@dataclass(frozen=True)
class _SemanticStatementSurface:
    step_id: str
    surface_step_id: str
    step_kind: str
    surface_step: SurfaceStep


























































































































def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        payload: dict[str, Any] = {}
        for field_def in fields(value):
            field_value = getattr(value, field_def.name)
            if field_def.metadata.get("json_omit_if_none") and field_value is None:
                continue
            serializer = field_def.metadata.get("json_serializer")
            payload[field_def.name] = _json_value(
                serializer(field_value) if serializer is not None else field_value
            )
        return payload
    return value
