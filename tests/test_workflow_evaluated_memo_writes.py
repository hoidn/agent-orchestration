from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import orchestrator.workflow.evaluated.closure as closure_module
import orchestrator.workflow.evaluated.memo as memo_module
from orchestrator.workflow.evaluated.memo import (
    MemoError,
    append_record,
    invalidate_suffix,
    memo_writer_lock,
    read_memo,
    repair_torn_tail,
    reduce_memo,
)


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


def test_reader_ignores_but_never_repairs_an_incomplete_tail(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    complete = _line(_started(FETCH))
    original = complete + b'{"record":"started","identity":"cut\r'
    journal.write_bytes(original)

    reduced = read_memo(journal, SITES)

    assert len(reduced.entries) == 1
    assert reduced.tail == original[len(complete) :]
    assert journal.read_bytes() == original
    with memo_writer_lock(tmp_path):
        repair_torn_tail(journal, reduced)
    assert journal.read_bytes() == complete


@pytest.mark.parametrize("raw", [b"\xff\n", b'{"record":"unknown"}\n'])
def test_complete_invalid_rows_are_inconsistent_not_torn(tmp_path: Path, raw: bytes) -> None:
    journal = tmp_path / "memo.jsonl"
    journal.write_bytes(raw)

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


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
@pytest.mark.parametrize("kind", ["started", "committed"])
def test_append_rejects_malformed_implementation_evidence_before_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    implementation_files: dict,
    kind: str,
) -> None:
    journal = tmp_path / "memo.jsonl"
    before = _write(journal, _started(FETCH))
    record = _started(FETCH) if kind == "started" else _committed(FETCH)
    record["implementation_files"] = implementation_files

    def unexpected_open(_path: Path) -> int:
        pytest.fail("invalid evidence reached journal open")

    monkeypatch.setattr(memo_module, "_open_append", unexpected_open)
    with pytest.raises(MemoError) as error:
        append_record(journal, record)

    assert error.value.code == "memo_inconsistent"
    assert journal.read_bytes() == before


def test_nonempty_implementation_evidence_round_trips_without_live_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "memo.jsonl"
    workspace = tmp_path / "workspace"
    source = workspace / "src" / "declared.py"
    file_target = workspace / "src" / "resolved.py"
    directory = workspace / "bin" / "tool"
    directory_target = workspace / "bin" / "resolved-tool"
    source.parent.mkdir(parents=True)
    directory.parent.mkdir(parents=True)
    source.write_text("source", encoding="utf-8")
    file_target.write_text("target", encoding="utf-8")
    directory.mkdir()
    directory_target.mkdir()
    evidence = {
        '["workspace","bin/tool",2]': {
            "kind": "directory",
            "digest": DIGEST,
            "target": "bin/resolved-tool",
        },
        '["workspace","src/declared.py",null]': {
            "kind": "file",
            "digest": DIGEST,
            "target": "src/resolved.py",
        },
    }

    journal.touch()
    with memo_writer_lock(tmp_path):
        append_record(journal, {**_started(FETCH), "implementation_files": evidence})
        append_record(journal, _committed(FETCH, implementation_files=evidence))
    shutil.rmtree(workspace)

    def no_live_resolution(*_args, **_kwargs):
        pytest.fail("memo read attempted live closure resolution or hashing")

    monkeypatch.setattr(closure_module, "resolve_command_evidence", no_live_resolution)
    monkeypatch.setattr(closure_module, "_file_digest", no_live_resolution)
    raw = journal.read_bytes()
    reduced = reduce_memo(raw, SITES)
    snapshot = read_memo(journal, SITES)

    assert reduced.active_commits[FETCH].data["value"] == {"ok": True}
    assert snapshot.latest_starts[FETCH].data["implementation_files"] == evidence
    assert snapshot.active_commits[FETCH].data["implementation_files"] == evidence


def test_invalidation_uses_byte_anchor_preserves_prefix_and_allows_future_retry(tmp_path: Path) -> None:
    second = "workflow:demo::run / second"
    journal = tmp_path / "memo.jsonl"
    sites = {**SITES, second: "command"}
    first_start = _started(FETCH)
    first_commit = _committed(FETCH)
    first_commit["value"] = {"label": "café"}
    second_start = _started(second)
    _write(journal, first_start, first_commit)
    with memo_writer_lock(tmp_path):
        append_record(journal, second_start)
        append_record(journal, _committed(second))
    before = journal.read_bytes()
    snapshot = read_memo(journal, sites)
    anchor = snapshot.active_commits[second].offset
    assert anchor == len(_line(first_start)) + len(_line(first_commit)) + len(_line(second_start))

    with memo_writer_lock(tmp_path):
        invalidation = invalidate_suffix(journal, second, sites)

    after = read_memo(journal, sites)
    assert invalidation["from_commit"] == anchor
    assert "identity" not in invalidation
    assert journal.read_bytes().startswith(before)
    assert set(after.active_commits) == {FETCH}

    with memo_writer_lock(tmp_path):
        append_record(journal, _started(second, 2))
        append_record(journal, _committed(second, 2))
    assert set(read_memo(journal, sites).active_commits) == {FETCH, second}


