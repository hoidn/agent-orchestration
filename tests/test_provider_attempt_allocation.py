"""Functional durability and allocation tests for provider attempt identity."""

from __future__ import annotations

import json
import importlib
import hashlib
import os
from pathlib import Path
import stat

import pytest

import orchestrator._common.io_atomic as io_atomic
from orchestrator.state import ForEachState, RunState, StateManager
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


def _allocation_entry(
    scope,
    *,
    prompt_fragment_identity_schema_version: object = ...,
) -> dict:
    entry = {
        "scope": scope.to_dict(),
        "last_allocated_ordinal": 1,
    }
    if prompt_fragment_identity_schema_version is not ...:
        entry["prompt_fragment_identity_schema_version"] = (
            prompt_fragment_identity_schema_version
        )
    return entry


def test_pre_q3_allocator_entry_round_trips_without_prompt_schema_authority(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="legacy-authority-roundtrip")
    scope = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    allocations = {scope.key: _allocation_entry(scope)}

    assert attempts.validate_provider_attempt_allocations(allocations) == allocations
    assert "prompt_fragment_identity_schema_version" not in allocations[scope.key]


@pytest.mark.parametrize(
    "schema_version",
    (
        "compiled_prompt_fragment_identity.v1",
        "compiled_prompt_fragment_identity.v2",
    ),
)
def test_allocator_entry_accepts_exact_scope_bound_prompt_schema_authority(
    tmp_path: Path,
    schema_version: str,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id=f"authority-{schema_version[-2:]}")
    scope = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    allocations = {
        scope.key: _allocation_entry(
            scope,
            prompt_fragment_identity_schema_version=schema_version,
        )
    }

    assert attempts.validate_provider_attempt_allocations(allocations) == allocations


@pytest.mark.parametrize(
    "schema_version",
    (None, True, "", "compiled_prompt_fragment_identity.v3"),
)
def test_allocator_entry_rejects_malformed_prompt_schema_authority(
    tmp_path: Path,
    schema_version: object,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="malformed-authority")
    scope = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    with pytest.raises(ValueError, match="provider attempt allocation entry|schema"):
        attempts.validate_provider_attempt_allocations(
            {
                scope.key: _allocation_entry(
                    scope,
                    prompt_fragment_identity_schema_version=schema_version,
                )
            }
        )


def test_allocator_entry_rejects_unknown_member_with_prompt_schema_authority(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="open-authority-entry")
    scope = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    entry = _allocation_entry(
        scope,
        prompt_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )
    entry["extra"] = None

    with pytest.raises(ValueError, match="closed object"):
        attempts.validate_provider_attempt_allocations({scope.key: entry})


def test_prompt_schema_authority_cannot_be_misbound_to_another_scope_key(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="misbound-authority")
    scope = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    entry = _allocation_entry(
        scope,
        prompt_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v2"
        ),
    )

    with pytest.raises(ValueError, match="key contradicts scope"):
        attempts.validate_provider_attempt_allocations(
            {"sha256:" + "0" * 64: entry}
        )

    changed = json.loads(json.dumps(entry))
    changed["scope"]["run_id"] = "different-run"
    with pytest.raises(ValueError, match="key contradicts scope"):
        attempts.validate_provider_attempt_allocations({scope.key: changed})


def test_q3_allocation_persists_scope_authority_in_the_same_state_write(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="q3-atomic-authority")
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )

    assert root.allocate_provider_attempt(
        scope,
        prompt_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v2"
        ),
    ) == 1

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["provider_attempt_allocations"][scope.key] == (
        _allocation_entry(
            scope,
            prompt_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )
    )


def test_allocation_without_prompt_schema_persists_counter_only_entry(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="legacy-entry-bytes")
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )

    assert root.allocate_provider_attempt(scope) == 1

    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["provider_attempt_allocations"][scope.key] == (
        _allocation_entry(scope)
    )


def test_bound_q3_scope_requires_the_same_authority_on_retry(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="q3-same-authority")
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    schema_version = "compiled_prompt_fragment_identity.v2"

    assert root.allocate_provider_attempt(
        scope,
        prompt_fragment_identity_schema_version=schema_version,
    ) == 1
    assert root.allocate_provider_attempt(
        scope,
        prompt_fragment_identity_schema_version=schema_version,
    ) == 2


