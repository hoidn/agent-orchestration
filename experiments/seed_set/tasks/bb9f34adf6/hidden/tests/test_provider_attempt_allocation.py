"""Functional durability and allocation tests for provider attempt identity."""

from __future__ import annotations

import json
import importlib
import hashlib
import os
from pathlib import Path
import stat
from contextlib import contextmanager
import multiprocessing
from types import SimpleNamespace

import pytest

from orchestrator.state import ForEachState, RunState, StateManager
import orchestrator.state_locking as state_locking
from orchestrator.runtime_observability import (
    close_executor_session,
    open_executor_session,
    record_compiled_frontend_provenance,
)
from orchestrator.workflow.call_frame_state import (
    _CallFrameStateManager,
    _path_safe_frame_scope_token,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.resume_projection_integrity import ResumeScopePath
from orchestrator.workflow.surface_ast import WorkflowProvenance


def _workflow(workspace: Path) -> str:
    relative = "workflow.yaml"
    (workspace / relative).write_text("version: '1.0'\nname: allocation-test\nsteps: []\n")
    return relative


class _NestedManager:
    def __init__(
        self,
        parent: StateManager | "_NestedManager",
        frame_id: str,
        state: RunState,
        scope: ResumeScopePath,
    ) -> None:
        self.parent_manager = parent
        self.frame_id = frame_id
        self.run_id = parent.run_id
        self.workspace = parent.workspace
        self.run_root = parent.run_root / "call_frames" / _path_safe_frame_scope_token(frame_id)
        self.state = state
        self.resume_scope_path = scope


def _nested_state(run_id: str, workflow_file: str, run_root: Path) -> RunState:
    return RunState(
        schema_version="2.1",
        run_id=run_id,
        workflow_file=workflow_file,
        workflow_checksum="sha256:" + "1" * 64,
        started_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        status="running",
        run_root=str(run_root),
    )


def _install_frame(parent_state: RunState, child: _NestedManager) -> None:
    parent_state.call_frames[child.frame_id] = {
        "call_frame_id": child.frame_id,
        "state": child.state.to_dict(),
    }


def _actual_nested_manager(
    parent: StateManager | _CallFrameStateManager,
    frame_id: str,
    state: RunState,
    scope: ResumeScopePath,
) -> _CallFrameStateManager:
    child = object.__new__(_CallFrameStateManager)
    child.parent_manager = parent
    child.frame_id = frame_id
    child.run_id = parent.run_id
    child.workspace = parent.workspace
    child.run_root = parent.run_root / "call_frames" / _path_safe_frame_scope_token(frame_id)
    child.state = state
    child.resume_scope_path = scope
    return child


def _attempt_module():
    return importlib.import_module("orchestrator.workflow.provider_attempts")


def _allocate_in_process(
    workspace: str,
    run_id: str,
    scope_payload: dict,
    results,
) -> None:
    try:
        manager = StateManager(Path(workspace), run_id=run_id)
        manager.load()
        scope = _attempt_module().ProviderAttemptScope.from_dict(scope_payload)
        results.put(("ok", manager.allocate_provider_attempt(scope)))
    except BaseException as exc:  # pragma: no cover - returned to parent assertion
        results.put(("error", repr(exc)))


def _allocate_and_publish_in_process(
    workspace: str,
    run_id: str,
    scope_payload: dict,
    results,
) -> None:
    try:
        manager = StateManager(Path(workspace), run_id=run_id)
        manager.load()
        scope = _attempt_module().ProviderAttemptScope.from_dict(scope_payload)
        ordinal = manager.allocate_provider_attempt(scope)
        manager.record_provider_attempt_publication(
            scope,
            ordinal,
            relative_path=f"records/attempt-{ordinal:06d}.json",
            file_sha256="sha256:" + f"{ordinal:064x}",
            record_kind="prompt_snapshot",
        )
        results.put(("ok", ordinal))
    except BaseException as exc:  # pragma: no cover - returned to parent assertion
        results.put(("error", repr(exc)))


def _affected_coordination_bundle() -> SimpleNamespace:
    return SimpleNamespace(
        ir=SimpleNamespace(
            nodes={
                "provider": SimpleNamespace(
                    execution_config=SimpleNamespace(
                        compiler_prompt_dependency_contract=object()
                    )
                )
            }
        ),
        imports={},
    )


def _coordinated_allocate_in_process(
    workspace: str,
    run_id: str,
    scope_payload: dict,
    barrier,
    first_done,
    is_first: bool,
    results,
) -> None:
    try:
        manager = StateManager(Path(workspace), run_id=run_id)
        manager.load()
        _attempt_module().enable_provider_attempt_coordination_for_bundle(
            manager,
            _affected_coordination_bundle(),
        )
        barrier.wait(timeout=10)
        if not is_first:
            assert first_done.wait(timeout=10)
        scope = _attempt_module().ProviderAttemptScope.from_dict(scope_payload)
        ordinal = manager.allocate_provider_attempt(scope)
        if is_first:
            first_done.set()
        results.put(("allocated", ordinal))
    except BaseException as exc:  # pragma: no cover - returned to parent assertion
        first_done.set()
        results.put(("error", repr(exc)))


def _coordinated_status_in_process(
    workspace: str,
    run_id: str,
    barrier,
    first_done,
    is_first: bool,
    results,
) -> None:
    try:
        manager = StateManager(Path(workspace), run_id=run_id)
        manager.load()
        _attempt_module().enable_provider_attempt_coordination_for_bundle(
            manager,
            _affected_coordination_bundle(),
        )
        barrier.wait(timeout=10)
        if not is_first:
            assert first_done.wait(timeout=10)
        manager.update_status("completed")
        if is_first:
            first_done.set()
        results.put(("status", "completed"))
    except BaseException as exc:  # pragma: no cover - returned to parent assertion
        first_done.set()
        results.put(("error", repr(exc)))


def _direct_scope_payload(root: StateManager, *, candidate: str | None = None) -> dict:
    assert root.state is not None
    return {
        "run_id": root.run_id,
        "resume_scope": {
            "root_workflow_file": root.state.workflow_file,
            "call_frame_ids": [],
        },
        "runtime_step_id": "ProviderStep",
        "enclosing_step": {
            "step_name": "Provider",
            "step_id": "ProviderStep",
            "visit_count": 1,
        },
        "loop_iteration": None,
        "adjudication_subject": (
            None if candidate is None else {"candidate_id": candidate}
        ),
    }


def _prepare_direct_scope_root(tmp_path: Path, run_id: str = "scope-root") -> StateManager:
    root = StateManager(tmp_path, run_id=run_id)
    root.initialize(_workflow(tmp_path))
    assert root.state is not None
    root.state.step_visits["Provider"] = 1
    root.state.current_step = {
        "name": "Provider",
        "step_id": "ProviderStep",
        "visit_count": 1,
    }
    return root


def test_old_state_omits_allocator_member_on_round_trip() -> None:
    old = {
        "schema_version": "2.1",
        "run_id": "old-run",
        "workflow_file": "workflow.yaml",
        "workflow_checksum": "sha256:" + "0" * 64,
        "started_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "status": "running",
        "context": {},
        "bound_inputs": {},
        "workflow_outputs": {},
        "finalization": {},
        "steps": {},
        "for_each": {},
        "repeat_until": {},
        "call_frames": {},
        "artifact_versions": {},
        "artifact_consumes": {},
        "private_artifact_versions": {},
        "private_artifact_consumes": {},
        "transition_count": 0,
        "step_visits": {},
    }

    assert RunState.from_dict(old).to_dict() == old

    for noncanonical_empty in ({}, []):
        with pytest.raises(ValueError, match="provider attempt allocation"):
            RunState.from_dict(
                {**old, "provider_attempt_allocations": noncanonical_empty}
            )


def test_unaffected_state_write_creates_no_process_lock(tmp_path: Path) -> None:
    manager = StateManager(tmp_path, run_id="unaffected")
    manager.initialize(_workflow(tmp_path))
    before = manager.state_file.read_bytes()

    manager.update_status("completed")

    assert not (manager.run_root / ".state-mutation.lock").exists()
    assert json.loads(before) | {"status": "completed"} != json.loads(
        manager.state_file.read_bytes()
    )  # updated_at changes as it did before this feature


def test_explicit_durable_enablement_coordinates_all_root_writes(tmp_path: Path) -> None:
    manager = StateManager(tmp_path, run_id="affected")
    manager.initialize(_workflow(tmp_path))

    manager.enable_durable_state_writes()
    manager.update_status("completed")

    assert (manager.run_root / ".state-mutation.lock").is_file()


def test_recursive_typed_contract_hook_enables_only_affected_initialization(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    hook = getattr(
        attempts,
        "enable_provider_attempt_coordination_for_bundle",
        None,
    )
    assert hook is not None
    affected_leaf = _affected_coordination_bundle()
    affected_root = SimpleNamespace(
        ir=SimpleNamespace(nodes={}),
        imports={"nested": affected_leaf},
    )
    unaffected_bundle = SimpleNamespace(
        ir=SimpleNamespace(
            nodes={
                "provider": SimpleNamespace(
                    execution_config=SimpleNamespace(
                        compiler_prompt_dependency_contract=None
                    )
                )
            }
        ),
        imports={},
    )

    affected = StateManager(tmp_path, run_id="affected-bundle")
    assert hook(affected, affected_root) is True
    affected.initialize(_workflow(tmp_path))
    assert (affected.run_root / ".state-mutation.lock").is_file()

    unaffected = StateManager(tmp_path, run_id="unaffected-bundle")
    assert hook(unaffected, unaffected_bundle) is False
    unaffected.initialize(_workflow(tmp_path))
    assert not (unaffected.run_root / ".state-mutation.lock").exists()


def test_recursive_typed_contract_detector_handles_shared_cycles_and_malformed_graphs() -> None:
    detector = _attempt_module().bundle_requires_provider_attempt_coordination
    first = SimpleNamespace(ir=SimpleNamespace(nodes={}), imports={})
    second = SimpleNamespace(ir=SimpleNamespace(nodes={}), imports={"first": first})
    first.imports["second"] = second
    assert detector(first) is False

    affected = _affected_coordination_bundle()
    shared_root = SimpleNamespace(
        ir=SimpleNamespace(nodes={}),
        imports={"left": affected, "right": affected},
    )
    assert detector(shared_root) is True

    malformed = SimpleNamespace(
        ir=SimpleNamespace(nodes={}),
        imports={"invalid": object()},
    )
    with pytest.raises(TypeError, match="executable workflow bundle"):
        detector(malformed)


@pytest.mark.parametrize(
    "import_order",
    [("affected", "malformed"), ("malformed", "affected")],
)
def test_recursive_typed_contract_detector_rejects_malformed_affected_siblings_in_any_order(
    import_order: tuple[str, str],
) -> None:
    detector = _attempt_module().bundle_requires_provider_attempt_coordination
    children = {
        "affected": _affected_coordination_bundle(),
        "malformed": object(),
    }
    root = SimpleNamespace(
        ir=SimpleNamespace(nodes={}),
        imports={name: children[name] for name in import_order},
    )

    with pytest.raises(TypeError, match="executable workflow bundle"):
        detector(root)


def test_recursive_typed_contract_detector_rejects_malformed_import_below_local_contract() -> None:
    detector = _attempt_module().bundle_requires_provider_attempt_coordination
    affected = _affected_coordination_bundle()
    affected.imports["malformed"] = object()

    with pytest.raises(TypeError, match="executable workflow bundle"):
        detector(affected)


def test_direct_durable_write_preserves_callers_current_context_mutation(
    tmp_path: Path,
) -> None:
    manager = StateManager(tmp_path, run_id="direct-durable-context")
    manager.initialize(_workflow(tmp_path))
    manager.enable_durable_state_writes()
    assert manager.state is not None
    manager.state.context["session_marker"] = "persist-me"

    manager._write_state()

    persisted = json.loads(manager.state_file.read_bytes())
    assert persisted["context"]["session_marker"] == "persist-me"


def test_stale_direct_durable_write_keeps_newer_root_allocator_projection(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="stale-direct-write")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    stale = StateManager(tmp_path, run_id=root.run_id)
    stale.load()
    assert root.allocate_provider_attempt(scope) == 2
    assert stale.state is not None
    stale.state.context["direct_marker"] = "kept"

    stale._write_state()

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["context"]["direct_marker"] == "kept"
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 2


def test_affected_managers_loaded_before_first_allocation_coordinate_ordinary_mutation(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="pre-allocation-stale-manager")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    stale = StateManager(tmp_path, run_id=root.run_id)
    stale.load()
    affected_bundle = SimpleNamespace(
        ir=SimpleNamespace(
            nodes={
                "provider": SimpleNamespace(
                    execution_config=SimpleNamespace(
                        compiler_prompt_dependency_contract=object()
                    )
                )
            }
        ),
        imports={},
    )
    hook = _attempt_module().enable_provider_attempt_coordination_for_bundle
    assert hook(root, affected_bundle) is True
    assert hook(stale, affected_bundle) is True
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    assert root.allocate_provider_attempt(scope) == 1
    stale.update_status("completed")

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["status"] == "completed"
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 1
    assert stale._durable_state_writes is True


def test_state_transaction_reloads_before_external_session_style_mutation(
    tmp_path: Path,
) -> None:
    root = StateManager(tmp_path, run_id="external-transaction")
    root.initialize(_workflow(tmp_path))
    root.enable_durable_state_writes()
    stale = StateManager(tmp_path, run_id=root.run_id)
    stale.load()
    stale.enable_durable_state_writes()
    root.update_run_error({"type": "newer-error"})

    with stale.state_transaction() as transaction_state:
        transaction_state.context["session_marker"] = "kept"

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["error"] == {"type": "newer-error"}
    assert persisted["context"]["session_marker"] == "kept"


def test_state_transaction_exception_rolls_back_memory_and_disk(tmp_path: Path) -> None:
    manager = StateManager(tmp_path, run_id="transaction-rollback")
    manager.initialize(_workflow(tmp_path))
    manager.enable_durable_state_writes()

    with pytest.raises(RuntimeError, match="abort transaction"):
        with manager.state_transaction() as transaction_state:
            transaction_state.context["must_not_persist"] = True
            raise RuntimeError("abort transaction")

    assert manager.state is not None
    assert "must_not_persist" not in manager.state.context
    assert "must_not_persist" not in json.loads(manager.state_file.read_bytes())["context"]


def test_production_callers_use_transactions_instead_of_direct_root_write() -> None:
    production_paths = (
        Path("orchestrator/workflow/executor.py"),
        Path("orchestrator/cli/commands/run.py"),
        Path("orchestrator/cli/commands/resume.py"),
    )

    assert all("._write_state(" not in path.read_text() for path in production_paths)


def test_external_runtime_transactions_preserve_newer_allocator_and_all_fields(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="external-runtime-fields")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    stale = StateManager(tmp_path, run_id=root.run_id)
    stale.load()
    assert root.allocate_provider_attempt(scope) == 2
    provenance = WorkflowProvenance(
        workflow_path=tmp_path / "workflow.orc",
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
        frontend_build_root=Path("build"),
        frontend_source_trace_path=Path("build/source-map.json"),
    )

    with stale.state_transaction() as transaction_state:
        transaction_state.observability = {"summary_mode": "on"}
        record_compiled_frontend_provenance(transaction_state, provenance)
        session_id = open_executor_session(
            transaction_state,
            entrypoint="resume",
            pid=12345,
            process_start_time="process-token",
        )
    stale.update_bound_inputs({"input": "value"})
    with stale.state_transaction() as transaction_state:
        close_executor_session(
            transaction_state,
            session_id=session_id,
            status="completed",
        )

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 2
    assert persisted["bound_inputs"] == {"input": "value"}
    assert persisted["observability"] == {"summary_mode": "on"}
    assert persisted["runtime_observability"]["compiled_frontend"][
        "frontend_kind"
    ] == "workflow_lisp"
    assert persisted["runtime_observability"]["executor_sessions"][0][
        "status"
    ] == "completed"


def test_workflow_boundary_persistence_after_allocation_keeps_bound_inputs(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="workflow-boundary-fields")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = root

    executor._persist_workflow_boundary_state(
        {
            "bound_inputs": {"input": "boundary-value"},
            "workflow_outputs": {"output": "value"},
            "finalization": {"status": "completed"},
            "error": None,
        }
    )

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["bound_inputs"] == {"input": "boundary-value"}
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 1


def test_loaded_nonempty_allocator_automatically_enables_durable_writes(
    tmp_path: Path,
) -> None:
    manager = StateManager(tmp_path, run_id="loaded-allocator")
    manager.initialize(_workflow(tmp_path))
    persisted = json.loads(manager.state_file.read_bytes())
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(manager)
    )
    persisted["provider_attempt_allocations"] = {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 1,
            "events": [{"ordinal": 1, "event": "allocated"}],
        }
    }
    manager.state_file.write_text(json.dumps(persisted, indent=2))

    loaded = StateManager(tmp_path, run_id="loaded-allocator")
    loaded.load()
    loaded.update_status("completed")

    assert (loaded.run_root / ".state-mutation.lock").is_file()
    assert loaded.state is not None
    assert loaded.state.provider_attempt_allocations == persisted[
        "provider_attempt_allocations"
    ]


