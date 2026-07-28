"""Closed, total metadata registry for phased-delivery diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True, slots=True)
class ValueProfileDefinition:
    name: str
    value_type: str


@dataclass(frozen=True, slots=True)
class SourceProfileDefinition:
    name: str
    primary_owner: str | None
    related_owners: tuple[str, ...]
    ordered_owner_chain: tuple[str, ...] = ()


VALUE_PROFILES = MappingProxyType(
    {
        "P_ABSENT": ValueProfileDefinition("P_ABSENT", "absent"),
        "P_BOOL_FALSE": ValueProfileDefinition("P_BOOL_FALSE", "boolean"),
        "P_INT_NULL": ValueProfileDefinition("P_INT_NULL", "integer"),
        "P_INT_EXACT": ValueProfileDefinition("P_INT_EXACT", "integer"),
        "P_ENUM_NULL": ValueProfileDefinition("P_ENUM_NULL", "enum"),
        "P_SCHEMA_NULL": ValueProfileDefinition(
            "P_SCHEMA_NULL",
            "schema_token",
        ),
        "P_SCHEMA_EXACT": ValueProfileDefinition(
            "P_SCHEMA_EXACT",
            "schema_token",
        ),
        "P_RANGE_EXACT": ValueProfileDefinition("P_RANGE_EXACT", "range"),
        "P_PAIRING_NULL": ValueProfileDefinition(
            "P_PAIRING_NULL",
            "pairing",
        ),
        "P_FRAGMENT_NULL": ValueProfileDefinition(
            "P_FRAGMENT_NULL",
            "fragment_shape",
        ),
        "P_CAPABILITY_NULL": ValueProfileDefinition(
            "P_CAPABILITY_NULL",
            "capability_shape",
        ),
        "P_CARRIAGE_NULL": ValueProfileDefinition(
            "P_CARRIAGE_NULL",
            "carriage_shape",
        ),
        "P_CANDIDATE_NULL": ValueProfileDefinition(
            "P_CANDIDATE_NULL",
            "candidate_shape",
        ),
        "P_DEADLINE_NULL": ValueProfileDefinition(
            "P_DEADLINE_NULL",
            "deadline_state",
        ),
        "P_LIFECYCLE_NULL": ValueProfileDefinition(
            "P_LIFECYCLE_NULL",
            "lifecycle_state",
        ),
        "P_VALIDATION_CODE": ValueProfileDefinition(
            "P_VALIDATION_CODE",
            "validation_code",
        ),
        "P_PUBLICATION_NULL": ValueProfileDefinition(
            "P_PUBLICATION_NULL",
            "publication_stage",
        ),
    }
)


SOURCE_PROFILES = MappingProxyType(
    {
        "S_DELIVERY": SourceProfileDefinition(
            "S_DELIVERY",
            "delivery_keyword",
            ("provider_application",),
        ),
        "S_ATTEMPTS": SourceProfileDefinition(
            "S_ATTEMPTS",
            "materialization_attempts_keyword",
            ("provider_application",),
        ),
        "S_FRAGMENT": SourceProfileDefinition(
            "S_FRAGMENT",
            "fragment_contract",
            ("provider_application",),
        ),
        "S_RESULT": SourceProfileDefinition(
            "S_RESULT",
            "result_contract_suffix",
            ("provider_application",),
        ),
        "S_PROVIDER": SourceProfileDefinition(
            "S_PROVIDER",
            "provider_application",
            (),
        ),
        "S_TEMPLATE": SourceProfileDefinition(
            "S_TEMPLATE",
            "resolved_provider_template",
            ("provider_application",),
        ),
        "S_CARRIAGE_PREFIX": SourceProfileDefinition(
            "S_CARRIAGE_PREFIX",
            None,
            (),
            (
                "provider_call_policy",
                "semantic_ir",
                "executable_ir",
                "persisted_provider_config",
                "lexical_checkpoint",
                "runtime_step",
            ),
        ),
        "S_CANDIDATE": SourceProfileDefinition(
            "S_CANDIDATE",
            "candidate_set",
            ("runtime_step", "phase_lifecycle"),
        ),
        "S_LEDGER": SourceProfileDefinition(
            "S_LEDGER",
            "phase_ledger",
            ("runtime_step", "phase_lifecycle"),
        ),
        "S_ENDPOINT": SourceProfileDefinition(
            "S_ENDPOINT",
            "submit_endpoint",
            ("runtime_step", "phase_lifecycle"),
        ),
        "S_Q2": SourceProfileDefinition(
            "S_Q2",
            "q2_output_contract",
            ("runtime_step", "candidate_set", "phase_lifecycle"),
        ),
        "S_LIFECYCLE": SourceProfileDefinition(
            "S_LIFECYCLE",
            "phase_lifecycle",
            ("runtime_step",),
        ),
        "S_ADAPTER": SourceProfileDefinition(
            "S_ADAPTER",
            "interactive_adapter",
            ("runtime_step", "phase_lifecycle"),
        ),
        "S_PUBLICATION": SourceProfileDefinition(
            "S_PUBLICATION",
            "phase_lifecycle",
            ("runtime_step", "phase_ledger"),
        ),
        "S_STATE": SourceProfileDefinition(
            "S_STATE",
            "workflow_state_commit",
            ("runtime_step", "phase_lifecycle"),
        ),
    }
)


@dataclass(frozen=True, slots=True)
class DiagnosticDefinition:
    reason: str
    code: str
    value_profile: str
    source_profile: str
    precedence: int
    summary: str

    @property
    def value_type(self) -> str:
        return VALUE_PROFILES[self.value_profile].value_type

    def __post_init__(self) -> None:
        if (
            not self.reason
            or not self.code
            or self.value_profile not in VALUE_PROFILES
            or self.source_profile not in SOURCE_PROFILES
            or isinstance(self.precedence, bool)
            or not isinstance(self.precedence, int)
            or self.precedence < 0
            or self.summary != self.reason
        ):
            raise ValueError("diagnostic definition is invalid")


@dataclass(frozen=True, slots=True)
class DeadlineOperationDefinition:
    operation: str
    before_reason: str
    during_reason: str
    code: str
    source_profile: str


def _static(
    reason: str,
    code: str,
    value_profile: str,
    source_profile: str,
) -> tuple[str, str, str, str]:
    return reason, code, value_profile, source_profile


_STATIC_ROWS = (
    _static(
        "target_below_2_23",
        "provider_phased_delivery_requires_dsl_2_23",
        "P_SCHEMA_EXACT",
        "S_DELIVERY",
    ),
    _static(
        "delivery_type_invalid",
        "provider_phased_delivery_policy_invalid",
        "P_SCHEMA_NULL",
        "S_DELIVERY",
    ),
    _static(
        "delivery_enum_invalid",
        "provider_phased_delivery_policy_invalid",
        "P_ENUM_NULL",
        "S_DELIVERY",
    ),
    _static(
        "attempts_literal_required",
        "provider_phased_delivery_policy_invalid",
        "P_INT_NULL",
        "S_ATTEMPTS",
    ),
    _static(
        "attempts_type_invalid",
        "provider_phased_delivery_policy_invalid",
        "P_INT_NULL",
        "S_ATTEMPTS",
    ),
    _static(
        "attempts_out_of_range",
        "provider_phased_delivery_policy_invalid",
        "P_INT_EXACT",
        "S_ATTEMPTS",
    ),
    _static(
        "attempts_pairing_invalid",
        "provider_phased_delivery_policy_invalid",
        "P_PAIRING_NULL",
        "S_ATTEMPTS",
    ),
    _static(
        "fragment_application_required",
        "provider_phased_delivery_policy_invalid",
        "P_FRAGMENT_NULL",
        "S_FRAGMENT",
    ),
    _static(
        "contract_suffix_required",
        "provider_phased_delivery_policy_invalid",
        "P_FRAGMENT_NULL",
        "S_RESULT",
    ),
    _static(
        "interactive_capability_absent",
        "provider_phased_interactive_capability_missing",
        "P_ABSENT",
        "S_TEMPLATE",
    ),
    _static(
        "interactive_capability_schema_unsupported",
        "provider_phased_interactive_capability_invalid",
        "P_SCHEMA_NULL",
        "S_TEMPLATE",
    ),
    _static(
        "turn_boundary_messages_not_true",
        "provider_phased_interactive_capability_invalid",
        "P_BOOL_FALSE",
        "S_TEMPLATE",
    ),
    _static(
        "interactive_capability_malformed",
        "provider_phased_interactive_capability_invalid",
        "P_CAPABILITY_NULL",
        "S_TEMPLATE",
    ),
    _static(
        "call_policy_carriage_missing",
        "provider_phased_delivery_carriage_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    _static(
        "call_policy_carriage_extra",
        "provider_phased_delivery_carriage_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    _static(
        "call_policy_carriage_mismatch",
        "provider_phased_delivery_carriage_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    _static(
        "attempt_identity_version_mismatch",
        "provider_phased_delivery_carriage_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    _static(
        "attempt_evidence_version_mismatch",
        "provider_phased_delivery_carriage_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    _static(
        "candidate_path_preexisting",
        "provider_phased_candidate_path_preexisting",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    _static(
        "preparation_failed",
        "provider_phased_preparation_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    _static(
        "submit_endpoint_allocation_failed",
        "provider_phased_preparation_failed",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "evidence_append_failed",
        "provider_phased_evidence_failed",
        "P_PUBLICATION_NULL",
        "S_LEDGER",
    ),
    _static(
        "candidate_reset_failed",
        "provider_phased_candidate_reset_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    _static(
        "candidate_freeze_failed",
        "provider_phased_candidate_freeze_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    _static(
        "ingress_shutdown_failed",
        "provider_phased_ingress_shutdown_failed",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "submit_binding_foreign",
        "provider_phased_submit_protocol_invalid",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "submit_binding_stale",
        "provider_phased_submit_protocol_invalid",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "submit_request_conflict",
        "provider_phased_submit_protocol_invalid",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "submit_duplicate_in_flight",
        "provider_phased_submit_protocol_invalid",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "submit_lifecycle_invalid",
        "provider_phased_submit_protocol_invalid",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    _static(
        "provider_exited_before_submit",
        "provider_phased_provider_exited_before_submit",
        "P_LIFECYCLE_NULL",
        "S_LIFECYCLE",
    ),
    _static(
        "output_validation_failed",
        "provider_phased_validation_rejected",
        "P_VALIDATION_CODE",
        "S_Q2",
    ),
    _static(
        "structured_result_validation_failed",
        "provider_phased_validation_rejected",
        "P_VALIDATION_CODE",
        "S_Q2",
    ),
    _static(
        "materialization_attempts_exhausted",
        "provider_phased_materialization_attempts_exhausted",
        "P_RANGE_EXACT",
        "S_LIFECYCLE",
    ),
    _static(
        "adapter_start_failed",
        "provider_phased_start_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "initial_offer_failed",
        "provider_phased_turn_offer_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "retry_offer_failed",
        "provider_phased_turn_offer_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "close_offer_failed",
        "provider_phased_graceful_close_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "natural_join_failed",
        "provider_phased_natural_close_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "adapter_start_cleanup_incomplete",
        "provider_phased_cleanup_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "adapter_cleanup_failed",
        "provider_phased_cleanup_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "provider_zero_survivor_unproven",
        "provider_phased_cleanup_failed",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    _static(
        "interrupted_nonterminal_visit",
        "provider_phased_interrupted_visit_quarantined",
        "P_LIFECYCLE_NULL",
        "S_LIFECYCLE",
    ),
    _static(
        "evidence_publication_failed",
        "provider_phased_publication_failed",
        "P_PUBLICATION_NULL",
        "S_PUBLICATION",
    ),
    _static(
        "frozen_restoration_failed",
        "provider_phased_publication_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    _static(
        "frozen_verification_failed",
        "provider_phased_publication_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    _static(
        "workflow_state_commit_failed",
        "provider_phased_publication_failed",
        "P_PUBLICATION_NULL",
        "S_STATE",
    ),
)


STATIC_DIAGNOSTIC_REGISTRY = tuple(
    DiagnosticDefinition(
        reason=reason,
        code=code,
        value_profile=value_profile,
        source_profile=source_profile,
        precedence=index,
        summary=reason,
    )
    for index, (reason, code, value_profile, source_profile) in enumerate(
        _STATIC_ROWS
    )
)


DEADLINE_OPERATION_REGISTRY = (
    DeadlineOperationDefinition(
        "preparation",
        "deadline_exhausted_before_preparation",
        "deadline_exhausted_during_preparation",
        "provider_phased_preparation_failed",
        "S_CANDIDATE",
    ),
    DeadlineOperationDefinition(
        "ledger_append",
        "deadline_exhausted_before_ledger_append",
        "deadline_exhausted_during_ledger_append",
        "provider_phased_evidence_failed",
        "S_LEDGER",
    ),
    DeadlineOperationDefinition(
        "adapter_start",
        "deadline_exhausted_before_start",
        "deadline_exhausted_during_start",
        "provider_phased_start_timeout",
        "S_ADAPTER",
    ),
    DeadlineOperationDefinition(
        "submit_endpoint_allocation",
        "deadline_exhausted_before_submit_endpoint_allocation",
        "deadline_exhausted_during_submit_endpoint_allocation",
        "provider_phased_preparation_failed",
        "S_ENDPOINT",
    ),
    DeadlineOperationDefinition(
        "initial_offer",
        "deadline_exhausted_before_initial_offer",
        "deadline_exhausted_during_initial_offer",
        "provider_phased_turn_offer_timeout",
        "S_ADAPTER",
    ),
    DeadlineOperationDefinition(
        "retry_offer",
        "deadline_exhausted_before_retry_offer",
        "deadline_exhausted_during_retry_offer",
        "provider_phased_turn_offer_timeout",
        "S_ADAPTER",
    ),
    DeadlineOperationDefinition(
        "submit",
        "deadline_exhausted_before_submit",
        "deadline_exhausted_during_submit",
        "provider_phased_submit_timeout",
        "S_ENDPOINT",
    ),
    DeadlineOperationDefinition(
        "validation",
        "deadline_exhausted_before_validation",
        "deadline_exhausted_during_validation",
        "provider_phased_submit_timeout",
        "S_Q2",
    ),
    DeadlineOperationDefinition(
        "candidate_reset",
        "deadline_exhausted_before_candidate_reset",
        "deadline_exhausted_during_candidate_reset",
        "provider_phased_candidate_reset_failed",
        "S_CANDIDATE",
    ),
    DeadlineOperationDefinition(
        "candidate_freeze",
        "deadline_exhausted_before_candidate_freeze",
        "deadline_exhausted_during_candidate_freeze",
        "provider_phased_candidate_freeze_failed",
        "S_CANDIDATE",
    ),
    DeadlineOperationDefinition(
        "close_offer",
        "deadline_exhausted_before_close_offer",
        "deadline_exhausted_during_close_offer",
        "provider_phased_graceful_close_timeout",
        "S_ADAPTER",
    ),
    DeadlineOperationDefinition(
        "ingress_shutdown",
        "deadline_exhausted_before_ingress_shutdown",
        "deadline_exhausted_during_ingress_shutdown",
        "provider_phased_ingress_shutdown_timeout",
        "S_ENDPOINT",
    ),
    DeadlineOperationDefinition(
        "natural_join",
        "deadline_exhausted_before_join",
        "deadline_exhausted_during_join",
        "provider_phased_natural_close_failed",
        "S_ADAPTER",
    ),
    DeadlineOperationDefinition(
        "evidence_publication",
        "deadline_exhausted_before_evidence_publication",
        "deadline_exhausted_during_evidence_publication",
        "provider_phased_publication_failed",
        "S_PUBLICATION",
    ),
    DeadlineOperationDefinition(
        "frozen_restoration",
        "deadline_exhausted_before_frozen_restoration",
        "deadline_exhausted_during_frozen_restoration",
        "provider_phased_publication_failed",
        "S_CANDIDATE",
    ),
    DeadlineOperationDefinition(
        "frozen_verification",
        "deadline_exhausted_before_frozen_verification",
        "deadline_exhausted_during_frozen_verification",
        "provider_phased_publication_failed",
        "S_CANDIDATE",
    ),
    DeadlineOperationDefinition(
        "state_commit",
        "deadline_exhausted_before_state_commit",
        "deadline_exhausted_during_state_commit_preparation",
        "provider_phased_publication_failed",
        "S_STATE",
    ),
    DeadlineOperationDefinition(
        "adapter_cleanup",
        "deadline_exhausted_before_adapter_cleanup",
        "deadline_exhausted_during_adapter_cleanup",
        "provider_phased_cleanup_failed",
        "S_ADAPTER",
    ),
)


_deadline_start = len(STATIC_DIAGNOSTIC_REGISTRY)
_deadline_definitions: list[DiagnosticDefinition] = []
for operation in DEADLINE_OPERATION_REGISTRY:
    for reason in (operation.before_reason, operation.during_reason):
        precedence = _deadline_start + len(_deadline_definitions)
        _deadline_definitions.append(
            DiagnosticDefinition(
                reason=reason,
                code=operation.code,
                value_profile="P_DEADLINE_NULL",
                source_profile=operation.source_profile,
                precedence=precedence,
                summary=reason,
            )
        )

DIAGNOSTIC_REGISTRY = (
    STATIC_DIAGNOSTIC_REGISTRY + tuple(_deadline_definitions)
)
_BY_REASON = MappingProxyType(
    {definition.reason: definition for definition in DIAGNOSTIC_REGISTRY}
)

_pairs: dict[str, list[str]] = {}
for definition in DIAGNOSTIC_REGISTRY:
    _pairs.setdefault(definition.code, []).append(definition.reason)
DIAGNOSTIC_CODE_REASON_PAIRS = MappingProxyType(
    {code: tuple(reasons) for code, reasons in _pairs.items()}
)

if len(_BY_REASON) != len(DIAGNOSTIC_REGISTRY):
    raise RuntimeError("duplicate phased-delivery diagnostic reason")


def diagnostic_definition(reason: str) -> DiagnosticDefinition:
    if not isinstance(reason, str):
        raise TypeError("diagnostic reason must be a string")
    try:
        return _BY_REASON[reason]
    except KeyError as exc:
        raise ValueError("unknown phased-delivery diagnostic reason") from exc


_SIGNED_64_MIN = -(2**63)
_SIGNED_64_MAX = 2**63 - 1
_TARGET_TOKEN_RE = re.compile(r"[0-9]+\.[0-9]+")
_NULL_VALUE_PROFILES = frozenset(
    {
        "P_ABSENT",
        "P_INT_NULL",
        "P_ENUM_NULL",
        "P_SCHEMA_NULL",
        "P_PAIRING_NULL",
        "P_FRAGMENT_NULL",
        "P_CAPABILITY_NULL",
        "P_CARRIAGE_NULL",
        "P_CANDIDATE_NULL",
        "P_DEADLINE_NULL",
        "P_LIFECYCLE_NULL",
        "P_PUBLICATION_NULL",
    }
)
_Q2_VALIDATION_CODES = frozenset(
    {
        "duplicate_artifact_name",
        "empty_relpath",
        "invalid_bool",
        "invalid_bundle_field",
        "invalid_bundle_fields",
        "invalid_bundle_path",
        "invalid_enum_value",
        "invalid_float",
        "invalid_integer",
        "invalid_json_document",
        "invalid_json_pointer",
        "invalid_list",
        "invalid_map",
        "invalid_map_key",
        "invalid_output_path",
        "invalid_relpath",
        "invalid_string",
        "invalid_transportable_value",
        "invalid_under_root",
        "invalid_variant_bundle",
        "json_pointer_not_found",
        "missing_artifact_name",
        "missing_bundle_file",
        "missing_output_file",
        "missing_target",
        "outside_under_root",
        "path_escape",
        "prompt_output_position_contract_mismatch",
        "prompt_output_position_destination_collision",
        "unsupported_type",
        "variant_discriminant_invalid",
        "variant_discriminant_missing",
        "variant_field_type_invalid",
        "variant_forbidden_field_present",
        "variant_required_field_missing",
    }
)
_AUTHORED_OWNERS = frozenset(
    {
        "delivery_keyword",
        "materialization_attempts_keyword",
        "provider_application",
        "fragment_contract",
        "result_contract_suffix",
    }
)
_CARRIER_OWNERS = SOURCE_PROFILES[
    "S_CARRIAGE_PREFIX"
].ordered_owner_chain
_RUNTIME_OWNERS = frozenset(
    {
        "runtime_step",
        "submit_endpoint",
        "q2_output_contract",
        "candidate_set",
        "phase_lifecycle",
        "phase_ledger",
    }
)
_OWNER_KINDS = MappingProxyType(
    {
        **{owner: frozenset({"authored_span"}) for owner in _AUTHORED_OWNERS},
        "resolved_provider_template": frozenset({"provider_template"}),
        **{
            owner: frozenset({"carrier_boundary"})
            for owner in _CARRIER_OWNERS
        },
        **{
            owner: frozenset(
                {"runtime_attempt", "carrier_boundary"}
                if owner == "runtime_step"
                else {"runtime_attempt"}
            )
            for owner in _RUNTIME_OWNERS
        },
        "interactive_adapter": frozenset({"adapter_operation"}),
        "workflow_state_commit": frozenset({"state_commit"}),
    }
)


def _normalized_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and "." not in path.parts
        and ".." not in path.parts
        and path.as_posix() == value
    )


def _validate_profile_value(
    definition: DiagnosticDefinition,
    rejected_value: RejectedValue,
) -> None:
    profile = definition.value_profile
    value = rejected_value.canonical_value
    if profile in _NULL_VALUE_PROFILES:
        valid = value is None
    elif profile == "P_BOOL_FALSE":
        valid = value is False
    elif profile == "P_INT_EXACT":
        valid = value is None or (
            type(value) is int and _SIGNED_64_MIN <= value <= _SIGNED_64_MAX
        )
    elif profile == "P_SCHEMA_EXACT":
        valid = (
            isinstance(value, str)
            and value.isascii()
            and _TARGET_TOKEN_RE.fullmatch(value) is not None
        )
    elif profile == "P_RANGE_EXACT":
        valid = type(value) is int and value in {1, 2, 3}
    elif profile == "P_VALIDATION_CODE":
        valid = isinstance(value, str) and value in _Q2_VALIDATION_CODES
    else:  # pragma: no cover - registry definition guard
        raise RuntimeError("unknown phased-delivery value profile")
    if not valid:
        raise ValueError("diagnostic canonical value violates its profile")


def _validate_source_profile(
    definition: DiagnosticDefinition,
    primary_source: DiagnosticSource,
    related_sources: tuple[DiagnosticSource, ...],
) -> None:
    profile = SOURCE_PROFILES[definition.source_profile]
    related_owners = tuple(source.owner for source in related_sources)
    if profile.ordered_owner_chain:
        try:
            failing_index = profile.ordered_owner_chain.index(
                primary_source.owner
            )
        except ValueError as exc:
            raise ValueError(
                "carriage source is not a legal carrier boundary"
            ) from exc
        expected_related = profile.ordered_owner_chain[:failing_index]
        if (
            primary_source.kind != "carrier_boundary"
            or any(
                source.kind != "carrier_boundary"
                for source in related_sources
            )
            or related_owners != expected_related
        ):
            raise ValueError(
                "carriage related sources must be the validated prefix"
            )
        return
    expected_static_kinds = {
        **{owner: "authored_span" for owner in _AUTHORED_OWNERS},
        "resolved_provider_template": "provider_template",
        **{owner: "runtime_attempt" for owner in _RUNTIME_OWNERS},
        "interactive_adapter": "adapter_operation",
        "workflow_state_commit": "state_commit",
    }
    if (
        primary_source.owner != profile.primary_owner
        or related_owners != profile.related_owners
        or primary_source.kind
        != expected_static_kinds[primary_source.owner]
        or any(
            source.kind != expected_static_kinds[source.owner]
            for source in related_sources
        )
    ):
        raise ValueError("diagnostic source profile is invalid")


@dataclass(frozen=True, slots=True)
class RejectedValue:
    type: str
    canonical_value: bool | int | str | None
    summary: str

    def __post_init__(self) -> None:
        if self.type not in {
            definition.value_type for definition in DIAGNOSTIC_REGISTRY
        }:
            raise ValueError("rejected value type is invalid")
        if (
            self.canonical_value is not None
            and type(self.canonical_value) not in {bool, int, str}
        ):
            raise TypeError("canonical value must be a JSON scalar or null")
        if not isinstance(self.summary, str) or not self.summary:
            raise TypeError("rejected value summary must be non-empty")


@dataclass(frozen=True, slots=True)
class DiagnosticSpan:
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __post_init__(self) -> None:
        values = (
            self.start_line,
            self.start_column,
            self.end_line,
            self.end_column,
        )
        if any(type(value) is not int or value < 1 for value in values):
            raise TypeError("diagnostic span positions must be positive integers")
        if (self.end_line, self.end_column) < (
            self.start_line,
            self.start_column,
        ):
            raise ValueError("diagnostic span end precedes its start")


@dataclass(frozen=True, slots=True)
class DiagnosticSource:
    kind: str
    owner: str
    path: str | None
    span: DiagnosticSpan | None

    def __post_init__(self) -> None:
        expected_kind = _OWNER_KINDS.get(self.owner)
        if expected_kind is None or self.kind not in expected_kind:
            raise ValueError("diagnostic source kind/owner pairing is invalid")
        if self.kind in {"authored_span", "carrier_boundary"}:
            if (
                not _normalized_relative_path(self.path)
                or type(self.span) is not DiagnosticSpan
            ):
                raise ValueError(
                    "authored and carrier sources require retained locations"
                )
        elif self.path is not None or self.span is not None:
            raise ValueError("runtime diagnostic sources forbid locations")


@dataclass(frozen=True, slots=True)
class PhasedDeliveryDiagnostic:
    code: str
    reason: str
    rejected_value: RejectedValue
    primary_source: DiagnosticSource
    related_sources: tuple[DiagnosticSource, ...]

    schema_version = "provider_phased_delivery_diagnostic.v1"

    def __post_init__(self) -> None:
        definition = diagnostic_definition(self.reason)
        if self.code != definition.code:
            raise ValueError("diagnostic code/reason pairing is invalid")
        if type(self.rejected_value) is not RejectedValue:
            raise TypeError("rejected_value must be exact")
        if (
            self.rejected_value.type != definition.value_type
            or self.rejected_value.summary != self.reason
        ):
            raise ValueError("rejected value profile is invalid")
        _validate_profile_value(definition, self.rejected_value)
        if type(self.primary_source) is not DiagnosticSource:
            raise TypeError("primary_source must be exact")
        if (
            not isinstance(self.related_sources, tuple)
            or any(
                type(source) is not DiagnosticSource
                for source in self.related_sources
            )
        ):
            raise TypeError("related_sources must be exact tuple")
        _validate_source_profile(
            definition,
            self.primary_source,
            self.related_sources,
        )


def build_phased_delivery_diagnostic(
    reason: str,
    *,
    canonical_value: bool | int | str | None,
    sources_by_owner: Mapping[str, DiagnosticSource],
    carriage_primary_owner: str | None = None,
) -> PhasedDeliveryDiagnostic:
    """Build one exact table-derived diagnostic from complete source owners."""

    definition = diagnostic_definition(reason)
    profile = SOURCE_PROFILES[definition.source_profile]
    if profile.ordered_owner_chain:
        if carriage_primary_owner not in profile.ordered_owner_chain:
            raise ValueError(
                "carriage diagnostics require one legal primary owner"
            )
        primary_index = profile.ordered_owner_chain.index(
            carriage_primary_owner
        )
        related_owners = profile.ordered_owner_chain[:primary_index]
        required_owners = (*related_owners, carriage_primary_owner)
    else:
        if carriage_primary_owner is not None:
            raise ValueError(
                "fixed source profiles forbid a carriage primary owner"
            )
        if profile.primary_owner is None:  # pragma: no cover - registry guard
            raise RuntimeError("fixed source profile has no primary owner")
        related_owners = profile.related_owners
        required_owners = (profile.primary_owner, *related_owners)

    if set(sources_by_owner) != set(required_owners):
        raise ValueError(
            "diagnostic sources must exactly match the selected profile"
        )
    primary_owner = (
        carriage_primary_owner
        if profile.ordered_owner_chain
        else profile.primary_owner
    )
    if primary_owner is None:  # pragma: no cover - guarded above
        raise RuntimeError("diagnostic primary owner is missing")
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value=canonical_value,
            summary=reason,
        ),
        primary_source=sources_by_owner[primary_owner],
        related_sources=tuple(
            sources_by_owner[owner] for owner in related_owners
        ),
    )
