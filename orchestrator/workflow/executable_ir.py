"""Immutable executable workflow IR records and bound reference addresses."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError

from .surface_ast import WorkflowProvenance, empty_frozen_mapping


WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"


class WorkflowRegion(str, Enum):
    """Top-level execution region membership."""

    BODY = "body"
    FINALIZATION = "finalization"


class ExecutableNodeKind(str, Enum):
    """Typed executable workflow node kinds."""

    COMMAND = "command"
    PROVIDER = "provider"
    ADJUDICATED_PROVIDER = "adjudicated_provider"
    WAIT_FOR = "wait_for"
    ASSERT = "assert"
    SET_SCALAR = "set_scalar"
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
    input_file: Any = None
    asset_file: Any = None
    depends_on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    asset_depends_on: tuple[Any, ...] = ()
    inject_output_contract: Optional[bool] = None
    inject_consumes: Optional[bool] = None
    prompt_consumes: Optional[tuple[Any, ...]] = None
    consumes_injection_position: Optional[str] = None
    managed_jobs: Optional[ManagedJobsConfig] = None


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
    | AdjudicatedProviderStepConfig
    | WaitForStepConfig
    | AssertStepConfig
    | SetScalarStepConfig
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


@dataclass(frozen=True)
class IfJoinNode(ExecutableNodeBase):
    """Typed if-statement join node."""

    statement_name: str = ""
    branch_outputs: Mapping[str, Mapping[str, ExecutableContract]] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class MatchCaseMarkerNode(ExecutableNodeBase):
    """Typed match-case guard marker."""

    statement_name: str = ""
    case_name: str = ""
    selector_address: Optional[BoundAddress] = None


@dataclass(frozen=True)
class MatchJoinNode(ExecutableNodeBase):
    """Typed match-statement join node."""

    statement_name: str = ""
    selector_address: Optional[BoundAddress] = None
    case_outputs: Mapping[str, Mapping[str, ExecutableContract]] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class RepeatUntilFrameNode(ExecutableNodeBase):
    """Typed repeat-until frame with nested lowered body nodes."""

    body_node_ids: tuple[str, ...] = ()
    body_entry_node_id: Optional[str] = None
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
    inputs: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    outputs: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)


_LEAF_EXECUTION_CONFIG_TYPES = (
    CommandStepConfig,
    ProviderStepConfig,
    AdjudicatedProviderStepConfig,
    WaitForStepConfig,
    AssertStepConfig,
    SetScalarStepConfig,
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
    ExecutableNodeKind.ADJUDICATED_PROVIDER: AdjudicatedProviderStepConfig,
    ExecutableNodeKind.WAIT_FOR: WaitForStepConfig,
    ExecutableNodeKind.ASSERT: AssertStepConfig,
    ExecutableNodeKind.SET_SCALAR: SetScalarStepConfig,
    ExecutableNodeKind.INCREMENT_SCALAR: IncrementScalarStepConfig,
    ExecutableNodeKind.MATERIALIZE_ARTIFACTS: MaterializeArtifactsStepConfig,
    ExecutableNodeKind.SELECT_VARIANT_OUTPUT: SelectVariantOutputStepConfig,
}
_COMPILE_TIME_TYPE_NAME_FRAGMENTS = ("ProcRef", "WorkflowRef", "SourceSpan", "Syntax")


def workflow_executable_ir_to_json(ir: ExecutableWorkflow) -> dict[str, Any]:
    """Serialize executable IR deterministically from the owning shared module."""

    return {
        "schema_version": ir.schema_version,
        "version": ir.version,
        "name": ir.name,
        "provenance": _json_value(ir.provenance),
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
        "inputs": {
            name: _json_value(contract)
            for name, contract in sorted(ir.inputs.items())
        },
        "outputs": {
            name: _json_value(contract)
            for name, contract in sorted(ir.outputs.items())
        },
    }


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
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    return value
