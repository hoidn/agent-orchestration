"""The evaluated journal follows its retained directory authority."""

import errno
import os
import stat
from pathlib import Path
from contextlib import contextmanager

import pytest

from orchestrator.run_lock import reserved_run_writer_lock, ReservedRunRootError
from orchestrator.workflow.evaluated.attempts import allocate_attempt
from orchestrator.workflow.evaluated.memo import MemoError, reduce_memo
from orchestrator.workflow.evaluated.memo import read_memo, repair_torn_tail
from orchestrator.workflow.evaluated.memo import append_record, invalidate_suffix
from orchestrator.workflow.evaluated import memo as memo_module
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_evaluated_attempts import FETCH, SITES, _started, _committed
from tests.test_workflow_evaluated_authority import program, _publish


def test_allocation_failure_keeps_memo_under_retained_root(tmp_path, monkeypatch):
    root = tmp_path / "run"
    original = tmp_path / "original"
    root.mkdir()
    (root / "memo.jsonl").touch()
    info = root.stat()
    real_fsync = os.fsync
    synced = []

    def observe_sync(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            synced.append(fd)
        real_fsync(fd)

    def swap_then_fail(owner, path):
        snapshot = reduce_memo(owner.read("memo.jsonl"), SITES)
        assert [row.data for row in snapshot.entries] == [_started(FETCH)]
        assert synced
        root.rename(original)
        root.mkdir()
        (root / "memo.jsonl").touch()
        raise OSError(errno.EIO, "injected allocation failure")

    monkeypatch.setattr(os, "fsync", observe_sync)
    monkeypatch.setattr(WorkspaceFiles, "mkdir_exclusive", swap_then_fail)
    with reserved_run_writer_lock(root, (info.st_dev, info.st_ino)) as fd:
        owner = WorkspaceFiles(root, root_fd=fd, owns_root=False)
        try:
            with pytest.raises(MemoError) as error:
                allocate_attempt(owner, root / "memo.jsonl", _started(FETCH))
            assert error.value.code == "effect_attempt_allocation_failed"
            snapshot = reduce_memo(owner.read("memo.jsonl"), SITES)
            assert [row.data["record"] for row in snapshot.entries] == ["started", "failed"]
            assert snapshot.entries[-1].data["attempt"] == 1
            assert (root / "memo.jsonl").read_bytes() == b""
            assert sorted(path.name for path in root.iterdir()) == ["memo.jsonl"]
        finally:
            owner.close()
        assert os.fstat(fd).st_ino == info.st_ino


def test_repair_compares_the_open_journal_after_root_swap(tmp_path, monkeypatch):
    root = tmp_path / "run"
    original = tmp_path / "original"
    root.mkdir()
    journal = root / "memo.jsonl"
    journal.write_bytes(b'{"record":')
    snapshot = read_memo(journal, {})
    real_open = memo_module._open_append

    def open_then_swap(path, *args):
        fd = real_open(path, *args)
        root.rename(original)
        root.mkdir()
        journal.write_bytes(b"replacement")
        return fd

    monkeypatch.setattr(memo_module, "_open_append", open_then_swap)
    repair_torn_tail(journal, snapshot)
    assert (original / "memo.jsonl").read_bytes() == b""
    assert journal.read_bytes() == b"replacement"


@pytest.mark.parametrize("operation", ["resume", "invalidate"])
def test_public_readers_use_the_root_held_by_the_writer_lock(tmp_path, monkeypatch, operation):
    from tests.test_workflow_evaluated_resume import _completed
    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.cli.commands.invalidate import invalidate_run
    from orchestrator.workflow.evaluated import authority as authority_module
    source, root = _completed(tmp_path)
    monkeypatch.chdir(tmp_path)
    original = root.with_name("original")
    real_read = authority_module._read_header_json
    owners = []

    def swap_then_read(path, run_files=None):
        if not owners:
            owners.append(run_files)
            root.rename(original)
            root.mkdir()
            (root / "run.json").write_bytes(b"replacement")
        return real_read(path, run_files) if run_files is not None else real_read(path)

    monkeypatch.setattr(authority_module, "_read_header_json", swap_then_read)
    if operation == "invalidate":
        monkeypatch.setattr("orchestrator.cli.commands.invalidate._read_header_json", swap_then_read)
        with pytest.raises((ValueError, ReservedRunRootError)):
            invalidate_run(root.name, "absent")
    else:
        assert resume_workflow(root.name) == 2
    assert owners and owners[0] is not None
    assert (root / "run.json").read_bytes() == b"replacement"
    assert sorted(p.name for p in root.iterdir()) == ["run.json"]


def test_normal_publication_retains_the_writer_lock_root(tmp_path, program, monkeypatch):
    from orchestrator.workflow.evaluated import authority as authority_module
    root = tmp_path / "runs/run"
    original = tmp_path / "original"
    real_lock = authority_module.run_writer_lock

    @contextmanager
    def swap_after_lock(path):
        with real_lock(path) as fd:
            root.rename(original)
            root.mkdir()
            yield fd

    monkeypatch.setattr(authority_module, "run_writer_lock", swap_after_lock)
    with pytest.raises((ValueError, ReservedRunRootError)):
        _publish(root, program)
    assert list(root.iterdir()) == []


def test_fd_read_append_repair_and_invalidation_share_original_journal(tmp_path):
    root = tmp_path / "run"
    original = tmp_path / "original"
    root.mkdir()
    journal = root / "memo.jsonl"
    journal.touch()
    owner = WorkspaceFiles(root)
    try:
        root.rename(original)
        root.mkdir()
        journal.write_bytes(b"replacement")
        started = _started(FETCH)
        append_record(journal, started, run_files=owner)
        append_record(journal, _committed(started), run_files=owner)
        snapshot = read_memo(journal, SITES, run_files=owner)
        assert snapshot.active_commits[FETCH].data["value"] == {"ok": True}
        with (original / "memo.jsonl").open("ab") as stream:
            stream.write(b'{"partial":')
        snapshot = read_memo(journal, SITES, run_files=owner)
        repair_torn_tail(journal, snapshot, run_files=owner)
        invalidate_suffix(journal, FETCH, SITES, run_files=owner)
        after = read_memo(journal, SITES, run_files=owner)
        assert [row.data["record"] for row in after.entries] == ["started", "committed", "invalidated"]
        assert not after.active_commits and not after.tail
        assert journal.read_bytes() == b"replacement"
    finally:
        owner.close()


@pytest.mark.parametrize("fault", ["short-write", "fsync", "changed", "invalid-line", "symlink"])
def test_fd_journal_keeps_existing_failure_contracts(tmp_path, monkeypatch, fault):
    root = tmp_path / "run"
    root.mkdir()
    journal = root / "memo.jsonl"
    journal.touch()
    owner = WorkspaceFiles(root)
    try:
        if fault == "symlink":
            journal.unlink()
            outside = tmp_path / "outside"
            outside.write_bytes(b"outside")
            journal.symlink_to(outside)
            with pytest.raises(MemoError, match="memo_inconsistent"):
                append_record(journal, _started(FETCH), run_files=owner)
            assert outside.read_bytes() == b"outside"
        elif fault == "invalid-line":
            journal.write_bytes(b'{}\n')
            with pytest.raises(MemoError, match="memo_inconsistent"):
                read_memo(journal, SITES, run_files=owner)
            assert journal.read_bytes() == b'{}\n'
        elif fault == "changed":
            journal.write_bytes(b'{"partial":')
            snapshot = read_memo(journal, SITES, run_files=owner)
            journal.write_bytes(b'{"changed":')
            with pytest.raises(MemoError, match="memo_changed"):
                repair_torn_tail(journal, snapshot, run_files=owner)
            assert journal.read_bytes() == b'{"changed":'
        else:
            real_write = os.write
            if fault == "short-write":
                monkeypatch.setattr(os, "write", lambda fd, content: real_write(fd, content[:5]))
            else:
                def fail_sync(fd):
                    raise OSError("injected fsync")
                monkeypatch.setattr(os, "fsync", fail_sync)
            code = "memo_write_failed" if fault == "short-write" else "memo_sync_failed"
            with pytest.raises(MemoError, match=code):
                append_record(journal, _started(FETCH), run_files=owner)
            snapshot = read_memo(journal, SITES, run_files=owner)
            assert bool(snapshot.tail) == (fault == "short-write")
            assert (FETCH in snapshot.latest_starts) == (fault == "fsync")
    finally:
        owner.close()


def _assert_failed_publication_stops_without_terminal(snapshot, caplog):
    assert [row.data["record"] for row in snapshot.entries] == ["started", "failed"]
    assert snapshot.entries[1].data["attempt"] == 1
    assert snapshot.terminal is None
    assert "view_write_failed" in caplog.text
    assert "reserved_run_root_changed" in caplog.text


def test_failed_publication_stops_on_borrowed_root(tmp_path, monkeypatch, caplog):
    from tests.test_workflow_evaluated_command_lifecycle import _program, _publish, _script
    from orchestrator.workflow.evaluated import runtime
    from orchestrator.workflow.evaluated.machine import site_classes
    _script(tmp_path)
    _, checked = _program(tmp_path,
        '(command-result emit :argv ("python" "probe.py") :returns Int)',
        bindings={"emit": "probe.py"})
    real_perform = runtime.perform_command
    attempt_owners = []
    with _publish(tmp_path, checked) as authority:
        root = authority.run_root
        original = root.with_name("original")
        fd = authority.run_files.root_fd

        def perform_then_swap(*args, **kwargs):
            result = real_perform(*args, **kwargs)
            attempt_owners.append(kwargs["attempt_files"])
            root.rename(original)
            root.mkdir()
            (root / "memo.jsonl").touch()
            return result

        monkeypatch.setattr(runtime, "perform_command", perform_then_swap)
        assert runtime.execute_pure_run(authority, {}, run_id=root.name, workspace=tmp_path) == (1, None)
        snapshot = read_memo(authority.memo_path, site_classes(checked), run_files=authority.run_files)
        _assert_failed_publication_stops_without_terminal(snapshot, caplog)
        assert (root / "memo.jsonl").read_bytes() == b""
        assert sorted(path.name for path in root.iterdir()) == ["memo.jsonl"]
        assert os.fstat(fd).st_ino == original.stat().st_ino
        assert not authority.run_files.closed
        assert attempt_owners[0].closed
