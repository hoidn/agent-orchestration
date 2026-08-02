from __future__ import annotations

import pytest

from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
)
from orchestrator.workflow.trial.verdict import (
    TrialVerdictError,
    aggregate_trial_verdict,
)


def _cost(amount: float = 0.01) -> dict[str, object]:
    return {
        "variant": "KNOWN",
        "amount": amount,
        "currency": "USD",
    }


def _tokens(total: int = 3) -> dict[str, object]:
    return {
        "variant": "KNOWN",
        "prompt_tokens": total - 1,
        "completion_tokens": 1,
        "total_tokens": total,
    }


def _attempt(*, duration_ms: int = 2) -> dict[str, object]:
    return {
        "attempt": 1,
        "global_attempt": 1,
        "status": "scored",
        "exit_code": 0,
        "duration_ms": duration_ms,
        "token_usage": _tokens(),
        "cost": _cost(),
    }


def _outcome(cell: TrialCellKey, status: str) -> dict[str, object]:
    return {
        "cell": cell.record,
        "outcome": status,
        "child_attempts": 1,
        "elapsed_ms": 5,
        "token_usage": _tokens(5),
        "cost": _cost(0.02),
    }


def _success_rule() -> dict[str, float]:
    return {
        "min_abs_improvement": 0.05,
        "max_cost_ratio": 2.0,
        "min_cost_reduction": 0.20,
    }


def test_all_completed_scored_repetitions_are_eligible_for_ranking() -> None:
    cells = (
        TrialCellKey("baseline", 1),
        TrialCellKey("candidate", 1),
    )
    labels = ("opaque-" + "1" * 64, "opaque-" + "2" * 64)
    sealed = build_sealed_opaque_label_map(cells, labels=labels)

    result = aggregate_trial_verdict(
        authored_arm_order=("baseline", "candidate"),
        reps=1,
        cell_outcomes=tuple(_outcome(cell, "COMPLETED") for cell in cells),
        score_rows=(
            {
                "evaluation_label": labels[0],
                "score_status": "scored",
                "score": 0.60,
                "charged_attempts": [_attempt()],
            },
            {
                "evaluation_label": labels[1],
                "score_status": "scored",
                "score": 0.90,
                "charged_attempts": [_attempt()],
            },
        ),
        sealed_label_map=sealed,
        success_rule=_success_rule(),
    )

    assert result["per_repetition"] == [
        {"arm_id": "baseline", "rep": 1, "outcome": "COMPLETED", "score": 0.6},
        {"arm_id": "candidate", "rep": 1, "outcome": "COMPLETED", "score": 0.9},
    ]
    assert result["ranking"] == ["candidate", "baseline"]
    assert result["selected_arm"] == "candidate"
    assert result["success_rule_disposition"] == "superior"
    assert result["budget_accounting"]["elapsed_ms"] == 14


def test_failed_outcome_raw_score_is_ineligible_and_cannot_select_an_arm() -> None:
    authored_order = ("failed-high", "winner", "failed-low")
    cells = tuple(TrialCellKey(arm_id, 1) for arm_id in authored_order)
    labels = tuple(f"opaque-{digit * 64}" for digit in ("3", "4", "5"))
    sealed = build_sealed_opaque_label_map(cells, labels=labels)

    result = aggregate_trial_verdict(
        authored_arm_order=authored_order,
        reps=1,
        cell_outcomes=(
            _outcome(cells[0], "FAILED"),
            _outcome(cells[1], "COMPLETED"),
            _outcome(cells[2], "FAILED"),
        ),
        score_rows=tuple(
            {
                "evaluation_label": label,
                "score_status": "scored",
                "score": score,
                "charged_attempts": [_attempt()],
            }
            for label, score in zip(labels, (0.99, 0.80, 0.10), strict=True)
        ),
        sealed_label_map=sealed,
        success_rule=_success_rule(),
    )

    assert [row["score"] for row in result["per_repetition"]] == [None, 0.8, None]
    assert result["aggregate_scores"] == [
        {
            "arm_id": "failed-high",
            "score": None,
            "completed_count": 0,
            "failed_count": 1,
        },
        {
            "arm_id": "winner",
            "score": 0.8,
            "completed_count": 1,
            "failed_count": 0,
        },
        {
            "arm_id": "failed-low",
            "score": None,
            "completed_count": 0,
            "failed_count": 1,
        },
    ]
    assert result["ranking"] == ["winner", "failed-high", "failed-low"]
    assert result["selected_arm"] is None
    assert result["success_rule_disposition"] == "insufficient_scored_arms"


def test_missing_evaluator_attempt_duration_fails_closed() -> None:
    cells = (TrialCellKey("left", 1), TrialCellKey("right", 1))
    labels = ("opaque-" + "6" * 64, "opaque-" + "7" * 64)
    sealed = build_sealed_opaque_label_map(cells, labels=labels)
    missing_duration = _attempt()
    del missing_duration["duration_ms"]

    with pytest.raises(TrialVerdictError, match="attempt accounting"):
        aggregate_trial_verdict(
            authored_arm_order=("left", "right"),
            reps=1,
            cell_outcomes=tuple(_outcome(cell, "COMPLETED") for cell in cells),
            score_rows=(
                {
                    "evaluation_label": labels[0],
                    "score_status": "scored",
                    "score": 0.5,
                    "charged_attempts": [missing_duration],
                },
                {
                    "evaluation_label": labels[1],
                    "score_status": "scored",
                    "score": 0.6,
                    "charged_attempts": [_attempt()],
                },
            ),
            sealed_label_map=sealed,
            success_rule=_success_rule(),
        )
