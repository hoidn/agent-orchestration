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
from orchestrator.state import RunState, StateManager
from tests.historical_state import write_historical_state


def _workflow(workspace: Path) -> str:
    relative = "workflow.yaml"
    (workspace / relative).write_text("version: '1.0'\nname: allocation-test\nsteps: []\n")
    return relative


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
    write_historical_state(root, _workflow(tmp_path))
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


