from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
from pathlib import Path

import pytest

import orchestrator.workflow.evaluated.memo as memo_module
import orchestrator.workflow.workspace_files as workspace_files_module
from orchestrator.workflow.evaluated.memo import (
    MemoError,
    append_record,
    invalidate_suffix,
    memo_writer_lock,
    read_memo,
)
from orchestrator.workflow.workspace_files import WorkspaceFiles


FETCH = "workflow:demo::run / fetch"
OTHER = "workflow:demo::run / other"
SITES = {FETCH: "command", OTHER: "command"}
DIGEST = "sha256:" + "0" * 64


def _attempts_module():
    return importlib.import_module("orchestrator.workflow.evaluated.attempts")


def _started(identity: str, attempt: int = 1) -> dict[str, object]:
    input_digest = "sha256:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    identity_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {
        "record": "started",
        "identity": identity,
        "attempt": attempt,
        "input_digest": input_digest,
        "input_parts": {"arguments": input_digest},
        "implementation_files": {},
        "result_path": (
            f"effects/{identity_digest}/attempt-{attempt}/result.json"
        ),
        "time": 1.0,
    }


def _failed(identity: str, attempt: int = 1) -> dict[str, object]:
    return {
        "record": "failed",
        "identity": identity,
        "attempt": attempt,
        "code": "command_failed",
        "exit_info": {},
    }


def _committed(started: dict[str, object]) -> dict[str, object]:
    return {
        "record": "committed",
        "identity": started["identity"],
        "attempt": started["attempt"],
        "input_digest": started["input_digest"],
        "input_parts": started["input_parts"],
        "implementation_files": started["implementation_files"],
        "value": {"ok": True},
        "result_path": started["result_path"],
        "result_digest": DIGEST,
        "depends_on": [],
        "effect_class": "command",
        "time": 2.0,
    }


def _append(journal: Path, *rows: dict[str, object]) -> None:
    journal.touch(exist_ok=True)
    with memo_writer_lock(journal.parent):
        for row in rows:
            append_record(journal, row)


def test_mkdir_exclusive_syncs_new_parent_entries_and_returns_pinned_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = WorkspaceFiles(tmp_path)
    real_fsync = os.fsync
    synchronized: list[bool] = []

    def record_fsync(fd: int) -> None:
        synchronized.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real_fsync(fd)

    monkeypatch.setattr(workspace_files_module.os, "fsync", record_fsync)
    try:
        attempt_owner = owner.mkdir_exclusive("effects/digest/attempt-1")
        assert synchronized == [True, True, True]
        assert stat.S_ISDIR(os.fstat(attempt_owner.root_fd).st_mode)
        attempt_owner.create("marker", b"pinned", exclusive=True)
        assert (tmp_path / "effects/digest/attempt-1/marker").read_bytes() == b"pinned"
        attempt_owner.close()
    finally:
        owner.close()


def test_mkdir_exclusive_collision_preserves_existing_leaf(tmp_path: Path) -> None:
    existing = tmp_path / "effects/digest/attempt-1"
    existing.mkdir(parents=True)
    sentinel = existing / "sentinel"
    sentinel.write_bytes(b"keep")
    owner = WorkspaceFiles(tmp_path)
    try:
        with pytest.raises(FileExistsError):
            owner.mkdir_exclusive("effects/digest/attempt-1")
    finally:
        owner.close()
    assert sentinel.read_bytes() == b"keep"


def test_mkdir_exclusive_rejects_symlinked_parent(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "effects").symlink_to(outside, target_is_directory=True)
    owner = WorkspaceFiles(tmp_path)
    try:
        with pytest.raises(OSError):
            owner.mkdir_exclusive("effects/digest/attempt-1")
    finally:
        owner.close()
    assert not (outside / "digest").exists()


def test_mkdir_exclusive_stays_beneath_the_opened_root_after_path_swap(
    tmp_path: Path,
) -> None:
    root = tmp_path / "run"
    moved = tmp_path / "run-opened"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    owner = WorkspaceFiles(root)
    try:
        root.rename(moved)
        root.symlink_to(outside, target_is_directory=True)
        attempt_owner = owner.mkdir_exclusive("effects/digest/attempt-1")
        attempt_owner.close()
    finally:
        owner.close()
        if root.is_symlink():
            root.unlink()
    assert (moved / "effects/digest/attempt-1").is_dir()
    assert not (outside / "effects").exists()


