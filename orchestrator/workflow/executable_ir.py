"""Immutable executable workflow IR records and bound reference addresses."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError

from .prompt_dependency_contract import (
    CompilerPromptDependencyContract,
    serialize_compiler_prompt_dependency_contract,
    validate_compiler_prompt_dependency_contract,
)
from .provider_supervision.models import (
    ProviderSupervisionObservation,
    ProviderSupervisionSourceOwnership,
)
from .provider_supervision.directive import (
    PROVIDER_STEERING_DIRECTIVE_CONTRACT_KIND,
    PROVIDER_STEERING_DIRECTIVE_CONTRACT_VALUE_TYPE,
    PROVIDER_STEERING_DIRECTIVE_TYPE_NAME,
    provider_steering_directive_type_descriptor,
)
from .provider_supervision.contracts import (
    bind_member_result_contract,
    derive_result_bundle_contract,
    validate_result_contract_identity,
)
from .provider_supervision.paths import (
    ProviderSupervisionPaths,
    derive_provider_supervision_paths,
)
from .pure_expr import (
    PureExprEvaluationError,
    canonical_json_for_pure_value,
    validate_pure_expr_payload,
)
from .surface_ast import WorkflowProvenance, empty_frozen_mapping


WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"
PROVIDER_SUPERVISION_SCHEMA_VERSION = "provider_supervision.v1"


def _serialize_provider_call_policy(policy: Mapping[str, str]) -> dict[str, str]:
    unexpected = set(policy) - {"model", "effort"}
    if unexpected:
        keys = ", ".join(sorted(str(key) for key in unexpected))
        raise ValueError(f"unexpected provider call policy key(s): {keys}")
    return {key: policy[key] for key in ("model", "effort") if key in policy}


class WorkflowRegion(str, Enum):
    """Top-level execution region membership."""

    BODY = "body"
    FINALIZATION = "finalization"


class ExecutableNodeKind(str, Enum):
    """Typed executable workflow node kinds."""

    COMMAND = "command"
    PROVIDER = "provider"
    PROVIDER_SUPERVISION = "provider_supervision"
    ADJUDICATED_PROVIDER = "adjudicated_provider"
    WAIT_FOR = "wait_for"
    ASSERT = "assert"
    SET_SCALAR = "set_scalar"
    RESOURCE_TRANSITION = "resource_transition"
    PURE_PROJECTION = "pure_projection"
    MATERIALIZE_VIEW = "materialize_view"
    INCREMENT_SCALAR = "increment_scalar"
    MATERIALIZE_ARTIFACTS = "materialize_artifacts"
    SELECT_VARIANT_OUTPUT = "select_variant_output"
    FOR_EACH = "for_each"
    CALL_BOUNDARY = "call_boundary"
    IF_BRANCH_MARKER = "if_branch_marker"
    IF_JOIN = "if_join"
    MATCH_CASE_MARKER = "match_case_marker"
    MATCH_JOIN = "match_join"
    REPEAT_UNTIL_FRAME = "repeat_until_frame"
    FINALIZATION_STEP = "finalization_step"


@dataclass(frozen=True)
class WorkflowInputAddress:
    """Bound workflow-input address."""

    input_name: str


@dataclass(frozen=True)
class NodeResultAddress:
    """Bound executable-node result address."""

    node_id: str
    field: str
    member: Optional[str] = None


@dataclass(frozen=True)
class BlockOutputAddress:
    """Bound structured-join output address."""

    node_id: str
    output_name: str


@dataclass(frozen=True)
class LoopOutputAddress:
    """Bound repeat-until frame output address."""

    node_id: str
    output_name: str


@dataclass(frozen=True)
class CallOutputAddress:
    """Bound call-boundary output address."""

    node_id: str
    output_name: str


BoundAddress = (
    WorkflowInputAddress
    | NodeResultAddress
    | BlockOutputAddress
    | LoopOutputAddress
    | CallOutputAddress
)


@dataclass(frozen=True)
class ExecutableTransfer:
    """One explicit routed transfer between executable nodes."""

    reason: str
    target_node_id: Optional[str]
    counts_as_transition: bool = False


@dataclass(frozen=True)
class ExecutableContract:
    """Lowered contract wrapper bound to durable addresses."""

    name: str
    kind: Optional[str]
    value_type: Optional[str]
    definition: Mapping[str, Any]
    source_address: Optional[BoundAddress] = None


@dataclass(frozen=True)
class ExecutablePrivateArtifact:
    """Compiler-classified private artifact catalog entry."""

    artifact_id: str
    contract: ExecutableContract
    origin: str
    prompt_render_mode: str = "json"


@dataclass(frozen=True)
class StepCommonConfig:
    """Runtime-relevant common step fields carried by executable nodes."""

    on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    consumes: tuple[Any, ...] = ()
    consume_bundle: Any = None
    publishes: tuple[Any, ...] = ()
    expected_outputs: tuple[Any, ...] = ()
    output_bundle: Any = None
    variant_output: Any = None
    pre_snapshot: Any = None
    requires_variant: Any = None
    persist_artifacts_in_state: Optional[bool] = None
    provider_session: Optional[Mapping[str, Any]] = None
    max_visits: Optional[int] = None
    retries: Any = None
    env: Optional[Mapping[str, Any]] = None
    secrets: tuple[str, ...] = ()
    timeout_sec: Any = None
    output_capture: Any = None
    output_file: Any = None
    allow_parse_error: Optional[bool] = None


@dataclass(frozen=True)
class CommandStepConfig:
    """Executable command-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    command: Any = ()