def test_ordinary_affected_write_acquires_process_lock_before_root_rlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.state as state_module

    manager = StateManager(tmp_path, run_id="lock-order")
    manager.initialize(_workflow(tmp_path))
    manager.enable_durable_state_writes()
    events: list[str] = []

    class TrackingRLock:
        def __enter__(self):
            events.append("rlock-acquire")
            return self

        def __exit__(self, exc_type, exc, traceback):
            events.append("rlock-release")
            return False

    @contextmanager
    def tracking_process_lock(path: Path):
        del path
        events.append("process-acquire")
        try:
            yield
        finally:
            events.append("process-release")

    manager._lock = TrackingRLock()  # type: ignore[assignment]
    monkeypatch.setattr(state_module, "exclusive_file_lock", tracking_process_lock)

    manager.update_status("completed")

    assert events[:2] == ["process-acquire", "rlock-acquire"]
    assert events[-2:] == ["rlock-release", "process-release"]


def test_ordinary_affected_write_preserves_newer_allocator_projection(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="stale-writer")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    stale = StateManager(tmp_path, run_id=root.run_id)
    stale.load()

    assert root.allocate_provider_attempt(scope) == 2
    stale.update_status("completed")

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["status"] == "completed"
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 2


def test_record_only_publication_takes_only_two_process_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquired: list[str] = []

    @contextmanager
    def tracking_lock(path: Path):
        acquired.append(path.name)
        yield

    monkeypatch.setattr(state_locking, "exclusive_file_lock", tracking_lock)

    with state_locking.record_only_publication_locks(tmp_path):
        acquired.append("body")

    assert acquired == [".state-mutation.lock", ".aggregate.lock", "body"]


