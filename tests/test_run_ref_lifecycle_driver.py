from __future__ import annotations

from dataclasses import replace
from threading import Event, Thread
import shutil

import pytest

import orchestrator.workflow.run_ref.ledger as ledger_module
import orchestrator.workflow.run_ref.runtime as runtime_module
from orchestrator.workflow.run_ref.ledger import (
    RunRefAttemptBindings,
    load_attempt_ledger,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.runtime import (
    RunRefLifecycleAcknowledgement,
    RunRefLifecycleDeadlineExceeded,
    acknowledge_persisted_run_ref_lifecycle_event,
    drive_run_ref_lifecycle,
    select_run_ref_lifecycle_allocation,
)
from tests.test_workflow_run_ref_runtime import (
    _RuntimeHarness,
    _runtime_request,
)


def _caller_acknowledge(request, event):
    payload = event.payload
    path = event.effect_instance_root / "run-ref-attempts.jsonl"
    if event.stage == "allocated":
        row = ledger_module.allocate_attempt(
            path,
            visit=request.visit,
            bindings=RunRefAttemptBindings(**payload["bindings"]),
        )
    else:
        row = ledger_module.advance_attempt(
            path,
            visit=request.visit,
            attempt_ordinal=event.attempt_ordinal,
            stage=event.stage,
            binding_updates=payload["binding_updates"],
        )
    durable = ledger_module.load_attempt_ledger(path).rows[-1]
    assert durable.row_digest == row.row_digest
    return RunRefLifecycleAcknowledgement._for_durable_row(
        event,
        authority=durable,
    )


def test_driver_emits_closed_acknowledged_lifecycle_and_never_mutates_ledger(
    tmp_path,
    monkeypatch,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    allocation = select_run_ref_lifecycle_allocation(request)
    observed = []

    monkeypatch.setattr(
        runtime_module,
        "load_attempt_ledger",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("driver read ledger head")
        ),
    )
    monkeypatch.setattr(
        runtime_module,
        "allocate_attempt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("driver called ledger allocator")
        ),
    )
    monkeypatch.setattr(
        runtime_module,
        "advance_attempt",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("driver called ledger mutator")
        ),
    )

    def acknowledge(event):
        assert set(event.record) == {
            "schema_version",
            "sequence",
            "event_kind",
            "stage",
            "visit",
            "attempt_ordinal",
            "effect_instance_root",
            "payload",
            "event_digest",
        }
        observed.append(event)
        return _caller_acknowledge(request, event)

    prepared = drive_run_ref_lifecycle(
        request,
        allocation=allocation,
        dependencies=harness.dependencies(),
        acknowledge=acknowledge,
    )

    assert [event.event_kind for event in observed] == [
        "allocation",
        "progress",
        "progress",
        "progress",
        "progress",
        "progress",
        "progress",
        "prepared",
    ]
    assert [event.stage for event in observed] == [
        "allocated",
        "materialized",
        "setup_completed",
        "program_prepared",
        "launched",
        "child_completed",
        "delta_captured",
        "completed_pending_parent_commit",
    ]
    assert len({event.event_digest for event in observed}) == len(observed)
    assert prepared.settled_result.attempt_ordinal == 1
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == (
        "completed_pending_parent_commit"
    )


def test_driver_waits_for_exact_acknowledgement_before_next_stage(tmp_path) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    allocation = select_run_ref_lifecycle_allocation(request)
    first_seen = Event()
    release = Event()
    stages: list[str] = []
    result = []

    def acknowledge(event):
        stages.append(event.stage)
        acknowledgement = _caller_acknowledge(request, event)
        if event.stage == "launched":
            first_seen.set()
            assert release.wait(2)
        return acknowledgement

    worker = Thread(
        target=lambda: result.append(
            drive_run_ref_lifecycle(
                request,
                allocation=allocation,
                dependencies=harness.dependencies(),
                acknowledge=acknowledge,
            )
        )
    )
    worker.start()
    assert first_seen.wait(2)
    assert stages[-1] == "launched"
    assert harness.launches == []
    release.set()
    worker.join(5)

    assert not worker.is_alive()
    assert result[0].settled_result.attempt_ordinal == 1
    assert stages[-1] == "completed_pending_parent_commit"