@dataclass(frozen=True)
class ManagedJobsRoutes:
    """Executable managed-job outcome routing."""

    complete: str
    failed: str
    invalid: str
    outstanding: str


@dataclass(frozen=True)
class ManagedJobsConfig:
    """Executable managed-job provider-step modifier."""

    policy: str
    watch_roots: tuple[str, ...]
    backend: str
    poll_budget_sec: int
    on: ManagedJobsRoutes


@dataclass(frozen=True)
class ProviderStepConfig:
    """Executable provider-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    provider: str = ""
    provider_params: Any = None
    provider_call_policy: Mapping[str, str] | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": _serialize_provider_call_policy,
        },
    )
    input_file: Any = None
    asset_file: Any = None
    depends_on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    asset_depends_on: tuple[Any, ...] = ()
    inject_output_contract: Optional[bool] = None
    inject_consumes: Optional[bool] = None
    prompt_consumes: Optional[tuple[Any, ...]] = None
    typed_prompt_inputs: tuple[Any, ...] = ()
    consumes_injection_position: Optional[str] = None
    managed_jobs: Optional[ManagedJobsConfig] = None
    compiler_prompt_dependency_contract: CompilerPromptDependencyContract | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": serialize_compiler_prompt_dependency_contract,
        },
    )


@dataclass(frozen=True)
class ProviderSupervisionMemberConfig:
    """One immutable member invocation and its provisional result contract."""

    member_id: str
    provider_config: ProviderStepConfig
    result_contract: ExecutableContract
    timeout_sec: int


@dataclass(frozen=True)
class ProviderSupervisionStepConfig:
    """Closed node-local executable contract for one bounded live group."""

    common: StepCommonConfig
    schema_version: str
    node_id: str
    worker: ProviderSupervisionMemberConfig
    supervisor: ProviderSupervisionMemberConfig
    observation: ProviderSupervisionObservation
    settlement_payload: Mapping[str, Any]
    settlement_result_contract: ExecutableContract
    max_steers: int
    paths: ProviderSupervisionPaths
    source_ownership: ProviderSupervisionSourceOwnership

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> ProviderSupervisionStepConfig:
        """Preserve the immutable typed contract across mapping copies."""

        memo[id(self)] = self
        return self


@dataclass(frozen=True)
class AdjudicatedProviderStepConfig:
    """Executable adjudicated-provider step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    adjudicated_provider: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    input_file: Any = None
    asset_file: Any = None
    depends_on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    asset_depends_on: tuple[Any, ...] = ()
    inject_output_contract: Optional[bool] = None
    inject_consumes: Optional[bool] = None
    prompt_consumes: Optional[tuple[Any, ...]] = None
    consumes_injection_position: Optional[str] = None


@dataclass(frozen=True)
class WaitForStepConfig:
    """Executable wait_for-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    wait_for: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class AssertStepConfig:
    """Executable assert-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)


@dataclass(frozen=True)
class SetScalarStepConfig:
    """Executable set_scalar-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    set_scalar: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class ResourceTransitionStepConfig:
    """Executable resource_transition-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    resource_transition: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class PureProjectionStepConfig:
    """Executable pure_projection-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    pure_projection: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class MaterializeViewStepConfig:
    """Executable materialize_view-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    materialize_view: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class IncrementScalarStepConfig:
    """Executable increment_scalar-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    increment_scalar: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class MaterializeArtifactsStepConfig:
    """Executable materialize_artifacts-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    materialize_artifacts: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SelectVariantOutputStepConfig:
    """Executable select_variant_output-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    select_variant_output: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class CallStepConfig:
    """Executable reusable-call step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    call: str = ""


@dataclass(frozen=True)
class ForEachStepConfig:
    """Executable for_each step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    items: tuple[Any, ...] = ()
    items_from: Optional[str] = None
    item_name: str = "item"


@dataclass(frozen=True)
class RepeatUntilStepConfig:
    """Executable repeat_until frame config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    body_id: str = "repeat_until"
    max_iterations: int = 0
    on_exhausted_outputs: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


ExecutableStepConfig = (
    CommandStepConfig
    | ProviderStepConfig
    | ProviderSupervisionStepConfig
    | AdjudicatedProviderStepConfig
    | WaitForStepConfig
    | AssertStepConfig
    | SetScalarStepConfig
    | ResourceTransitionStepConfig
    | PureProjectionStepConfig
    | MaterializeViewStepConfig
    | IncrementScalarStepConfig
    | MaterializeArtifactsStepConfig
    | SelectVariantOutputStepConfig
    | CallStepConfig
    | ForEachStepConfig
    | RepeatUntilStepConfig
)