def test_durable_writer_retries_short_writes_and_syncs_file_and_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "state.json"
    payload = b'{"state":"' + (b"x" * 80) + b'"}'
    real_write = os.write
    real_fsync = os.fsync
    write_sizes: list[int] = []
    sync_kinds: list[str] = []
    replaces: list[tuple[Path, Path]] = []

    def short_write(fd: int, data: bytes | memoryview) -> int:
        written = real_write(fd, bytes(data[:7]))
        write_sizes.append(written)
        return written

    def tracking_fsync(fd: int) -> None:
        mode = os.fstat(fd).st_mode
        sync_kinds.append("directory" if stat.S_ISDIR(mode) else "file")
        real_fsync(fd)

    real_replace = os.replace

    def tracking_replace(source: Path | str, target: Path | str) -> None:
        replaces.append((Path(source), Path(target)))
        real_replace(source, target)

    monkeypatch.setattr(state_locking.os, "write", short_write)
    monkeypatch.setattr(state_locking.os, "fsync", tracking_fsync)
    monkeypatch.setattr(state_locking.os, "replace", tracking_replace)

    state_locking.durable_atomic_write(destination, payload)

    assert destination.read_bytes() == payload
    assert len(write_sizes) > 1
    assert sync_kinds == ["file", "directory"]
    assert replaces and replaces[0][1] == destination


