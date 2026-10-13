"""Parallel E1 publication failures drain concurrent work without rewriting authority."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
import re
import threading

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.evaluated import effect_execution, run_ref as adapter, runtime, views
from orchestrator.workflow.evaluated.memo import read_memo
from orchestrator.workflow.evaluated.machine import site_classes, site_nodes
from orchestrator.workflow.evaluated.parallel import ParallelCoordinator
from orchestrator.workflow.evaluated.views import ViewPublicationError
from orchestrator.workflow.run_ref import runtime as e1
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from tests.test_workflow_evaluated_command_template_scopes import _write_boundaries, _write_probe
from tests.test_workflow_evaluated_parallel_run_ref import _parallel_e1_fixture
from tests.test_workflow_evaluated_run_ref import _authority, _public_fixture
from tests.test_workflow_evaluated_run_ref_settlement import _service_run


def _wait(event):
    assert event.wait(30), "parallel E1 fault fixture did not reach its barrier"


def _mixed_command_fixture(root):
    command = '(command-result emit :argv ("python" "probe.py") :returns Int)'

    def definitions(call):
        return f'''(defworkflow invoke ((repo String)) -> Bool
          (if (= repo "c") (let* ((value {command})) (= value 0))
            (let* ((child {call})) child.value)))'''

    body = '''(let* ((items (list/map-effect ((repo (list "a" "b" "c")))
      :max 3 :parallel 3 :workspace repo (call invoke :repo repo))))
      (= (list/length items) 3))'''
    parent, source, refs = _public_fixture(
        root,
        parent_target="2.37",
        child_target="2.35",
        definitions=definitions,
        body=lambda _call: body,
    )
    for item in "abc":
        (parent / item).mkdir()
    _write_probe(parent)
    _write_probe(parent / "c")
    return parent, source, refs, _write_boundaries(parent)


def _fd_is_open(descriptor):
    try:
        os.fstat(descriptor)
    except OSError:
        return False
    return True


def _capture_fault_bytes(state, run_root, ledger_path):
    state["bytes_at_fault"] = (
        (run_root / "memo.jsonl").read_bytes(),
        ledger_path.read_bytes(),
    )
    state["fault_reached"].set()


def _install_failed_memo_sync_fault(monkeypatch, state):
    real_fsync = os.fsync

    def fail_failed_row_sync(descriptor):
        try:
            target = os.readlink(f"/proc/self/fd/{descriptor}")
        except OSError:
            return real_fsync(descriptor)
        if Path(target).name != "memo.jsonl" or state["failed_sync_injected"]:
            return real_fsync(descriptor)
        flags = fcntl.fcntl(descriptor, fcntl.F_GETFL)
        if flags & os.O_ACCMODE != os.O_RDWR:
            return real_fsync(descriptor)
        size = os.fstat(descriptor).st_size
        if not size:
            return real_fsync(descriptor)
        raw = os.pread(descriptor, size, 0)
        lines = raw.splitlines()
        last_row = json.loads(lines[-1]) if lines else {}
        if last_row.get("record") == "failed":
            state["failed_sync_injected"] = True
            state["failed_row_bytes"] = raw
            state["failed_row_at_fault"] = last_row
            request = state["requests"][0]
            _capture_fault_bytes(state, request.parent_run_root, request.ledger_path)
            raise OSError("injected failed-row fsync failure")
        return real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", fail_failed_row_sync)


def _install_fault_scenario(monkeypatch, parent, source, refs, boundaries, phase):
    state = {
        "command_started": threading.Event(),
        "release_command": threading.Event(),
        "allocated": threading.Event(),
        "deferred": threading.Event(),
        "fault_reached": threading.Event(),
        "requests": [],
        "child_launches": [],
        "deferred_ids": [],
        "granted_ids": [],
        "command_attempts": [],
        "failed_sync_injected": False,
    }

    real_launch = effect_execution.launch_command

    def hold_command(node, argv, *, attempt_files, **kwargs):
        state["command_started"].set()
        _wait(state["release_command"])
        return real_launch(node, argv, attempt_files=attempt_files, **kwargs)

    monkeypatch.setattr(effect_execution, "launch_command", hold_command)
    real_service = ParallelCoordinator._service

    def observe_service(coordinator, request):
        kind, args, _reply = request
        if kind == "prepare" and args[1]["class"] == "run_ref":
            if coordinator.e1_owner is None:
                state["granted_ids"].append(args[3])
            else:
                state["deferred_ids"].append(args[3])
                result = real_service(coordinator, request)
                state["deferred"].set()
                return result
        return real_service(coordinator, request)

    monkeypatch.setattr(ParallelCoordinator, "_service", observe_service)
    real_drive = e1.drive_run_ref_lifecycle

    def drive(request, *, acknowledge, **kwargs):
        state["requests"].append(request)
        effects = e1.RunRefRuntimeDependencies()
        real_child_launch = effects.launch_child

        def capture_child_launch(launch):
            state["child_launches"].append(launch)
            if phase == "failed-sync":
                raise RuntimeError("injected ordinary child launch operation failure")
            return real_child_launch(launch)

        def acknowledge_and_hold(event):
            result = acknowledge(event)
            if event.stage == "allocated" and not state["allocated"].is_set():
                state["allocated"].set()
                _wait(state["command_started"])
                _wait(state["deferred"])
            return result

        return real_drive(
            request,
            acknowledge=acknowledge_and_hold,
            dependencies=replace(effects, launch_child=capture_child_launch),
            **kwargs,
        )

    monkeypatch.setattr(e1, "drive_run_ref_lifecycle", drive)
    def capture_parent_authority(*args, **kwargs):
        attempt = real_prepare(*args, **kwargs)
        node = getattr(attempt, "node", None)
        if node is not None and node.get("class") == "command":
            state["command_attempts"].append(attempt)
        return attempt

    real_prepare = runtime.prepare_effect
    monkeypatch.setattr(runtime, "prepare_effect", capture_parent_authority)

    if phase.startswith("finalize-"):
        real_finalize = adapter.finalize_run_ref_parent_commit

        def finalize(request, prepared, **kwargs):
            if phase == "finalize-after":
                real_finalize(request, prepared, **kwargs)
            _capture_fault_bytes(state, request.parent_run_root, request.ledger_path)
            if phase == "finalize-after":
                raise RuntimeError("injected E1 finalization interruption")
            raise RuntimeError("injected E1 pre-finalization interruption")

        monkeypatch.setattr(adapter, "finalize_run_ref_parent_commit", finalize)
    elif phase == "settled-view":
        real_publish = views.publish_evaluated_view

        def publish(authority, entry):
            if entry.data["record"] == "settled":
                _capture_fault_bytes(
                    state,
                    authority.run_root,
                    state["requests"][0].ledger_path,
                )
                raise ViewPublicationError("injected settled-view publication failure")
            return real_publish(authority, entry)

        monkeypatch.setattr(views, "publish_evaluated_view", publish)
    else:
        _install_failed_memo_sync_fault(monkeypatch, state)

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        _service_run,
        monkeypatch,
        parent,
        source,
        refs,
        "--command-boundaries-file",
        str(boundaries),
    )
    return executor, future, state


def _memo_rows(snapshot, record):
    return [entry.data for entry in snapshot.entries if entry.data["record"] == record]


def _assert_parent_fault_rows(snapshot, state, phase):
    starts = _memo_rows(snapshot, "started")
    commits = _memo_rows(snapshot, "committed")
    settled = _memo_rows(snapshot, "settled")
    identities = {row["identity"] for row in starts}
    assert identities == {
        state["requests"][0].parent_identity,
        state["command_attempts"][0].identity,
    }
    assert len(commits) == int(phase != "failed-sync")
    if commits:
        assert commits[0]["effect_class"] == "run_ref"
    assert len(settled) == int(phase == "settled-view")
    failed = _memo_rows(snapshot, "failed")
    assert len(failed) == int(phase == "failed-sync")
    if failed:
        assert failed[0] == state["failed_row_at_fault"]
    assert snapshot.terminal is None


def _assert_fault_kept_e1_head(state, phase):
    assert len(state["child_launches"]) == len(state["granted_ids"]) == 1
    assert len(state["deferred_ids"]) == 1
    assert state["deferred_ids"][0] not in state["granted_ids"]
    assert state["requests"][0].ledger_path.read_bytes() == state["bytes_at_fault"][1]
    ledger = load_attempt_ledger(state["requests"][0].ledger_path)
    assert sum(row.stage == "allocated" for row in ledger.rows) == 1
    expected_stage = {
        "finalize-before": "completed_pending_parent_commit",
        "failed-sync": "launched",
    }.get(phase, "committed")
    assert ledger.rows[-1].stage == expected_stage


def _assert_drained_fault(authority, snapshot, state, phase):
    _assert_parent_fault_rows(snapshot, state, phase)
    _assert_fault_kept_e1_head(state, phase)
    assert authority.memo_path.read_bytes() == state["bytes_at_fault"][0]


def _assert_resources_open(state):
    request = state["requests"][0]
    command_attempt = state["command_attempts"][0]
    assert not request.run_files.closed
    assert not command_attempt.attempt_files.closed
    assert not command_attempt.workspace_files.closed
    assert _fd_is_open(request.run_files.root_fd)
    assert _fd_is_open(command_attempt.attempt_files.root_fd)
    assert _fd_is_open(command_attempt.workspace_files.root_fd)
    assert _fd_is_open(state["child_launches"][0].parent_root_fd)
    state["descriptors"] = (
        request.run_files.root_fd,
        command_attempt.attempt_files.root_fd,
        command_attempt.workspace_files.root_fd,
        state["child_launches"][0].parent_root_fd,
    )


def _assert_resources_closed(state):
    command_attempt = state["command_attempts"][0]
    assert command_attempt.attempt_files.closed
    assert command_attempt.workspace_files.closed
    assert all(not _fd_is_open(descriptor) for descriptor in state["descriptors"])


def _assert_failed_row_visible(state):
    assert state["failed_sync_injected"]
    assert state["failed_row_at_fault"]["record"] == "failed"
    assert json.loads(state["failed_row_bytes"].splitlines()[-1]) == state["failed_row_at_fault"]
    assert state["bytes_at_fault"][0] == state["failed_row_bytes"]


@pytest.mark.parametrize(
    "phase", ["finalize-before", "finalize-after", "settled-view", "failed-sync"]
)
def test_e1_publication_fault_drains_siblings_before_releasing_owned_descriptors(
    tmp_path, monkeypatch, phase
):
    parent, source, refs, boundaries = _mixed_command_fixture(tmp_path)
    executor, future, state = _install_fault_scenario(
        monkeypatch, parent, source, refs, boundaries, phase
    )
    try:
        _wait(state["fault_reached"])
        assert not future.done()
        if phase == "failed-sync":
            _assert_failed_row_visible(state)
        _assert_resources_open(state)
        state["release_command"].set()
        assert future.result(timeout=45).exit_code == 1
        _assert_resources_closed(state)
    finally:
        state["release_command"].set()
        executor.shutdown(wait=True)

    authority, snapshot = _authority(parent)
    _assert_drained_fault(authority, snapshot, state, phase)


def _partial_e1_run(root, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(root)
    real_drive = e1.drive_run_ref_lifecycle
    fail_next_launch = [True]
    child_launches = []

    def drive(request, **kwargs):
        effects = e1.RunRefRuntimeDependencies()
        real_child_launch = effects.launch_child

        def fail_first_child(launch):
            child_launches.append(launch)
            if fail_next_launch[0]:
                fail_next_launch[0] = False
                raise RuntimeError("injected ordinary child launch operation failure")
            return real_child_launch(launch)

        return real_drive(
            request,
            dependencies=replace(effects, launch_child=fail_first_child),
            **kwargs,
        )

    with monkeypatch.context() as context:
        context.setattr(e1, "drive_run_ref_lifecycle", drive)
        result = _service_run(context, parent, source, refs)
    assert result.exit_code == 1
    authority, snapshot = _authority(parent)
    assert len(snapshot.active_commits) == 1
    assert len([entry for entry in snapshot.entries if entry.data["record"] == "failed"]) == 1
    assert len(child_launches) == 2
    return parent, refs, authority, snapshot


def _incomplete_workspace(authority):
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    groups = {}
    for row in ledger.rows:
        groups.setdefault((row.visit, row.attempt_ordinal), []).append(row)
    incomplete = [
        rows[-1]
        for rows in groups.values()
        if any(row.stage == "launched" for row in rows)
        and not any(row.stage == "committed" for row in rows)
    ]
    assert len(incomplete) == 1
    return incomplete[0].bindings.workspace_path


def _inject_discard_write_fault(monkeypatch):
    details = []
    real_discard = e1._discard_incomplete_attempt
    real_write = e1._write_canonical_document

    def discard(request, dependencies):
        try:
            return real_discard(request, dependencies)
        except e1.RunRefRuntimeError as exc:
            details.append((exc.code, exc.detail))
            raise

    def write(path, value):
        if path.name == "disposition.json":
            raise OSError("injected disposition write failure")
        return real_write(path, value)

    monkeypatch.setattr(e1, "_discard_incomplete_attempt", discard)
    monkeypatch.setattr(e1, "_write_canonical_document", write)
    return details


def _resume_in_process(monkeypatch, parent, refs, run_id):
    monkeypatch.chdir(parent)
    return resume_workflow(run_id, run_ref_root=str(refs))


def _assert_disposition_write_authority(after_authority, before, ledger_bytes, errors):
    assert errors == [("run_ref_workspace_discard_failed", "attempt_disposition_write_failed")]
    after = read_memo(after_authority.memo_path, site_classes(after_authority.program))
    assert after.active_commits.keys() == before.active_commits.keys()
    assert (after_authority.run_root / "run-ref-attempts.jsonl").read_bytes() == ledger_bytes
    return after


def _assert_retry_start_unsettled(after, committed_identity):
    starts = _memo_rows(after, "started")
    assert [row["attempt"] for row in starts if row["identity"] == committed_identity] == [1]
    failed = _memo_rows(after, "failed")
    latest_start = max(
        (row for row in starts if row["identity"] != committed_identity),
        key=lambda row: row["attempt"],
    )
    assert not any(
        row["identity"] == latest_start["identity"]
        and row["attempt"] == latest_start["attempt"]
        for row in failed
    )
    assert after.terminal is None
    assert latest_start["identity"] in after.pending_starts


def _fresh_pending_coordinator(authority, start):
    identity = start["identity"]
    static_identity = re.sub(r"\[\d+\]", "[*]", identity)
    node = site_nodes(authority.program)[static_identity]
    assert node["class"] == "run_ref"
    coordinator = ParallelCoordinator(
        lambda *_args, **_kwargs: None,
        authority,
        {"site_classes": site_classes(authority.program)},
    )
    token = object()
    coordinator.active[identity] = token
    coordinator.e1_owner = token
    request_args = (token, node, (), identity, "owner", None, {})
    return coordinator, request_args


def test_uncleared_fresh_start_makes_physical_prepare_refusal_fatal(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    assert _service_run(monkeypatch, parent, source, refs).exit_code == 0
    authority, snapshot = _authority(parent)
    start = next(
        entry.data
        for entry in snapshot.entries
        if entry.data["record"] == "started"
    )
    authority.memo_path.write_bytes(json.dumps(start, separators=(",", ":")).encode() + b"\n")
    coordinator, request_args = _fresh_pending_coordinator(authority, start)
    refusal = e1.RunRefRuntimeError(
        "run_ref_workspace_discard_failed", "bound_workspace_delete_failed"
    )
    pending = read_memo(authority.memo_path, site_classes(authority.program))
    assert start["identity"] in pending.pending_starts
    assert coordinator._fatal_request("prepare", request_args, refusal)

    failed = {
        "record": "failed",
        "identity": start["identity"],
        "attempt": start["attempt"],
        "code": refusal.code,
        "exit_info": {},
    }
    authority.memo_path.write_bytes(
        json.dumps(start, separators=(",", ":")).encode()
        + b"\n"
        + json.dumps(failed, separators=(",", ":")).encode()
        + b"\n"
    )
    durable_failure = read_memo(authority.memo_path, site_classes(authority.program))
    assert not durable_failure.pending_starts
    coordinator.active.pop(start["identity"])
    coordinator.e1_owner = None
    for detail in ("bound_workspace_delete_failed", "bound_workspace_still_exists"):
        ordinary_refusal = e1.RunRefRuntimeError(refusal.code, detail)
        assert not coordinator._fatal_request("prepare", request_args, ordinary_refusal)


def test_disposition_write_failure_is_fatal_without_starting_another_e1_item(
    tmp_path, monkeypatch
):
    parent, refs, authority, before = _partial_e1_run(tmp_path, monkeypatch)
    assert _incomplete_workspace(authority).exists()
    ledger_path = authority.run_root / "run-ref-attempts.jsonl"
    ledger_bytes_before = ledger_path.read_bytes()
    errors = _inject_discard_write_fault(monkeypatch)
    assert _resume_in_process(monkeypatch, parent, refs, authority.run_root.name) == 1

    after_authority, _after = _authority(parent)
    after = _assert_disposition_write_authority(
        after_authority, before, ledger_bytes_before, errors
    )
    committed_identity = next(iter(before.active_commits))
    _assert_retry_start_unsettled(after, committed_identity)