def test_bound_q3_scope_rejects_conflicting_authority_before_allocating(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="q3-conflicting-authority")
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    assert root.allocate_provider_attempt(
        scope,
        prompt_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v2"
        ),
    ) == 1
    before = root.state_file.read_bytes()

    for conflicting in (
        None,
        "compiled_prompt_fragment_identity.v1",
        "compiled_prompt_fragment_identity.v3",
    ):
        kwargs = (
            {}
            if conflicting is None
            else {
                "prompt_fragment_identity_schema_version": conflicting
            }
        )
        with pytest.raises(ValueError, match="schema|authority"):
            root.allocate_provider_attempt(scope, **kwargs)
        assert root.state_file.read_bytes() == before


def test_legacy_scope_cannot_be_rebound_as_q3(tmp_path: Path) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="legacy-no-upgrade")
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    assert root.allocate_provider_attempt(scope) == 1
    before = root.state_file.read_bytes()

    with pytest.raises(ValueError, match="schema|authority"):
        root.allocate_provider_attempt(
            scope,
            prompt_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )

    assert root.state_file.read_bytes() == before


def test_failed_q3_authority_bind_leaves_ordinary_state_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="q3-bind-write-failure")
    root._write_state()
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    before = root.state_file.read_bytes()
    real_write = root._write_state
    monkeypatch.setattr(
        root,
        "_write_state",
        lambda: (_ for _ in ()).throw(OSError("authority write failed")),
    )

    with pytest.raises(OSError, match="authority write failed"):
        root.allocate_provider_attempt(
            scope,
            prompt_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v2"
            ),
        )

    assert root.state_file.read_bytes() == before
    monkeypatch.setattr(root, "_write_state", real_write)
    assert root.allocate_provider_attempt(
        scope,
        prompt_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v2"
        ),
    ) == 1


def test_prompt_schema_authority_distinguishes_dynamic_loop_scopes(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="q3-loop-authority")
    assert root.state is not None
    root.state.step_visits = {"Loop": 2}
    root.state.current_step = {
        "name": "Loop",
        "step_id": "LoopStep",
        "visit_count": 2,
    }
    root.state.for_each["Loop"] = ForEachState(items=["a", "b"], current_index=0)
    scopes = []
    for iteration, schema_version in enumerate(
        (
            "compiled_prompt_fragment_identity.v1",
            "compiled_prompt_fragment_identity.v2",
        )
    ):
        root.state.for_each["Loop"] = ForEachState(
            items=["a", "b"],
            current_index=iteration,
        )
        payload = _direct_scope_payload(root)
        payload["runtime_step_id"] = f"LoopStep#{iteration}.BodyProvider"
        payload["enclosing_step"] = {
            "step_name": "Loop",
            "step_id": "LoopStep",
            "visit_count": 2,
        }
        payload["loop_iteration"] = {
            "kind": "for_each",
            "loop_step_id": "LoopStep",
            "iteration": iteration,
        }
        scope = attempts.ProviderAttemptScope.from_dict(payload)
        root._write_state()
        assert root.allocate_provider_attempt(
            scope,
            prompt_fragment_identity_schema_version=schema_version,
        ) == 1
        scopes.append(scope)

    persisted = json.loads(root.state_file.read_bytes())[
        "provider_attempt_allocations"
    ]
    assert scopes[0].key != scopes[1].key
    assert persisted[scopes[0].key][
        "prompt_fragment_identity_schema_version"
    ] == "compiled_prompt_fragment_identity.v1"
    assert persisted[scopes[1].key][
        "prompt_fragment_identity_schema_version"
    ] == "compiled_prompt_fragment_identity.v2"


