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


@dataclass(frozen=True)
class ExecutableNodeBase:
    """Common executable-node fields."""

    node_id: str
    step_id: str
    presentation_name: str
    kind: ExecutableNodeKind
    region: WorkflowRegion
    lexical_scope: tuple[str, ...]
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
    nodes: Mapping[str, ExecutableNode]
    artifacts: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    inputs: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
    outputs: Mapping[str, ExecutableContract] = field(default_factory=empty_frozen_mapping)