@dataclass(frozen=True)
class ExecutableNodeBase:
    """Common executable-node fields."""

    node_id: str
    step_id: str
    presentation_name: str
    kind: ExecutableNodeKind
    region: WorkflowRegion
    lexical_scope: tuple[str, ...]
    execution_config: Optional[ExecutableStepConfig] = None
    fallthrough_node_id: Optional[str] = None
    routed_transfers: Mapping[str, ExecutableTransfer] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class LeafExecutableNode(ExecutableNodeBase):
    """Leaf node adapted into the existing step executors later."""

    bound_when_predicate: Any = None
    bound_assert_predicate: Any = None


@dataclass(frozen=True)
class ForEachNode(ExecutableNodeBase):
    """Typed for-each execution node plus lowered nested body nodes."""

    body_node_ids: tuple[str, ...] = ()
    body_entry_node_id: Optional[str] = None
    bound_when_predicate: Any = None
    bound_assert_predicate: Any = None


@dataclass(frozen=True)
class CallBoundaryNode(ExecutableNodeBase):
    """Typed reusable-workflow call boundary."""

    call_alias: str = ""
    available_outputs: tuple[str, ...] = ()
    bound_inputs: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    bound_when_predicate: Any = None
    bound_assert_predicate: Any = None


@dataclass(frozen=True)
class IfBranchMarkerNode(ExecutableNodeBase):
    """Typed if-branch guard marker."""

    statement_name: str = ""
    branch_name: str = ""
    guard_condition: Any = None
    invert_guard: bool = False
    bound_when_predicate: Any = None


@dataclass(frozen=True)
class IfJoinNode(ExecutableNodeBase):
    """Typed if-statement join node."""

    statement_name: str = ""
    branch_outputs: Mapping[str, Mapping[str, ExecutableContract]] = field(default_factory=empty_frozen_mapping)
    bound_when_predicate: Any = None


@dataclass(frozen=True)
class MatchCaseMarkerNode(ExecutableNodeBase):
    """Typed match-case guard marker."""

    statement_name: str = ""
    case_name: str = ""
    selector_address: Optional[BoundAddress] = None
    bound_when_predicate: Any = None


@dataclass(frozen=True)
class MatchJoinNode(ExecutableNodeBase):
    """Typed match-statement join node."""

    statement_name: str = ""
    selector_address: Optional[BoundAddress] = None
    case_outputs: Mapping[str, Mapping[str, ExecutableContract]] = field(default_factory=empty_frozen_mapping)
    bound_when_predicate: Any = None


@dataclass(frozen=True)
class RepeatUntilFrameNode(ExecutableNodeBase):
    """Typed repeat-until frame with nested lowered body nodes."""

    body_node_ids: tuple[str, ...] = ()
    body_entry_node_id: Optional[str] = None
    bound_when_predicate: Any = None
    condition: Any = None
    max_iterations: Optional[int] = None
    output_contracts: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    on_exhausted_outputs: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class FinalizationStepNode(ExecutableNodeBase):
    """Typed workflow-finalization node."""

    execution_kind: ExecutableNodeKind = ExecutableNodeKind.COMMAND
    bound_when_predicate: Any = None
    bound_assert_predicate: Any = None


ExecutableNode = (
    LeafExecutableNode
    | ForEachNode
    | CallBoundaryNode
    | IfBranchMarkerNode
    | IfJoinNode
    | MatchCaseMarkerNode
    | MatchJoinNode
    | RepeatUntilFrameNode
    | FinalizationStepNode
)


@dataclass(frozen=True)
class ExecutableWorkflow:
    """Lowered executable workflow plus projection-facing metadata."""

    schema_version: str
    version: str
    name: Optional[str]
    provenance: WorkflowProvenance
    body_region: tuple[str, ...]
    finalization_region: tuple[str, ...]
    finalization_entry_node_id: Optional[str]
    nodes: Mapping[str, ExecutableNode]
    artifacts: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    private_artifacts: Mapping[str, ExecutablePrivateArtifact] = field(default_factory=empty_frozen_mapping)
    inputs: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    outputs: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    result_guidance: Mapping[str, Any] | None = None