def test_prompt_schema_authority_distinguishes_equal_runtime_ids_in_call_frames(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = StateManager(tmp_path, run_id="q3-call-frame-authority")
    root_state = root.initialize(_workflow(tmp_path))
    children = []
    for frame_id in ("first", "second"):
        scope_path = ResumeScopePath.root(root_state.workflow_file).child(frame_id)
        child_root = (
            root.run_root
            / "call_frames"
            / _path_safe_frame_scope_token(frame_id)
        )
        child = _actual_nested_manager(
            root,
            frame_id,
            _nested_state(root.run_id, f"{frame_id}.orc", child_root),
            scope_path,
        )
        child.state.step_visits = {"Provider": 1}
        child.state.current_step = {
            "name": "Provider",
            "step_id": "NestedProvider",
            "visit_count": 1,
        }
        root_state.call_frames[frame_id] = {
            "call_frame_id": frame_id,
            "state": child.state.to_dict(),
        }
        children.append(child)
    root._write_state()

    scopes = []
    for child, schema_version in zip(
        children,
        (
            "compiled_prompt_fragment_identity.v1",
            "compiled_prompt_fragment_identity.v2",
        ),
        strict=True,
    ):
        scope = attempts.ProviderAttemptScope.from_dict(
            {
                "run_id": root.run_id,
                "resume_scope": {
                    "root_workflow_file": root_state.workflow_file,
                    "call_frame_ids": [child.frame_id],
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
        assert child.allocate_provider_attempt(
            scope,
            prompt_fragment_identity_schema_version=schema_version,
        ) == 1
        scopes.append(scope)

    persisted = json.loads(root.state_file.read_bytes())[
        "provider_attempt_allocations"
    ]
    assert scopes[0].runtime_step_id == scopes[1].runtime_step_id
    assert scopes[0].key != scopes[1].key
    assert children[0].state.provider_attempt_allocations == {}
    assert children[1].state.provider_attempt_allocations == {}
    assert {
        persisted[scope.key]["prompt_fragment_identity_schema_version"]
        for scope in scopes
    } == {
        "compiled_prompt_fragment_identity.v1",
        "compiled_prompt_fragment_identity.v2",
    }


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


def test_state_transaction_exception_rolls_back_memory_and_disk(tmp_path: Path) -> None:
    manager = StateManager(tmp_path, run_id="transaction-rollback")
    manager.initialize(_workflow(tmp_path))

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


def test_single_writer_runtime_transactions_preserve_allocator_and_all_fields(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="external-runtime-fields")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    assert root.allocate_provider_attempt(scope) == 1
    assert root.allocate_provider_attempt(scope) == 2
    provenance = WorkflowProvenance(
        workflow_path=tmp_path / "workflow.orc",
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
        frontend_build_root=Path("build"),
        frontend_source_trace_path=Path("build/source-map.json"),
    )

    with root.state_transaction() as transaction_state:
        transaction_state.observability = {"summary_mode": "on"}
        record_compiled_frontend_provenance(transaction_state, provenance)
        session_id = open_executor_session(
            transaction_state,
            entrypoint="resume",
            pid=12345,
            process_start_time="process-token",
        )
    root.update_bound_inputs({"input": "value"})
    with root.state_transaction() as transaction_state:
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

    monkeypatch.setattr(io_atomic.os, "write", short_write)
    monkeypatch.setattr(io_atomic.os, "fsync", tracking_fsync)
    monkeypatch.setattr(io_atomic.os, "replace", tracking_replace)

    io_atomic.durable_atomic_write(destination, payload)

    assert destination.read_bytes() == payload
    assert len(write_sizes) > 1
    assert sync_kinds == ["file", "directory"]
    assert replaces and replaces[0][1] == destination


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


def test_counter_only_allocation_creates_no_repair_barrier_or_aggregate_lock(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="no-allocation-lock-files")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )

    assert root.allocate_provider_attempt(scope) == 1
    assert not (root.run_root / ".provider-attempt-allocation-started").exists()
    assert not (
        root.run_root
        / "workflow_lisp"
        / "prompt_dependencies"
        / ".aggregate.lock"
    ).exists()


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

    assert repairing.attempt_repair() is False
    assert repairing.state is None
    assert repairing.state_file.read_bytes() == corrupt_primary
    assert backup.read_bytes() == backup_bytes


def test_unaffected_repair_retains_ordinary_backup_copy(
    tmp_path: Path,
) -> None:
    manager = StateManager(tmp_path, run_id="unaffected-repair-writer")
    manager.initialize(_workflow(tmp_path))
    expected = manager.state_file.read_bytes()
    backup = manager.run_root / "state.json.step_valid.bak"
    backup.write_bytes(expected)
    manager.state_file.write_text("invalid json {")
    repairing = StateManager(tmp_path, run_id=manager.run_id)

    assert repairing.attempt_repair() is True
    assert repairing.state_file.read_bytes() == expected
    assert not (repairing.run_root / ".state-mutation.lock").exists()


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


def test_provider_attempt_scope_legacy_six_field_bytes_remain_exact() -> None:
    payload = {
        "run_id": "compat-run",
        "resume_scope": {
            "root_workflow_file": "workflow.orc",
            "call_frame_ids": [],
        },
        "runtime_step_id": "root.Provider",
        "enclosing_step": {
            "step_name": "Provider",
            "step_id": "root.Provider",
            "visit_count": 7,
        },
        "loop_iteration": None,
        "adjudication_subject": None,
    }
    expected = (
        b'{"adjudication_subject":null,"enclosing_step":{"step_id":"root.Provider",'
        b'"step_name":"Provider","visit_count":7},"loop_iteration":null,'
        b'"resume_scope":{"call_frame_ids":[],"root_workflow_file":"workflow.orc"},'
        b'"run_id":"compat-run","runtime_step_id":"root.Provider"}'
    )

    scope = _attempt_module().ProviderAttemptScope.from_dict(payload)

    assert set(scope.to_dict()) == {
        "run_id",
        "resume_scope",
        "runtime_step_id",
        "enclosing_step",
        "loop_iteration",
        "adjudication_subject",
    }
    assert scope.canonical_bytes() == expected
    assert scope.key == (
        "sha256:c8f414f3844ef77aad66c40c60868799ec4d05cd9e9d0a17b1e009ed23867ffb"
    )


def test_provider_attempt_scope_prefix_like_legacy_ids_remain_opaque_and_canonical(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(
        tmp_path,
        run_id="legacy-prefix-like-runtime-step",
    )
    base = attempts.ProviderAttemptScope.from_dict(
        _direct_scope_payload(root)
    )
    qualified = attempts.derive_provider_attempt_member_turn_scope(
        base,
        member_id="worker",
        turn_ordinal=0,
    )
    legacy_runtime_step_ids = (
        "provider_attempt_member_turn.v1:not*base64",
        qualified.runtime_step_id + "=",
    )

    for runtime_step_id in legacy_runtime_step_ids:
        payload = _direct_scope_payload(root)
        payload["runtime_step_id"] = runtime_step_id
        payload["enclosing_step"]["step_id"] = runtime_step_id
        assert root.state is not None
        root.state.current_step["step_id"] = runtime_step_id
        expected = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

        scope = attempts.ProviderAttemptScope.from_dict(payload)
        attempts.validate_provider_attempt_scope(
            scope,
            attempts.resolve_aggregate_run_owner(root),
        )

        assert scope.to_dict() == payload
        assert scope.canonical_bytes() == expected
        assert scope.runtime_step_id == runtime_step_id


def test_provider_attempt_member_turn_scopes_are_distinct_closed_allocations(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="member-turn-distinct")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    base = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    scopes = [
        attempts.derive_provider_attempt_member_turn_scope(
            base,
            member_id="worker/a",
            turn_ordinal=0,
        ),
        attempts.derive_provider_attempt_member_turn_scope(
            base,
            member_id="worker%2Fa",
            turn_ordinal=0,
        ),
        attempts.derive_provider_attempt_member_turn_scope(
            base,
            member_id="worker/a",
            turn_ordinal=1,
        ),
        attempts.derive_provider_attempt_member_turn_scope(
            base,
            member_id="supervisor-\N{GREEK SMALL LETTER ALPHA}",
            turn_ordinal=0,
        ),
    ]

    for scope in scopes:
        attempts.validate_provider_attempt_scope(
            scope,
            attempts.resolve_aggregate_run_owner(root),
        )
        assert set(scope.to_dict()) == set(base.to_dict())
        assert scope.to_dict()["enclosing_step"] == base.to_dict()["enclosing_step"]
        assert root.allocate_provider_attempt(scope) == 1

    assert len({scope.runtime_step_id for scope in scopes}) == len(scopes)
    assert len({scope.canonical_bytes() for scope in scopes}) == len(scopes)
    assert len({scope.key for scope in scopes}) == len(scopes)
    persisted = json.loads(root.state_file.read_bytes())
    assert set(persisted["provider_attempt_allocations"]) == {
        scope.key for scope in scopes
    }
    assert all(
        set(entry["scope"]) == set(base.to_dict())
        for entry in persisted["provider_attempt_allocations"].values()
    )


@pytest.mark.parametrize(
    ("member_id", "turn_ordinal"),
    [
        ("", 0),
        ("worker", -1),
        ("worker", True),
        ("worker", "0"),
    ],
)
def test_provider_attempt_member_turn_scope_rejects_invalid_components(
    tmp_path: Path,
    member_id: object,
    turn_ordinal: object,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="member-turn-invalid")
    base = attempts.ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    with pytest.raises((TypeError, ValueError)):
        attempts.derive_provider_attempt_member_turn_scope(
            base,
            member_id=member_id,
            turn_ordinal=turn_ordinal,
        )


def test_provider_attempt_member_turn_scope_rejects_nested_qualifier(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="member-turn-malformed")
    base_payload = _direct_scope_payload(root)
    base = attempts.ProviderAttemptScope.from_dict(base_payload)
    qualified = attempts.derive_provider_attempt_member_turn_scope(
        base,
        member_id="worker",
        turn_ordinal=0,
    )

    with pytest.raises(ValueError, match="already qualified"):
        attempts.derive_provider_attempt_member_turn_scope(
            qualified,
            member_id="nested",
            turn_ordinal=0,
        )


def test_provider_attempt_member_turn_scope_preserves_loop_validation(
    tmp_path: Path,
) -> None:
    attempts = _attempt_module()
    root = _prepare_direct_scope_root(tmp_path, run_id="member-turn-loop")
    assert root.state is not None
    root.state.step_visits = {"Loop": 2}
    root.state.current_step = {
        "name": "Loop",
        "step_id": "LoopStep",
        "visit_count": 2,
    }
    root.state.for_each["Loop"] = ForEachState(
        items=[0, 1, 2, 3],
        current_index=3,
    )
    payload = _direct_scope_payload(root)
    payload["runtime_step_id"] = "LoopStep#3.NestedProvider"
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
    base = attempts.ProviderAttemptScope.from_dict(payload)
    qualified = attempts.derive_provider_attempt_member_turn_scope(
        base,
        member_id="worker",
        turn_ordinal=0,
    )

    attempts.validate_provider_attempt_scope(
        qualified,
        attempts.resolve_aggregate_run_owner(root),
    )

    wrong_payload = dict(payload)
    wrong_payload["runtime_step_id"] = "LoopStep#2.NestedProvider"
    wrong_base = attempts.ProviderAttemptScope.from_dict(wrong_payload)
    wrong_qualified = attempts.derive_provider_attempt_member_turn_scope(
        wrong_base,
        member_id="worker",
        turn_ordinal=0,
    )
    with pytest.raises(ValueError, match="runtime_step_id"):
        attempts.validate_provider_attempt_scope(
            wrong_qualified,
            attempts.resolve_aggregate_run_owner(root),
        )


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


def test_root_allocator_persists_complete_scope_and_monotonic_counter(
    tmp_path: Path,
) -> None:
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
        }
    }


def test_counter_only_allocation_persists_strictly_increasing_ordinals_without_lifecycle_events(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="counter-only")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    ordinals = [root.allocate_provider_attempt(scope) for _ in range(4)]

    assert ordinals == [1, 2, 3, 4]
    assert all(left < right for left, right in zip(ordinals, ordinals[1:]))
    persisted = json.loads(root.state_file.read_bytes())
    assert persisted["provider_attempt_allocations"] == {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 4,
        }
    }


def test_independent_scope_counters_advance_without_cross_scope_interference(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="independent-scopes")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    first_scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root, candidate="candidate_a")
    )
    second_scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root, candidate="candidate_b")
    )

    first_ordinals = [
        root.allocate_provider_attempt(first_scope),
        root.allocate_provider_attempt(first_scope),
    ]
    second_ordinals = [root.allocate_provider_attempt(second_scope)]
    first_ordinals.append(root.allocate_provider_attempt(first_scope))
    second_ordinals.append(root.allocate_provider_attempt(second_scope))

    assert first_ordinals == [1, 2, 3]
    assert second_ordinals == [1, 2]
    persisted = json.loads(root.state_file.read_bytes())[
        "provider_attempt_allocations"
    ]
    assert persisted == {
        first_scope.key: {
            "scope": first_scope.to_dict(),
            "last_allocated_ordinal": 3,
        },
        second_scope.key: {
            "scope": second_scope.to_dict(),
            "last_allocated_ordinal": 2,
        },
    }


