"""Run-reference ledger IO follows the retained parent directory."""

from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

import orchestrator.workflow.run_ref.ledger as ledger_module
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_run_ref_ledger import _allocated_bindings, _visit
from tests.test_workflow_run_ref_runtime import _RuntimeHarness, _runtime_request
from orchestrator.workflow.run_ref.runtime import (
    finalize_run_ref_parent_commit,
    acknowledge_persisted_run_ref_lifecycle_event,
    prepare_run_ref_settlement,
    recover_run_ref_settlement,
    select_run_ref_lifecycle_allocation,
    validate_completed_run_ref_authority,
    RunRefLifecycleEvent,
    RunRefRuntimeError,
)


def test_ledger_fd_lifecycle_never_reopens_logical_root(tmp_path, monkeypatch):
    root = tmp_path / "parent"
    retained = tmp_path / "retained-parent"
    root.mkdir()
    ledger_path = root / "run-ref-attempts.jsonl"
    substitute_bytes = b"substitute must remain unchanged\n"
    real_write = WorkspaceFiles.write_atomic
    owner = WorkspaceFiles(root)

    def swap_then_write(files, path, payload, **kwargs):
        assert files is owner
        assert Path(path) == ledger_path
        root.rename(retained)
        root.mkdir()
        ledger_path.write_bytes(substitute_bytes)
        real_write(files, path, payload, **kwargs)

    monkeypatch.setattr(WorkspaceFiles, "write_atomic", swap_then_write)
    try:
        allocated = ledger_module.allocate_attempt(
            ledger_path,
            visit=_visit(),
            bindings=_allocated_bindings(tmp_path),
            recorded_at="2026-08-01T12:00:00.000000Z",
            run_files=owner,
        )
        expected = canonical_json_bytes(allocated.record) + b"\n"
        assert (retained / ledger_path.name).is_file()
        assert owner.read(ledger_path) == expected
        assert ledger_path.read_bytes() == substitute_bytes
        assert sorted(path.name for path in root.iterdir()) == [ledger_path.name]
    finally:
        owner.close()


def _forbid_logical_ledger_io(monkeypatch, ledger_path):
    real_read = Path.read_bytes
    real_lstat = Path.lstat
    real_lexists = os.path.lexists
    real_write = ledger_module.durable_atomic_write

    def forbid_logical_read(path):
        assert path != ledger_path, "ledger read reopened logical root"
        return real_read(path)

    def forbid_logical_write(path, payload):
        assert Path(path) != ledger_path, "ledger write reopened logical root"
        return real_write(path, payload)

    def forbid_logical_lstat(path):
        assert path != ledger_path, "ledger stat reopened logical root"
        return real_lstat(path)

    def forbid_logical_exists(path):
        assert Path(path) != ledger_path, "ledger existence checked logical root"
        return real_lexists(path)

    monkeypatch.setattr(Path, "read_bytes", forbid_logical_read)
    monkeypatch.setattr(Path, "lstat", forbid_logical_lstat)
    monkeypatch.setattr(os.path, "lexists", forbid_logical_exists)
    monkeypatch.setattr(ledger_module, "durable_atomic_write", forbid_logical_write)
    return real_read


def test_runtime_fd_persist_ack_finalize_recovery_and_reuse(tmp_path, monkeypatch):
    request = _runtime_request(tmp_path, mode="path")
    owner = WorkspaceFiles(request.parent_run_root)
    request = replace(request, run_files=owner)
    real_read = _forbid_logical_ledger_io(monkeypatch, request.ledger_path)
    harness = _RuntimeHarness()
    try:
        prepared = prepare_run_ref_settlement(request, dependencies=harness.dependencies())
        assert ledger_module.validate_pending_parent_commit(
            request.ledger_path, visit=request.visit, attempt_ordinal=1,
            current_step_config_digest=request.step_config.step_config_digest,
            settled_result=prepared.settled_result, run_files=owner,
        )
        root = request.parent_run_root
        root.rename(root.with_name("retained-parent"))
        root.mkdir()
        substitute = b"substitute must remain unchanged\n"
        request.ledger_path.write_bytes(substitute)
        finalized = finalize_run_ref_parent_commit(
            request, prepared, persisted_settled_result=prepared.settled_result.record,
        )
        recovered = recover_run_ref_settlement(
            request, settled_result=prepared.settled_result.record, reconcile_pending=True,
        )
        reused = validate_completed_run_ref_authority(
            request, settled_result=prepared.settled_result.record,
            artifacts=prepared.artifacts, reconcile_pending=False,
        )
        rows = ledger_module.load_attempt_ledger(request.ledger_path, run_files=owner).rows
        assert len(rows) == 9
        assert rows[-1].stage == "committed"
        assert finalized.committed_row_digest == recovered.committed_row_digest == reused.committed_row_digest
        assert recovered.envelope == reused.envelope == prepared.envelope
        assert len(harness.launches) == 1
        assert real_read(request.ledger_path) == substitute
        assert sorted(path.name for path in root.iterdir()) == [request.ledger_path.name]
    finally:
        owner.close()


