from __future__ import annotations


import pytest

from orchestrator.state import (
    RunState,
)
from orchestrator.workflow.human_input import (
    validate_human_input_record,
)


def _pending_record() -> dict[str, object]:
    return {
        "request_id": "00000000-0000-4000-8000-000000000001",
        "resume_scope": {"root_workflow_file": "workflow.yaml", "call_frame_ids": []},
        "runtime_step_id": "request",
        "enclosing_step": {
            "step_name": "request", "step_id": "request", "visit_count": 1,
        },
        "loop_iteration": None,
        "question": "Continue?",
        "status": "pending",
    }


def test_human_input_record_is_closed_and_pending_omits_reply() -> None:
    record = _pending_record()
    assert validate_human_input_record(record) == record
    with pytest.raises(ValueError):
        validate_human_input_record({**record, "reply": None})
    with pytest.raises(ValueError):
        validate_human_input_record({**record, "extra": True})
    for reply in (
        {"variant": "ANSWERED"},
        {"variant": "ANSWERED", "text": 0},
        {"variant": "CANCELLED", "text": "unexpected"},
        {"variant": "UNKNOWN"},
    ):
        with pytest.raises(ValueError):
            validate_human_input_record({**record, "status": "answered", "reply": reply})


def test_run_state_omits_absent_human_input_and_validates_present_value() -> None:
    state = RunState(
        schema_version="2.1", run_id="run", workflow_file="workflow.yaml",
        workflow_checksum="checksum", started_at="now", updated_at="now", status="running",
    )
    assert "human_input" not in state.to_dict()
    state.human_input = _pending_record()
    assert RunState.from_dict(state.to_dict()).human_input == _pending_record()


@pytest.mark.parametrize("request_id", [0, {}, []])
def test_invalid_request_id_type_is_a_value_error(request_id: object) -> None:
    record = _pending_record()
    record["request_id"] = request_id
    with pytest.raises(ValueError, match="request_id"):
        validate_human_input_record(record)
