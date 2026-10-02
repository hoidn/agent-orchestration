from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.memo import MemoError, read_memo


FETCH = "workflow:demo::run / fetch"
CHILD = "workflow:demo::run / child"
SITES = {FETCH: "command", CHILD: "run_ref"}
DIGEST = "sha256:" + "0" * 64


def _row(record: str, identity: str | None = None, attempt: int | None = None, **fields):
    result = {"record": record, **fields}
    if identity is not None:
        result["identity"] = identity
    if attempt is not None:
        result["attempt"] = attempt
    return result


def _line(row: dict) -> bytes:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def _write(path: Path, *rows: dict) -> bytes:
    data = b"".join(_line(row) for row in rows)
    path.write_bytes(data)
    return data


def _started(identity: str, attempt: int = 1) -> dict:
    input_digest = "sha256:" + hashlib.sha256(identity.encode()).hexdigest()
    return _row(
        "started",
        identity,
        attempt,
        input_digest=input_digest,
        input_parts={"arguments": input_digest},
        implementation_files={},
        result_path=f"effects/{hashlib.sha256(identity.encode()).hexdigest()}/attempt-{attempt}/result.json",
        time=1.0,
    )


def _committed(identity: str, attempt: int = 1, *, effect_class="command", **fields) -> dict:
    started = _started(identity, attempt)
    committed = {
        "input_digest": started["input_digest"],
        "input_parts": started["input_parts"],
        "implementation_files": started["implementation_files"],
        "result_path": started["result_path"],
        "result_digest": DIGEST,
        "value": {"ok": True},
        "depends_on": [],
        "effect_class": effect_class,
        "time": 2.0,
    }
    committed.update(fields)
    return _row(
        "committed",
        identity,
        attempt,
        **committed,
    )


def _run_ref_proof(identity: str, tmp_path: Path) -> dict:
    digest = DIGEST
    root = tmp_path / "run-refs"
    return {
        "settled_result": {
            "visit": {
                "parent_run_id": "parent-run",
                "execution_frame_id": "root",
                "call_frame_id": None,
                "step_id": "root." + hashlib.sha256(
                    json.dumps(identity, separators=(",", ":")).encode()
                ).hexdigest(),
                "visit_count": 1,
            },
            "attempt_ordinal": 1,
            "step_config_digest": digest,
            "run_ref_root": root.as_posix(),
            "workspace_path": (root / "child").as_posix(),
            "child_run_id": "child-run",
            "pending_row_digest": digest,
            "child_terminal_state_digest": digest,
            "result_contract_digest": digest,
            "result_payload_digest": digest,
            "workspace_delta_digest": digest,
            "accounting_digest": digest,
            "evidence_manifest_digest": digest,
        },
        "artifacts": {},
    }


def test_reducer_keeps_retries_terminal_reopening_and_current_authority(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(FETCH),
        _row("failed", FETCH, 1, code="command_failed", exit_info={}, violations=[]),
        _row("terminal", outcome="failed", code="command_failed", message="first try"),
        _started(FETCH, 2),
        _committed(FETCH, 2),
        _row("terminal", outcome="completed", value={"answer": 42}),
    )

    reduced = read_memo(journal, SITES)

    assert reduced.active_commits[FETCH].data["attempt"] == 2
    assert reduced.latest_starts[FETCH].data["attempt"] == 2
    assert reduced.terminal.data["value"] == {"answer": 42}
    assert reduced.unsettled_coordinators == {}


@pytest.mark.parametrize(
    "rows",
    [
        [_started(FETCH), _committed(FETCH, effect_class="provider")],
        [_started("workflow:demo::run / typo"), _committed("workflow:demo::run / typo")],
        [_row("terminal", outcome="failed", code="x", message="x"), _row("terminal", outcome="completed", value=None)],
        [_started(FETCH, 2)],
        [_started(FETCH), _started(FETCH)],
    ],
    ids=["class-disagrees-with-checked-site", "unknown-site", "adjacent-terminals", "ordinal-gap", "ordinal-collision"],
)
def test_reducer_rejects_malformed_transitions_before_returning_a_view(tmp_path: Path, rows: list[dict]) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, *rows)

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_retry_uses_next_ordinal_after_surviving_start_without_invented_failure(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(FETCH),
        _started(FETCH, 2),
        _committed(FETCH, 2),
        _row("terminal", outcome="completed", value={"answer": 2}),
    )

    reduced = read_memo(journal, SITES)

    assert reduced.latest_starts[FETCH].data["attempt"] == 2
    assert reduced.active_commits[FETCH].data["attempt"] == 2
    assert reduced.terminal.data["value"] == {"answer": 2}
    assert [entry.data["record"] for entry in reduced.entries] == [
        "started",
        "started",
        "committed",
        "terminal",
    ]


