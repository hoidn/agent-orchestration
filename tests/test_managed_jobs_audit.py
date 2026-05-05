from pathlib import Path

import pytest

from orchestrator.managed_jobs.audit import AuditEventError, append_event, read_events


def test_audit_append_creates_parent_and_reads_events_in_order(tmp_path: Path) -> None:
    audit_path = tmp_path / "run" / "managed_job_events.jsonl"

    append_event(
        audit_path,
        {
            "event": "job_submitted",
            "job_id": "job-1",
            "job_state_path": "state/jobs/job-1/job_state.json",
        },
    )
    append_event(
        audit_path,
        {
            "event": "job_completed",
            "job_id": "job-1",
            "terminal_state": "COMPLETED",
        },
    )

    assert [event["event"] for event in read_events(audit_path)] == [
        "job_submitted",
        "job_completed",
    ]


def test_audit_rejects_unknown_event_type(tmp_path: Path) -> None:
    with pytest.raises(AuditEventError, match="unknown event type"):
        append_event(tmp_path / "events.jsonl", {"event": "surprise"})


def test_audit_rejects_malformed_json(tmp_path: Path) -> None:
    audit_path = tmp_path / "events.jsonl"
    audit_path.write_text('{"event": "job_submitted"\\n', encoding="utf-8")

    with pytest.raises(AuditEventError, match="malformed JSON"):
        read_events(audit_path)