def test_attempt_paths_advances_after_failed_and_invalidated_starts(
    tmp_path: Path,
) -> None:
    attempts = _attempts_module()
    failed_journal = tmp_path / "failed.jsonl"
    first = _started(FETCH)
    _append(failed_journal, first, _failed(FETCH))
    failed_snapshot = read_memo(failed_journal, SITES)

    invalidated_journal = tmp_path / "invalidated.jsonl"
    committed_start = _started(FETCH)
    _append(invalidated_journal, committed_start, _committed(committed_start))
    with memo_writer_lock(tmp_path):
        invalidate_suffix(invalidated_journal, FETCH, SITES)
    invalidated_snapshot = read_memo(invalidated_journal, SITES)

    expected_digest = hashlib.sha256(FETCH.encode("utf-8")).hexdigest()
    assert attempts.attempt_paths(failed_snapshot, FETCH) == (
        2,
        f"effects/{expected_digest}/attempt-2",
        f"effects/{expected_digest}/attempt-2/result.json",
    )
    assert attempts.attempt_paths(invalidated_snapshot, FETCH)[0] == 2
    assert attempts.attempt_paths(failed_snapshot, OTHER)[0] == 1


def test_allocate_attempt_syncs_started_before_entering_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _attempts_module()
    journal = tmp_path / "memo.jsonl"
    journal.touch()
    started = _started(FETCH)
    run_files = WorkspaceFiles(tmp_path)
    real_fsync = os.fsync
    real_mkdir = WorkspaceFiles.mkdir_exclusive
    events: list[str] = []

    def record_fsync(fd: int) -> None:
        events.append("memo_fsync" if stat.S_ISREG(os.fstat(fd).st_mode) else "dir_fsync")
        real_fsync(fd)

    def observe_mkdir(owner: WorkspaceFiles, path: str | Path) -> WorkspaceFiles:
        events.append("mkdir")
        snapshot = read_memo(journal, SITES)
        assert snapshot.latest_starts[FETCH].data == started
        assert events[:2] == ["memo_fsync", "mkdir"]
        return real_mkdir(owner, path)

    monkeypatch.setattr(memo_module.os, "fsync", record_fsync)
    monkeypatch.setattr(WorkspaceFiles, "mkdir_exclusive", observe_mkdir)
    try:
        with memo_writer_lock(tmp_path):
            attempt_owner = attempts.allocate_attempt(run_files, journal, started)
        assert attempt_owner.workspace == tmp_path / Path(started["result_path"]).parent
        assert events[:2] == ["memo_fsync", "mkdir"]
        attempt_owner.close()
    finally:
        run_files.close()


def test_started_sync_failure_stops_before_directory_creation_and_consumes_ordinal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _attempts_module()
    journal = tmp_path / "memo.jsonl"
    journal.touch()
    started = _started(FETCH)
    run_files = WorkspaceFiles(tmp_path)

    def fail_fsync(_fd: int) -> None:
        raise OSError("injected journal fsync failure")

    try:
        with memo_writer_lock(tmp_path):
            with monkeypatch.context() as patched:
                patched.setattr(memo_module.os, "fsync", fail_fsync)
                with pytest.raises(MemoError, match="memo_sync_failed"):
                    attempts.allocate_attempt(run_files, journal, started)
        snapshot = read_memo(journal, SITES)
        assert snapshot.latest_starts[FETCH].data["attempt"] == 1
        assert attempts.attempt_paths(snapshot, FETCH)[0] == 2
        assert not (tmp_path / Path(started["result_path"]).parent).exists()
    finally:
        run_files.close()


def test_attempt_collision_preserves_files_and_appends_failed(tmp_path: Path) -> None:
    attempts = _attempts_module()
    journal = tmp_path / "memo.jsonl"
    journal.touch()
    started = _started(FETCH)
    existing = tmp_path / Path(started["result_path"]).parent
    existing.mkdir(parents=True)
    sentinel = existing / "sentinel"
    sentinel.write_bytes(b"keep")
    run_files = WorkspaceFiles(tmp_path)

    try:
        with memo_writer_lock(tmp_path):
            with pytest.raises(MemoError) as error:
                attempts.allocate_attempt(run_files, journal, started)
        assert error.value.code == "effect_attempt_path_exists"
        snapshot = read_memo(journal, SITES)
        assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed"]
        assert snapshot.entries[-1].data["code"] == "effect_attempt_path_exists"
        assert snapshot.entries[-1].data["attempt"] == 1
        assert sentinel.read_bytes() == b"keep"
    finally:
        run_files.close()