@pytest.mark.parametrize("failure_point", ["open", "write", "file_fsync", "replace", "dir_fsync"])
def test_affected_root_write_never_reports_success_after_durability_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    manager = StateManager(tmp_path, run_id=f"fault-{failure_point}")
    manager.initialize(_workflow(tmp_path))
    manager.enable_durable_state_writes()
    real_open = state_locking.os.open
    real_write = state_locking.os.write
    real_fsync = state_locking.os.fsync
    real_replace = state_locking.os.replace
    fsync_count = 0

    def failing_open(path: Path | str, flags: int, mode: int = 0o777) -> int:
        if failure_point == "open" and str(path).endswith(".tmp"):
            raise OSError("injected open failure")
        return real_open(path, flags, mode)

    def failing_write(fd: int, data: bytes | memoryview) -> int:
        if failure_point == "write":
            raise OSError("injected write failure")
        return real_write(fd, data)

    def failing_fsync(fd: int) -> None:
        nonlocal fsync_count
        fsync_count += 1
        if failure_point == "file_fsync" and fsync_count == 1:
            raise OSError("injected file fsync failure")
        if failure_point == "dir_fsync" and stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("injected directory fsync failure")
        real_fsync(fd)

    def failing_replace(source: Path | str, target: Path | str) -> None:
        if failure_point == "replace":
            raise OSError("injected replace failure")
        real_replace(source, target)

    monkeypatch.setattr(state_locking.os, "open", failing_open)
    monkeypatch.setattr(state_locking.os, "write", failing_write)
    monkeypatch.setattr(state_locking.os, "fsync", failing_fsync)
    monkeypatch.setattr(state_locking.os, "replace", failing_replace)

    with pytest.raises(OSError, match="injected"):
        manager.update_status("completed")


def test_affected_backup_repair_uses_durable_root_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.state as state_module

    manager = StateManager(tmp_path, run_id="durable-repair", backup_enabled=True)
    manager.initialize(_workflow(tmp_path))
    manager.backup_state("Provider")
    manager.enable_durable_state_writes()
    calls: list[Path] = []
    real_writer = state_module.durable_atomic_write

    def tracking_writer(path: Path, payload: bytes) -> None:
        calls.append(path)
        real_writer(path, payload)

    monkeypatch.setattr(state_module, "durable_atomic_write", tracking_writer)

    assert manager.attempt_repair() is True
    assert calls == [manager.state_file]


def test_affected_durable_repair_uses_backup_without_reloading_corrupt_primary(
    tmp_path: Path,
) -> None:
    manager = StateManager(tmp_path, run_id="durable-corrupt-repair", backup_enabled=True)
    manager.initialize(_workflow(tmp_path))
    manager.backup_state("Valid")
    manager.enable_durable_state_writes()
    manager.state_file.write_text("invalid json {")

    assert manager.attempt_repair() is True
    assert StateManager(tmp_path, run_id=manager.run_id).load().status == "running"


def test_repair_skips_semantically_invalid_newest_backup_for_older_valid_backup(
    tmp_path: Path,
) -> None:
    manager = StateManager(tmp_path, run_id="semantic-backup-fallback")
    state = manager.initialize(_workflow(tmp_path))
    valid_backup = manager.run_root / "state.json.step_a-valid.bak"
    valid_backup.write_bytes(manager.state_file.read_bytes())
    invalid_payload = state.to_dict()
    invalid_payload["provider_attempt_allocations"] = {}
    invalid_backup = manager.run_root / "state.json.step_z-invalid.bak"
    invalid_backup.write_text(json.dumps(invalid_payload, indent=2))
    manager.state_file.write_text("invalid json {")

    assert manager.attempt_repair() is True
    assert json.loads(manager.state_file.read_bytes()) == json.loads(
        valid_backup.read_bytes()
    )


def test_repair_refuses_pre_allocation_backup_after_committed_provider_ordinal(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="pre-allocation-repair")
    root.backup_enabled = True
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    root.backup_state("Provider")
    backup = root.run_root / "state.json.step_Provider.bak"
    backup_bytes = backup.read_bytes()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )

    assert root.allocate_provider_attempt(scope) == 1
    assert (
        root.run_root / ".provider-attempt-allocation-started"
    ).read_bytes() == b'{"schema_version":"provider_attempt_repair_barrier.v1"}\n'
    corrupt_primary = b"invalid json {"
    root.state_file.write_bytes(corrupt_primary)
    repairing = StateManager(tmp_path, run_id=root.run_id)

    assert repairing.attempt_repair() is False
    assert repairing.state_file.read_bytes() == corrupt_primary
    assert backup.read_bytes() == backup_bytes


def test_provider_attempt_barrier_failure_prevents_allocator_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.state as state_module

    root = _prepare_direct_scope_root(tmp_path, run_id="barrier-write-failure")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    primary_before = root.state_file.read_bytes()
    real_writer = state_module.durable_atomic_write

    def fail_barrier(path: Path, payload: bytes) -> None:
        if path.name == ".provider-attempt-allocation-started":
            raise OSError("barrier write failed")
        real_writer(path, payload)

    monkeypatch.setattr(state_module, "durable_atomic_write", fail_barrier)

    with pytest.raises(OSError, match="barrier write failed"):
        root.allocate_provider_attempt(scope)

    assert root.state_file.read_bytes() == primary_before
    assert not (root.run_root / ".provider-attempt-allocation-started").exists()
    assert root.state is not None
    assert root.state.provider_attempt_allocations == {}


def test_repair_refuses_legacy_aggregate_lock_without_new_barrier(
    tmp_path: Path,
) -> None:
    manager = StateManager(tmp_path, run_id="legacy-aggregate-repair", backup_enabled=True)
    manager.initialize(_workflow(tmp_path))
    manager.backup_state("Provider")
    backup = manager.run_root / "state.json.step_Provider.bak"
    backup_bytes = backup.read_bytes()
    legacy_lock = (
        manager.run_root
        / "workflow_lisp"
        / "prompt_dependencies"
        / ".aggregate.lock"
    )
    legacy_lock.parent.mkdir(parents=True, exist_ok=True)
    legacy_lock.touch()
    corrupt_primary = b"invalid json {"
    manager.state_file.write_bytes(corrupt_primary)
    repairing = StateManager(tmp_path, run_id=manager.run_id)

    assert repairing.attempt_repair() is False
    assert repairing.state_file.read_bytes() == corrupt_primary
    assert backup.read_bytes() == backup_bytes


def test_repair_refuses_allocator_bearing_backup_without_legacy_signal(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="allocator-backup-repair")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    backup_payload = json.loads(root.state_file.read_bytes())
    backup_payload["provider_attempt_allocations"] = {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 1,
            "events": [{"ordinal": 1, "event": "allocated"}],
        }
    }
    backup = root.run_root / "state.json.step_Provider.bak"
    backup.write_text(json.dumps(backup_payload, indent=2), encoding="utf-8")
    backup_bytes = backup.read_bytes()
    corrupt_primary = b"invalid json {"
    root.state_file.write_bytes(corrupt_primary)
    repairing = StateManager(tmp_path, run_id=root.run_id)

    assert repairing.attempt_repair() is False
    assert repairing.state_file.read_bytes() == corrupt_primary
    assert backup.read_bytes() == backup_bytes


def test_allocator_bearing_repair_fails_closed_without_mutating_files(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="allocator-repair-enablement")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    backup = root.run_root / "state.json.step_allocator.bak"
    backup.write_bytes(root.state_file.read_bytes())
    backup_bytes = backup.read_bytes()
    corrupt_primary = b"invalid json {"
    root.state_file.write_bytes(corrupt_primary)
    repairing = StateManager(tmp_path, run_id=root.run_id)

    assert repairing._durable_state_writes is False
    assert repairing.attempt_repair() is False
    assert repairing._durable_state_writes is False
    assert repairing.state is None
    assert repairing.state_file.read_bytes() == corrupt_primary
    assert backup.read_bytes() == backup_bytes