def test_legacy_and_fd_ledger_share_identical_bytes_and_rows(tmp_path):
    root = tmp_path / "parent"
    root.mkdir()
    owner = WorkspaceFiles(root)
    try:
        kwargs = dict(visit=_visit(), bindings=_allocated_bindings(tmp_path),
                      recorded_at="2026-08-01T12:00:00.000000Z")
        legacy = ledger_module.allocate_attempt(root / "legacy.jsonl", **kwargs)
        pinned = ledger_module.allocate_attempt(root / "pinned.jsonl", run_files=owner, **kwargs)
        assert legacy == pinned
        assert (root / "legacy.jsonl").read_bytes() == owner.read(root / "pinned.jsonl")
        assert ledger_module.load_attempt_ledger(root / "legacy.jsonl") == ledger_module.load_attempt_ledger(root / "pinned.jsonl", run_files=owner)
        assert ledger_module.load_attempt_ledger(root / "missing.jsonl").rows == ()
        assert ledger_module.load_attempt_ledger(root / "missing.jsonl", run_files=owner).rows == ()
    finally:
        owner.close()


@pytest.mark.parametrize("payload", [b"", b"{}", b"\n", b"{}\n", b'{"a":1,"a":1}\n', b"NaN\n", b"\xff\n"])
def test_fd_and_legacy_reject_the_same_corrupt_bytes(tmp_path, payload):
    owner = WorkspaceFiles(tmp_path)
    path = tmp_path / "ledger.jsonl"
    try:
        path.write_bytes(payload)
        with pytest.raises(ledger_module.RunRefLedgerError) as legacy:
            ledger_module.load_attempt_ledger(path)
        with pytest.raises(ledger_module.RunRefLedgerError) as pinned:
            ledger_module.load_attempt_ledger(path, run_files=owner)
        assert str(pinned.value) == str(legacy.value)
        assert path.read_bytes() == payload
    finally:
        owner.close()


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_fd_loader_rejects_non_regular_ledger_without_following_or_blocking(tmp_path, kind):
    path = tmp_path / "ledger.jsonl"
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        target = tmp_path / "target.jsonl"
        target.write_bytes(b"preserved\n")
        path.symlink_to(target)
    else:
        os.mkfifo(path)
    owner = WorkspaceFiles(tmp_path)
    try:
        with pytest.raises(ledger_module.RunRefLedgerError):
            ledger_module.load_attempt_ledger(path, run_files=owner)
        assert path.lstat().st_mode
        if kind == "symlink":
            assert target.read_bytes() == b"preserved\n"
    finally:
        owner.close()


def test_fd_absence_is_independent_of_substitute_ledger(tmp_path):
    root = tmp_path / "parent"
    root.mkdir()
    owner = WorkspaceFiles(root)
    try:
        root.rename(tmp_path / "retained-parent")
        root.mkdir()
        path = root / "ledger.jsonl"
        path.write_bytes(b"substitute\n")
        assert ledger_module.load_attempt_ledger(path, run_files=owner).rows == ()
        assert path.read_bytes() == b"substitute\n"
    finally:
        owner.close()


def test_fd_discard_reloads_and_appends_to_retained_parent(tmp_path):
    root = tmp_path / "parent"
    root.mkdir()
    path = root / "ledger.jsonl"
    owner = WorkspaceFiles(root)
    try:
        allocated = ledger_module.allocate_attempt(path, visit=_visit(),
                                                  bindings=_allocated_bindings(tmp_path), run_files=owner)
        root.rename(tmp_path / "retained-parent")
        root.mkdir()
        path.write_bytes(b"substitute\n")
        assert ledger_module.identify_incomplete_attempt(
            path, visit=_visit(), current_step_config_digest=allocated.bindings.step_config_digest,
            run_files=owner,
        ) == allocated
        discarded = ledger_module.record_discarded_attempt(
            path, visit=_visit(), attempt_ordinal=1, workspace_path=allocated.bindings.workspace_path,
            disposition_digest="sha256:" + "a" * 64, run_files=owner,
        )
        assert discarded.status == "discarded"
        assert discarded.previous_row_digest == allocated.row_digest
        assert ledger_module.load_attempt_ledger(path, run_files=owner).rows == (allocated, discarded)
        assert path.read_bytes() == b"substitute\n"
        assert sorted(child.name for child in root.iterdir()) == [path.name]
    finally:
        owner.close()


