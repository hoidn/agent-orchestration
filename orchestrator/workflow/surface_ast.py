"""Immutable authored-shape workflow surface AST records."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .prompt_dependency_contract import CompilerPromptDependencyContract
from .prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    CompilerPromptFragmentContractCarrier,
    serialize_compiler_prompt_attempt_binding_plan,
    validate_compiler_prompt_attempt_pair,
    validate_compiler_prompt_fragment_pair,
)

from .state_layout import GeneratedPathAllocation


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
    PROVIDER_SUPERVISION = "provider_supervision"
    PROVIDER_PEER_GROUP = "provider_peer_group"
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
    REPEAT_UNTIL = "repeat_until"
    CALL = "call"
    IF = "if"
    MATCH = "match"


@dataclass(frozen=True)
class SurfaceOnHandler:
    """Typed authored control-flow handler."""

    goto: Optional[str] = None


@dataclass(frozen=True)
class SurfaceOnConfig:
    """Typed authored `on` routing configuration."""

    success: Optional[SurfaceOnHandler] = None
    failure: Optional[SurfaceOnHandler] = None
    always: Optional[SurfaceOnHandler] = None


@dataclass(frozen=True)
class SurfaceManagedJobsRoutes:
    """Typed authored managed-job outcome routing."""

    complete: str
    failed: str
    invalid: str
    outstanding: str


@dataclass(frozen=True)
class SurfaceManagedJobsConfig:
    """Typed authored managed-job provider-step modifier."""

    policy: str
    watch_roots: tuple[str, ...]
    backend: str
    poll_budget_sec: int
    on: SurfaceManagedJobsRoutes


@dataclass(frozen=True)
class SurfaceStepCommonConfig:
    """Typed authored step fields shared across executable step kinds."""

    on: Optional[SurfaceOnConfig] = None
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
class PrivateExecContextBinding:
    """Structured runtime-owned context binding metadata carried by the bundle."""

    binding_id: str
    source_param_name: str
    context_family: str
    bridge_class: str
    generated_input_names: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()
    derived_phase_identity: str | None = None
    allocation_ids: tuple[str, ...] = ()
    projection_hints: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    source_provenance: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class WorkflowProvenance:
    """Typed workflow-path and source-root metadata."""

    workflow_path: Path
    source_root: Path
    generated_path_allocations: tuple[GeneratedPathAllocation, ...] = ()
    managed_write_root_inputs: tuple[str, ...] = ()
    runtime_context_inputs: tuple[str, ...] = ()
    private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    imported_aliases: tuple[str, ...] = ()
    frontend_kind: str | None = None
    frontend_build_root: Path | None = None
    frontend_source_trace_path: Path | None = None
    frontend_entry_workflow: str | None = None
    frontend_source_map_schema_version: str | None = None
    frontend_source_map_coverage: Mapping[str, str] | None = None
    frontend_persisted_surface_path: Path | None = None
    frontend_persisted_surface_schema_version: str | None = None
    frontend_persisted_surface_entry_workflow: str | None = None
    frontend_persisted_surface_sha256: str | None = None
    lexical_checkpoint_points: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ImportedWorkflowMetadata:
    """Typed metadata for one imported workflow binding."""

    alias: str
    workflow_path: Path
    source_root: Path
    generated_path_allocations: tuple[GeneratedPathAllocation, ...] = ()
    managed_write_root_inputs: tuple[str, ...] = ()
    runtime_context_inputs: tuple[str, ...] = ()
    private_exec_context_bindings: tuple[PrivateExecContextBinding, ...] = ()
    compatibility_bridge_inputs: tuple[str, ...] = ()
    workflow_name: Optional[str] = None
    output_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class SurfaceContract:
    """Typed contract wrapper used on authored workflow boundaries."""

    name: str
    kind: Optional[str]
    value_type: Optional[str]
    definition: Mapping[str, Any]
    from_ref: Any = None


@dataclass(frozen=True)
class SurfaceBranchBlock:
    """Typed authored branch block for structured if/else."""

    branch_name: str
    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    outputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceMatchCaseBlock:
    """Typed authored case block for structured match."""

    case_name: str
    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    outputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)


@dataclass(frozen=True)
class SurfaceRepeatUntilBlock:
    """Typed authored repeat-until block."""

    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]
    outputs: Mapping[str, SurfaceContract]
    condition: Any
    max_iterations: Optional[int]
    on_exhausted_outputs: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    exhaustion_diagnostic_code: str | None = None


@dataclass(frozen=True)
class SurfaceFinallyBlock:
    """Typed authored workflow finalization block."""

    token: str
    step_id: str
    steps: tuple["SurfaceStep", ...]


@dataclass(frozen=True)
class SurfaceStep:
    """Typed authored step node."""

    name: str
    step_id: str
    kind: SurfaceStepKind
    authored_id: Optional[str] = None
    common: SurfaceStepCommonConfig = field(default_factory=SurfaceStepCommonConfig)
    when_predicate: Any = None
    assert_predicate: Any = None
    references: tuple[Any, ...] = ()
    command: Any = ()
    provider: Optional[str] = None
    provider_params: Any = None
    provider_call_policy: Optional[Mapping[str, str]] = None
    managed_jobs: Optional[SurfaceManagedJobsConfig] = None
    adjudicated_provider: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    input_file: Any = None
    asset_file: Any = None
    depends_on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    asset_depends_on: tuple[Any, ...] = ()
    inject_output_contract: Optional[bool] = None
    inject_consumes: Optional[bool] = None
    prompt_consumes: Optional[tuple[Any, ...]] = None
    typed_prompt_inputs: tuple[Any, ...] = ()
    consumes_injection_position: Optional[str] = None
    compiler_prompt_dependency_contract: CompilerPromptDependencyContract | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    compiler_prompt_fragment_contract: CompilerPromptFragmentContractCarrier | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
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
    provider_supervision: Any = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    provider_peer_group: Any = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )
    wait_for: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    set_scalar: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    resource_transition: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    pure_projection: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    materialize_view: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    increment_scalar: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    materialize_artifacts: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    select_variant_output: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    if_condition: Any = None
    then_branch: Optional[SurfaceBranchBlock] = None
    else_branch: Optional[SurfaceBranchBlock] = None
    match_ref: Any = None
    match_cases: Mapping[str, SurfaceMatchCaseBlock] = field(default_factory=empty_frozen_mapping)
    for_each_items: tuple[Any, ...] = ()
    for_each_items_from: Optional[str] = None
    for_each_item_name: str = "item"
    for_each_steps: tuple["SurfaceStep", ...] = ()
    repeat_until: Optional[SurfaceRepeatUntilBlock] = None
    call_alias: Optional[str] = None
    call_bindings: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)

    def __post_init__(self) -> None:
        validate_compiler_prompt_fragment_pair(
            self.compiler_prompt_fragment_contract,
            self.compiled_prompt_fragment_identity,
            self.common.expected_outputs,
        )
        validate_compiler_prompt_attempt_pair(
            self.prompt_attempt_identity_version,
            self.compiler_prompt_attempt_binding_plan,
            fragment_contract=self.compiler_prompt_fragment_contract,
            dependency_contract=self.compiler_prompt_dependency_contract,
            typed_prompt_inputs=self.typed_prompt_inputs,
        )


@dataclass(frozen=True)
class SurfaceWorkflow:
    """Typed authored workflow root."""

    version: str
    name: Optional[str]
    steps: tuple[SurfaceStep, ...]
    provenance: WorkflowProvenance
    strict_flow: bool = True
    context: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    providers: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    secrets: tuple[str, ...] = ()
    inbox_dir: Optional[str] = None
    processed_dir: Optional[str] = None
    failed_dir: Optional[str] = None
    task_extension: Optional[str] = None
    max_transitions: Optional[int] = None
    artifacts: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    inputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    outputs: Mapping[str, SurfaceContract] = field(default_factory=empty_frozen_mapping)
    imports: Mapping[str, ImportedWorkflowMetadata] = field(default_factory=empty_frozen_mapping)
    finalization: Optional[SurfaceFinallyBlock] = None
    result_guidance: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for step in _iter_surface_steps(
            (
                *self.steps,
                *(
                    ()
                    if self.finalization is None
                    else self.finalization.steps
                ),
            )
        ):
            if step.kind is not SurfaceStepKind.PROVIDER:
                continue
            validate_compiler_prompt_attempt_pair(
                step.prompt_attempt_identity_version,
                step.compiler_prompt_attempt_binding_plan,
                fragment_contract=step.compiler_prompt_fragment_contract,
                dependency_contract=(
                    step.compiler_prompt_dependency_contract
                ),
                typed_prompt_inputs=step.typed_prompt_inputs,
                target_dsl_version=self.version,
            )


def _iter_surface_steps(
    steps: tuple[SurfaceStep, ...],
):
    for step in steps:
        yield step
        if step.then_branch is not None:
            yield from _iter_surface_steps(step.then_branch.steps)
        if step.else_branch is not None:
            yield from _iter_surface_steps(step.else_branch.steps)
        for case in step.match_cases.values():
            yield from _iter_surface_steps(case.steps)
        yield from _iter_surface_steps(step.for_each_steps)
        if step.repeat_until is not None:
            yield from _iter_surface_steps(step.repeat_until.steps)
