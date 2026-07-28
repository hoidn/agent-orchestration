from __future__ import annotations

import pytest

from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DEADLINE_OPERATION_REGISTRY,
    DIAGNOSTIC_CODE_REASON_PAIRS,
    DIAGNOSTIC_REGISTRY,
    DiagnosticSource,
    DiagnosticSpan,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    SOURCE_PROFILES,
    STATIC_DIAGNOSTIC_REGISTRY,
    diagnostic_definition,
)


_EXPECTED_CODE_REASON_PAIRS = {
    "provider_phased_delivery_requires_dsl_2_23": ("target_below_2_23",),
    "provider_phased_delivery_policy_invalid": (
        "delivery_type_invalid",
        "delivery_enum_invalid",
        "attempts_literal_required",
        "attempts_type_invalid",
        "attempts_out_of_range",
        "attempts_pairing_invalid",
        "fragment_application_required",
        "contract_suffix_required",
    ),
    "provider_phased_interactive_capability_missing": (
        "interactive_capability_absent",
    ),
    "provider_phased_interactive_capability_invalid": (
        "interactive_capability_schema_unsupported",
        "turn_boundary_messages_not_true",
        "interactive_capability_malformed",
    ),
    "provider_phased_delivery_carriage_mismatch": (
        "call_policy_carriage_missing",
        "call_policy_carriage_extra",
        "call_policy_carriage_mismatch",
        "attempt_identity_version_mismatch",
        "attempt_evidence_version_mismatch",
    ),
    "provider_phased_preparation_failed": (
        "preparation_failed",
        "submit_endpoint_allocation_failed",
        "deadline_exhausted_before_preparation",
        "deadline_exhausted_during_preparation",
        "deadline_exhausted_before_submit_endpoint_allocation",
        "deadline_exhausted_during_submit_endpoint_allocation",
    ),
    "provider_phased_evidence_failed": (
        "evidence_append_failed",
        "deadline_exhausted_before_ledger_append",
        "deadline_exhausted_during_ledger_append",
    ),
    "provider_phased_start_failed": ("adapter_start_failed",),
    "provider_phased_start_timeout": (
        "deadline_exhausted_before_start",
        "deadline_exhausted_during_start",
    ),
    "provider_phased_turn_offer_failed": (
        "initial_offer_failed",
        "retry_offer_failed",
    ),
    "provider_phased_turn_offer_timeout": (
        "deadline_exhausted_before_initial_offer",
        "deadline_exhausted_during_initial_offer",
        "deadline_exhausted_before_retry_offer",
        "deadline_exhausted_during_retry_offer",
    ),
    "provider_phased_submit_timeout": (
        "deadline_exhausted_before_submit",
        "deadline_exhausted_during_submit",
        "deadline_exhausted_before_validation",
        "deadline_exhausted_during_validation",
    ),
    "provider_phased_submit_protocol_invalid": (
        "submit_binding_foreign",
        "submit_binding_stale",
        "submit_request_conflict",
        "submit_duplicate_in_flight",
        "submit_lifecycle_invalid",
    ),
    "provider_phased_provider_exited_before_submit": (
        "provider_exited_before_submit",
    ),
    "provider_phased_candidate_path_preexisting": (
        "candidate_path_preexisting",
    ),
    "provider_phased_validation_rejected": (
        "output_validation_failed",
        "structured_result_validation_failed",
    ),
    "provider_phased_candidate_reset_failed": (
        "candidate_reset_failed",
        "deadline_exhausted_before_candidate_reset",
        "deadline_exhausted_during_candidate_reset",
    ),
    "provider_phased_candidate_freeze_failed": (
        "candidate_freeze_failed",
        "deadline_exhausted_before_candidate_freeze",
        "deadline_exhausted_during_candidate_freeze",
    ),
    "provider_phased_materialization_attempts_exhausted": (
        "materialization_attempts_exhausted",
    ),
    "provider_phased_graceful_close_failed": ("close_offer_failed",),
    "provider_phased_graceful_close_timeout": (
        "deadline_exhausted_before_close_offer",
        "deadline_exhausted_during_close_offer",
    ),
    "provider_phased_ingress_shutdown_failed": ("ingress_shutdown_failed",),
    "provider_phased_ingress_shutdown_timeout": (
        "deadline_exhausted_before_ingress_shutdown",
        "deadline_exhausted_during_ingress_shutdown",
    ),
    "provider_phased_natural_close_failed": (
        "deadline_exhausted_before_join",
        "deadline_exhausted_during_join",
        "natural_join_failed",
    ),
    "provider_phased_publication_failed": (
        "deadline_exhausted_before_evidence_publication",
        "deadline_exhausted_during_evidence_publication",
        "deadline_exhausted_before_frozen_restoration",
        "deadline_exhausted_during_frozen_restoration",
        "deadline_exhausted_before_frozen_verification",
        "deadline_exhausted_during_frozen_verification",
        "deadline_exhausted_before_state_commit",
        "deadline_exhausted_during_state_commit_preparation",
        "evidence_publication_failed",
        "frozen_restoration_failed",
        "frozen_verification_failed",
        "workflow_state_commit_failed",
    ),
    "provider_phased_cleanup_failed": (
        "deadline_exhausted_before_adapter_cleanup",
        "deadline_exhausted_during_adapter_cleanup",
        "adapter_start_cleanup_incomplete",
        "adapter_cleanup_failed",
        "provider_zero_survivor_unproven",
    ),
    "provider_phased_interrupted_visit_quarantined": (
        "interrupted_nonterminal_visit",
    ),
}