def test_no_ordinal_reuse_after_partial_attempt_consumes_counter(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="partial-attempt")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))

    assert root.allocate_provider_attempt(scope) == 1
    partial_record = (
        root.run_root
        / "workflow_lisp"
        / "prompt_dependencies"
        / "partial"
        / "attempt-000001.json"
    )
    partial_record.parent.mkdir(parents=True)
    partial_record.write_text('{"incomplete":', encoding="utf-8")

    resumed = StateManager(tmp_path, run_id=root.run_id)
    resumed.load()
    assert resumed.allocate_provider_attempt(scope) == 2
    assert partial_record.read_text(encoding="utf-8") == '{"incomplete":'
    persisted = json.loads(resumed.state_file.read_bytes())
    assert persisted["provider_attempt_allocations"] == {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 2,
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
        pytest.param(
            "counter_ahead",
            id="event_counter_disagreement-counter_ahead",
        ),
        pytest.param(
            "events_ahead",
            id="event_counter_disagreement-events_ahead",
        ),
        pytest.param(
            "malformed_legacy_scope",
            id="legacy_allocation_events-malformed_scope",
        ),
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
        entry["events"] = [{"ordinal": 1, "event": "allocated"}]
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
        elif corruption == "counter_ahead":
            entry["last_allocated_ordinal"] = 2
        elif corruption == "events_ahead":
            entry["events"].append({"ordinal": 2, "event": "allocated"})
        elif corruption == "malformed_legacy_scope":
            entry["scope"]["resume_scope"]["call_frame_ids"] = "not-a-list"
    root.state_file.write_text(json.dumps(persisted, indent=2))

    with pytest.raises(ValueError, match="provider attempt allocation"):
        StateManager(tmp_path, run_id=root.run_id).load()


def test_provider_attempt_membership_accepts_only_allocated_scope_and_ordinal(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="attempt-membership")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    ordinal = root.allocate_provider_attempt(scope)
    before = root.state_file.read_bytes()

    entry = _attempt_module().validate_provider_attempt_membership(
        root,
        scope,
        ordinal,
    )

    assert entry == {
        "scope": scope.to_dict(),
        "last_allocated_ordinal": ordinal,
    }
    with pytest.raises(ValueError, match="ordinal is missing"):
        _attempt_module().validate_provider_attempt_membership(
            root,
            scope,
            ordinal + 1,
        )
    assert root.state_file.read_bytes() == before


def test_counter_only_allocation_uses_ordinary_state_writer_and_rolls_back_failed_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="ordinary-write")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    scope = _attempt_module().ProviderAttemptScope.from_dict(_direct_scope_payload(root))
    before = root.state_file.read_bytes()
    real_write = root._write_state

    monkeypatch.setattr(
        root,
        "_write_state",
        lambda: (_ for _ in ()).throw(OSError("ordinary write failed")),
    )
    with pytest.raises(OSError, match="ordinary write failed"):
        root.allocate_provider_attempt(scope)

    assert root.state_file.read_bytes() == before
    monkeypatch.setattr(root, "_write_state", real_write)
    assert root.allocate_provider_attempt(scope) == 1


