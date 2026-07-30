"""Dedicated adjudicated-provider resume test selector.

The underlying resume scenarios live with the runtime integration harness in
``test_adjudicated_provider_runtime``. Re-exporting them here keeps the approved
plan's final verification selector stable while avoiding duplicate harness code.
"""

from pathlib import Path

import pytest

from tests.test_adjudicated_provider_runtime import (
    _resume,
    _run,
    _workflow,
    test_existing_adjudication_sidecars_fail_fast_without_rebaseline,
    test_resume_after_baseline_snapshot_reuses_baseline_and_runs_candidates,
    test_resume_after_committed_promotion_finalizes_ledger_mirror_and_publication,
    test_resume_after_committed_promotion_publishes_root_result_bundle,
    test_resume_after_partial_candidate_generation_runs_remaining_candidates,
    test_resume_after_scored_candidates_promotes_without_rerunning_candidates,
    test_resume_reruns_mismatched_adjudication_sidecars,
    test_resume_reruns_scorer_unavailable_sidecars_that_no_longer_match,
    test_resume_source_mutation_reports_root_checksum_mismatch_before_adjudication,
)


def test_consistent_adjudication_resume_reuses_without_invocation(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    candidate_attempts = tmp_path / "candidate_attempts.txt"
    evaluator_attempts = tmp_path / "evaluator_attempts.txt"
    workflow = _workflow(scores={"a": 0.9})
    workflow["steps"][0]["adjudicated_provider"]["candidates"] = [
        {"id": "a", "provider": "candidate_a"},
    ]
    workflow["providers"]["candidate_a"]["command"] = [
        "python",
        "-c",
        (
            "from pathlib import Path\n"
            f"attempt_file = Path({candidate_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "Path('state').mkdir(parents=True, exist_ok=True)\n"
            "Path('docs/plans').mkdir(parents=True, exist_ok=True)\n"
            "Path('state/result_path.txt').write_text('docs/plans/a.md\\n', encoding='utf-8')\n"
            "Path('docs/plans/a.md').write_text('selected once', encoding='utf-8')\n"
        ),
    ]
    workflow["providers"]["evaluator"]["command"] = [
        "python",
        "-c",
        (
            "import json, sys\n"
            "from pathlib import Path\n"
            f"attempt_file = Path({evaluator_attempts.as_posix()!r})\n"
            "attempt = int(attempt_file.read_text(encoding='utf-8')) + 1 if attempt_file.exists() else 1\n"
            "attempt_file.write_text(str(attempt), encoding='utf-8')\n"
            "packet = json.loads(sys.stdin.read().split('Evaluator Packet:', 1)[1])\n"
            "print(json.dumps({'candidate_id': packet['candidate_id'], 'score': 0.9, 'summary': 'scored'}))\n"
        ),
    ]

    caplog.set_level("WARNING")
    initial = _run(tmp_path, workflow)
    initial_adjudication = initial["steps"]["Draft"]["adjudication"]
    caplog.clear()
    resumed = _resume(tmp_path, workflow)

    assert initial["status"] == "completed"
    assert resumed["status"] == "completed"
    assert resumed["step_visits"]["Draft"] == 1
    assert resumed["steps"]["Draft"]["adjudication"] == initial_adjudication
    assert candidate_attempts.read_text(encoding="utf-8") == "1"
    assert evaluator_attempts.read_text(encoding="utf-8") == "1"
    assert not [
        record
        for record in caplog.records
        if getattr(record, "orchestrator_diagnostic", None)
        == "adjudication_state_mismatch_rerun"
    ]
