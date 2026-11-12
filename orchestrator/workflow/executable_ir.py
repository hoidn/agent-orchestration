"""Immutable executable workflow IR records and bound reference addresses."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Mapping, NoReturn, Optional

from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError
from orchestrator.providers.types import (
    canonical_workflow_call_policy,
    validate_phased_delivery_carriage,
)

from .prompt_dependency_contract import (
    CompilerPromptDependencyContract,
    serialize_compiler_prompt_dependency_contract,
    validate_compiler_prompt_dependency_contract,
)
from .prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    CompilerPromptFragmentContractCarrier,
    serialize_compiler_prompt_attempt_binding_plan,
    serialize_compiler_prompt_fragment_contract,
    validate_compiler_prompt_attempt_pair,
    validate_compiler_prompt_fragment_pair,
)
from .run_ref.config import (
    BundleProgram,
    RunRefBundleCapsuleBinding,
    RunRefStaticConfig,
    validate_run_ref_bundle_capsule_binding,
    validate_run_ref_static_config_authority,
)
from .run_ref.confined_config import (
    RunRefConfinedStaticConfig,
    decode_run_ref_confined_static_config,
    encode_run_ref_confined_static_config,
)
from .run_ref.contracts import canonical_sha256
from .trial.config import (
    TrialStaticConfig,
    validate_trial_static_config_authority,
)
from .surface_ast import WorkflowProvenance, empty_frozen_mapping
from .statements import is_valid_exhaustion_diagnostic_code


WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"
RUN_REF_STEP_CONFIG_IDENTITY_SCHEMA = "run_ref_step_config_identity.v1"
TRIAL_STEP_CONFIG_IDENTITY_SCHEMA = "trial_step_config_identity.v1"
HUMAN_INPUT_MIN_TARGET_DSL_VERSION = (2, 32)


def _target_dsl_at_least(value: str, minimum: tuple[int, int]) -> bool:
    try:
        parts = tuple(int(part) for part in value.split("."))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("target DSL version is invalid") from exc
    return parts >= minimum


def validate_request_input_config(
    value: Any,
    *,
    target_dsl_version: str,
    executable: bool = False,
) -> Mapping[str, Any]:
    """Validate the closed request-input question source."""

    if not _target_dsl_at_least(target_dsl_version, HUMAN_INPUT_MIN_TARGET_DSL_VERSION):
        raise ValueError("request input requires target DSL 2.32")
    if not isinstance(value, Mapping) or set(value) != {"question"}:
        raise ValueError("request input must be {question: {literal|ref: String}}")
    question = value["question"]
    if not isinstance(question, Mapping) or len(question) != 1:
        raise ValueError("request input question must have exactly one source")
    if "literal" in question:
        if not isinstance(question["literal"], str):
            raise ValueError("request input literal question must be a String")
    elif "ref" in question:
        ref = question["ref"]
        if executable:
            if not isinstance(ref, BoundAddress):
                raise ValueError("request input question ref requires a bound address")
        elif not isinstance(ref, str) or not ref:
            raise ValueError("request input question ref must be a non-empty String")
    else:
        raise ValueError("request input question must use literal or ref")
    return value


def _serialize_provider_call_policy(
    policy: Mapping[str, object],
) -> dict[str, object]:
    return canonical_workflow_call_policy(policy)


def _validate_static_config(config: RunRefStaticConfig | RunRefConfinedStaticConfig) -> None:
    """v1 configs and confined v2 configs (`run_ref_static_config.v2`) match their canonical bytes."""
    if type(config) is RunRefConfinedStaticConfig:
        if decode_run_ref_confined_static_config(encode_run_ref_confined_static_config(config)) != config:
            raise ValueError("confined run-ref static config does not match canonical bytes")
        return
    validate_run_ref_static_config_authority(config)


def _serialize_run_ref_static_config(
    config: RunRefStaticConfig | RunRefConfinedStaticConfig,
) -> dict[str, Any]:
    _validate_static_config(config)
    return config.record


def _serialize_run_ref_capsule_binding(
    binding: RunRefBundleCapsuleBinding,
) -> dict[str, str]:
    validate_run_ref_bundle_capsule_binding(binding)
    return binding.record


def _serialize_trial_static_config(
    config: TrialStaticConfig,
) -> dict[str, Any]:
    validate_trial_static_config_authority(config)
    return config.record


class WorkflowRegion(str, Enum):
    """Top-level execution region membership."""

    BODY = "body"
    FINALIZATION = "finalization"


class ExecutableNodeKind(str, Enum):
    """Typed executable workflow node kinds."""

    COMMAND = "command"
    PROVIDER = "provider"
    PROVIDER_SUPERVISION = "provider_supervision"
    PROVIDER_PEER_GROUP = "provider_peer_group"
    RUN_REF = "run_ref"
    TRIAL = "trial"
    ADJUDICATED_PROVIDER = "adjudicated_provider"
    REQUEST_INPUT = "request_input"
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
    provider_call_policy: Mapping[str, object] | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": _serialize_provider_call_policy,
        },
    )
    provider_context: Mapping[str, Any] | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
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
        if not isinstance(self.common, StepCommonConfig):
            return
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
        validate_phased_delivery_carriage(
            self.provider_call_policy,
            prompt_attempt_identity_version=(
                self.prompt_attempt_identity_version
            ),
        )


@dataclass(frozen=True)
class RunRefStepConfig:
    """Closed executable config for one pinned child-run reference."""

    common: StepCommonConfig
    run_ref: RunRefStaticConfig | RunRefConfinedStaticConfig = field(
        metadata={"json_serializer": _serialize_run_ref_static_config},
    )
    capsule_binding: RunRefBundleCapsuleBinding | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": _serialize_run_ref_capsule_binding,
        },
    )

    def __post_init__(self) -> None:
        if type(self.common) is not StepCommonConfig:
            raise TypeError("run_ref executable common config must be StepCommonConfig")
        _validate_static_config(self.run_ref)
        if self.capsule_binding is not None:
            validate_run_ref_bundle_capsule_binding(self.capsule_binding)
            if not isinstance(self.run_ref.program, BundleProgram):
                raise ValueError(
                    "run_ref capsule binding is valid only for a bundle program"
                )

    @property
    def step_config_digest(self) -> str:
        """Bind runtime reuse to both static semantics and capsule content."""

        return canonical_sha256(
            {
                "schema_version": RUN_REF_STEP_CONFIG_IDENTITY_SCHEMA,
                "run_ref_static_config_digest": self.run_ref.digest,
                "capsule_binding": (
                    self.capsule_binding.record
                    if self.capsule_binding is not None
                    else None
                ),
            }
        )


@dataclass(frozen=True)
class TrialArmStepConfig:
    """One authored trial arm with complete E1 executable authority."""

    arm_id: str
    run_ref: RunRefStepConfig

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, str) or not self.arm_id:
            raise ValueError("trial arm id must be non-empty")
        if type(self.run_ref) is not RunRefStepConfig:
            raise TypeError("trial arm requires RunRefStepConfig")


@dataclass(frozen=True)
class TrialStepConfig:
    """Closed executable config for one bounded static trial."""

    common: StepCommonConfig
    trial: TrialStaticConfig = field(
        metadata={"json_serializer": _serialize_trial_static_config},
    )
    arms: tuple[TrialArmStepConfig, ...]

    def __post_init__(self) -> None:
        if type(self.common) is not StepCommonConfig:
            raise TypeError("trial executable common config must be StepCommonConfig")
        validate_trial_static_config_authority(self.trial)
        if not isinstance(self.arms, tuple) or any(
            type(arm) is not TrialArmStepConfig for arm in self.arms
        ):
            raise TypeError("trial executable arms must be an ordered tuple")
        if len(self.arms) != len(self.trial.arms):
            raise ValueError("trial executable arm count disagrees with static authority")
        for arm, static_arm in zip(self.arms, self.trial.arms, strict=True):
            if (
                arm.arm_id != static_arm.arm_id
                or arm.run_ref.run_ref != static_arm.run_ref
            ):
                raise ValueError(
                    "trial executable arm authority disagrees with static config"
                )

    @property
    def step_config_digest(self) -> str:
        return canonical_sha256(
            {
                "schema_version": TRIAL_STEP_CONFIG_IDENTITY_SCHEMA,
                "trial_static_config_digest": self.trial.digest,
                "result_contract_digest": self.trial.result_digest,
                "arms": [
                    {
                        "arm_id": arm.arm_id,
                        "run_ref_step_config_digest": (
                            arm.run_ref.step_config_digest
                        ),
                    }
                    for arm in self.arms
                ],
            }
        )


def derive_unbound_trial_step_config(
    trial: TrialStaticConfig,
    *,
    common: StepCommonConfig | None = None,
) -> TrialStepConfig:
    """Derive the unique pre-capsule executable carrier from static authority."""

    validate_trial_static_config_authority(trial)
    return TrialStepConfig(
        common=StepCommonConfig() if common is None else common,
        trial=trial,
        arms=tuple(
            TrialArmStepConfig(
                arm_id=arm.arm_id,
                run_ref=RunRefStepConfig(
                    common=StepCommonConfig(),
                    run_ref=arm.run_ref,
                ),
            )
            for arm in trial.arms
        ),
    )


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
class RequestInputStepConfig:
    """Executable host-input request configuration."""

    common: StepCommonConfig = field(default_factory=StepCommonConfig)
    request_input: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)


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
    exhaustion_diagnostic_code: str | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )


ExecutableStepConfig = (
    CommandStepConfig
    | ProviderStepConfig
    | RunRefStepConfig
    | TrialStepConfig
    | AdjudicatedProviderStepConfig
    | RequestInputStepConfig
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
    exhaustion_diagnostic_code: str | None = field(
        default=None,
        metadata={"json_omit_if_none": True},
    )


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

    def __post_init__(self) -> None:
        for node in self.nodes.values():
            config = getattr(node, "execution_config", None)
            if not isinstance(config, ProviderStepConfig):
                continue
            validate_compiler_prompt_attempt_pair(
                config.prompt_attempt_identity_version,
                config.compiler_prompt_attempt_binding_plan,
                fragment_contract=config.compiler_prompt_fragment_contract,
                dependency_contract=(
                    config.compiler_prompt_dependency_contract
                ),
                typed_prompt_inputs=config.typed_prompt_inputs,
                target_dsl_version=self.version,
            )
            validate_phased_delivery_carriage(
                config.provider_call_policy,
                prompt_attempt_identity_version=(
                    config.prompt_attempt_identity_version
                ),
                target_dsl_version=self.version,
            )


_LEAF_EXECUTION_CONFIG_TYPES = (
    CommandStepConfig,
    ProviderStepConfig,
    RunRefStepConfig,
    TrialStepConfig,
    AdjudicatedProviderStepConfig,
    RequestInputStepConfig,
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
    ExecutableNodeKind.RUN_REF: RunRefStepConfig,
    ExecutableNodeKind.TRIAL: TrialStepConfig,
    ExecutableNodeKind.ADJUDICATED_PROVIDER: AdjudicatedProviderStepConfig,
    ExecutableNodeKind.REQUEST_INPUT: RequestInputStepConfig,
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
        _validate_node_shape(
            node,
            workflow_name=ir.name,
            known_node_ids=known_node_ids,
            target_dsl_version=ir.version,
        )
        config = getattr(node, "execution_config", None)
        if isinstance(config, ProviderStepConfig) and config.provider_context is not None:
            from .provider_context import (
                validate_capture_output_contract, validate_provider_context_config,
            )

            try:
                validate_provider_context_config(
                    config.provider_context, step_kind="provider",
                    target_dsl_version=ir.version,
                    provider_call_policy=config.provider_call_policy,
                    executable=True,
                )
                if config.common.provider_session is not None:
                    raise ValueError("provider context requires a fresh call without provider_session")
                validate_capture_output_contract(
                    config.provider_context, config.common.output_bundle, config.common.variant_output,
                )
                context_input = config.provider_context.get("input")
                if context_input is not None:
                    address = context_input["ref"]
                    if isinstance(address, WorkflowInputAddress) and address.input_name not in ir.inputs:
                        raise ValueError("provider context input targets an unknown workflow input")
                    _validate_bound_address(
                        address, workflow_name=ir.name, known_node_ids=known_node_ids,
                        known_nodes=ir.nodes, current_node=node,
                    )
            except (TypeError, ValueError) as exc:
                _raise_executable_ir_invalid(
                    f"executable_ir_invalid: provider context is invalid: {exc}",
                    workflow_name=ir.name, node=node,
                )
        if isinstance(config, RequestInputStepConfig):
            try:
                if config.common.output_bundle is not None or config.common.variant_output is not None:
                    raise ValueError("request input has a fixed reply, not an output bundle")
                request_input = validate_request_input_config(
                    config.request_input,
                    target_dsl_version=ir.version,
                    executable=True,
                )
                question = request_input["question"]
                if "ref" in question:
                    address = question["ref"]
                    if isinstance(address, WorkflowInputAddress) and address.input_name not in ir.inputs:
                        raise ValueError("request input question targets an unknown workflow input")
                    _validate_bound_address(
                        address,
                        workflow_name=ir.name,
                        known_node_ids=known_node_ids,
                        known_nodes=ir.nodes,
                        current_node=node,
                    )
            except (TypeError, ValueError) as exc:
                _raise_executable_ir_invalid(
                    f"executable_ir_invalid: request input is invalid: {exc}",
                    workflow_name=ir.name,
                    node=node,
                )
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
    target_dsl_version: str,
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
            try:
                _validate_provider_prompt_fragment_binding(
                    node.execution_config,
                    target_dsl_version=target_dsl_version,
                )
            except (TypeError, ValueError) as exc:
                message = str(exc)
                if not message.startswith(
                    (
                        "prompt_attempt_identity_version_",
                        "prompt_attempt_binding_plan_",
                    )
                ):
                    message = (
                        "executable_ir_invalid: provider prompt fragment "
                        "contract is invalid"
                    )
                _raise_executable_ir_invalid(
                    message,
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
        if (
            node.exhaustion_diagnostic_code
            != node.execution_config.exhaustion_diagnostic_code
        ):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` has inconsistent exhaustion diagnostic metadata",
                workflow_name=workflow_name,
                node=node,
            )
        if (
            node.exhaustion_diagnostic_code is not None
            and not is_valid_exhaustion_diagnostic_code(
                node.exhaustion_diagnostic_code
            )
        ):
            _raise_executable_ir_invalid(
                f"executable_ir_invalid: node `{node.node_id}` has invalid exhaustion diagnostic metadata",
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

    if isinstance(node.execution_config, RunRefStepConfig):
        _validate_run_ref_step_config(
            node.execution_config,
            workflow_name=workflow_name,
            node=node,
            target_dsl_version=target_dsl_version,
        )
    if isinstance(node.execution_config, TrialStepConfig):
        _validate_trial_step_config(
            node.execution_config,
            workflow_name=workflow_name,
            node=node,
            target_dsl_version=target_dsl_version,
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


def _validate_run_ref_step_config(
    config: RunRefStepConfig,
    *,
    workflow_name: str | None,
    node: ExecutableNode,
    target_dsl_version: str,
) -> None:
    try:
        validate_run_ref_static_config_authority(config.run_ref)
        if config.capsule_binding is not None:
            validate_run_ref_bundle_capsule_binding(config.capsule_binding)
            if not isinstance(config.run_ref.program, BundleProgram):
                raise ValueError(
                    "capsule binding is valid only for a bundle program"
                )
    except (TypeError, ValueError) as exc:
        _raise_executable_ir_invalid(
            "executable_ir_invalid: run_ref config authority is invalid: "
            f"{exc}",
            workflow_name=workflow_name,
            node=node,
        )
    if not _target_dsl_at_least_2_24(target_dsl_version):
        _raise_executable_ir_invalid(
            "executable_ir_invalid: run_ref requires target DSL 2.24 or later",
            workflow_name=workflow_name,
            node=node,
        )


def _validate_trial_step_config(
    config: TrialStepConfig,
    *,
    workflow_name: str | None,
    node: ExecutableNode,
    target_dsl_version: str,
) -> None:
    try:
        validate_trial_static_config_authority(config.trial)
        TrialStepConfig(
            common=config.common,
            trial=config.trial,
            arms=config.arms,
        )
    except (TypeError, ValueError) as exc:
        _raise_executable_ir_invalid(
            "executable_ir_invalid: trial config authority is invalid: "
            f"{exc}",
            workflow_name=workflow_name,
            node=node,
        )
    if not _target_dsl_at_least_2_25(target_dsl_version):
        _raise_executable_ir_invalid(
            "executable_ir_invalid: trial requires target DSL 2.25 or later",
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


def _validate_provider_prompt_fragment_binding(
    config: ProviderStepConfig,
    *,
    target_dsl_version: str,
) -> None:
    """Validate fragment pairing and its required dependency-origin coupling."""

    validate_compiler_prompt_fragment_pair(
        config.compiler_prompt_fragment_contract,
        config.compiled_prompt_fragment_identity,
        config.common.expected_outputs,
    )
    validate_compiler_prompt_attempt_pair(
        config.prompt_attempt_identity_version,
        config.compiler_prompt_attempt_binding_plan,
        fragment_contract=config.compiler_prompt_fragment_contract,
        dependency_contract=config.compiler_prompt_dependency_contract,
        typed_prompt_inputs=config.typed_prompt_inputs,
        target_dsl_version=target_dsl_version,
    )
    dependency_contract = config.compiler_prompt_dependency_contract
    fragment_origin = (
        dependency_contract is not None
        and dependency_contract.origin_kind.value == "workflow_lisp_prompt_fragment"
    )
    if (config.compiler_prompt_fragment_contract is not None) != fragment_origin:
        raise ValueError(
            "fragment renderer and fragment dependency contracts must be paired"
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
    if type(value) is RunRefStaticConfig:
        try:
            validate_run_ref_static_config_authority(value)
        except (TypeError, ValueError) as exc:
            _raise_executable_ir_invalid(
                "executable_ir_invalid: run_ref config authority is invalid: "
                f"{exc}",
                workflow_name=workflow_name,
                node=current_node,
            )
        return
    if type(value) is TrialStaticConfig:
        try:
            validate_trial_static_config_authority(value)
        except (TypeError, ValueError) as exc:
            _raise_executable_ir_invalid(
                "executable_ir_invalid: trial config authority is invalid: "
                f"{exc}",
                workflow_name=workflow_name,
                node=current_node,
            )
        return
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


_CANONICAL_TARGET_COMPONENT_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def _target_dsl_at_least_2_24(value: str) -> bool:
    if not isinstance(value, str):
        return False
    raw_parts = value.split(".")
    if len(raw_parts) < 2 or any(
        _CANONICAL_TARGET_COMPONENT_RE.fullmatch(part) is None
        for part in raw_parts
    ):
        return False
    return tuple(int(part) for part in raw_parts) >= (2, 24)


def _target_dsl_at_least_2_25(value: str) -> bool:
    if not isinstance(value, str):
        return False
    raw_parts = value.split(".")
    if len(raw_parts) < 2 or any(
        _CANONICAL_TARGET_COMPONENT_RE.fullmatch(part) is None
        for part in raw_parts
    ):
        return False
    return tuple(int(part) for part in raw_parts) >= (2, 25)


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
) -> NoReturn:
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
    from orchestrator.workflow.surface_ast import public_restore_metadata

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
