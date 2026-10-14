"""Read-only historical transition audit consumers; execution is retired."""

from hashlib import sha256
import json

import pytest

from orchestrator.workflow.transition_executor import (
    read_transition_audit_rows,
    transition_audit_file_digest,
)


def test_missing_transition_audit_is_not_created_by_readers(tmp_path):
    audit_path = tmp_path / "nested" / "transition-audit.jsonl"
    assert read_transition_audit_rows(audit_path) == []
    assert transition_audit_file_digest(audit_path) is None
    assert not audit_path.parent.exists()


@pytest.mark.parametrize("rows", [[], [{"status": "COMMITTED", "message": "héllo"}],
    [{"outcome_code": "committed", "version": 1, "result": {"status": "BLOCKED"}},
     {"outcome_code": "rejected", "version": 1, "reason": None}]])
def test_historical_transition_audit_rows_and_digest_are_readonly(tmp_path, rows):
    audit_path = tmp_path / "transition-audit.jsonl"
    raw = ("\n" + "\n \n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode()
    audit_path.write_bytes(raw)
    assert read_transition_audit_rows(audit_path) == rows
    assert transition_audit_file_digest(audit_path) == "sha256:" + sha256(raw).hexdigest()
    assert audit_path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [audit_path]


def test_malformed_transition_audit_is_not_repaired_or_rewritten(tmp_path):
    audit_path = tmp_path / "transition-audit.jsonl"
    raw = b'{"outcome_code":"committed"}\n{"partial":'
    audit_path.write_bytes(raw)
    with pytest.raises(json.JSONDecodeError):
        read_transition_audit_rows(audit_path)
    assert transition_audit_file_digest(audit_path) == "sha256:" + sha256(raw).hexdigest()
    assert audit_path.read_bytes() == raw
    assert list(tmp_path.iterdir()) == [audit_path]