def test_allocator_bearing_repair_never_invokes_state_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.state as state_module

    root = _prepare_direct_scope_root(tmp_path, run_id="allocator-repair-writer")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    backup = root.run_root / "state.json.step_allocator.bak"
    backup.write_bytes(root.state_file.read_bytes())
    backup_bytes = backup.read_bytes()
    corrupt_primary = b"invalid json {"
    root.state_file.write_bytes(corrupt_primary)
    repairing = StateManager(tmp_path, run_id=root.run_id)
    calls: list[tuple[Path, bytes]] = []
    real_writer = state_module.durable_atomic_write

    def tracking_writer(path: Path, payload: bytes) -> None:
        calls.append((path, payload))
        real_writer(path, payload)

    monkeypatch.setattr(state_module, "durable_atomic_write", tracking_writer)

    assert repairing.attempt_repair() is False
    assert calls == []
    assert repairing.state_file.read_bytes() == corrupt_primary
    assert backup.read_bytes() == backup_bytes
    assert repairing._durable_state_writes is False


def test_unaffected_repair_retains_legacy_copy_without_durable_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.state as state_module

    manager = StateManager(tmp_path, run_id="unaffected-repair-writer")
    manager.initialize(_workflow(tmp_path))
    expected = manager.state_file.read_bytes()
    backup = manager.run_root / "state.json.step_valid.bak"
    backup.write_bytes(expected)
    manager.state_file.write_text("invalid json {")
    repairing = StateManager(tmp_path, run_id=manager.run_id)
    calls: list[tuple[Path, bytes]] = []

    def tracking_writer(path: Path, payload: bytes) -> None:
        calls.append((path, payload))

    monkeypatch.setattr(state_module, "durable_atomic_write", tracking_writer)

    assert repairing.attempt_repair() is True
    assert calls == []
    assert repairing.state_file.read_bytes() == expected
    assert repairing._durable_state_writes is False
    assert (repairing.run_root / ".state-mutation.lock").is_file()


def test_resolve_aggregate_owner_returns_root_scope_and_leaf(tmp_path: Path) -> None:
    root = StateManager(tmp_path, run_id="root-owner")
    root_state = root.initialize(_workflow(tmp_path))

    resolution = _attempt_module().resolve_aggregate_run_owner(root)

    assert resolution.root_manager is root
    assert resolution.resume_scope_path == ResumeScopePath.root(root_state.workflow_file)
    assert resolution.leaf_state is root_state
    assert resolution.aggregate_root == root.run_root


def test_resolve_aggregate_owner_walks_two_call_levels_in_order(tmp_path: Path) -> None:
    root = StateManager(tmp_path, run_id="nested-owner")
    root_state = root.initialize(_workflow(tmp_path))
    first_scope = ResumeScopePath.root(root_state.workflow_file).child("frame-one")
    first_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("frame-one")
    first = _NestedManager(
        root,
        "frame-one",
        _nested_state(root.run_id, "first.orc", first_root),
        first_scope,
    )
    second_scope = first_scope.child("frame-two")
    second_root = first.run_root / "call_frames" / _path_safe_frame_scope_token("frame-two")
    second = _NestedManager(
        first,
        "frame-two",
        _nested_state(root.run_id, "second.orc", second_root),
        second_scope,
    )
    _install_frame(first.state, second)
    _install_frame(root_state, first)

    resolution = _attempt_module().resolve_aggregate_run_owner(second)

    assert resolution.root_manager is root
    assert resolution.resume_scope_path == second_scope
    assert resolution.leaf_state.to_dict() == second.state.to_dict()
    assert resolution.aggregate_root == root.run_root


def test_resolve_aggregate_owner_rejects_wrong_intermediate_scope_prefix(
    tmp_path: Path,
) -> None:
    root = StateManager(tmp_path, run_id="intermediate-scope")
    root_state = root.initialize(_workflow(tmp_path))
    root_scope = ResumeScopePath.root(root_state.workflow_file)
    first_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("first")
    first = _NestedManager(
        root,
        "first",
        _nested_state(root.run_id, "first.orc", first_root),
        root_scope.child("wrong-first"),
    )
    correct_leaf_scope = root_scope.child("first").child("second")
    second_root = first.run_root / "call_frames" / _path_safe_frame_scope_token("second")
    second = _NestedManager(
        first,
        "second",
        _nested_state(root.run_id, "second.orc", second_root),
        correct_leaf_scope,
    )
    _install_frame(first.state, second)
    _install_frame(root_state, first)

    with pytest.raises(ValueError, match="scope path prefix"):
        _attempt_module().resolve_aggregate_run_owner(second)