_EXPECTED_STATIC_ROWS = (
    ("target_below_2_23", "P_SCHEMA_EXACT", "S_DELIVERY"),
    ("delivery_type_invalid", "P_SCHEMA_NULL", "S_DELIVERY"),
    ("delivery_enum_invalid", "P_ENUM_NULL", "S_DELIVERY"),
    ("attempts_literal_required", "P_INT_NULL", "S_ATTEMPTS"),
    ("attempts_type_invalid", "P_INT_NULL", "S_ATTEMPTS"),
    ("attempts_out_of_range", "P_INT_EXACT", "S_ATTEMPTS"),
    ("attempts_pairing_invalid", "P_PAIRING_NULL", "S_ATTEMPTS"),
    (
        "fragment_application_required",
        "P_FRAGMENT_NULL",
        "S_FRAGMENT",
    ),
    ("contract_suffix_required", "P_FRAGMENT_NULL", "S_RESULT"),
    ("interactive_capability_absent", "P_ABSENT", "S_TEMPLATE"),
    (
        "interactive_capability_schema_unsupported",
        "P_SCHEMA_NULL",
        "S_TEMPLATE",
    ),
    ("turn_boundary_messages_not_true", "P_BOOL_FALSE", "S_TEMPLATE"),
    (
        "interactive_capability_malformed",
        "P_CAPABILITY_NULL",
        "S_TEMPLATE",
    ),
    (
        "call_policy_carriage_missing",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    (
        "call_policy_carriage_extra",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    (
        "call_policy_carriage_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    (
        "attempt_identity_version_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    (
        "attempt_evidence_version_mismatch",
        "P_CARRIAGE_NULL",
        "S_CARRIAGE_PREFIX",
    ),
    (
        "candidate_path_preexisting",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    ("preparation_failed", "P_CANDIDATE_NULL", "S_CANDIDATE"),
    (
        "submit_endpoint_allocation_failed",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    ("evidence_append_failed", "P_PUBLICATION_NULL", "S_LEDGER"),
    ("candidate_reset_failed", "P_CANDIDATE_NULL", "S_CANDIDATE"),
    ("candidate_freeze_failed", "P_CANDIDATE_NULL", "S_CANDIDATE"),
    ("ingress_shutdown_failed", "P_LIFECYCLE_NULL", "S_ENDPOINT"),
    ("submit_binding_foreign", "P_LIFECYCLE_NULL", "S_ENDPOINT"),
    ("submit_binding_stale", "P_LIFECYCLE_NULL", "S_ENDPOINT"),
    ("submit_request_conflict", "P_LIFECYCLE_NULL", "S_ENDPOINT"),
    (
        "submit_duplicate_in_flight",
        "P_LIFECYCLE_NULL",
        "S_ENDPOINT",
    ),
    ("submit_lifecycle_invalid", "P_LIFECYCLE_NULL", "S_ENDPOINT"),
    (
        "provider_exited_before_submit",
        "P_LIFECYCLE_NULL",
        "S_LIFECYCLE",
    ),
    ("output_validation_failed", "P_VALIDATION_CODE", "S_Q2"),
    (
        "structured_result_validation_failed",
        "P_VALIDATION_CODE",
        "S_Q2",
    ),
    (
        "materialization_attempts_exhausted",
        "P_RANGE_EXACT",
        "S_LIFECYCLE",
    ),
    ("adapter_start_failed", "P_LIFECYCLE_NULL", "S_ADAPTER"),
    ("initial_offer_failed", "P_LIFECYCLE_NULL", "S_ADAPTER"),
    ("retry_offer_failed", "P_LIFECYCLE_NULL", "S_ADAPTER"),
    ("close_offer_failed", "P_LIFECYCLE_NULL", "S_ADAPTER"),
    ("natural_join_failed", "P_LIFECYCLE_NULL", "S_ADAPTER"),
    (
        "adapter_start_cleanup_incomplete",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    ("adapter_cleanup_failed", "P_LIFECYCLE_NULL", "S_ADAPTER"),
    (
        "provider_zero_survivor_unproven",
        "P_LIFECYCLE_NULL",
        "S_ADAPTER",
    ),
    (
        "interrupted_nonterminal_visit",
        "P_LIFECYCLE_NULL",
        "S_LIFECYCLE",
    ),
    (
        "evidence_publication_failed",
        "P_PUBLICATION_NULL",
        "S_PUBLICATION",
    ),
    (
        "frozen_restoration_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    (
        "frozen_verification_failed",
        "P_CANDIDATE_NULL",
        "S_CANDIDATE",
    ),
    (
        "workflow_state_commit_failed",
        "P_PUBLICATION_NULL",
        "S_STATE",
    ),
)

_EXPECTED_DEADLINE_OPERATIONS = (
    (
        "preparation",
        "deadline_exhausted_before_preparation",
        "deadline_exhausted_during_preparation",
        "provider_phased_preparation_failed",
        "S_CANDIDATE",
    ),
    (
        "ledger_append",
        "deadline_exhausted_before_ledger_append",
        "deadline_exhausted_during_ledger_append",
        "provider_phased_evidence_failed",
        "S_LEDGER",
    ),
    (
        "adapter_start",
        "deadline_exhausted_before_start",
        "deadline_exhausted_during_start",
        "provider_phased_start_timeout",
        "S_ADAPTER",
    ),
    (
        "submit_endpoint_allocation",
        "deadline_exhausted_before_submit_endpoint_allocation",
        "deadline_exhausted_during_submit_endpoint_allocation",
        "provider_phased_preparation_failed",
        "S_ENDPOINT",
    ),
    (
        "initial_offer",
        "deadline_exhausted_before_initial_offer",
        "deadline_exhausted_during_initial_offer",
        "provider_phased_turn_offer_timeout",
        "S_ADAPTER",
    ),
    (
        "retry_offer",
        "deadline_exhausted_before_retry_offer",
        "deadline_exhausted_during_retry_offer",
        "provider_phased_turn_offer_timeout",
        "S_ADAPTER",
    ),
    (
        "submit",
        "deadline_exhausted_before_submit",
        "deadline_exhausted_during_submit",
        "provider_phased_submit_timeout",
        "S_ENDPOINT",
    ),
    (
        "validation",
        "deadline_exhausted_before_validation",
        "deadline_exhausted_during_validation",
        "provider_phased_submit_timeout",
        "S_Q2",
    ),
    (
        "candidate_reset",
        "deadline_exhausted_before_candidate_reset",
        "deadline_exhausted_during_candidate_reset",
        "provider_phased_candidate_reset_failed",
        "S_CANDIDATE",
    ),
    (
        "candidate_freeze",
        "deadline_exhausted_before_candidate_freeze",
        "deadline_exhausted_during_candidate_freeze",
        "provider_phased_candidate_freeze_failed",
        "S_CANDIDATE",
    ),
    (
        "close_offer",
        "deadline_exhausted_before_close_offer",
        "deadline_exhausted_during_close_offer",
        "provider_phased_graceful_close_timeout",
        "S_ADAPTER",
    ),
    (
        "ingress_shutdown",
        "deadline_exhausted_before_ingress_shutdown",
        "deadline_exhausted_during_ingress_shutdown",
        "provider_phased_ingress_shutdown_timeout",
        "S_ENDPOINT",
    ),
    (
        "natural_join",
        "deadline_exhausted_before_join",
        "deadline_exhausted_during_join",
        "provider_phased_natural_close_failed",
        "S_ADAPTER",
    ),
    (
        "evidence_publication",
        "deadline_exhausted_before_evidence_publication",
        "deadline_exhausted_during_evidence_publication",
        "provider_phased_publication_failed",
        "S_PUBLICATION",
    ),
    (
        "frozen_restoration",
        "deadline_exhausted_before_frozen_restoration",
        "deadline_exhausted_during_frozen_restoration",
        "provider_phased_publication_failed",
        "S_CANDIDATE",
    ),
    (
        "frozen_verification",
        "deadline_exhausted_before_frozen_verification",
        "deadline_exhausted_during_frozen_verification",
        "provider_phased_publication_failed",
        "S_CANDIDATE",
    ),
    (
        "state_commit",
        "deadline_exhausted_before_state_commit",
        "deadline_exhausted_during_state_commit_preparation",
        "provider_phased_publication_failed",
        "S_STATE",
    ),
    (
        "adapter_cleanup",
        "deadline_exhausted_before_adapter_cleanup",
        "deadline_exhausted_during_adapter_cleanup",
        "provider_phased_cleanup_failed",
        "S_ADAPTER",
    ),
)


def _code_by_reason() -> dict[str, str]:
    return {
        reason: code
        for code, reasons in _EXPECTED_CODE_REASON_PAIRS.items()
        for reason in reasons
    }


def test_diagnostic_registry_is_total_unique_and_bijective() -> None:
    reasons = tuple(row.reason for row in DIAGNOSTIC_REGISTRY)
    codes_by_reason = {
        reason: code
        for code, legal_reasons in DIAGNOSTIC_CODE_REASON_PAIRS.items()
        for reason in legal_reasons
    }

    assert len(reasons) == 83
    assert len(reasons) == len(set(reasons))
    assert set(DIAGNOSTIC_CODE_REASON_PAIRS) == set(
        _EXPECTED_CODE_REASON_PAIRS
    )
    assert {
        code: frozenset(legal_reasons)
        for code, legal_reasons in DIAGNOSTIC_CODE_REASON_PAIRS.items()
    } == {
        code: frozenset(legal_reasons)
        for code, legal_reasons in _EXPECTED_CODE_REASON_PAIRS.items()
    }
    assert set(codes_by_reason) == set(reasons)
    assert set(codes_by_reason.values()) == {
        row.code for row in DIAGNOSTIC_REGISTRY
    }
    assert tuple(row.precedence for row in DIAGNOSTIC_REGISTRY) == tuple(
        range(len(DIAGNOSTIC_REGISTRY))
    )
    assert all(row.summary == row.reason for row in DIAGNOSTIC_REGISTRY)
    assert all(row.value_profile for row in DIAGNOSTIC_REGISTRY)
    assert all(row.source_profile for row in DIAGNOSTIC_REGISTRY)


def test_owner_deferred_isolation_row_is_the_exact_registry_subtraction() -> None:
    reasons = {row.reason for row in DIAGNOSTIC_REGISTRY}
    codes = set(DIAGNOSTIC_CODE_REASON_PAIRS)

    assert "isolation_required_unsupported" not in reasons
    assert "provider_phased_isolation_unsupported" not in codes
    assert len(STATIC_DIAGNOSTIC_REGISTRY) == 47
    assert len(DEADLINE_OPERATION_REGISTRY) == 18


def test_static_registry_has_exact_order_profiles_precedence_and_summary() -> None:
    code_by_reason = _code_by_reason()
    expected = tuple(
        (
            reason,
            code_by_reason[reason],
            value_profile,
            source_profile,
            precedence,
            reason,
        )
        for precedence, (
            reason,
            value_profile,
            source_profile,
        ) in enumerate(_EXPECTED_STATIC_ROWS)
    )
    actual = tuple(
        (
            row.reason,
            row.code,
            row.value_profile,
            row.source_profile,
            row.precedence,
            row.summary,
        )
        for row in STATIC_DIAGNOSTIC_REGISTRY
    )

    assert actual == expected


def test_deadline_registry_has_exact_operation_and_projection_order() -> None:
    assert tuple(
        (
            row.operation,
            row.before_reason,
            row.during_reason,
            row.code,
            row.source_profile,
        )
        for row in DEADLINE_OPERATION_REGISTRY
    ) == _EXPECTED_DEADLINE_OPERATIONS

    generated = {
        reason
        for operation in DEADLINE_OPERATION_REGISTRY
        for reason in (operation.before_reason, operation.during_reason)
    }
    registered = {
        row.reason
        for row in DIAGNOSTIC_REGISTRY
        if row.value_profile == "P_DEADLINE_NULL"
    }

    assert len(generated) == 36
    assert generated == registered
    deadline_rows = DIAGNOSTIC_REGISTRY[len(_EXPECTED_STATIC_ROWS) :]
    expected_deadline_metadata = tuple(
        (reason, operation[3], operation[4])
        for operation in _EXPECTED_DEADLINE_OPERATIONS
        for reason in operation[1:3]
    )
    expected_rows = tuple(
        (
            reason,
            code,
            "P_DEADLINE_NULL",
            source_profile,
            len(_EXPECTED_STATIC_ROWS) + ordinal,
            reason,
        )
        for ordinal, (
            reason,
            code,
            source_profile,
        ) in enumerate(expected_deadline_metadata)
    )
    assert tuple(
        (
            row.reason,
            row.code,
            row.value_profile,
            row.source_profile,
            row.precedence,
            row.summary,
        )
        for row in deadline_rows
    ) == expected_rows


def _span() -> DiagnosticSpan:
    return DiagnosticSpan(
        start_line=1,
        start_column=1,
        end_line=1,
        end_column=10,
    )


def _source(
    *,
    kind: str,
    owner: str,
    located: bool,
) -> DiagnosticSource:
    return DiagnosticSource(
        kind=kind,
        owner=owner,
        path="workflows/example.orc" if located else None,
        span=_span() if located else None,
    )


def _diagnostic(
    reason: str,
    canonical_value: bool | int | str | None,
    primary_source: DiagnosticSource,
    related_sources: tuple[DiagnosticSource, ...],
) -> PhasedDeliveryDiagnostic:
    definition = diagnostic_definition(reason)
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value=canonical_value,
            summary=reason,
        ),
        primary_source=primary_source,
        related_sources=related_sources,
    )


def test_diagnostic_projection_enforces_exact_value_and_static_source_profiles() -> None:
    delivery = _source(
        kind="authored_span",
        owner="delivery_keyword",
        located=True,
    )
    application = _source(
        kind="authored_span",
        owner="provider_application",
        located=True,
    )
    assert (
        _diagnostic(
            "target_below_2_23",
            "2.22",
            delivery,
            (application,),
        ).reason
        == "target_below_2_23"
    )

    invalid_values = (
        ("interactive_capability_absent", "arbitrary"),
        ("turn_boundary_messages_not_true", True),
        ("materialization_attempts_exhausted", 99),
        ("target_below_2_23", "not a target"),
        ("output_validation_failed", "not_a_q2_violation"),
    )
    sources = {
        "interactive_capability_absent": (
            _source(
                kind="provider_template",
                owner="resolved_provider_template",
                located=False,
            ),
            (application,),
        ),
        "turn_boundary_messages_not_true": (
            _source(
                kind="provider_template",
                owner="resolved_provider_template",
                located=False,
            ),
            (application,),
        ),
        "materialization_attempts_exhausted": (
            _source(
                kind="runtime_attempt",
                owner="phase_lifecycle",
                located=False,
            ),
            (
                _source(
                    kind="runtime_attempt",
                    owner="runtime_step",
                    located=False,
                ),
            ),
        ),
        "target_below_2_23": (delivery, (application,)),
        "output_validation_failed": (
            _source(
                kind="runtime_attempt",
                owner="q2_output_contract",
                located=False,
            ),
            (
                _source(
                    kind="runtime_attempt",
                    owner="runtime_step",
                    located=False,
                ),
                _source(
                    kind="runtime_attempt",
                    owner="candidate_set",
                    located=False,
                ),
                _source(
                    kind="runtime_attempt",
                    owner="phase_lifecycle",
                    located=False,
                ),
            ),
        ),
    }
    for reason, value in invalid_values:
        primary, related = sources[reason]
        with pytest.raises((TypeError, ValueError)):
            _diagnostic(reason, value, primary, related)

    with pytest.raises(ValueError):
        _diagnostic(
            "target_below_2_23",
            "2.22",
            _source(
                kind="runtime_attempt",
                owner="delivery_keyword",
                located=False,
            ),
            (application,),
        )
    with pytest.raises(ValueError):
        _diagnostic("target_below_2_23", "2.22", delivery, ())


def test_carriage_profile_enforces_primary_boundary_and_validated_prefix() -> None:
    carrier = lambda owner: _source(
        kind="carrier_boundary",
        owner=owner,
        located=True,
    )
    first = carrier("provider_call_policy")
    second = carrier("semantic_ir")
    third = carrier("executable_ir")

    assert (
        _diagnostic(
            "call_policy_carriage_mismatch",
            None,
            third,
            (first, second),
        ).primary_source.owner
        == "executable_ir"
    )
    for related in ((second, first), (first,), (first, second, third)):
        with pytest.raises(ValueError):
            _diagnostic(
                "call_policy_carriage_mismatch",
                None,
                third,
                related,
            )
    assert SOURCE_PROFILES["S_CARRIAGE_PREFIX"].ordered_owner_chain == (
        "provider_call_policy",
        "semantic_ir",
        "executable_ir",
        "persisted_provider_config",
        "lexical_checkpoint",
        "runtime_step",
    )