def test_runtime_fd_discard_retry_preserves_history_without_logical_io(tmp_path, monkeypatch):
    request = _runtime_request(tmp_path, mode="path")
    owner = WorkspaceFiles(request.parent_run_root)
    request = replace(request, run_files=owner)
    harness = _RuntimeHarness()
    _forbid_logical_ledger_io(monkeypatch, request.ledger_path)

    def crash(boundary):
        if boundary == "child_completion":
            raise RuntimeError("injected crash")

    try:
        with pytest.raises(RuntimeError, match="injected crash"):
            prepare_run_ref_settlement(request, dependencies=replace(harness.dependencies(), crash_hook=crash))
        incomplete = ledger_module.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        recovered = prepare_run_ref_settlement(request, dependencies=harness.dependencies())
        rows = ledger_module.load_attempt_ledger(request.ledger_path, run_files=owner).rows
        discarded = [row for row in rows if row.status == "discarded"]
        assert len(discarded) == 1
        assert discarded[0].attempt_ordinal == 1
        assert discarded[0].stage == incomplete.stage == "child_completed"
        assert not incomplete.bindings.workspace_path.exists()
        disposition = incomplete.bindings.workspace_path.parent / "disposition.json"
        assert discarded[0].bindings.disposition_digest == canonical_sha256(json.loads(disposition.read_bytes()))
        assert recovered.settled_result.attempt_ordinal == 2
        assert rows[-1].stage == "completed_pending_parent_commit"
        assert len(harness.launches) == 2
    finally:
        owner.close()


@pytest.mark.parametrize("corruption", ["digest", "sequence", "truncated", "noncanonical", "unknown-key"])
def test_fd_parser_preserves_wire_digest_and_closed_schema_checks(tmp_path, corruption):
    path = tmp_path / "ledger.jsonl"
    row = ledger_module.allocate_attempt(path, visit=_visit(), bindings=_allocated_bindings(tmp_path))
    record = dict(row.record)
    if corruption == "digest":
        record["row_digest"] = "sha256:" + "0" * 64
    elif corruption == "sequence":
        record["sequence"] = 2
    elif corruption == "unknown-key":
        record["root_fd"] = 123
    payload = canonical_json_bytes(record) + b"\n"
    if corruption == "truncated":
        payload = payload[:-1]
    elif corruption == "noncanonical":
        payload = b" " + payload
    path.write_bytes(payload)
    owner = WorkspaceFiles(tmp_path)
    try:
        with pytest.raises(ledger_module.RunRefLedgerError) as legacy:
            ledger_module.load_attempt_ledger(path)
        with pytest.raises(ledger_module.RunRefLedgerError) as pinned:
            ledger_module.load_attempt_ledger(path, run_files=owner)
        assert str(legacy.value) == str(pinned.value)
        assert path.read_bytes() == payload
    finally:
        owner.close()


@pytest.mark.parametrize("pairing", ["wrong-workspace", "wrong-fd"])
def test_runtime_request_rejects_mismatched_parent_file_authority(tmp_path, pairing):
    request = _runtime_request(tmp_path, mode="path")
    other = tmp_path / "other-parent"
    other.mkdir()
    owner = WorkspaceFiles(other)
    borrowed = WorkspaceFiles(request.parent_run_root, root_fd=owner.root_fd)
    try:
        candidate = owner if pairing == "wrong-workspace" else borrowed
        with pytest.raises(RunRefRuntimeError, match="parent_run_files_authority_disagrees"):
            replace(request, run_files=candidate)
        assert list(other.iterdir()) == []
        assert list(request.parent_run_root.iterdir()) == []
    finally:
        borrowed.close()
        owner.close()


