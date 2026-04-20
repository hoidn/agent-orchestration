"""Dedicated adjudicated-provider resume test selector.

The underlying resume scenarios live with the runtime integration harness in
``test_adjudicated_provider_runtime``. Re-exporting them here keeps the approved
plan's final verification selector stable while avoiding duplicate harness code.
"""

from tests.test_adjudicated_provider_runtime import (
    test_existing_adjudication_sidecars_fail_fast_without_rebaseline,
    test_resume_after_baseline_snapshot_reuses_baseline_and_runs_candidates,
    test_resume_after_committed_promotion_finalizes_ledger_mirror_and_publication,
    test_resume_after_partial_candidate_generation_runs_remaining_candidates,
    test_resume_after_scored_candidates_promotes_without_rerunning_candidates,
    test_resume_rejects_mismatched_adjudication_sidecars,
    test_resume_rejects_scorer_unavailable_sidecars_that_no_longer_match,
)
