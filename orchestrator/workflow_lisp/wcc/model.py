"""Workflow Core Calculus data model and identity helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.result_contract import (
    is_transportable_type_descriptor,
    validate_run_ref_result_descriptor,
)
from orchestrator.workflow.type_descriptor import (
    validate_compiler_normalized_type_descriptor,
)

from ..effects import EMPTY_EFFECT_SUMMARY, EffectSummary
from ..spans import SourceSpan
from ..type_env import TypeRef

if TYPE_CHECKING:
    from orchestrator.workflow.run_ref.config import RunRefProgram
    from orchestrator.workflow.run_ref.source import SourceRequest


WCC_M1_ROUTE_SCHEMA_VERSION = "wcc_m1"
WCC_M2_ROUTE_SCHEMA_VERSION = "wcc_m2"
WCC_M3_ROUTE_SCHEMA_VERSION = "wcc_m3"
WCC_M4_ROUTE_SCHEMA_VERSION = "wcc_m4"
_RUN_REF_SITE_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RUN_REF_RESULT_NAME = re.compile(r"RunRefResult\$[0-9a-f]{16}\Z")
_RUN_REF_INPUT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_TRIAL_RESULT_NAME = re.compile(r"TrialResult\$[0-9a-f]{16}\Z")


def _stable_identity_digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


@dataclass(frozen=True)
class WccNodeMetadata:
    """Stable semantic identity and provenance attached to every WCC node."""

    node_id: str
    type_ref: TypeRef
    scope_id: str
    source_span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()
    effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY
    proof_context: tuple[object, ...] = ()
    allocation_requests: tuple[object, ...] = ()
    phase_scope: "WccPhaseScope | None" = None


@dataclass(frozen=True)
class WccPhaseScope:
    """Authored intrinsic `with-phase` lowering context carried transparently through WCC."""

    ctx_expr: object
    phase_name: str
    source_span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()


@dataclass(frozen=True)
class WccIdentityFactory:
    """Deterministic semantic identity generator for one lexical WCC scope."""

    owner_name: str
    lexical_owner_chain: tuple[str, ...] = ()
    route_schema_version: str = WCC_M1_ROUTE_SCHEMA_VERSION

    @property
    def scope_id(self) -> str:
        digest = _stable_identity_digest(
            {
                "route_schema_version": self.route_schema_version,
                "owner_name": self.owner_name,
                "lexical_owner_chain": self.lexical_owner_chain,
            }
        )
        return f"wcc-scope:{self.route_schema_version}:{digest}"

    def child_scope(self, scope_role: str, *, authored_binding_name: str | None = None) -> "WccIdentityFactory":
        segment = scope_role if authored_binding_name is None else f"{scope_role}:{authored_binding_name}"
        return WccIdentityFactory(
            owner_name=self.owner_name,
            lexical_owner_chain=(*self.lexical_owner_chain, segment),
            route_schema_version=self.route_schema_version,
        )

    def _metadata(
        self,
        *,
        node_kind: str,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        digest = _stable_identity_digest(
            {
                "route_schema_version": self.route_schema_version,
                "owner_name": self.owner_name,
                "lexical_owner_chain": self.lexical_owner_chain,
                "node_kind": node_kind,
                "role": role,
            }
        )
        return WccNodeMetadata(
            node_id=f"wcc-node:{self.route_schema_version}:{digest}",
            type_ref=type_ref,
            scope_id=self.scope_id,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )

    def atom_metadata(
        self,
        *,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        return self._metadata(
            node_kind="atom",
            role=role,
            type_ref=type_ref,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )

    def value_metadata(
        self,
        *,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        return self._metadata(
            node_kind="value",
            role=role,
            type_ref=type_ref,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )

    def body_metadata(
        self,
        *,
        role: str,
        type_ref: TypeRef,
        source_span: SourceSpan,
        form_path: tuple[str, ...],
        expansion_stack: tuple[object, ...] = (),
        effect_summary: EffectSummary = EMPTY_EFFECT_SUMMARY,
        proof_context: tuple[object, ...] = (),
        allocation_requests: tuple[object, ...] = (),
        phase_scope: "WccPhaseScope | None" = None,
    ) -> WccNodeMetadata:
        return self._metadata(
            node_kind="body",
            role=role,
            type_ref=type_ref,
            source_span=source_span,
            form_path=form_path,
            expansion_stack=expansion_stack,
            effect_summary=effect_summary,
            proof_context=proof_context,
            allocation_requests=allocation_requests,
            phase_scope=phase_scope,
        )


@dataclass(frozen=True)
class WccLiteralAtom:
    metadata: WccNodeMetadata
    value: str | int | bool
    literal_kind: str


@dataclass(frozen=True)
class WccNameAtom:
    metadata: WccNodeMetadata
    name: str


@dataclass(frozen=True)
class WccFieldAccessAtom:
    metadata: WccNodeMetadata
    base: "WccAtom"
    fields: tuple[str, ...]


@dataclass(frozen=True)
class WccPhaseTargetAtom:
    metadata: WccNodeMetadata
    target_name: str


@dataclass(frozen=True)
class WccRecordAtom:
    metadata: WccNodeMetadata
    type_name: str
    fields: tuple[tuple[str, "WccValue"], ...]


@dataclass(frozen=True)
class WccPureOp:
    metadata: WccNodeMetadata
    operator: str
    args: tuple["WccValue", ...]
    field_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WccOpaqueFrontendValue:
    metadata: WccNodeMetadata
    expr: object


WccAtom = WccLiteralAtom | WccNameAtom | WccFieldAccessAtom | WccPhaseTargetAtom | WccRecordAtom | WccOpaqueFrontendValue


@dataclass(frozen=True)
class WccInject:
    metadata: WccNodeMetadata
    union_name: str
    variant_name: str
    fields: tuple[tuple[str, WccValue], ...]


WccValue = WccAtom | WccInject | WccPureOp


@dataclass(frozen=True, init=False)
class WccRunRefPayload:
    """Closed static run-ref facts carried separately from dynamic WCC inputs."""

    source: SourceRequest
    program: RunRefProgram
    site_digest: str
    generated_result_type: str
    result_digest: str
    allow_nested_structures: bool
    _result_descriptor_json: bytes = field(repr=False)
    _input_type_descriptor_rows: tuple[tuple[str, bytes], ...] = field(
        repr=False
    )

    def __init__(
        self,
        *,
        source: SourceRequest,
        program: RunRefProgram,
        site_digest: str,
        generated_result_type: str,
        result_descriptor: Mapping[str, object],
        result_digest: str,
        allow_nested_structures: bool = False,
        input_type_descriptors: tuple[
            tuple[str, Mapping[str, object]], ...
        ],
    ) -> None:
        from orchestrator.workflow.run_ref.config import BundleProgram, PathProgram
        from orchestrator.workflow.run_ref.source import (
            SourceRequest,
            canonical_source_request,
            source_request_from_dict,
        )

        if not isinstance(source, SourceRequest):
            raise TypeError("WCC run-ref source must be a SourceRequest")
        if not isinstance(program, (BundleProgram, PathProgram)):
            raise TypeError("WCC run-ref program must be a closed program")
        if not isinstance(site_digest, str) or _RUN_REF_SITE_DIGEST.fullmatch(
            site_digest
        ) is None:
            raise ValueError("WCC run-ref site digest is invalid")
        if (
            not isinstance(generated_result_type, str)
            or _RUN_REF_RESULT_NAME.fullmatch(generated_result_type) is None
            or generated_result_type.removeprefix("RunRefResult$")
            != site_digest[:16]
        ):
            raise ValueError("WCC run-ref generated result identity is invalid")
        if type(allow_nested_structures) is not bool:
            raise TypeError("WCC run-ref nested-transport capability must be boolean")
        validate_run_ref_result_descriptor(
            result_descriptor,
            expected_generated_name=generated_result_type,
            expected_digest=result_digest,
            allow_nested_structures=allow_nested_structures,
        )
        if isinstance(program, PathProgram):
            value_descriptor = result_descriptor["envelope"]["fields"][0]["type"]
            refinement = program.return_refinement
            if refinement is None:
                if value_descriptor != {"kind": "primitive", "name": "Value"}:
                    raise ValueError(
                        "WCC path run-ref without refinement requires Value"
                    )
            elif refinement != value_descriptor:
                raise ValueError(
                    "WCC path run-ref refinement does not match its result"
                )
        if not isinstance(input_type_descriptors, tuple):
            raise TypeError("WCC run-ref input descriptors must be a tuple")
        frozen_inputs: list[tuple[str, bytes]] = []
        seen: set[str] = set()
        for name, descriptor in input_type_descriptors:
            if (
                not isinstance(name, str)
                or _RUN_REF_INPUT_NAME.fullmatch(name) is None
                or name in seen
            ):
                raise ValueError("WCC run-ref input name is invalid or repeated")
            validate_compiler_normalized_type_descriptor(
                descriptor,
                context=f"wcc_run_ref_input.{name}",
            )
            if not is_transportable_type_descriptor(
                descriptor,
                allow_nested_structures=allow_nested_structures,
            ):
                raise ValueError("WCC run-ref input type is not transportable")
            seen.add(name)
            frozen_inputs.append((name, canonical_json_bytes(descriptor)))

        canonical_source = source_request_from_dict(
            canonical_source_request(source)
        )
        object.__setattr__(self, "source", canonical_source)
        object.__setattr__(self, "program", program)
        object.__setattr__(self, "site_digest", site_digest)
        object.__setattr__(self, "generated_result_type", generated_result_type)
        object.__setattr__(self, "result_digest", result_digest)
        object.__setattr__(
            self,
            "allow_nested_structures",
            allow_nested_structures,
        )
        object.__setattr__(
            self,
            "_result_descriptor_json",
            canonical_json_bytes(result_descriptor),
        )
        object.__setattr__(
            self,
            "_input_type_descriptor_rows",
            tuple(frozen_inputs),
        )

    @property
    def result_descriptor(self) -> dict[str, object]:
        return json.loads(self._result_descriptor_json)

    @property
    def input_type_descriptors(
        self,
    ) -> tuple[tuple[str, dict[str, object]], ...]:
        return tuple(
            (name, json.loads(descriptor_json))
            for name, descriptor_json in self._input_type_descriptor_rows
        )


@dataclass(frozen=True)
class WccTrialArmPayload:
    """One closed nested E1 payload and its dynamic WCC keyword names."""

    arm_id: str
    run_ref: WccRunRefPayload
    input_keywords: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, str) or not self.arm_id:
            raise ValueError("WCC trial arm id must be non-empty")
        if not isinstance(self.run_ref, WccRunRefPayload):
            raise TypeError("WCC trial arm requires a closed run-ref payload")
        if not isinstance(self.input_keywords, tuple):
            raise TypeError("WCC trial arm input keywords must be a tuple")
        source_names = tuple(name for name, _ in self.input_keywords)
        keyword_names = tuple(name for _, name in self.input_keywords)
        if source_names != tuple(
            name for name, _ in self.run_ref.input_type_descriptors
        ):
            raise ValueError("WCC trial arm inputs disagree with run-ref payload")
        if len(set(keyword_names)) != len(keyword_names) or any(
            _RUN_REF_INPUT_NAME.fullmatch(name) is None for name in keyword_names
        ):
            raise ValueError("WCC trial arm keyword identities are invalid")


@dataclass(frozen=True, init=False)
class WccTrialPayload:
    """Closed static trial facts carried separately from dynamic arm inputs."""

    arms: tuple[WccTrialArmPayload, ...]
    site_digest: str
    generated_result_type: str
    result_digest: str
    reps: int
    max_concurrency: int
    _evaluation_json: bytes = field(repr=False)
    _budget_json: bytes = field(repr=False)
    _result_descriptor_json: bytes = field(repr=False)

    def __init__(
        self,
        *,
        arms: tuple[WccTrialArmPayload, ...],
        site_digest: str,
        generated_result_type: str,
        result_descriptor: Mapping[str, object],
        result_digest: str,
        reps: int,
        max_concurrency: int,
        evaluation: Mapping[str, object],
        budget: Mapping[str, object],
    ) -> None:
        if (
            not isinstance(arms, tuple)
            or not 2 <= len(arms) <= 16
            or any(not isinstance(arm, WccTrialArmPayload) for arm in arms)
        ):
            raise ValueError("WCC trial requires 2-16 typed arms")
        arm_ids = tuple(arm.arm_id for arm in arms)
        if len(set(arm_ids)) != len(arm_ids):
            raise ValueError("WCC trial arm ids must be unique")
        keyword_names = tuple(
            keyword
            for arm in arms
            for _, keyword in arm.input_keywords
        )
        if len(set(keyword_names)) != len(keyword_names):
            raise ValueError("WCC trial input keyword identities must be unique")
        if not isinstance(site_digest, str) or _RUN_REF_SITE_DIGEST.fullmatch(
            site_digest
        ) is None:
            raise ValueError("WCC trial site digest is invalid")
        if (
            not isinstance(generated_result_type, str)
            or _TRIAL_RESULT_NAME.fullmatch(generated_result_type) is None
            or generated_result_type.removeprefix("TrialResult$")
            != site_digest[:16]
        ):
            raise ValueError("WCC trial generated result identity is invalid")
        if type(reps) is not int or not 1 <= reps <= 64 or len(arms) * reps > 256:
            raise ValueError("WCC trial repetitions are invalid")
        if (
            type(max_concurrency) is not int
            or not 1 <= max_concurrency <= 32
            or max_concurrency > len(arms) * reps
        ):
            raise ValueError("WCC trial concurrency is invalid")
        descriptor = dict(result_descriptor)
        if set(descriptor) != {"schema", "envelope"}:
            raise ValueError("WCC trial result descriptor is not closed")
        validate_compiler_normalized_type_descriptor(
            descriptor["envelope"],
            context="wcc_trial_result",
        )
        if descriptor["envelope"].get("name") != generated_result_type:
            raise ValueError("WCC trial result descriptor identity changed")
        from orchestrator.workflow.run_ref.contracts import canonical_sha256

        if canonical_sha256(descriptor) != result_digest:
            raise ValueError("WCC trial result digest is invalid")
        object.__setattr__(self, "arms", arms)
        object.__setattr__(self, "site_digest", site_digest)
        object.__setattr__(self, "generated_result_type", generated_result_type)
        object.__setattr__(self, "result_digest", result_digest)
        object.__setattr__(self, "reps", reps)
        object.__setattr__(self, "max_concurrency", max_concurrency)
        object.__setattr__(self, "_evaluation_json", canonical_json_bytes(evaluation))
        object.__setattr__(self, "_budget_json", canonical_json_bytes(budget))
        object.__setattr__(
            self,
            "_result_descriptor_json",
            canonical_json_bytes(descriptor),
        )

    @property
    def evaluation(self) -> dict[str, object]:
        return json.loads(self._evaluation_json)

    @property
    def budget(self) -> dict[str, object]:
        return json.loads(self._budget_json)

    @property
    def result_descriptor(self) -> dict[str, object]:
        return json.loads(self._result_descriptor_json)


@dataclass(frozen=True)
class WccPerform:
    metadata: WccNodeMetadata
    perform_kind: str
    target_name: str
    prompt_name: str | None
    positional_args: tuple[WccValue, ...]
    keyword_args: tuple[tuple[str, WccValue], ...]
    returns_type_name: str | None
    operation_payload: object | None = None


@dataclass(frozen=True)
class WccSpecializationCapture:
    """One bind-site value routed to an exact specialization boundary."""

    owner_kind: str
    argument_index: int | None
    source_name: str
    value: WccValue


@dataclass(frozen=True)
class WccCall:
    metadata: WccNodeMetadata
    callee_name: str
    specialized_callee_name: str
    args: tuple[WccValue, ...]
    specialization_captures: tuple[
        WccSpecializationCapture,
        ...,
    ] = ()
    proc_ref_callee_source: str | None = None
    proc_ref_callee_masks_deferred: bool = False
    proc_ref_argument_sources: tuple[
        tuple[int, str, bool],
        ...,
    ] = ()


@dataclass(frozen=True)
class WccProviderSupervisionMember:
    metadata: WccNodeMetadata
    binding_metadata: WccNodeMetadata
    binding_name: str
    normalized_body: "WccBody"
    provider_binding_name: str | None = None


@dataclass(frozen=True)
class WccProviderSupervision:
    metadata: WccNodeMetadata
    observation_metadata: WccNodeMetadata
    members: tuple[WccProviderSupervisionMember, ...]
    supervisor_name: str
    worker_name: str
    settlement_body: "WccBody"


@dataclass(frozen=True)
class WccProviderPeerGroupMember:
    metadata: WccNodeMetadata
    binding_metadata: WccNodeMetadata
    binding_name: str
    normalized_body: "WccBody"
    provider_binding_name: str | None = None
    lexical_capture_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WccProviderPeerGroup:
    metadata: WccNodeMetadata
    members: tuple[WccProviderPeerGroupMember, ...]
    settlement_body: "WccBody"


WccBindingValue = (
    WccValue
    | WccPerform
    | WccCall
    | WccProviderSupervision
    | WccProviderPeerGroup
)


@dataclass(frozen=True)
class WccRunProviderPhasePayload:
    phase_name: str
    ctx_expr: WccValue
    inputs_expr: WccValue
    provider_name: str
    prompt_name: str


@dataclass(frozen=True)
class WccProduceOneOfPayload:
    ctx_expr: WccValue
    provider_name: str
    prompt_name: str
    producer_inputs: tuple[WccValue, ...]
    candidates: tuple[object, ...]


@dataclass(frozen=True)
class WccResumeOrStartPayload:
    resume_name: str
    ctx_expr: WccValue
    resume_from_expr: WccValue
    valid_when: tuple[str, ...]
    start_value: WccBindingValue
    validation_spec: object | None


@dataclass(frozen=True)
class WccCaseArm:
    variant_name: str
    binding_name: str
    binding_type_ref: TypeRef
    body: "WccBody"


@dataclass(frozen=True)
class WccCase:
    metadata: WccNodeMetadata
    subject: WccAtom
    arms: tuple[WccCaseArm, ...]


@dataclass(frozen=True)
class WccIf:
    metadata: WccNodeMetadata
    condition: WccValue
    condition_shape: object
    then_body: "WccBody"
    else_body: "WccBody"


@dataclass(frozen=True)
class WccJoinParam:
    name: str
    type_ref: TypeRef


@dataclass(frozen=True)
class WccJoin:
    metadata: WccNodeMetadata
    join_name: str
    params: tuple[WccJoinParam, ...]
    body: "WccBody"
    continuation: "WccBody"


@dataclass(frozen=True)
class WccJump:
    metadata: WccNodeMetadata
    join_name: str
    args: tuple[WccValue, ...]


@dataclass(frozen=True)
class WccLoopRole:
    frame_role: str = "loop_frame"
    iteration_role: str = "loop_iteration"


@dataclass(frozen=True)
class WccLoopContinue:
    metadata: WccNodeMetadata
    target_name: str
    state_args: tuple[WccValue, ...]


@dataclass(frozen=True)
class WccLoopDone:
    metadata: WccNodeMetadata
    result: WccValue
    state: WccValue | None = None


@dataclass(frozen=True)
class WccRecJoin:
    metadata: WccNodeMetadata
    loop_name: str
    params: tuple[WccJoinParam, ...]
    budget: WccValue
    body: "WccBody"
    exhaustion: "WccBody | None"
    initial_state: WccValue | None = None
    roles: WccLoopRole = WccLoopRole()
    exhaustion_diagnostic_code: str | None = None
    single_iteration_effect_kinds: tuple[str, ...] | None = None
    effect_cardinality_diagnostic_code: str | None = None


@dataclass(frozen=True)
class WccHalt:
    metadata: WccNodeMetadata
    result: WccValue


@dataclass(frozen=True)
class WccLet:
    metadata: WccNodeMetadata
    bound_name: str
    bound_type_ref: TypeRef
    bound_value: WccBindingValue
    body: "WccBody"


WccBody = WccLet | WccCase | WccIf | WccJoin | WccJump | WccLoopContinue | WccLoopDone | WccRecJoin | WccHalt
WccProgram = WccBody
