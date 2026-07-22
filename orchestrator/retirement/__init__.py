"""Stable, lazily imported public retirement-evidence surface."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "ContractError",
    "Issue",
    "MaterializationError",
    "MaterializationReceipt",
    "canonical_json_bytes",
    "canonical_sha256",
    "compare_failure_sets",
    "derive_broad_baseline_comparison",
    "derive_review_binding",
    "build_broad_evidence_bootstrap_subject",
    "build_broad_known_failure_baseline",
    "build_broad_outcome",
    "build_initial_execution_ledger",
    "build_implementation_focused_report",
    "build_implementation_verification_subject",
    "apply_skip_change",
    "failure_signature",
    "load_json_closed",
    "materialize_pending",
    "materialize_transaction",
    "normalize_failure_payload",
    "parse_exit_bytes",
    "parse_junit_outcomes",
    "publish_immutable_review",
    "validate_generation",
    "validate_record",
    "validate_review_binding_pair",
    "validate_fixture_manifest",
    "validate_bound_record",
    "validate_review_pair",
    "validate_review_subject",
    "validate_implementation_focused_report",
]

_MATERIALIZATION_EXPORTS = {
    "MaterializationError",
    "MaterializationReceipt",
    "materialize_pending",
    "materialize_transaction",
    "validate_generation",
}


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    module_name = "materialization" if name in _MATERIALIZATION_EXPORTS else "broad_evidence"
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value