@pytest.mark.parametrize("allocator_location", ["live", "snapshot"])
def test_resolve_aggregate_owner_rejects_nested_root_owned_allocator_state(
    tmp_path: Path,
    allocator_location: str,
) -> None:
    root = StateManager(tmp_path, run_id=f"nested-allocator-{allocator_location}")
    root_state = root.initialize(_workflow(tmp_path))
    scope_path = ResumeScopePath.root(root_state.workflow_file).child("frame")
    child_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("frame")
    child = _actual_nested_manager(
        root,
        "frame",
        _nested_state(root.run_id, "child.orc", child_root),
        scope_path,
    )
    nested_scope = _attempt_module().ProviderAttemptScope.from_dict(
        {
            "run_id": root.run_id,
            "resume_scope": {
                "root_workflow_file": root_state.workflow_file,
                "call_frame_ids": ["frame"],
            },
            "runtime_step_id": "NestedProvider",
            "enclosing_step": {
                "step_name": "Provider",
                "step_id": "NestedProvider",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )
    nested_allocations = {
        nested_scope.key: {
            "scope": nested_scope.to_dict(),
            "last_allocated_ordinal": 1,
            "events": [{"ordinal": 1, "event": "allocated"}],
        }
    }
    if allocator_location == "live":
        child.state.provider_attempt_allocations = nested_allocations
    _install_frame(root_state, child)
    if allocator_location == "snapshot":
        root_state.call_frames["frame"]["state"][
            "provider_attempt_allocations"
        ] = nested_allocations
    before_root_bytes = root.state_file.read_bytes()

    with pytest.raises(ValueError, match="root-owned"):
        _attempt_module().resolve_aggregate_run_owner(child)
    with pytest.raises(ValueError, match="root-owned"):
        child.allocate_provider_attempt(nested_scope)
    assert root.state_file.read_bytes() == before_root_bytes


@pytest.mark.parametrize(
    ("contradiction", "message"),
    [
        ("run_id", "run_id"),
        ("run_root", "run_root"),
        ("frame_id", "call frame"),
        ("truncated_scope", "scope path"),
        ("extended_scope", "scope path"),
        ("malformed_state", "nested state"),
    ],
)
def test_resolve_aggregate_owner_rejects_identity_and_snapshot_contradictions(
    tmp_path: Path,
    contradiction: str,
    message: str,
) -> None:
    root = StateManager(tmp_path, run_id=f"contradiction-{contradiction}")
    root_state = root.initialize(_workflow(tmp_path))
    scope = ResumeScopePath.root(root_state.workflow_file).child("frame")
    child_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("frame")
    child = _NestedManager(
        root,
        "frame",
        _nested_state(root.run_id, "child.orc", child_root),
        scope,
    )
    _install_frame(root_state, child)
    if contradiction == "run_id":
        child.run_id = "different-run"
    elif contradiction == "run_root":
        child.run_root = root.run_root / "wrong"
    elif contradiction == "frame_id":
        root_state.call_frames["frame"]["call_frame_id"] = "different-frame"
    elif contradiction == "truncated_scope":
        child.resume_scope_path = ResumeScopePath.root(root_state.workflow_file)
    elif contradiction == "extended_scope":
        child.resume_scope_path = scope.child("extra")
    elif contradiction == "malformed_state":
        root_state.call_frames["frame"]["state"] = {"schema_version": "2.1"}

    with pytest.raises(ValueError, match=message):
        _attempt_module().resolve_aggregate_run_owner(child)


def test_resolve_aggregate_owner_rejects_cycle_and_non_root_terminal(tmp_path: Path) -> None:
    root = StateManager(tmp_path, run_id="cycle-owner")
    root_state = root.initialize(_workflow(tmp_path))
    scope = ResumeScopePath.root(root_state.workflow_file).child("frame")
    child_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("frame")
    child = _NestedManager(
        root,
        "frame",
        _nested_state(root.run_id, "child.orc", child_root),
        scope,
    )
    child.parent_manager = child
    with pytest.raises(ValueError, match="cycle"):
        _attempt_module().resolve_aggregate_run_owner(child)

    child.parent_manager = object()  # type: ignore[assignment]
    with pytest.raises(TypeError, match="terminal root"):
        _attempt_module().resolve_aggregate_run_owner(child)


def test_provider_attempt_scope_is_closed_canonical_and_full_sha256_keyed(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path)
    payload = _direct_scope_payload(root)

    scope = _attempt_module().ProviderAttemptScope.from_dict(payload)
    _attempt_module().validate_provider_attempt_scope(
        scope,
        _attempt_module().resolve_aggregate_run_owner(root),
    )

    expected_bytes = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    assert scope.to_dict() == payload
    assert scope.canonical_bytes() == expected_bytes
    assert scope.key == "sha256:" + hashlib.sha256(expected_bytes).hexdigest()


@pytest.mark.parametrize("shape", ["direct", "for_each", "repeat_until", "candidate"])
def test_provider_attempt_scope_validates_supported_runtime_shapes(
    tmp_path: Path,
    shape: str,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id=f"scope-{shape}")
    payload = _direct_scope_payload(root, candidate="candidate_a" if shape == "candidate" else None)
    if shape in {"for_each", "repeat_until"}:
        assert root.state is not None
        root.state.step_visits = {"Loop": 2}
        root.state.current_step = {
            "name": "Loop",
            "step_id": "LoopStep",
            "visit_count": 2,
        }
        payload["runtime_step_id"] = "LoopStep#3.NestedProvider"
        payload["enclosing_step"] = {
            "step_name": "Loop",
            "step_id": "LoopStep",
            "visit_count": 2,
        }
        payload["loop_iteration"] = {
            "kind": shape,
            "loop_step_id": "LoopStep",
            "iteration": 3,
        }
        if shape == "for_each":
            root.state.for_each["Loop"] = ForEachState(
                items=[0, 1, 2, 3], current_index=3
            )
        else:
            root.state.repeat_until["Loop"] = {"current_iteration": 3}

    scope = _attempt_module().ProviderAttemptScope.from_dict(payload)
    _attempt_module().validate_provider_attempt_scope(
        scope,
        _attempt_module().resolve_aggregate_run_owner(root),
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "null",
        "wrong_type",
        "zero_visit",
        "retry_index",
        "nested_loop",
        "bad_candidate",
    ],
)
def test_provider_attempt_scope_rejects_non_closed_or_invalid_fields(
    tmp_path: Path,
    mutation: str,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id=f"invalid-{mutation}")
    payload = _direct_scope_payload(root)
    if mutation == "missing":
        del payload["runtime_step_id"]
    elif mutation == "extra":
        payload["unexpected"] = True
    elif mutation == "null":
        payload["runtime_step_id"] = None
    elif mutation == "wrong_type":
        payload["enclosing_step"]["visit_count"] = True
    elif mutation == "zero_visit":
        payload["enclosing_step"]["visit_count"] = 0
    elif mutation == "retry_index":
        payload["retry_index"] = 0
    elif mutation == "nested_loop":
        payload["loop_iteration"] = [
            {"kind": "for_each", "loop_step_id": "LoopOne", "iteration": 0},
            {"kind": "for_each", "loop_step_id": "LoopTwo", "iteration": 0},
        ]
    elif mutation == "bad_candidate":
        payload["adjudication_subject"] = {"candidate_id": "bad/candidate"}

    with pytest.raises((TypeError, ValueError)):
        _attempt_module().ProviderAttemptScope.from_dict(payload)


def test_provider_attempt_scope_rejects_current_step_contradiction(tmp_path: Path) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="current-contradiction")
    payload = _direct_scope_payload(root)
    assert root.state is not None
    root.state.current_step["visit_count"] = 2
    scope = _attempt_module().ProviderAttemptScope.from_dict(payload)

    with pytest.raises(ValueError, match="current_step"):
        _attempt_module().validate_provider_attempt_scope(
            scope,
            _attempt_module().resolve_aggregate_run_owner(root),
        )


@pytest.mark.parametrize(
    "runtime_step_id",
    [
        "UnrelatedProvider",
        "OtherLoop#3.NestedProvider",
        "LoopStep#2.NestedProvider",
        "LoopStep#3.",
    ],
)
def test_loop_scope_rejects_noncanonical_runtime_step_projection(
    tmp_path: Path,
    runtime_step_id: str,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="loop-runtime-id")
    assert root.state is not None
    root.state.step_visits = {"Loop": 2}
    root.state.current_step = {
        "name": "Loop",
        "step_id": "LoopStep",
        "visit_count": 2,
    }
    root.state.for_each["Loop"] = ForEachState(items=[0, 1, 2, 3], current_index=3)
    payload = _direct_scope_payload(root)
    payload["runtime_step_id"] = runtime_step_id
    payload["enclosing_step"] = {
        "step_name": "Loop",
        "step_id": "LoopStep",
        "visit_count": 2,
    }
    payload["loop_iteration"] = {
        "kind": "for_each",
        "loop_step_id": "LoopStep",
        "iteration": 3,
    }
    scope = _attempt_module().ProviderAttemptScope.from_dict(payload)

    with pytest.raises(ValueError, match="runtime_step_id"):
        _attempt_module().validate_provider_attempt_scope(
            scope,
            _attempt_module().resolve_aggregate_run_owner(root),
        )