_LEAF_EXECUTION_CONFIG_TYPES = (
    CommandStepConfig,
    ProviderStepConfig,
    ProviderSupervisionStepConfig,
    AdjudicatedProviderStepConfig,
    WaitForStepConfig,
    AssertStepConfig,
    SetScalarStepConfig,
    ResourceTransitionStepConfig,
    PureProjectionStepConfig,
    MaterializeViewStepConfig,
    IncrementScalarStepConfig,
    MaterializeArtifactsStepConfig,
    SelectVariantOutputStepConfig,
)
_NODE_TYPE_BY_KIND = {
    ExecutableNodeKind.FOR_EACH: ForEachNode,
    ExecutableNodeKind.CALL_BOUNDARY: CallBoundaryNode,
    ExecutableNodeKind.IF_BRANCH_MARKER: IfBranchMarkerNode,
    ExecutableNodeKind.IF_JOIN: IfJoinNode,
    ExecutableNodeKind.MATCH_CASE_MARKER: MatchCaseMarkerNode,
    ExecutableNodeKind.MATCH_JOIN: MatchJoinNode,
    ExecutableNodeKind.REPEAT_UNTIL_FRAME: RepeatUntilFrameNode,
    ExecutableNodeKind.FINALIZATION_STEP: FinalizationStepNode,
}
_LEAF_KIND_TO_CONFIG = {
    ExecutableNodeKind.COMMAND: CommandStepConfig,
    ExecutableNodeKind.PROVIDER: ProviderStepConfig,
    ExecutableNodeKind.PROVIDER_SUPERVISION: ProviderSupervisionStepConfig,
    ExecutableNodeKind.ADJUDICATED_PROVIDER: AdjudicatedProviderStepConfig,
    ExecutableNodeKind.WAIT_FOR: WaitForStepConfig,
    ExecutableNodeKind.ASSERT: AssertStepConfig,
    ExecutableNodeKind.SET_SCALAR: SetScalarStepConfig,
    ExecutableNodeKind.RESOURCE_TRANSITION: ResourceTransitionStepConfig,
    ExecutableNodeKind.PURE_PROJECTION: PureProjectionStepConfig,
    ExecutableNodeKind.MATERIALIZE_VIEW: MaterializeViewStepConfig,
    ExecutableNodeKind.INCREMENT_SCALAR: IncrementScalarStepConfig,
    ExecutableNodeKind.MATERIALIZE_ARTIFACTS: MaterializeArtifactsStepConfig,
    ExecutableNodeKind.SELECT_VARIANT_OUTPUT: SelectVariantOutputStepConfig,
}
_COMPILE_TIME_TYPE_NAME_FRAGMENTS = ("ProcRef", "WorkflowRef", "SourceSpan", "Syntax")


def workflow_executable_ir_to_json(ir: ExecutableWorkflow) -> dict[str, Any]:
    """Serialize executable IR deterministically from the owning shared module."""

    payload = {
        "schema_version": ir.schema_version,
        "version": ir.version,
        "name": ir.name,
        "provenance": _provenance_json_value(ir.provenance),
        "body_region": list(ir.body_region),
        "finalization_region": list(ir.finalization_region),
        "finalization_entry_node_id": ir.finalization_entry_node_id,
        "nodes": {
            node_id: _json_value(node)
            for node_id, node in sorted(ir.nodes.items())
        },
        "artifacts": {
            name: _json_value(contract)
            for name, contract in sorted(ir.artifacts.items())
        },
        "private_artifacts": {
            name: _json_value(artifact)
            for name, artifact in sorted(ir.private_artifacts.items())
        },
        "inputs": {
            name: _json_value(contract)
            for name, contract in sorted(ir.inputs.items())
        },
        "outputs": {
            name: _json_value(contract)
            for name, contract in sorted(ir.outputs.items())
        },
    }
    if ir.result_guidance is not None:
        payload["result_guidance"] = _json_value(ir.result_guidance)
    return payload


def provider_supervision_config_to_runtime_dict(
    config: ProviderSupervisionStepConfig,
) -> dict[str, Any]:
    """Return the node-local mapping view; common fields remain step-level."""

    payload = _json_value(config)
    if not isinstance(payload, dict):
        raise TypeError("provider supervision config must serialize to an object")
    payload.pop("common", None)
    return payload


def validate_executable_workflow(ir: ExecutableWorkflow) -> None:
    """Validate one authoritative executable workflow contract."""

    if ir.schema_version != WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION:
        _raise_executable_ir_invalid(
            f"executable_ir_invalid: unsupported executable IR schema `{ir.schema_version}`",
            workflow_name=ir.name,
        )

    known_node_ids = set(ir.nodes)
    if len(known_node_ids) != len(ir.nodes):
        _raise_executable_ir_invalid(
            "executable_ir_invalid: executable node ids must be unique",
            workflow_name=ir.name,
        )

    body_ids = set(ir.body_region)
    finalization_ids = set(ir.finalization_region)
    if body_ids & finalization_ids:
        _raise_executable_ir_invalid(
            "executable_ir_invalid: body and finalization regions must not overlap",
            workflow_name=ir.name,
        )

    for node_id in ir.body_region:
        if node_id not in known_node_ids:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: body region references unknown node id `{node_id}`",
                workflow_name=ir.name,
            )
        node = ir.nodes[node_id]
        if node.region is not WorkflowRegion.BODY:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: body region node `{node_id}` must declare body region membership",
                workflow_name=ir.name,
                node=node,
            )

    for node_id in ir.finalization_region:
        if node_id not in known_node_ids:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: finalization region references unknown node id `{node_id}`",
                workflow_name=ir.name,
            )
        node = ir.nodes[node_id]
        if node.region is not WorkflowRegion.FINALIZATION:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: finalization region node `{node_id}` must declare finalization region membership",
                workflow_name=ir.name,
                node=node,
            )

    if ir.finalization_entry_node_id is not None and ir.finalization_entry_node_id not in finalization_ids:
        _raise_executable_ir_invalid(
            "executable_ir_invalid: finalization entry node must resolve inside the finalization region",
            workflow_name=ir.name,
        )

    for key, artifact in ir.private_artifacts.items():
        if key != artifact.artifact_id:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: private artifact mapping key `{key}` does not match artifact id `{artifact.artifact_id}`",
                workflow_name=ir.name,
            )
        if key in ir.artifacts:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: private artifact `{key}` must not appear in the public artifact catalog",
                workflow_name=ir.name,
            )

    for key, node in ir.nodes.items():
        if key != node.node_id:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node mapping key `{key}` does not match node id `{node.node_id}`",
                workflow_name=ir.name,
                node=node,
            )
        _validate_node_shape(node, workflow_name=ir.name, known_node_ids=known_node_ids)
        _validate_target_node_id(
            node.fallthrough_node_id,
            known_node_ids=known_node_ids,
            workflow_name=ir.name,
            node=node,
            context="fallthrough target",
        )
        for transfer_name, transfer in node.routed_transfers.items():
            _validate_target_node_id(
                transfer.target_node_id,
                known_node_ids=known_node_ids,
                workflow_name=ir.name,
                node=node,
                context=f"routed transfer `{transfer_name}` target",
            )
        if isinstance(node, (ForEachNode, RepeatUntilFrameNode)):
            for nested_node_id in node.body_node_ids:
                _validate_target_node_id(
                    nested_node_id,
                    known_node_ids=known_node_ids,
                    workflow_name=ir.name,
                    node=node,
                    context="nested body node",
                )
            _validate_target_node_id(
                node.body_entry_node_id,
                known_node_ids=known_node_ids,
                workflow_name=ir.name,
                node=node,
                context="body entry node",
            )
        _validate_ir_payload(
            node,
            workflow_name=ir.name,
            known_node_ids=known_node_ids,
            known_nodes=ir.nodes,
            current_node=node,
        )

    for contract in tuple(ir.artifacts.values()) + tuple(ir.inputs.values()) + tuple(ir.outputs.values()):
        _validate_contract(
            contract,
            workflow_name=ir.name,
            known_node_ids=known_node_ids,
            known_nodes=ir.nodes,
            current_node=None,
        )