def test_invalidation_rejects_bad_anchor_and_any_coordinator_in_suffix_without_writes(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(
        journal,
        _started(FETCH),
        _committed(FETCH),
        _started(CHILD),
        _committed(CHILD, effect_class="run_ref", proof=_run_ref_proof(CHILD, tmp_path)),
    )
    before = journal.read_bytes()

    with pytest.raises(MemoError, match="invalidate_coordinator_committed"):
        with memo_writer_lock(tmp_path):
            invalidate_suffix(journal, FETCH, SITES)
    assert journal.read_bytes() == before

    with pytest.raises(MemoError, match="invalidate_not_committed"):
        with memo_writer_lock(tmp_path):
            invalidate_suffix(journal, "workflow:demo::run / missing", SITES)
    assert journal.read_bytes() == before


def test_reducer_rejects_non_active_invalidation_anchor(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH), _committed(FETCH), _row("invalidated", from_commit=1, time=3.0))

    with pytest.raises(MemoError) as error:
        read_memo(journal, SITES)

    assert error.value.code == "memo_inconsistent"


def test_invalidation_partial_write_stays_invisible_until_next_writer_preflights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH), _committed(FETCH))
    original = journal.read_bytes()
    real_write = memo_module.os.write

    with memo_writer_lock(tmp_path):
        def short_write(fd: int, data: bytes) -> int:
            return real_write(fd, data[:5])

        monkeypatch.setattr(memo_module.os, "write", short_write)
        with pytest.raises(MemoError, match="memo_write_failed"):
            invalidate_suffix(journal, FETCH, SITES)

    partial = read_memo(journal, SITES)
    assert journal.read_bytes().startswith(original)
    assert partial.tail
    assert FETCH in partial.active_commits
    monkeypatch.setattr(memo_module.os, "write", real_write)
    with memo_writer_lock(tmp_path):
        invalidate_suffix(journal, FETCH, SITES)
    assert journal.read_bytes().startswith(original)
    assert read_memo(journal, SITES).active_commits == {}


def test_invalidation_fsync_failure_leaves_one_complete_visible_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH), _committed(FETCH))
    original = journal.read_bytes()
    real_fsync = memo_module.os.fsync

    with memo_writer_lock(tmp_path):
        def failed_fsync(fd: int) -> None:
            raise OSError("injected fsync failure")

        monkeypatch.setattr(memo_module.os, "fsync", failed_fsync)
        with pytest.raises(MemoError, match="memo_sync_failed"):
            invalidate_suffix(journal, FETCH, SITES)

    after = journal.read_bytes()
    assert after.startswith(original)
    assert len(after) > len(original)
    assert after[len(original) :].endswith(b"\n")
    assert read_memo(journal, SITES).active_commits == {}
    monkeypatch.setattr(memo_module.os, "fsync", real_fsync)


def test_write_error_after_complete_invalidation_keeps_the_complete_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH), _committed(FETCH))
    original = journal.read_bytes()
    real_write = memo_module.os.write

    with memo_writer_lock(tmp_path):
        def write_then_raise(fd: int, data: bytes) -> int:
            real_write(fd, data)
            raise OSError("injected lost acknowledgement")

        monkeypatch.setattr(memo_module.os, "write", write_then_raise)
        with pytest.raises(MemoError, match="memo_write_failed"):
            invalidate_suffix(journal, FETCH, SITES)

    after = journal.read_bytes()
    assert after.startswith(original)
    assert after[len(original) :].endswith(b"\n")
    assert read_memo(journal, SITES).active_commits == {}


def test_reader_does_not_lock_out_writer_and_second_writer_maps_to_memo_busy(tmp_path: Path) -> None:
    journal = tmp_path / "memo.jsonl"
    _write(journal, _started(FETCH))

    with memo_writer_lock(tmp_path):
        assert len(read_memo(journal, SITES).entries) == 1
        with pytest.raises(MemoError) as error:
            with memo_writer_lock(tmp_path):
                pass

    assert error.value.code == "memo_busy"