def test_allocator_uses_no_repair_barrier_or_process_lock_layer(
) -> None:
    import orchestrator.state as state_module
    import orchestrator.workflow.provider_attempts as attempt_module

    obsolete_state_symbols = {
        "PROVIDER_ATTEMPT_REPAIR_BARRIER_NAME",
        "PROVIDER_ATTEMPT_REPAIR_BARRIER_BYTES",
        "enable_durable_state_writes",
        "_persist_state_durably",
        "_ensure_provider_attempt_repair_barrier",
        "_reload_state_for_coordinated_mutation",
        "_allocate_provider_attempt_from",
        "record_provider_attempt_publication",
        "_record_provider_attempt_publication_from",
        "_record_provider_attempt_publication_already_process_locked",
        "_validate_provider_attempt_publication_already_process_locked",
    }
    obsolete_lock_symbols = {
        "exclusive_file_lock",
        "provider_attempt_process_locks",
        "record_only_publication_locks",
    }
    obsolete_coordination_symbols = {
        "bundle_requires_provider_attempt_coordination",
        "enable_provider_attempt_coordination_for_bundle",
    }

    assert not (obsolete_state_symbols & set(vars(state_module.StateManager)))
    assert not (obsolete_lock_symbols & set(vars(io_atomic)))
    assert not (obsolete_coordination_symbols & set(vars(attempt_module)))