def test_allocation_sync_failure_preserves_created_directory_and_appends_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _attempts_module()
    journal = tmp_path / "memo.jsonl"
    journal.touch()
    started = _started(FETCH)
    run_files = WorkspaceFiles(tmp_path)
    real_fsync = os.fsync
    directory_syncs = 0

    def fail_final_directory_sync(fd: int) -> None:
        nonlocal directory_syncs
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_syncs += 1
            if directory_syncs == 3:
                raise OSError("injected attempt parent fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(workspace_files_module.os, "fsync", fail_final_directory_sync)
    try:
        with memo_writer_lock(tmp_path):
            with pytest.raises(MemoError) as error:
                attempts.allocate_attempt(run_files, journal, started)
        assert error.value.code == "effect_attempt_allocation_failed"
        attempt_dir = tmp_path / Path(started["result_path"]).parent
        assert attempt_dir.is_dir()
        assert list(attempt_dir.iterdir()) == []
        snapshot = read_memo(journal, SITES)
        assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed"]
        assert snapshot.entries[-1].data["code"] == "effect_attempt_allocation_failed"
    finally:
        run_files.close()


def test_failed_record_sync_error_propagates_after_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _attempts_module()
    journal = tmp_path / "memo.jsonl"
    journal.touch()
    started = _started(FETCH)
    existing = tmp_path / Path(started["result_path"]).parent
    existing.mkdir(parents=True)
    sentinel = existing / "sentinel"
    sentinel.write_bytes(b"keep")
    run_files = WorkspaceFiles(tmp_path)
    real_fsync = os.fsync
    journal_syncs = 0

    def fail_failed_record_sync(fd: int) -> None:
        nonlocal journal_syncs
        if stat.S_ISREG(os.fstat(fd).st_mode):
            journal_syncs += 1
            if journal_syncs == 2:
                raise OSError("injected failed-row fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(memo_module.os, "fsync", fail_failed_record_sync)
    try:
        with memo_writer_lock(tmp_path):
            with pytest.raises(MemoError, match="memo_sync_failed"):
                attempts.allocate_attempt(run_files, journal, started)
        assert journal_syncs == 2
        assert sentinel.read_bytes() == b"keep"
        snapshot = read_memo(journal, SITES)
        assert [entry.data["record"] for entry in snapshot.entries] == ["started", "failed"]
    finally:
        run_files.close()


def test_retry_resyncs_existing_parent_after_earlier_parent_sync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    attempts = _attempts_module()
    journal = tmp_path / "memo.jsonl"
    journal.touch()
    run_files = WorkspaceFiles(tmp_path)
    real_fsync = os.fsync
    directory_inodes: list[int] = []

    def fail_first_directory_sync(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            directory_inodes.append(os.fstat(fd).st_ino)
            if len(directory_inodes) == 1:
                raise OSError("injected first parent fsync failure")
        real_fsync(fd)

    monkeypatch.setattr(workspace_files_module.os, "fsync", fail_first_directory_sync)
    try:
        with memo_writer_lock(tmp_path):
            with pytest.raises(MemoError) as error:
                attempts.allocate_attempt(run_files, journal, _started(FETCH))
        assert error.value.code == "effect_attempt_allocation_failed"
        assert (tmp_path / "effects").is_dir()

        second_start = _started(FETCH, 2)
        snapshot = read_memo(journal, SITES)
        assert attempts.attempt_paths(snapshot, FETCH)[0] == 2
        root_inode = os.fstat(run_files.root_fd).st_ino
        before_retry = len(directory_inodes)
        with memo_writer_lock(tmp_path):
            attempt_owner = attempts.allocate_attempt(run_files, journal, second_start)
        assert attempt_owner.workspace == tmp_path / Path(second_start["result_path"]).parent
        attempt_owner.close()

        effects_inode = (tmp_path / "effects").stat().st_ino
        digest_inode = (tmp_path / "effects" / hashlib.sha256(FETCH.encode("utf-8")).hexdigest()).stat().st_ino
        assert directory_inodes[before_retry:] == [
            root_inode,
            effects_inode,
            digest_inode,
        ]
    finally:
        run_files.close()