def test_runtime_request_rejects_swapped_parent_before_admitting_fd(tmp_path):
    request = _runtime_request(tmp_path, mode="path")
    owner = WorkspaceFiles(request.parent_run_root)
    try:
        root = request.parent_run_root
        root.rename(root.with_name("retained-parent"))
        root.mkdir()
        with pytest.raises(RunRefRuntimeError, match="parent_run_files_authority_disagrees"):
            replace(request, run_files=owner)
        assert list(root.iterdir()) == []
    finally:
        owner.close()


def test_runtime_request_rejects_invalid_or_closed_file_owner(tmp_path):
    request = _runtime_request(tmp_path, mode="path")
    with pytest.raises(TypeError, match="WorkspaceFiles"):
        replace(request, run_files=object())
    owner = WorkspaceFiles(request.parent_run_root)
    owner.close()
    with pytest.raises(OSError, match="closed"):
        replace(request, run_files=owner)
    assert list(request.parent_run_root.iterdir()) == []


@pytest.mark.parametrize("field", ["source_digest", "program_digest", "child_run_id", "workspace_path", "run_ref_root"])
def test_fd_acknowledgement_requires_full_exact_row_and_current_head(tmp_path, field):
    request = _runtime_request(tmp_path, mode="path")
    owner = WorkspaceFiles(request.parent_run_root)
    request = replace(request, run_files=owner)
    try:
        allocation = select_run_ref_lifecycle_allocation(request)
        row = ledger_module.allocate_attempt(request.ledger_path, visit=request.visit,
                                             bindings=allocation.bindings, run_files=owner)
        event_args = dict(sequence=1, event_kind="allocation", stage="allocated",
                          visit=request.visit, attempt_ordinal=1,
                          effect_instance_root=allocation.effect_instance_root)
        changed = {"source_digest": "sha256:" + "0" * 64,
                   "program_digest": "sha256:" + "0" * 64,
                   "child_run_id": "another-child",
                   "workspace_path": allocation.bindings.workspace_path.with_name("another-workspace"),
                   "run_ref_root": request.run_ref_root.parent}
        bindings = replace(allocation.bindings, **{field: changed[field]})
        wrong = RunRefLifecycleEvent.build(**event_args, payload={"bindings": bindings.record})
        with pytest.raises(ValueError, match="allocation acknowledgement disagrees"):
            acknowledge_persisted_run_ref_lifecycle_event(wrong, expected_row_digest=row.row_digest,
                                                         run_files=owner)
        event = RunRefLifecycleEvent.build(**event_args, payload={"bindings": allocation.bindings.record})
        acknowledgement = acknowledge_persisted_run_ref_lifecycle_event(event, expected_row_digest=row.row_digest,
                                                                       run_files=owner)
        assert acknowledgement.authority == row
        ledger_module.advance_attempt(request.ledger_path, visit=request.visit, attempt_ordinal=1,
                                      stage="materialized", binding_updates={"verified_git_tree_id": "git-tree:" + "a" * 40},
                                      run_files=owner)
        with pytest.raises(ValueError, match="head"):
            acknowledge_persisted_run_ref_lifecycle_event(event, expected_row_digest=row.row_digest,
                                                         run_files=owner)
    finally:
        owner.close()


def test_runtime_allocation_reads_retained_history_after_parent_swap(tmp_path):
    request = _runtime_request(tmp_path, mode="path")
    first = select_run_ref_lifecycle_allocation(request)
    allocated = ledger_module.allocate_attempt(
        request.ledger_path, visit=request.visit, bindings=first.bindings,
    )
    ledger_module.record_discarded_attempt(
        request.ledger_path, visit=request.visit, attempt_ordinal=1,
        workspace_path=allocated.bindings.workspace_path,
        disposition_digest="sha256:" + "a" * 64,
    )
    owner = WorkspaceFiles(request.parent_run_root)
    try:
        request = replace(request, run_files=owner)
        original_bytes = owner.read(request.ledger_path)
        previous = ledger_module.load_attempt_ledger(request.ledger_path, run_files=owner).rows[-1]
        retained = request.parent_run_root.with_name("retained-parent")
        request.parent_run_root.rename(retained)
        request.parent_run_root.mkdir()

        selected = select_run_ref_lifecycle_allocation(request)

        assert selected.attempt_ordinal == 2
        assert selected.expected_ledger_sequence == 3
        assert selected.expected_previous_row_digest == previous.row_digest
        assert owner.read(request.ledger_path) == original_bytes
        assert list(request.parent_run_root.iterdir()) == []
    finally:
        owner.close()
