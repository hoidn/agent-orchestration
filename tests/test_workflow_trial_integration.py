from __future__ import annotations


from orchestrator.state import StepResult
from orchestrator.workflow.step_results import to_step_result


def test_trial_step_result_round_trips_exact_outer_authority() -> None:
    trial = {
        "schema_version": "trial_parent_result.v1",
        "request_digest": "sha256:" + "1" * 64,
        "prepared_row_digest": "sha256:" + "2" * 64,
        "result_envelope": {"outcomes": [], "verdict": {}, "verdict_artifact": "artifacts/trials/verdict.json"},
    }

    encoded = StepResult(status="completed", trial=trial).to_dict()
    decoded = to_step_result(encoded, "Compare")

    assert encoded["trial"] == trial
    assert decoded.trial == trial
