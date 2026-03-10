"""Immutable executable workflow IR records and bound reference addresses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional

from .surface_ast import WorkflowProvenance, empty_frozen_mapping


class WorkflowRegion(str, Enum):
    """Top-level execution region membership."""

    BODY = "body"
    FINALIZATION = "finalization"


class ExecutableNodeKind(str, Enum):
    """Typed executable workflow node kinds."""

    COMMAND = "command"
    PROVIDER = "provider"
    WAIT_FOR = "wait_for"
    ASSERT = "assert"
    SET_SCALAR = "set_scalar"
    INCREMENT_SCALAR = "increment_scalar"
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
    raw: Mapping[str, Any]
    source_address: Optional[BoundAddress] = None


def _compatibility_value(value: Any) -> Any:
    """Convert frozen execution-config values into plain runtime payloads."""
    if isinstance(value, Mapping):
        return {str(key): _compatibility_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_compatibility_value(item) for item in value]
    if isinstance(value, list):
        return [_compatibility_value(item) for item in value]
    return value


def _set_runtime_field(
    step: dict[str, Any],
    field_name: str,
    value: Any,
    *,
    include_empty: bool = False,
) -> None:
    """Attach one config field to a runtime step payload when present."""
    if value is None:
        return
    if not include_empty and isinstance(value, Mapping) and not value:
        return
    if not include_empty and isinstance(value, (list, tuple)) and not value:
        return
    step[field_name] = _compatibility_value(value)


@dataclass(frozen=True)
class StepCommonConfig:
    """Runtime-relevant common step fields carried by executable nodes."""

    on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    consumes: tuple[Any, ...] = ()
    consume_bundle: Any = None
    publishes: tuple[Any, ...] = ()
    expected_outputs: tuple[Any, ...] = ()
    output_bundle: Any = None
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
class ProviderStepConfig:
    """Executable provider-step config."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    provider: str = ""
    provider_params: Any = None
    input_file: Any = None
    asset_file: Any = None
    depends_on: tuple[Any, ...] = ()
    asset_depends_on: tuple[Any, ...] = ()
    inject_output_contract: Optional[bool] = None
    inject_consumes: Optional[bool] = None
    prompt_consumes: tuple[Any, ...] = ()
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


ExecutableStepConfig = (
    CommandStepConfig
    | ProviderStepConfig
    | WaitForStepConfig
    | AssertStepConfig
    | SetScalarStepConfig
    | IncrementScalarStepConfig
    | CallStepConfig
    | ForEachStepConfig
    | RepeatUntilStepConfig
)


def _render_common_config(step: dict[str, Any], common: StepCommonConfig) -> None:
    """Project shared runtime fields from one executable config."""
    _set_runtime_field(step, "on", common.on)
    _set_runtime_field(step, "consumes", common.consumes)
    _set_runtime_field(step, "consume_bundle", common.consume_bundle)
    _set_runtime_field(step, "publishes", common.publishes)
    _set_runtime_field(step, "expected_outputs", common.expected_outputs)
    _set_runtime_field(step, "output_bundle", common.output_bundle)
    if common.persist_artifacts_in_state is not None:
        step["persist_artifacts_in_state"] = common.persist_artifacts_in_state
    _set_runtime_field(step, "provider_session", common.provider_session)
    if common.max_visits is not None:
        step["max_visits"] = common.max_visits
    _set_runtime_field(step, "retries", common.retries)
    _set_runtime_field(step, "env", common.env)
    _set_runtime_field(step, "secrets", common.secrets)
    _set_runtime_field(step, "timeout_sec", common.timeout_sec)
    _set_runtime_field(step, "output_capture", common.output_capture)
    _set_runtime_field(step, "output_file", common.output_file)
    if common.allow_parse_error is not None:
        step["allow_parse_error"] = common.allow_parse_error


def materialize_execution_config(
    config: ExecutableStepConfig,
    *,
    step_name: str,
    step_id: str,
    nested_steps: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Render one executable config into the mutable runtime step shape."""
    step: dict[str, Any] = {
        "name": step_name,
        "step_id": step_id,
    }

    if isinstance(config, CommandStepConfig):
        _render_common_config(step, config.common)
        _set_runtime_field(step, "command", config.command, include_empty=True)
        return step

    if isinstance(config, ProviderStepConfig):
        _render_common_config(step, config.common)
        step["provider"] = config.provider
        _set_runtime_field(step, "provider_params", config.provider_params)
        _set_runtime_field(step, "input_file", config.input_file)
        _set_runtime_field(step, "asset_file", config.asset_file)
        _set_runtime_field(step, "depends_on", config.depends_on)
        _set_runtime_field(step, "asset_depends_on", config.asset_depends_on)
        if config.inject_output_contract is not None:
            step["inject_output_contract"] = config.inject_output_contract
        if config.inject_consumes is not None:
            step["inject_consumes"] = config.inject_consumes
        _set_runtime_field(step, "prompt_consumes", config.prompt_consumes)
        if config.consumes_injection_position is not None:
            step["consumes_injection_position"] = config.consumes_injection_position
        return step

    if isinstance(config, WaitForStepConfig):
        _render_common_config(step, config.common)
        _set_runtime_field(step, "wait_for", config.wait_for, include_empty=True)
        return step

    if isinstance(config, AssertStepConfig):
        _render_common_config(step, config.common)
        return step

    if isinstance(config, SetScalarStepConfig):
        _render_common_config(step, config.common)
        _set_runtime_field(step, "set_scalar", config.set_scalar, include_empty=True)
        return step

    if isinstance(config, IncrementScalarStepConfig):
        _render_common_config(step, config.common)
        _set_runtime_field(step, "increment_scalar", config.increment_scalar, include_empty=True)
        return step

    if isinstance(config, CallStepConfig):
        _render_common_config(step, config.common)
        step["call"] = config.call
        return step

    if isinstance(config, ForEachStepConfig):
        _render_common_config(step, config.common)
        for_each: dict[str, Any] = {}
        if config.items_from is not None:
            for_each["items_from"] = config.items_from
        else:
            for_each["items"] = _compatibility_value(config.items)
        if config.item_name != "item":
            for_each["as"] = config.item_name
        if nested_steps is not None:
            for_each["steps"] = nested_steps
        step["for_each"] = for_each
        return step

    _render_common_config(step, config.common)
    repeat_until: dict[str, Any] = {
        "id": config.body_id,
        "max_iterations": config.max_iterations,
    }
    if nested_steps is not None:
        repeat_until["steps"] = nested_steps
    step["repeat_until"] = repeat_until
    return step


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
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
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
