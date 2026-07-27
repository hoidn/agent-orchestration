"""Private deterministic pilot-summary synthesis."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction

from ._reporting_metrics import _fraction, collect_treatment_metrics
from ._reporting_reviews import resolve_reviews
from ._reporting_types import (
    COMPARISONS,
    TREATMENTS,
    ReviewBinding,
    UnblindingBinding,
)
from ._reporting_validation import (
    _fail,
    _validate_attempt_sequence,
    _validate_record,
    assess_readiness,
)
from .contracts import canonical_sha256


def build_pilot_summary(
    *,
    lock: Mapping[str, object],
    block_attempts: Sequence[Mapping[str, object]],
    reviews: Sequence[Mapping[str, object]],
    sealed_review_bindings: Sequence[ReviewBinding],
    unblinding: Sequence[UnblindingBinding],
) -> dict[str, object]:
    """Build one deterministic summary from exact locked records and bindings."""

    lock_record = _validate_record(lock, "pilot_lock.v1")
    _smoke, live_attempts = _validate_attempt_sequence(
        lock=lock_record,
        block_attempts=block_attempts,
    )
    status = assess_readiness(lock=lock_record, block_attempts=block_attempts)
    valid_attempts = [
        attempt for attempt in live_attempts if attempt["status"] == "VALID"
    ]
    if len(valid_attempts) > lock_record["valid_block_count"]:
        _fail("attempt_after_denominator")
    excluded = [
        {
            "block_id": attempt["block_id"],
            "block_attempt_digest": canonical_sha256(attempt),
            "status": attempt["status"],
        }
        for attempt in live_attempts
        if attempt["status"] != "VALID"
    ]
    resolved = resolve_reviews(
        lock=lock_record,
        valid_attempts=valid_attempts,
        reviews=reviews,
        sealed_review_bindings=sealed_review_bindings,
        unblinding=unblinding,
    )
    metrics = collect_treatment_metrics(
        lock=lock_record,
        valid_attempts=valid_attempts,
    )

    valid_blocks: list[dict[str, object]] = []
    comparison_counts = {
        name: {
            "comparison": name,
            "a_win_count": 0,
            "b_win_count": 0,
            "tie_count": 0,
            "indeterminate_count": 0,
            "tie_nonviable_count": 0,
        }
        for name, _a, _b in COMPARISONS
    }
    for attempt in valid_attempts:
        executions = metrics.executions_by_block[attempt["block_id"]]
        method_outcomes: list[dict[str, object]] = []
        for comparison, treatment_a, treatment_b in COMPARISONS:
            a = executions[treatment_a]
            b = executions[treatment_b]
            a_viable = a["lifecycle_outcome"] == "COMPLETED"
            b_viable = b["lifecycle_outcome"] == "COMPLETED"
            review_outcome, review_digests = resolved.decided_outcomes.get(
                (attempt["block_id"], comparison),
                (None, []),
            )
            if a_viable and not b_viable:
                viability, method, quality = "A_ONLY", "A_WIN", "NOT_APPLICABLE"
            elif b_viable and not a_viable:
                viability, method, quality = "B_ONLY", "B_WIN", "NOT_APPLICABLE"
            elif a_viable and b_viable:
                if review_outcome is None:
                    _fail("review_outcome_missing")
                viability = "BOTH"
                method = {
                    "A": "A_WIN",
                    "B": "B_WIN",
                    "TIE": "TIE",
                    "INDETERMINATE": "INDETERMINATE",
                }[review_outcome]
                quality = {
                    "outcome": review_outcome,
                    "review_result_digests": review_digests,
                }
            else:
                viability, method = "NEITHER", "TIE_NONVIABLE"
                both_products_reviewable = (
                    a["product_frozen"] and b["product_frozen"]
                )
                if both_products_reviewable:
                    if review_outcome is None:
                        _fail("review_outcome_missing")
                    quality = {
                        "outcome": review_outcome,
                        "review_result_digests": review_digests,
                    }
                else:
                    if review_outcome is not None:
                        _fail("review_outcome_unreviewable")
                    quality = "NOT_REVIEWABLE"
            method_outcomes.append(
                {
                    "comparison": comparison,
                    "viability_case": viability,
                    "method_outcome": method,
                    "product_quality_review": quality,
                }
            )
            count_key = {
                "A_WIN": "a_win_count",
                "B_WIN": "b_win_count",
                "TIE": "tie_count",
                "INDETERMINATE": "indeterminate_count",
                "TIE_NONVIABLE": "tie_nonviable_count",
            }[method]
            comparison_counts[comparison][count_key] += 1
        valid_blocks.append(
            {
                "block_id": attempt["block_id"],
                "block_attempt_digest": canonical_sha256(attempt),
                "method_outcomes": method_outcomes,
            }
        )

    guess_confusion = [
        {
            "actual_treatment_id": actual,
            "guessed_treatment_id": guessed,
            "count": resolved.guess_counts[(actual, guessed)],
        }
        for actual in TREATMENTS
        for guessed in (*TREATMENTS, "UNKNOWN")
    ]
    summary: dict[str, object] = {
        "record_kind": "pilot_summary.v1",
        "summary_id": f"summary-{lock_record['pilot_id']}",
        "pilot_lock_digest": canonical_sha256(lock_record),
        "status": status,
        "valid_blocks": valid_blocks,
        "excluded_block_references": excluded,
        "comparison_counts": [
            comparison_counts[name] for name, _a, _b in COMPARISONS
        ],
        "treatment_statistics": metrics.treatment_statistics,
        "review_diagnostics": {
            "agreement_count": resolved.agreement_count,
            "disagreement_count": resolved.disagreement_count,
            "adjudication_count": resolved.adjudication_count,
            "blocks": resolved.diagnostic_blocks,
            "guess_accuracy": (
                "UNKNOWN"
                if resolved.total_guesses == 0
                else _fraction(
                    Fraction(
                        resolved.correct_guesses,
                        resolved.total_guesses,
                    )
                )
            ),
            "guess_confusion": guess_confusion,
        },
        "hard_contract_findings": metrics.hard_contract_findings,
        "medians": metrics.medians,
        "ratios": metrics.ratios,
    }
    if status != "EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED":
        summary["terminal_reason_code"] = status
    _validate_record(summary, "pilot_summary.v1")
    return summary