def test_root_allocator_persists_complete_scope_and_monotonic_events(tmp_path: Path) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="allocate-root")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    first = root.allocate_provider_attempt(scope)
    second = root.allocate_provider_attempt(scope)

    assert (first, second) == (1, 2)
    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["provider_attempt_allocations"] == {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 2,
            "events": [
                {"ordinal": 1, "event": "allocated"},
                {"ordinal": 2, "event": "allocated"},
            ],
        }
    }


@pytest.mark.parametrize(
    "corruption",
    [
        "key",
        "duplicate",
        "reordered",
        "conflicting",
        "allocation_gap",
        "noncanonical_publication",
    ],
)
def test_allocator_rejects_corrupt_persisted_projection_before_increment(
    tmp_path: Path,
    corruption: str,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id=f"corrupt-{corruption}")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    root.allocate_provider_attempt(scope)
    persisted = json.loads(root.state_file.read_bytes())
    entry = persisted["provider_attempt_allocations"].pop(scope.key)
    if corruption == "key":
        persisted["provider_attempt_allocations"]["sha256:" + "f" * 64] = entry
    else:
        persisted["provider_attempt_allocations"][scope.key] = entry
        if corruption == "duplicate":
            entry["events"].append({"ordinal": 1, "event": "allocated"})
        elif corruption == "reordered":
            entry["last_allocated_ordinal"] = 2
            entry["events"] = [
                {"ordinal": 2, "event": "allocated"},
                {"ordinal": 1, "event": "allocated"},
            ]
        elif corruption == "conflicting":
            entry["events"].append(
                {
                    "ordinal": 1,
                    "event": "evidence_published",
                    "relative_path": "record.json",
                    "file_sha256": "sha256:" + "a" * 64,
                    "record_kind": "failure",
                }
            )
            entry["events"].append(
                {
                    "ordinal": 1,
                    "event": "evidence_published",
                    "relative_path": "other.json",
                    "file_sha256": "sha256:" + "b" * 64,
                    "record_kind": "prompt_snapshot",
                }
            )
        elif corruption == "allocation_gap":
            entry["last_allocated_ordinal"] = 3
            entry["events"] = [
                {"ordinal": 1, "event": "allocated"},
                {"ordinal": 3, "event": "allocated"},
            ]
        elif corruption == "noncanonical_publication":
            entry["last_allocated_ordinal"] = 2
            entry["events"] = [
                {"ordinal": 1, "event": "allocated"},
                {"ordinal": 2, "event": "allocated"},
                {
                    "ordinal": 1,
                    "event": "evidence_published",
                    "relative_path": "record.json",
                    "file_sha256": "sha256:" + "a" * 64,
                    "record_kind": "failure",
                },
            ]
    root.state_file.write_text(json.dumps(persisted, indent=2))

    with pytest.raises(ValueError, match="provider attempt allocation"):
        StateManager(tmp_path, run_id=root.run_id).load()


def test_publication_event_is_durable_closed_and_follows_allocation(tmp_path: Path) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="publication-event")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    ordinal = root.allocate_provider_attempt(scope)

    root.record_provider_attempt_publication(
        scope,
        ordinal,
        relative_path="workflow_lisp/prompt_dependencies/step/visit/attempt-000001.json",
        file_sha256="sha256:" + "a" * 64,
        record_kind="prompt_snapshot",
    )

    persisted = json.loads(root.state_file.read_bytes())
    events = persisted["provider_attempt_allocations"][scope.key]["events"]
    assert events == [
        {"ordinal": 1, "event": "allocated"},
        {
            "ordinal": 1,
            "event": "evidence_published",
            "relative_path": "workflow_lisp/prompt_dependencies/step/visit/attempt-000001.json",
            "file_sha256": "sha256:" + "a" * 64,
            "record_kind": "prompt_snapshot",
        },
    ]
    with pytest.raises(ValueError, match="already published"):
        root.record_provider_attempt_publication(
            scope,
            ordinal,
            relative_path="other.json",
            file_sha256="sha256:" + "b" * 64,
            record_kind="failure",
        )


def test_publication_event_rejects_non_hex_file_digest(tmp_path: Path) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="publication-digest")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    ordinal = root.allocate_provider_attempt(scope)

    with pytest.raises(ValueError, match="file_sha256"):
        root.record_provider_attempt_publication(
            scope,
            ordinal,
            relative_path="record.json",
            file_sha256="sha256:" + "g" * 64,
            record_kind="failure",
        )


@pytest.mark.parametrize("publication_order", [(1, 2), (2, 1)])
def test_publication_allows_interleaved_allocations_for_same_scope(
    tmp_path: Path,
    publication_order: tuple[int, int],
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="interleaved-publication")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    first = root.allocate_provider_attempt(scope)
    second = root.allocate_provider_attempt(scope)

    assert (first, second) == (1, 2)
    for ordinal in publication_order:
        root.record_provider_attempt_publication(
            scope,
            ordinal,
            relative_path=f"records/attempt-{ordinal:06d}.json",
            file_sha256="sha256:" + f"{ordinal:064x}",
            record_kind="prompt_snapshot",
        )

    events = json.loads(root.state_file.read_bytes())["provider_attempt_allocations"][
        scope.key
    ]["events"]
    assert events == [
        {"ordinal": 1, "event": "allocated"},
        {
            "ordinal": 1,
            "event": "evidence_published",
            "relative_path": "records/attempt-000001.json",
            "file_sha256": "sha256:" + f"{1:064x}",
            "record_kind": "prompt_snapshot",
        },
        {"ordinal": 2, "event": "allocated"},
        {
            "ordinal": 2,
            "event": "evidence_published",
            "relative_path": "records/attempt-000002.json",
            "file_sha256": "sha256:" + f"{2:064x}",
            "record_kind": "prompt_snapshot",
        },
    ]


def test_allocation_failure_before_durable_write_reuses_same_next_ordinal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="before-durable")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    real_persist = root._persist_state_durably
    monkeypatch.setattr(
        root,
        "_persist_state_durably",
        lambda: (_ for _ in ()).throw(OSError("allocation crash")),
    )
    with pytest.raises(OSError, match="allocation crash"):
        root.allocate_provider_attempt(scope)
    monkeypatch.setattr(root, "_persist_state_durably", real_persist)

    assert root.allocate_provider_attempt(scope) == 1


def test_failed_publication_transition_keeps_allocated_gap_and_next_is_larger(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="publication-crash")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    real_persist = root._persist_state_durably
    monkeypatch.setattr(
        root,
        "_persist_state_durably",
        lambda: (_ for _ in ()).throw(OSError("publication crash")),
    )
    with pytest.raises(OSError, match="publication crash"):
        root.record_provider_attempt_publication(
            scope,
            1,
            relative_path="record.json",
            file_sha256="sha256:" + "a" * 64,
            record_kind="failure",
        )
    monkeypatch.setattr(root, "_persist_state_durably", real_persist)

    assert root.allocate_provider_attempt(scope) == 2
    events = json.loads(root.state_file.read_bytes())["provider_attempt_allocations"][
        scope.key
    ]["events"]
    assert events == [
        {"ordinal": 1, "event": "allocated"},
        {"ordinal": 2, "event": "allocated"},
    ]