def test_legacy_allocation_events_read_then_canonicalize_counter_only(
    tmp_path: Path,
) -> None:
    root = _prepare_direct_scope_root(tmp_path, run_id="legacy-ledger-read")
    root.update_control_flow_counters(1, {"Provider": 1})
    root.start_step("Provider", 0, "provider", "ProviderStep", 1)
    legacy_scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root, candidate="legacy")
    )
    q3_scope = _attempt_module().ProviderAttemptScope.from_dict(
        _direct_scope_payload(root, candidate="q3")
    )
    persisted = json.loads(root.state_file.read_bytes())
    persisted["provider_attempt_allocations"] = {
        legacy_scope.key: {
            "scope": legacy_scope.to_dict(),
            "last_allocated_ordinal": 2,
            "events": [
                {"ordinal": 1, "event": "allocated"},
                {
                    "ordinal": 1,
                    "event": "evidence_published",
                    "relative_path": "records/legacy-attempt-000001.json",
                    "file_sha256": "sha256:" + "a" * 64,
                    "record_kind": "prompt_snapshot",
                },
                {"ordinal": 2, "event": "allocated"},
            ],
        },
        q3_scope.key: {
            "scope": q3_scope.to_dict(),
            "last_allocated_ordinal": 1,
            "events": [
                {"ordinal": 1, "event": "allocated"},
                {
                    "ordinal": 1,
                    "event": "evidence_published",
                    "relative_path": "records/q3-attempt-000001.json",
                    "file_sha256": "sha256:" + "b" * 64,
                    "record_kind": "failure",
                },
            ],
            "prompt_fragment_identity_schema_version": (
                "compiled_prompt_fragment_identity.v2"
            ),
        },
    }
    root.state_file.write_text(json.dumps(persisted, indent=2), encoding="utf-8")

    loaded = StateManager(tmp_path, run_id=root.run_id)
    state = loaded.load()
    normalized_in_memory = json.loads(
        json.dumps(state.provider_attempt_allocations)
    )
    loaded.update_status("completed")
    normalized_on_disk = json.loads(loaded.state_file.read_bytes())[
        "provider_attempt_allocations"
    ]
    expected = {
        legacy_scope.key: {
            "scope": legacy_scope.to_dict(),
            "last_allocated_ordinal": 2,
        },
        q3_scope.key: {
            "scope": q3_scope.to_dict(),
            "last_allocated_ordinal": 1,
            "prompt_fragment_identity_schema_version": (
                "compiled_prompt_fragment_identity.v2"
            ),
        },
    }

    assert normalized_in_memory == expected
    assert normalized_on_disk == expected


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
    assert not (root.run_root / "workflow_lisp/prompt_dependencies").exists()


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