def test_driver_rejects_wrong_ack_and_does_not_advance(tmp_path) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    allocation = select_run_ref_lifecycle_allocation(request)
    observed = []

    def acknowledge(event):
        observed.append(event)
        applied = _caller_acknowledge(request, event)
        return replace(
            applied,
            event_digest="sha256:" + "0" * 64,
        )

    with pytest.raises(ValueError, match="acknowledgement"):
        drive_run_ref_lifecycle(
            request,
            allocation=allocation,
            dependencies=harness.dependencies(),
            acknowledge=acknowledge,
        )

    assert [event.stage for event in observed] == ["allocated"]
    assert harness.launches == []
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == "allocated"


def test_deadline_or_kill_mid_child_leaves_launched_attempt_incomplete(
    tmp_path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    allocation = select_run_ref_lifecycle_allocation(request)
    expired = False
    acknowledged = []

    def acknowledge(event):
        nonlocal expired
        acknowledged.append(event)
        applied = _caller_acknowledge(request, event)
        if event.stage == "launched":
            expired = True
        return applied

    with pytest.raises(RunRefLifecycleDeadlineExceeded):
        drive_run_ref_lifecycle(
            request,
            allocation=allocation,
            dependencies=replace(
                harness.dependencies(),
                monotonic_ns=lambda: 11 if expired else 0,
            ),
            acknowledge=acknowledge,
            deadline_monotonic_ns=10,
        )

    assert acknowledged[-1].stage == "launched"
    assert all(event.stage != "child_completed" for event in acknowledged)
    assert harness.launches == []
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == "launched"


def test_deadline_expiring_after_child_start_allows_settlement_and_charges_work(
    tmp_path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    allocation = select_run_ref_lifecycle_allocation(request)
    deadline_crossed = False

    def launch_then_cross_deadline(launch):
        nonlocal deadline_crossed
        result = harness.launch(launch)
        deadline_crossed = True
        return result

    prepared = drive_run_ref_lifecycle(
        request,
        allocation=allocation,
        dependencies=replace(
            harness.dependencies(),
            launch_child=launch_then_cross_deadline,
            monotonic_ns=lambda: 11_000_000 if deadline_crossed else 0,
        ),
        acknowledge=lambda event: _caller_acknowledge(request, event),
        deadline_monotonic_ns=10_000_000,
        started_monotonic_ns=0,
    )

    assert len(harness.launches) == 1
    assert prepared.envelope["accounting"]["terminal_status"] == "completed"
    assert prepared.envelope["accounting"]["elapsed_ms"] == 11
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == (
        "completed_pending_parent_commit"
    )


def test_ordinary_wrapper_preserves_the_existing_synchronous_ledger(tmp_path) -> None:
    from orchestrator.workflow.run_ref.runtime import prepare_run_ref_settlement

    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()

    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )

    assert [row.stage for row in load_attempt_ledger(request.ledger_path).rows] == [
        "allocated",
        "materialized",
        "setup_completed",
        "program_prepared",
        "launched",
        "child_completed",
        "delta_captured",
        "completed_pending_parent_commit",
    ]
    assert prepared.ledger_path == request.ledger_path


@pytest.mark.parametrize("bypass_discard_preflight", (False, True))
def test_ordinary_wrapper_translates_malformed_preflight_ledger_errors(
    tmp_path,
    monkeypatch,
    bypass_discard_preflight,
) -> None:
    from orchestrator.workflow.run_ref.runtime import prepare_run_ref_settlement

    request = _runtime_request(tmp_path)
    request.ledger_path.parent.mkdir(parents=True, exist_ok=True)
    request.ledger_path.write_bytes(b"{not-json}\n")
    harness = _RuntimeHarness()
    if bypass_discard_preflight:
        monkeypatch.setattr(
            runtime_module,
            "_discard_incomplete_attempt",
            lambda *_args, **_kwargs: None,
        )

    with pytest.raises(runtime_module.RunRefRuntimeError) as caught:
        prepare_run_ref_settlement(
            request,
            dependencies=harness.dependencies(),
        )

    assert caught.value.code == "run_ref_ledger_invalid"
    assert harness.launches == []


def test_effect_instance_digest_namespaces_workspace_and_child_identity(
    tmp_path,
) -> None:
    ordinary = _runtime_request(tmp_path)
    ordinary_allocation = select_run_ref_lifecycle_allocation(ordinary)
    first = select_run_ref_lifecycle_allocation(
        ordinary,
        effect_instance_root=(tmp_path / "cell-one-ledger").resolve(),
        effect_instance_digest="sha256:" + "1" * 64,
    )
    second = select_run_ref_lifecycle_allocation(
        ordinary,
        effect_instance_root=(tmp_path / "cell-two-ledger").resolve(),
        effect_instance_digest="sha256:" + "2" * 64,
    )

    assert ordinary_allocation.effect_instance_digest is None
    assert "/effect-instances/" not in ordinary_allocation.bindings.workspace_path.as_posix()
    assert first.bindings.workspace_path != second.bindings.workspace_path
    assert first.bindings.child_run_id != second.bindings.child_run_id
    assert first.bindings.run_ref_root == second.bindings.run_ref_root
    assert first.effect_instance_root != second.effect_instance_root


def test_worker_killed_mid_child_emits_no_synthetic_settlement(tmp_path) -> None:
    request = _runtime_request(tmp_path)
    allocation = select_run_ref_lifecycle_allocation(request)
    harness = _RuntimeHarness()
    child_started = Event()
    release_child = Event()
    failure: list[BaseException] = []

    def killed(_launch):
        child_started.set()
        assert release_child.wait(2)
        raise OSError("worker killed")

    def run() -> None:
        try:
            drive_run_ref_lifecycle(
                request,
                allocation=allocation,
                dependencies=replace(harness.dependencies(), launch_child=killed),
                acknowledge=lambda event: _caller_acknowledge(request, event),
            )
        except BaseException as exc:  # fixture captures the worker boundary
            failure.append(exc)

    worker = Thread(target=run)
    worker.start()
    assert child_started.wait(2)
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == "launched"
    release_child.set()
    worker.join(5)

    assert not worker.is_alive()
    assert len(failure) == 1
    assert "run_ref_child_launch_failed" in str(failure[0])
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == "launched"
    assert all(
        row.stage not in {"child_completed", "completed_pending_parent_commit"}
        for row in load_attempt_ledger(request.ledger_path).rows
    )


@pytest.mark.parametrize(
    ("stage", "payload"),
    (
        ("materialized", {"binding_updates": {}}),
        (
            "launched",
            {
                "binding_updates": {
                    "child_launch_digest": "sha256:" + "1" * 64,
                    "extra": "sha256:" + "2" * 64,
                }
            },
        ),
    ),
)
def test_lifecycle_event_payload_is_closed_per_stage(
    tmp_path,
    stage,
    payload,
) -> None:
    request = _runtime_request(tmp_path)
    allocation = select_run_ref_lifecycle_allocation(request)

    with pytest.raises(ValueError, match="closed"):
        runtime_module.RunRefLifecycleEvent.build(
            sequence=2,
            event_kind="progress",
            stage=stage,
            visit=request.visit,
            attempt_ordinal=allocation.attempt_ordinal,
            effect_instance_root=allocation.effect_instance_root,
            payload=payload,
        )


@pytest.mark.parametrize(
    "field",
    (
        "result_envelope_digest",
        "artifact_projection_digest",
        "evidence_manifest_digest",
    ),
)
def test_prepared_lifecycle_event_requires_canonical_digest_values(
    tmp_path,
    field,
) -> None:
    request = _runtime_request(tmp_path)
    allocation = select_run_ref_lifecycle_allocation(request)
    payload = {
        "binding_updates": {},
        "result_envelope_digest": "sha256:" + "1" * 64,
        "artifact_projection_digest": "sha256:" + "2" * 64,
        "evidence_manifest_digest": "sha256:" + "3" * 64,
    }
    payload[field] = "not-a-digest"

    with pytest.raises(ValueError, match="digest"):
        runtime_module.RunRefLifecycleEvent.build(
            sequence=8,
            event_kind="prepared",
            stage="completed_pending_parent_commit",
            visit=request.visit,
            attempt_ordinal=allocation.attempt_ordinal,
            effect_instance_root=allocation.effect_instance_root,
            payload=payload,
        )


def test_acknowledgement_rejects_non_durable_or_superseded_row(tmp_path) -> None:
    request = _runtime_request(tmp_path)
    allocation = select_run_ref_lifecycle_allocation(request)
    event = runtime_module.RunRefLifecycleEvent.build(
        sequence=1,
        event_kind="allocation",
        stage="allocated",
        visit=request.visit,
        attempt_ordinal=1,
        effect_instance_root=allocation.effect_instance_root,
        payload={"bindings": allocation.bindings.record},
    )

    with pytest.raises(ValueError, match="durable"):
        acknowledge_persisted_run_ref_lifecycle_event(
            event,
            expected_row_digest="sha256:" + "0" * 64,
        )

    applied = ledger_module.allocate_attempt(
        allocation.ledger_path,
        visit=request.visit,
        bindings=allocation.bindings,
    )
    ledger_module.advance_attempt(
        allocation.ledger_path,
        visit=request.visit,
        attempt_ordinal=1,
        stage="materialized",
        binding_updates={"verified_git_tree_id": "git-tree:" + "a" * 40},
    )
    with pytest.raises(ValueError, match="head"):
        acknowledge_persisted_run_ref_lifecycle_event(
            event,
            expected_row_digest=applied.row_digest,
        )


def test_synchronous_wrapper_matches_direct_adapter_bytes_and_settlement(
    tmp_path,
    monkeypatch,
) -> None:
    from orchestrator.workflow.run_ref.runtime import prepare_run_ref_settlement

    request = _runtime_request(tmp_path)
    frozen_timestamp = "2026-08-02T12:00:00.000000Z"
    monkeypatch.setattr(ledger_module, "_utc_timestamp", lambda: frozen_timestamp)

    direct_harness = _RuntimeHarness()
    direct_clock = iter((100, 110))
    allocation = select_run_ref_lifecycle_allocation(request)
    direct = drive_run_ref_lifecycle(
        request,
        allocation=allocation,
        dependencies=replace(
            direct_harness.dependencies(),
            monotonic_ns=lambda: next(direct_clock),
        ),
        acknowledge=lambda event: _caller_acknowledge(request, event),
    )
    direct_ledger = request.ledger_path.read_bytes()
    direct_documents = {
        path.name: path.read_bytes()
        for path in sorted(direct.evidence_manifest_path.parent.iterdir())
        if path.is_file()
    }
    direct_envelope = canonical_json_bytes(dict(direct.envelope))
    direct_artifacts = canonical_json_bytes(dict(direct.artifacts))
    direct_settlement = canonical_json_bytes(direct.settled_result.record)

    request.ledger_path.unlink()
    shutil.rmtree(request.run_ref_root)

    wrapper_harness = _RuntimeHarness()
    wrapper_clock = iter((100, 110))
    wrapped = prepare_run_ref_settlement(
        request,
        dependencies=replace(
            wrapper_harness.dependencies(),
            monotonic_ns=lambda: next(wrapper_clock),
        ),
    )

    assert request.ledger_path.read_bytes() == direct_ledger
    assert {
        path.name: path.read_bytes()
        for path in sorted(wrapped.evidence_manifest_path.parent.iterdir())
        if path.is_file()
    } == direct_documents
    assert canonical_json_bytes(dict(wrapped.envelope)) == direct_envelope
    assert canonical_json_bytes(dict(wrapped.artifacts)) == direct_artifacts
    assert canonical_json_bytes(wrapped.settled_result.record) == direct_settlement
