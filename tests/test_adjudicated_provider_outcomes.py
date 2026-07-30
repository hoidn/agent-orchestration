from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.workflow.adjudication import (
    AdjudicationDeadline,
    adjudication_outcome,
    adjudication_visit_paths,
)
from orchestrator.workflow.adjudication_resume import (
    AdjudicationResumeDecision,
    classify_adjudication_resume_mismatch,
)


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
        (
            "adjudication_state_integrity_error",
            2,
            "pre_execution",
            "adjudication_state_integrity_error",
            False,
        ),
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


def test_adjudication_resume_mismatch_classifies_one_exact_scope_for_rerun(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / ".orchestrate" / "runs" / "run-1"
    run_root.mkdir(parents=True)
    visit_paths = adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        1,
    )

    decision = classify_adjudication_resume_mismatch(
        run_root=run_root,
        frame_scope="root",
        step_id="root.draft",
        visit_count=1,
        visit_paths=visit_paths,
        message="candidate metadata does not match",
    )

    assert decision.kind == "rerun_exact_scope"
    assert decision.scope is not None
    assert decision.scope.run_root == run_root
    assert decision.scope.frame_scope == "root"
    assert decision.scope.step_id == "root.draft"
    assert decision.scope.visit_count == 1
    assert decision.scope.visit_paths == visit_paths
    assert decision.message == "candidate metadata does not match"


@pytest.mark.parametrize(
    "invalid_scope",
    (
        "missing_frame_scope",
        "invalid_step_id",
        "invalid_visit_count",
        "noncanonical_visit_paths",
        "escaping_visit_paths",
    ),
)
def test_adjudication_resume_mismatch_unprovable_scope_is_integrity_error(
    tmp_path: Path,
    invalid_scope: str,
) -> None:
    run_root = tmp_path / ".orchestrate" / "runs" / "run-1"
    run_root.mkdir(parents=True)
    frame_scope: object = "root"
    step_id: object = "root.draft"
    visit_count: object = 1
    visit_paths = adjudication_visit_paths(
        run_root,
        str(frame_scope),
        str(step_id),
        int(visit_count),
    )

    if invalid_scope == "missing_frame_scope":
        frame_scope = None
    elif invalid_scope == "invalid_step_id":
        step_id = "../outside"
    elif invalid_scope == "invalid_visit_count":
        visit_count = 0
    elif invalid_scope == "noncanonical_visit_paths":
        visit_paths = replace(
            visit_paths,
            run_score_ledger_path=run_root
            / "adjudication"
            / "root"
            / "root.other"
            / "1"
            / "candidate_scores.jsonl",
        )
    elif invalid_scope == "escaping_visit_paths":
        visit_paths = replace(
            visit_paths,
            adjudication_root=tmp_path / "outside",
        )

    decision = classify_adjudication_resume_mismatch(
        run_root=run_root,
        frame_scope=frame_scope,
        step_id=step_id,
        visit_count=visit_count,
        visit_paths=visit_paths,
        message="unprovable mismatch",
    )

    assert decision.kind == "integrity_error"
    assert decision.scope is None
    assert decision.message


def test_adjudication_resume_mismatch_aliased_scope_is_integrity_error(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / ".orchestrate" / "runs" / "run-1"
    run_root.mkdir(parents=True)
    outside = tmp_path / "aliased-adjudication"
    outside.mkdir()
    (run_root / "adjudication").symlink_to(outside, target_is_directory=True)
    visit_paths = adjudication_visit_paths(
        run_root,
        "root",
        "root.draft",
        1,
    )

    decision = classify_adjudication_resume_mismatch(
        run_root=run_root,
        frame_scope="root",
        step_id="root.draft",
        visit_count=1,
        visit_paths=visit_paths,
        message="aliased mismatch",
    )

    assert decision.kind == "integrity_error"
    assert decision.scope is None


def test_adjudication_resume_reuse_has_no_cleanup_scope() -> None:
    decision = AdjudicationResumeDecision.reuse()

    assert decision.kind == "reuse"
    assert decision.scope is None
    assert decision.message is None