def _validate_node_shape(
    node: ExecutableNode,
    *,
    workflow_name: str | None,
    known_node_ids: set[str],
) -> None:
    expected_type = _NODE_TYPE_BY_KIND.get(node.kind)
    if expected_type is not None:
        if not isinstance(node, expected_type):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
    elif not isinstance(node, LeafExecutableNode):
        _raise_executable_ir_invalid(
            f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.kind.value}`",
            workflow_name=workflow_name,
            node=node,
        )

    if isinstance(node, LeafExecutableNode):
        expected_config_type = _LEAF_KIND_TO_CONFIG.get(node.kind)
        if expected_config_type is None or not isinstance(node.execution_config, expected_config_type):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
        if isinstance(node.execution_config, ProviderStepConfig):
            try:
                _validate_provider_prompt_dependency_binding(
                    node.execution_config,
                    required=False,
                )
            except (TypeError, ValueError):
                _raise_executable_ir_invalid(
                    "executable_ir_invalid: provider prompt dependency contract is invalid",
                    workflow_name=workflow_name,
                    node=node,
                )
        if isinstance(node.execution_config, ProviderSupervisionStepConfig):
            _validate_provider_supervision_step_config(
                node.execution_config,
                workflow_name=workflow_name,
                node=node,
            )
    elif isinstance(node, CallBoundaryNode):
        if not isinstance(node.execution_config, CallStepConfig):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
    elif isinstance(node, ForEachNode):
        if not isinstance(node.execution_config, ForEachStepConfig):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
    elif isinstance(node, RepeatUntilFrameNode):
        if not isinstance(node.execution_config, RepeatUntilStepConfig):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
    elif isinstance(node, FinalizationStepNode):
        if node.execution_kind not in _LEAF_KIND_TO_CONFIG:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: finalization node `{node.node_id}` uses unsupported execution kind `{node.execution_kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
        expected_config_type = _LEAF_KIND_TO_CONFIG[node.execution_kind]
        if not isinstance(node.execution_config, expected_config_type):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` kind/config mismatch for `{node.execution_kind.value}`",
                workflow_name=workflow_name,
                node=node,
            )
    else:
        if node.execution_config is not None:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: structural node `{node.node_id}` must not carry an execution config",
                workflow_name=workflow_name,
                node=node,
            )

    if isinstance(node, FinalizationStepNode) and node.region is not WorkflowRegion.FINALIZATION:
        _raise_executable_ir_invalid(
            f"executable_ir_invalid: finalization node `{node.node_id}` must live in the finalization region",
            workflow_name=workflow_name,
            node=node,
        )
    if not isinstance(node, FinalizationStepNode) and node.region is WorkflowRegion.FINALIZATION:
        _raise_executable_ir_invalid(
            f"executable_ir_invalid: non-finalization node `{node.node_id}` must not declare finalization region membership",
            workflow_name=workflow_name,
            node=node,
        )


def _validate_provider_prompt_dependency_binding(
    config: ProviderStepConfig,
    *,
    required: bool,
) -> None:
    """Validate one typed contract and its exact compatibility mapping."""

    contract = config.compiler_prompt_dependency_contract
    if contract is None:
        if required:
            raise ValueError("compiler prompt dependency contract is required")
        return
    validate_compiler_prompt_dependency_contract(contract)
    depends_on = config.depends_on
    if not isinstance(depends_on, Mapping) or set(depends_on) != {
        "required",
        "optional",
        "inject",
    }:
        raise ValueError("prompt dependency mapping is not closed")
    required_templates = depends_on.get("required")
    optional_templates = depends_on.get("optional")
    if not isinstance(required_templates, (list, tuple)) or not isinstance(
        optional_templates,
        (list, tuple),
    ):
        raise ValueError("prompt dependency templates must be sequences")
    if tuple(required_templates) != tuple(
        f"${{{ref}}}"
        for ref in contract.required_binding_refs
    ) or tuple(optional_templates) != tuple(
        f"${{{ref}}}"
        for ref in contract.optional_binding_refs
    ):
        raise ValueError("prompt dependency templates contradict the contract")
    inject = depends_on.get("inject")
    expected_inject_keys = {"mode", "position"}
    instruction_digest = contract.instruction_utf8_sha256_or_null
    if instruction_digest is not None:
        expected_inject_keys.add("instruction")
    if (
        not isinstance(inject, Mapping)
        or set(inject) != expected_inject_keys
        or inject.get("mode") != "content"
        or inject.get("position") != contract.position.value
    ):
        raise ValueError("prompt dependency injection contradicts the contract")
    if instruction_digest is not None:
        instruction = inject.get("instruction")
        if not isinstance(instruction, str):
            raise ValueError("prompt dependency instruction must be a string")
        observed_digest = (
            "sha256:"
            + sha256(instruction.encode("utf-8")).hexdigest()
        )
        if observed_digest != instruction_digest:
            raise ValueError(
                "prompt dependency instruction contradicts the contract"
            )


def _validate_provider_supervision_step_config(
    config: ProviderSupervisionStepConfig,
    *,
    workflow_name: str | None,
    node: ExecutableNode,
) -> None:
    def fail(reason: str) -> None:
        _raise_executable_ir_invalid(
            f"executable_ir_invalid: provider supervision {reason}",
            workflow_name=workflow_name,
            node=node,
        )

    def contract_descriptor_matches(
        contract: ExecutableContract,
        observed_descriptor: Any,
        *,
        malformed_reason: str,
        require_closed_definition: bool = False,
    ) -> bool:
        definition = contract.definition
        if (
            not isinstance(definition, Mapping)
            or "type" not in definition
            or (
                require_closed_definition
                and set(definition) != {"type"}
            )
        ):
            fail(malformed_reason)
        try:
            contract_descriptor_json = canonical_json_for_pure_value(
                definition["type"]
            )
            observed_descriptor_json = canonical_json_for_pure_value(
                observed_descriptor
            )
        except (KeyError, TypeError, ValueError):
            fail(malformed_reason)
        return contract_descriptor_json == observed_descriptor_json

    if config.schema_version != PROVIDER_SUPERVISION_SCHEMA_VERSION:
        fail("schema is unsupported")
    if not isinstance(config.node_id, str) or config.node_id != node.node_id:
        fail("node id does not match its executable node")
    if not isinstance(config.common, StepCommonConfig):
        fail("step common config must be StepCommonConfig")
    if (
        isinstance(config.common.timeout_sec, bool)
        or not isinstance(config.common.timeout_sec, int)
        or config.common.timeout_sec <= 0
    ):
        fail("step timeout must be a positive integer")
    if isinstance(config.max_steers, bool) or config.max_steers != 1:
        fail("max_steers must be exactly integer 1")

    if not isinstance(config.worker, ProviderSupervisionMemberConfig):
        fail("worker member must be typed")
    if not isinstance(config.supervisor, ProviderSupervisionMemberConfig):
        fail("supervisor member must be typed")
    members = (config.worker, config.supervisor)
    for role, member in zip(("worker", "supervisor"), members):
        if not isinstance(member.member_id, str) or not member.member_id:
            fail(f"{role} member id must be non-empty")
        if not isinstance(member.provider_config, ProviderStepConfig):
            fail(f"{role} provider config must be ProviderStepConfig")
        if not isinstance(
            member.provider_config.common,
            StepCommonConfig,
        ):
            fail(f"{role} provider common config must be StepCommonConfig")
        if (
            not isinstance(member.provider_config.provider, str)
            or not member.provider_config.provider
        ):
            fail(f"{role} provider must be non-empty")
        if member.provider_config.inject_output_contract is not True:
            fail(f"{role} provider must inject its output contract")
        try:
            _validate_provider_prompt_dependency_binding(
                member.provider_config,
                required=True,
            )
        except (TypeError, ValueError):
            fail(
                f"{role} provider prompt dependency binding is invalid"
            )
        if not isinstance(member.result_contract, ExecutableContract):
            fail(f"{role} result contract must be ExecutableContract")
        try:
            validate_result_contract_identity(member.result_contract)
        except (TypeError, ValueError):
            fail(
                (
                    "supervisor directive contract descriptor or identity "
                    "is invalid"
                    if role == "supervisor"
                    else "worker member contract identity is invalid"
                )
            )
        if (
            isinstance(member.timeout_sec, bool)
            or not isinstance(member.timeout_sec, int)
            or member.timeout_sec <= 0
        ):
            fail(f"{role} timeout must be a positive integer")
        if member.provider_config.common.timeout_sec != member.timeout_sec:
            fail(f"{role} provider timeout contradicts its member timeout")
    expected_step_timeout = (
        max(config.worker.timeout_sec, config.supervisor.timeout_sec)
        + config.worker.timeout_sec
    )
    if config.common.timeout_sec != expected_step_timeout:
        fail(
            "whole-step timeout budget must equal the concurrent initial turn "
            "plus one worker resume"
        )
    if config.worker.member_id == config.supervisor.member_id:
        fail("worker and supervisor member ids must be distinct")
    directive_contract = config.supervisor.result_contract
    if (
        directive_contract.name != PROVIDER_STEERING_DIRECTIVE_TYPE_NAME
        or directive_contract.kind != PROVIDER_STEERING_DIRECTIVE_CONTRACT_KIND
        or directive_contract.value_type
        != PROVIDER_STEERING_DIRECTIVE_CONTRACT_VALUE_TYPE
    ):
        fail("supervisor directive contract identity is invalid")
    if not contract_descriptor_matches(
        directive_contract,
        provider_steering_directive_type_descriptor(),
        malformed_reason="supervisor directive contract descriptor is invalid",
        require_closed_definition=True,
    ):
        fail("supervisor directive contract descriptor is invalid")

    if not isinstance(config.observation, ProviderSupervisionObservation):
        fail("observation edge must be typed")
    if (
        config.observation.observer_member_id != config.supervisor.member_id
        or config.observation.observed_member_id != config.worker.member_id
    ):
        fail("observation edge must be exactly supervisor to worker")

    if not isinstance(config.settlement_result_contract, ExecutableContract):
        fail("settlement result contract must be ExecutableContract")
    try:
        validate_result_contract_identity(
            config.settlement_result_contract
        )
        derive_result_bundle_contract(
            config.settlement_result_contract,
            path=(
                ".orchestrate/provider-supervision-validation/"
                "settlement-result.json"
            ),
        )
    except (TypeError, ValueError):
        fail("settlement result contract identity is invalid")
    if not isinstance(config.settlement_payload, Mapping):
        fail("settlement payload must be a mapping")
    try:
        validate_pure_expr_payload(config.settlement_payload)
    except (PureExprEvaluationError, TypeError, ValueError):
        fail("settlement payload is not a validated pure expression")
    bindings = config.settlement_payload.get("bindings")
    if not isinstance(bindings, Mapping) or set(bindings) != {
        config.worker.member_id,
        config.supervisor.member_id,
    }:
        fail("settlement bindings must be exactly the worker and supervisor")
    for role, member in zip(("worker", "supervisor"), members):
        binding = bindings.get(member.member_id)
        if (
            not isinstance(binding, Mapping)
            or "type" not in binding
        ):
            fail(
                f"settlement binding `{member.member_id}` is incompatible with "
                "its member result contract"
            )
        if not contract_descriptor_matches(
            member.result_contract,
            binding["type"],
            malformed_reason=f"{role} member contract descriptor is invalid",
        ):
            fail(
                f"settlement binding `{member.member_id}` is incompatible with "
                "its member result contract"
            )
    if not contract_descriptor_matches(
        config.settlement_result_contract,
        config.settlement_payload.get("result_type"),
        malformed_reason="settlement result contract descriptor is invalid",
    ):
        fail("settlement result contract is incompatible with the pure result type")
    for role, member in zip(("worker", "supervisor"), members):
        try:
            bind_member_result_contract(
                member,
                path=(
                    ".orchestrate/provider-supervision-validation/"
                    f"{role}-result.json"
                ),
            )
        except (TypeError, ValueError):
            fail(f"{role} result contract prototype is invalid")

    if not isinstance(config.source_ownership, ProviderSupervisionSourceOwnership):
        fail("source ownership must be typed")
    if not isinstance(config.paths, ProviderSupervisionPaths):
        fail("path plan must be typed")
    expected_paths = derive_provider_supervision_paths(
        node_id=config.node_id,
        worker_member_id=config.worker.member_id,
        supervisor_member_id=config.supervisor.member_id,
    )
    if config.paths != expected_paths:
        fail("path plan does not match the fixed member and turn roles")


def _validate_contract(
    contract: ExecutableContract,
    *,
    workflow_name: str | None,
    known_node_ids: set[str],
    known_nodes: Mapping[str, ExecutableNode],
    current_node: ExecutableNode | None,
) -> None:
    _validate_ir_payload(
        contract,
        workflow_name=workflow_name,
        known_node_ids=known_node_ids,
        known_nodes=known_nodes,
        current_node=current_node,
    )


def _validate_target_node_id(
    node_id: str | None,
    *,
    known_node_ids: set[str],
    workflow_name: str | None,
    node: ExecutableNode,
    context: str,
) -> None:
    if node_id is None:
        return
    if node_id not in known_node_ids:
        _raise_executable_ir_invalid(
            f"executable_ir_invalid: node `{node.node_id}` {context} references unknown node id `{node_id}`",
            workflow_name=workflow_name,
            node=node,
        )


def _validate_ir_payload(
    value: Any,
    *,
    workflow_name: str | None,
    known_node_ids: set[str],
    known_nodes: Mapping[str, ExecutableNode],
    current_node: ExecutableNode | None,
) -> None:
    if value is None or isinstance(value, (str, int, float, bool, Enum, Path)):
        return
    if isinstance(value, Mapping):
        for entry in value.values():
            _validate_ir_payload(
                entry,
                workflow_name=workflow_name,
                known_node_ids=known_node_ids,
                known_nodes=known_nodes,
                current_node=current_node,
            )
        return
    if isinstance(value, tuple | list):
        for entry in value:
            _validate_ir_payload(
                entry,
                workflow_name=workflow_name,
                known_node_ids=known_node_ids,
                known_nodes=known_nodes,
                current_node=current_node,
            )
        return
    if isinstance(value, (WorkflowInputAddress, NodeResultAddress, BlockOutputAddress, LoopOutputAddress, CallOutputAddress)):
        _validate_bound_address(
            value,
            workflow_name=workflow_name,
            known_node_ids=known_node_ids,
            known_nodes=known_nodes,
            current_node=current_node,
        )
        return
    if is_dataclass(value):
        module_name = type(value).__module__
        type_name = type(value).__name__
        if module_name.startswith("orchestrator.workflow_lisp"):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: executable IR contains frontend-only object `{module_name}.{type_name}`",
                workflow_name=workflow_name,
                node=current_node,
            )
        if any(fragment in type_name for fragment in _COMPILE_TIME_TYPE_NAME_FRAGMENTS):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: executable IR contains compile-time-only object `{type_name}`",
                workflow_name=workflow_name,
                node=current_node,
            )
        for field_def in fields(value):
            _validate_ir_payload(
                getattr(value, field_def.name),
                workflow_name=workflow_name,
                known_node_ids=known_node_ids,
                known_nodes=known_nodes,
                current_node=current_node,
            )
        return
    _raise_executable_ir_invalid(
        f"executable_ir_invalid: executable IR contains unsupported runtime payload `{type(value).__module__}.{type(value).__name__}`",
        workflow_name=workflow_name,
        node=current_node,
    )


def _validate_bound_address(
    address: BoundAddress,
    *,
    workflow_name: str | None,
    known_node_ids: set[str],
    known_nodes: Mapping[str, ExecutableNode],
    current_node: ExecutableNode | None,
) -> None:
    if isinstance(address, WorkflowInputAddress):
        return
    node_id = getattr(address, "node_id", None)
    if not isinstance(node_id, str) or node_id not in known_node_ids:
        message = (
            f"executable_ir_invalid: node `{current_node.node_id}` references unknown node id `{node_id}`"
            if current_node is not None
            else f"executable_ir_invalid: contract source address references unknown node id `{node_id}`"
        )
        _raise_executable_ir_invalid(
            message,
            workflow_name=workflow_name,
            node=current_node,
        )
    node = known_nodes[node_id]
    if isinstance(address, CallOutputAddress):
        if not isinstance(node, CallBoundaryNode):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: call output address `{node_id}.{address.output_name}` must reference call boundary node",
                workflow_name=workflow_name,
                node=current_node or node,
            )
        if address.output_name not in node.available_outputs:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: call output address `{node_id}.{address.output_name}` references unknown call output",
                workflow_name=workflow_name,
                node=current_node or node,
            )
        return
    if isinstance(address, LoopOutputAddress):
        if not isinstance(node, RepeatUntilFrameNode):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: repeat-until output address `{node_id}.{address.output_name}` must reference repeat-until frame node",
                workflow_name=workflow_name,
                node=current_node or node,
            )
        if address.output_name not in node.output_contracts:
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: repeat-until output address `{node_id}.{address.output_name}` references unknown repeat-until output",
                workflow_name=workflow_name,
                node=current_node or node,
            )


def _raise_executable_ir_invalid(
    message: str,
    *,
    workflow_name: str | None,
    node: ExecutableNode | None = None,
) -> None:
    subject_refs = ()
    if node is not None:
        subject_refs = (
            ValidationSubjectRef(
                subject_kind="step_id",
                subject_name=node.step_id,
                workflow_name=workflow_name,
            ),
        )
    elif workflow_name:
        subject_refs = (
            ValidationSubjectRef(
                subject_kind="workflow",
                subject_name=workflow_name,
                workflow_name=workflow_name,
            ),
        )
    raise WorkflowValidationError(
        [
            ValidationError(
                message=message,
                subject_refs=subject_refs,
            )
        ]
    )


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
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
            if serializer is not None:
                payload[field_def.name] = serializer(field_value)
                continue
            payload[field_def.name] = _json_value(field_value)
        return payload
    return value


def _provenance_json_value(provenance: WorkflowProvenance) -> dict[str, Any]:
    from orchestrator.workflow_lisp.lexical_checkpoint_restore import public_restore_metadata

    payload = _json_value(provenance)
    if not isinstance(payload, dict):
        return payload
    points = payload.get("lexical_checkpoint_points")
    if not isinstance(points, list):
        return payload
    sanitized_points: list[Any] = []
    for point in points:
        if not isinstance(point, dict):
            sanitized_points.append(point)
            continue
        sanitized = dict(point)
        restore = sanitized.get("restore")
        if isinstance(restore, Mapping):
            sanitized["restore"] = public_restore_metadata(restore)
        sanitized_points.append(sanitized)
    return {**payload, "lexical_checkpoint_points": sanitized_points}
