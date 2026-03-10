"""Immutable authored-shape workflow surface AST records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional


def empty_frozen_mapping() -> Mapping[str, Any]:
    """Return an immutable empty mapping."""
    return MappingProxyType({})


def freeze_value(value: Any) -> Any:
    """Recursively freeze JSON-like workflow values for AST storage."""
    if isinstance(value, dict):
        return MappingProxyType({str(key): freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(freeze_value(item) for item in value)
    return value


def freeze_mapping(value: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Freeze one mapping into an immutable view."""
    if not isinstance(value, Mapping):
        return empty_frozen_mapping()
    return MappingProxyType({str(key): freeze_value(item) for key, item in value.items()})


class SurfaceStepKind(str, Enum):
    """Supported authored surface step categories."""

    COMMAND = "command"
    PROVIDER = "provider"
    WAIT_FOR = "wait_for"
    ASSERT = "assert"
    SET_SCALAR = "set_scalar"
    INCREMENT_SCALAR = "increment_scalar"
    FOR_EACH = "for_each"
    REPEAT_UNTIL = "repeat_until"
    CALL = "call"
    IF = "if"
    MATCH = "match"


@dataclass(frozen=True)
class WorkflowProvenance:
    """Typed workflow-path and source-root metadata."""

    workflow_path: Path
    source_root: Path
    managed_write_root_inputs: tuple[str, ...] = ()
    imported_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportedWorkflowMetadata:
    """Typed metadata for one imported workflow binding."""

    alias: str
    workflow_path: Path
    source_root: Path
    managed_write_root_inputs: tuple[str, ...] = ()
    workflow_name: Optional[str] = None


@dataclass(frozen=True)
class SurfaceContract:
    """Typed contract wrapper used on authored workflow boundaries."""

    name: str
    kind: Optional[str]
    value_type: Optional[str]
    raw: Mapping[str, Any]
    from_ref: Any = None


@dataclass(frozen=True)
class SurfaceBranchBlock:
    """Typed authored branch block for structured if/else."""

    branch_name: str
    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    outputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceMatchCaseBlock:
    """Typed authored case block for structured match."""

    case_name: str
    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    outputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceRepeatUntilBlock:
    """Typed authored repeat-until block."""

    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    outputs: Mapping[str, SurfaceContract]
    condition: Any
    max_iterations: Optional[int]
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceFinallyBlock:
    """Typed authored workflow finalization block."""

    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceStep:
    """Typed authored step node."""

    name: str
    step_id: str
    kind: SurfaceStepKind
    authored_id: Optional[str] = None
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    when_predicate: Any = None
    assert_predicate: Any = None
    references: tuple[Any, ...] = ()
    if_condition: Any = None
    then_branch: Optional[SurfaceBranchBlock] = None
    else_branch: Optional[SurfaceBranchBlock] = None
    match_ref: Any = None
    match_cases: Mapping[str, SurfaceMatchCaseBlock] = field(default_factory=empty_frozen_mapping)
    for_each_steps: tuple["SurfaceStep", ...] = ()
    repeat_until: Optional[SurfaceRepeatUntilBlock] = None
    call_alias: Optional[str] = None
    call_bindings: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceWorkflow:
    """Typed authored workflow root."""

    version: str
    name: Optional[str]
    steps: tuple[SurfaceStep, ...]
    provenance: WorkflowProvenance
    artifacts: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    inputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    outputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    imports: Mapping[str, ImportedWorkflowMetadata] = field(default_factory=empty_frozen_mapping)
    finalization: Optional[SurfaceFinallyBlock] = None
    raw: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