def test_allocator_never_enumerates_evidence_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="no-enumeration")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    def reject_enumeration(*args, **kwargs):
        raise AssertionError("allocator enumerated evidence")

    monkeypatch.setattr(Path, "iterdir", reject_enumeration)
    monkeypatch.setattr(Path, "glob", reject_enumeration)
    monkeypatch.setattr(Path, "rglob", reject_enumeration)

    assert root.allocate_provider_attempt(scope) == 1
    assert (root.run_root / "workflow_lisp/prompt_dependencies/.aggregate.lock").is_file()


def test_two_level_nested_manager_delegates_one_allocation_to_root(tmp_path: Path) -> None:
    root = StateManager(tmp_path, run_id="nested-allocation")
    root_state = root.initialize(_workflow(tmp_path))
    root_scope = ResumeScopePath.root(root_state.workflow_file)
    first_scope = root_scope.child("first")
    first_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("first")
    first = _actual_nested_manager(
        root,
        "first",
        _nested_state(root.run_id, "first.orc", first_root),
        first_scope,
    )
    second_scope = first_scope.child("second")
    second_root = first.run_root / "call_frames" / _path_safe_frame_scope_token("second")
    second = _actual_nested_manager(
        first,
        "second",
        _nested_state(root.run_id, "second.orc", second_root),
        second_scope,
    )
    second.state.step_visits = {"Provider": 1}
    second.state.current_step = {
        "name": "Provider",
        "step_id": "NestedProvider",
        "visit_count": 1,
    }
    first.state.call_frames["second"] = {
        "call_frame_id": "second",
        "state": second.state.to_dict(),
    }
    root_state.call_frames["first"] = {
        "call_frame_id": "first",
        "state": first.state.to_dict(),
    }
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        {
            "run_id": root.run_id,
            "resume_scope": {
                "root_workflow_file": root_state.workflow_file,
                "call_frame_ids": ["first", "second"],
            },
            "runtime_step_id": "NestedProvider",
            "enclosing_step": {
                "step_name": "Provider",
                "step_id": "NestedProvider",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )

    assert second.allocate_provider_attempt(scope) == 1

    persisted = json.loads(root.state_file.read_bytes())
    assert list(persisted["provider_attempt_allocations"]) == [scope.key]
    assert second.state.provider_attempt_allocations == {}
    assert first.state.provider_attempt_allocations == {}


def test_loop_in_call_scope_uses_leaf_visit_and_iteration(tmp_path: Path) -> None:
    root = StateManager(tmp_path, run_id="loop-call-allocation")
    root_state = root.initialize(_workflow(tmp_path))
    scope_path = ResumeScopePath.root(root_state.workflow_file).child("loop-frame")
    child_root = root.run_root / "call_frames" / _path_safe_frame_scope_token("loop-frame")
    child = _actual_nested_manager(
        root,
        "loop-frame",
        _nested_state(root.run_id, "child.orc", child_root),
        scope_path,
    )
    child.state.step_visits = {"Loop": 2}
    child.state.current_step = {
        "name": "Loop",
        "step_id": "LoopStep",
        "visit_count": 2,
    }
    child.state.for_each["Loop"] = ForEachState(
        items=["a", "b", "c"], current_index=1
    )
    root_state.call_frames["loop-frame"] = {
        "call_frame_id": "loop-frame",
        "state": child.state.to_dict(),
    }
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        {
            "run_id": root.run_id,
            "resume_scope": {
                "root_workflow_file": root_state.workflow_file,
                "call_frame_ids": ["loop-frame"],
            },
            "runtime_step_id": "LoopStep#1.BodyProvider",
            "enclosing_step": {
                "step_name": "Loop",
                "step_id": "LoopStep",
                "visit_count": 2,
            },
            "loop_iteration": {
                "kind": "for_each",
                "loop_step_id": "LoopStep",
                "iteration": 1,
            },
            "adjudication_subject": None,
        }
    )

    assert child.allocate_provider_attempt(scope) == 1


def test_cross_process_allocations_are_unique_and_monotonic(tmp_path: Path) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="process-allocation")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope_payload = _direct_scope_payload(root)
    context = multiprocessing.get_context("fork")
    results = context.Queue()
    processes = [
        context.Process(
            target=_allocate_in_process,
            args=(str(tmp_path), root.run_id, scope_payload, results),
        )
        for _ in range(8)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0
    rows = [results.get(timeout=2) for _ in processes]

    assert all(status == "ok" for status, _ in rows), rows
    assert sorted(value for _, value in rows) == list(range(1, 9))
    persisted = json.loads(root.state_file.read_bytes())
    scope = _attempt_module().ProviderAttemptScope.from_dict(scope_payload)
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 8


@pytest.mark.parametrize("first_operation", ["allocate", "status"])
def test_hook_enabled_processes_preserve_first_allocation_and_ordinary_mutation(
    tmp_path: Path,
    first_operation: str,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id=f"hook-race-{first_operation}")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    first_done = context.Event()
    results = context.Queue()
    allocate = context.Process(
        target=_coordinated_allocate_in_process,
        args=(
            str(tmp_path),
            root.run_id,
            _direct_scope_payload(root),
            barrier,
            first_done,
            first_operation == "allocate",
            results,
        ),
    )
    status = context.Process(
        target=_coordinated_status_in_process,
        args=(
            str(tmp_path),
            root.run_id,
            barrier,
            first_done,
            first_operation == "status",
            results,
        ),
    )

    allocate.start()
    status.start()
    for process in (allocate, status):
        process.join(timeout=15)
        assert process.exitcode == 0
    rows = {results.get(timeout=2) for _ in range(2)}
    assert rows == {("allocated", 1), ("status", "completed")}

    persisted = json.loads(root.state_file.read_bytes())
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert persisted["status"] == "completed"
    assert persisted["provider_attempt_allocations"][scope.key][
        "last_allocated_ordinal"
    ] == 1


def test_cross_process_workers_allocate_and_publish_complete_paired_events(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="process-publication")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope_payload = _direct_scope_payload(root)
    context = multiprocessing.get_context("fork")
    results = context.Queue()
    processes = [
        context.Process(
            target=_allocate_and_publish_in_process,
            args=(str(tmp_path), root.run_id, scope_payload, results),
        )
        for _ in range(8)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=15)
        assert process.exitcode == 0
    rows = [results.get(timeout=2) for _ in processes]

    assert all(status == "ok" for status, _ in rows), rows
    assert sorted(value for _, value in rows) == list(range(1, 9))
    persisted = json.loads(root.state_file.read_bytes())
    scope = _attempt_module().ProviderAttemptScope.from_dict(scope_payload)
    events = persisted["provider_attempt_allocations"][scope.key]["events"]
    for ordinal in range(1, 9):
        allocated = {"ordinal": ordinal, "event": "allocated"}
        publications = [
            event
            for event in events
            if event.get("ordinal") == ordinal
            and event.get("event") == "evidence_published"
        ]
        assert events.count(allocated) == 1
        assert len(publications) == 1
        assert events.index(allocated) < events.index(publications[0])