def test_latest_uncommitted_retry_start_replaces_pending_evidence(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH), _started(FETCH, 2))

    reduced = read_memo(journal, SITES)

    assert reduced.latest_starts[FETCH].data["attempt"] == 2
    assert reduced.pending_starts[FETCH].data["attempt"] == 2


@pytest.mark.parametrize("stale_record", ["committed", "failed"])
def test_retry_rejects_completion_for_superseded_start(tmp_path: Path, stale_record: str) -> None:
    journal = tmp_path / "memo.jsonl"
    stale = (
        _committed(FETCH, 1)
        if stale_record == "committed"
        else _row("failed", FETCH, 1, code="old_attempt", exit_info={})
    )
    _write(journal, _started(FETCH), _started(FETCH, 2), stale)

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_carriage_return_is_content_not_a_record_boundary(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    raw = _line(_started(FETCH)).removesuffix(b"\n") + b"\r" + _line(_committed(FETCH))
    journal.write_bytes(raw)

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"
    assert journal.read_bytes() == raw


@pytest.mark.parametrize(
    "implementation_files",
    [
        {"[ \"workspace\", \"script.py\", null ]": {"kind": "file", "digest": DIGEST}},
        {"[\"workspace\",\"script.py\",true]": {"kind": "file", "digest": DIGEST}},
        {"[\"workspace\",\"script.py\",null]": {"kind": "file", "digest": DIGEST, "extra": "x"}},
        {"[\"workspace\",\"script.py\",null]": {"kind": "file", "digest": DIGEST, "target": "../outside"}},
        {"[\"workspace\",\"script.py\",null]": {"kind": "directory", "target": "script.py"}},
    ],
)
def test_reader_rejects_malformed_implementation_evidence_without_repair(
    tmp_path: Path, implementation_files: dict
) -> None:
    journal = tmp_path / "memo.jsonl"
    started = _started(FETCH)
    started["implementation_files"] = implementation_files
    raw = _write(journal, started)

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"
    assert journal.read_bytes() == raw


@pytest.mark.parametrize("proof", [None, [], "proof"])
def test_reducer_requires_structured_proof_for_checked_coordinator_site(tmp_path: Path, proof) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(CHILD),
        _committed(CHILD, effect_class="run_ref", proof=proof),
    )

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_valid_coordinator_proof_settles_once_before_terminal(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    proof = _run_ref_proof(CHILD, tmp_path)
    _write(
        journal,
        _started(CHILD),
        _committed(CHILD, effect_class="run_ref", proof=proof),
        _row("settled", CHILD, 1, by="settle"),
        _row("terminal", outcome="completed", value={"answer": 1}),
    )

    reduced = read_memo(journal, SITES)

    assert reduced.settlements == {(CHILD, 1)}
    assert reduced.unsettled_coordinators == {}


def test_coordinator_proof_binds_checked_identity_but_not_memo_ordinal(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    proof = _run_ref_proof(CHILD, tmp_path)
    _write(
        journal,
        _started(CHILD),
        _row("failed", CHILD, 1, code="retry", exit_info={}),
        _started(CHILD, 2),
        _committed(CHILD, 2, effect_class="run_ref", proof=proof),
        _row("settled", CHILD, 2, by="reconcile"),
    )

    reduced = read_memo(journal, SITES)

    assert reduced.active_commits[CHILD].data["attempt"] == 2
    assert reduced.settlements == {(CHILD, 2)}


def test_checked_command_site_cannot_become_coordinator_from_proof_presence(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(FETCH),
        _committed(FETCH, effect_class="run_ref", proof=_run_ref_proof(FETCH, tmp_path)),
    )

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_checked_wildcard_site_accepts_normalized_dynamic_identity(tmp_path: Path) -> None:
    identity = "workflow:demo::run / fetch[12]"
    sites = {"workflow:demo::run / fetch[*]": "command"}
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(identity), _committed(identity))

    assert identity in read_memo(journal, sites).active_commits


def test_checked_wildcard_site_rejects_uninstantiated_identity(tmp_path: Path) -> None:
    identity = "workflow:demo::run / loop:state[*] / fetch"
    sites = {identity: "command"}
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(identity), _committed(identity))

    with pytest.raises(MemoError) as error:
        read_memo(journal, sites)

    assert error.value.code == "memo_inconsistent"


