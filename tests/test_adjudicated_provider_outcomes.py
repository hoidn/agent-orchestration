import pytest

from orchestrator.workflow.adjudication import AdjudicationDeadline, adjudication_outcome


@pytest.mark.parametrize(
    ("error_type", "exit_code", "phase", "klass", "retryable"),
    [
        ("adjudication_no_valid_candidates", 2, "post_execution", "adjudication_no_valid_candidates", False),
        ("adjudication_scorer_unavailable", 2, "execution", "adjudication_scorer_unavailable", False),
        ("adjudication_partial_scoring_failed", 2, "execution", "adjudication_partial_scoring_failed", False),
        ("timeout", 124, "execution", "timeout", True),
        ("ledger_path_collision", 2, "post_execution", "ledger_path_collision", False),
        ("ledger_conflict", 2, "post_execution", "ledger_conflict", False),
        ("ledger_mirror_failed", 2, "post_execution", "ledger_mirror_failed", False),
        ("promotion_conflict", 2, "post_execution", "promotion_conflict", False),
        ("promotion_validation_failed", 2, "post_execution", "promotion_validation_failed", False),
        ("promotion_rollback_conflict", 2, "post_execution", "promotion_rollback_conflict", False),
        ("adjudication_resume_mismatch", 2, "pre_execution", "adjudication_resume_mismatch", False),
    ],
)
def test_adjudication_outcome_mapping(error_type: str, exit_code: int, phase: str, klass: str, retryable: bool) -> None:
    outcome = adjudication_outcome(error_type)

    assert outcome["exit_code"] == exit_code
    assert outcome["outcome"] == {
        "status": "failed",
        "phase": phase,
        "class": klass,
        "retryable": retryable,
    }


def test_adjudication_deadline_reports_remaining_time_and_expiry() -> None:
    deadline = AdjudicationDeadline(started_monotonic=10.0, timeout_sec=5.0)

    assert deadline.remaining_timeout_sec(12.0) == 3.0
    assert deadline.remaining_timeout_sec(16.0) == 0.0
    with pytest.raises(TimeoutError):
        deadline.require_time_remaining("promotion", 16.0)


def test_adjudication_deadline_without_timeout_is_unbounded() -> None:
    deadline = AdjudicationDeadline(started_monotonic=10.0, timeout_sec=None)

    assert deadline.remaining_timeout_sec(1000.0) is None
    deadline.require_time_remaining("selection", 1000.0)