def test_checked_static_identity_keeps_escaped_literal_brackets(tmp_path: Path) -> None:
    identity = "workflow:demo::run / loop:state%5B*%5D / fetch"
    sites = {identity: "command"}
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(identity), _committed(identity))

    assert identity in read_memo(journal, sites).active_commits


def test_checked_wildcard_site_normalizes_multiple_concrete_indices(tmp_path: Path) -> None:
    identity = "workflow:demo::run / loop:state[2] / par-map:item[4] / fetch"
    sites = {"workflow:demo::run / loop:state[*] / par-map:item[*] / fetch": "command"}
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(identity), _committed(identity))

    assert identity in read_memo(journal, sites).active_commits


def test_checked_wildcard_site_accepts_canonical_zero_ordinal(tmp_path: Path) -> None:
    identity = "workflow:demo::run / loop:state[0] / fetch"
    sites = {"workflow:demo::run / loop:state[*] / fetch": "command"}
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(identity), _committed(identity))

    assert identity in read_memo(journal, sites).active_commits


def test_checked_wildcard_site_rejects_leading_zero_ordinal(tmp_path: Path) -> None:
    identity = "workflow:demo::run / loop:state[00] / fetch"
    sites = {"workflow:demo::run / loop:state[*] / fetch": "command"}
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(identity), _committed(identity))

    with pytest.raises(MemoError) as error:
        read_memo(journal, sites)

    assert error.value.code == "memo_inconsistent"


def test_terminal_rejects_unsettled_coordinator_and_settlement_must_match_attempt(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(CHILD),
        _committed(CHILD, effect_class="run_ref", proof=_run_ref_proof(CHILD, tmp_path)),
        _row("settled", CHILD, 2, by="settle"),
    )

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_latest_start_is_retained_when_earlier_start_has_no_failed_row(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH))

    reduced = read_memo(journal, SITES)

    assert reduced.latest_starts[FETCH].data["attempt"] == 1
    assert reduced.pending_starts[FETCH].data["attempt"] == 1


def test_terminal_failure_after_effect_commit_is_valid(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(FETCH),
        _committed(FETCH),
        _row("terminal", outcome="failed", code="downstream_failed", message="later pure step"),
    )

    reduced = read_memo(journal, SITES)

    assert FETCH in reduced.active_commits
    assert reduced.terminal.data["outcome"] == "failed"


@pytest.mark.parametrize("by", [None, [], "complete"])
def test_settlement_requires_contract_by_value(tmp_path: Path, by) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(CHILD),
        _committed(CHILD, effect_class="run_ref", proof=_run_ref_proof(CHILD, tmp_path)),
        _row("settled", CHILD, 1, by=by),
    )

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


@pytest.mark.parametrize("depends_on", [["workflow:demo::run / missing"], [FETCH, FETCH]])
def test_dependencies_must_be_unique_and_active_checked_sites(tmp_path: Path, depends_on: list[str]) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH), _committed(FETCH, depends_on=depends_on))

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_active_checked_dependency_is_accepted(tmp_path: Path) -> None:
    second = "workflow:demo::run / second"
    journal = tmp_path / "memo.jsonl"
    sites = {**SITES, second: "command"}
    _write(
        journal,
        _started(FETCH),
        _committed(FETCH),
        _started(second),
        _committed(second, depends_on=[FETCH]),
    )

    assert read_memo(journal, sites).active_commits[second].data["depends_on"] == [FETCH]
