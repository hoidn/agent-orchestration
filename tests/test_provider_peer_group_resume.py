"""Whole-visit resume quarantine for provider peer groups."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import logging
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.providers import (
    InputMode,
    InteractiveSessionSupport,
    ProviderTemplate,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import (
    ProviderPeerGroupStepConfig,
    WorkflowRegion,
)
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow import provider_attempts
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.provider_peer_group.coordinator import (
    ProviderPeerGroupCoordinator,
)
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.state_projection import (
    CompatibilityNodeProjection,
    CompatibilityStepDefinition,
    WorkflowStateProjection,
)
from orchestrator.workflow.surface_ast import WorkflowProvenance
from tests.workflow_bundle_helpers import bundle_context_dict


PEER_GROUP_KIND = "provider_peer_group"


def _run_tree_snapshot(root: Path) -> tuple[tuple[str, str, bytes], ...]:
    entries: list[tuple[str, str, bytes]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append((relative, "directory", b""))
        else:
            entries.append((relative, "file", path.read_bytes()))
    return tuple(entries)


def _peer_group_bundle(workflow_path: Path):
    from tests.test_provider_peer_group_ir import (
        _config,
        _generated_surface,
    )

    provenance = WorkflowProvenance(
        workflow_path=workflow_path,
        source_root=workflow_path.parent,
        frontend_kind="workflow_lisp",
    )
    surface = replace(
        _generated_surface(
            _config(
                node_id="peers",
                member_ids=("planner", "reviewer"),
            )
        ),
        provenance=provenance,
    )
    return build_loaded_workflow_bundle(surface, imports={})


def _register_peer_test_providers(executor: WorkflowExecutor) -> None:
    [node_id] = executor.executable_ir.body_region
    config = executor.executable_ir.nodes[node_id].execution_config
    assert isinstance(config, ProviderPeerGroupStepConfig)
    support = InteractiveSessionSupport(
        schema_version="interactive_terminal_turn_queue.v1",
        turn_boundary_messages=True,
        command=("peer-test-provider", "${PROMPT}"),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )
    for member in config.members:
        executor.provider_registry.register(
            ProviderTemplate(
                name=member.provider_config.provider,
                command=["peer-test-provider", "${PROMPT}"],
                input_mode=InputMode.ARGV,
                interactive_session_support=support,
            )
        )


def _peer_group_projection(
    report_kind: str = PEER_GROUP_KIND,
) -> WorkflowStateProjection:
    entry = CompatibilityNodeProjection(
        node_id="root.peers",
        step_id="root.peers",
        presentation_key="Peers",
        display_name="Peers",
        region=WorkflowRegion.BODY,
        compatibility_index=0,
        step_definition=CompatibilityStepDefinition(
            report_kind=report_kind,
        ),
    )
    return WorkflowStateProjection(
        entries_by_node_id=MappingProxyType({"root.peers": entry}),
        node_id_by_compatibility_index=MappingProxyType({0: "root.peers"}),
        compatibility_index_by_node_id=MappingProxyType({"root.peers": 0}),
        presentation_key_by_node_id=MappingProxyType({"root.peers": "Peers"}),
        node_id_by_step_id=MappingProxyType({"root.peers": "root.peers"}),
    )


def _running_peer_group_state(
    *,
    visit_count: object = 2,
    result: object = None,
) -> dict[str, object]:
    steps = {} if result is None else {"Peers": result}
    return {
        "status": "running",
        "steps": steps,
        "current_step": {
            "name": "Peers",
            "index": 0,
            "type": PEER_GROUP_KIND,
            "status": "running",
            "step_id": "root.peers",
            "visit_count": visit_count,
        },
    }


def test_interrupted_peer_group_visit_requests_fresh_rerun_disposition() -> None:
    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        _running_peer_group_state(),
        projection=_peer_group_projection(),
    )

    assert (guard or {}).get("kind") == "rerun_interrupted_visit"


def test_interrupted_peer_group_at_least_once_does_not_claim_completed_same_visit(
) -> None:
    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        _running_peer_group_state(
            result={
                "status": "completed",
                "step_id": "root.peers",
                "visit_count": 2,
            }
        ),
        projection=_peer_group_projection(),
    )

    assert guard is None


def test_interrupted_peer_group_at_least_once_projection_mismatch_is_integrity_error_before_launch(
) -> None:
    state = _running_peer_group_state()
    current_step = state["current_step"]
    assert isinstance(current_step, dict)
    current_step["type"] = "provider_supervision"

    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        state,
        projection=_peer_group_projection(),
    )

    assert (guard or {}).get("kind") == "integrity_error"


@pytest.mark.parametrize(
    ("persisted_result", "expected_kind"),
    [
        (
            {
                "status": "completed",
                "step_id": "root.peers",
                "visit_count": 1,
                "output": "older visit",
            },
            "rerun_interrupted_visit",
        ),
        (
            {
                "status": "completed",
                "step_id": "root.peers",
                "visit_count": 2,
                "output": "exact current visit",
            },
            None,
        ),
        (
            {
                "status": "completed",
                "step_id": "root.other",
                "visit_count": 2,
                "output": "different terminal identity",
            },
            "integrity_error",
        ),
        (
            {
                "status": "failed",
                "step_id": "root.peers",
                "visit_count": 2,
                "error": {"type": "terminal_group_failure"},
            },
            None,
        ),
    ],
)
def test_peer_group_resume_guard_requires_exact_visit_terminal_result(
    persisted_result: dict[str, object],
    expected_kind: str | None,
) -> None:
    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        _running_peer_group_state(result=persisted_result),
        projection=_peer_group_projection(),
    )

    assert (guard or {}).get("kind") == expected_kind


@pytest.mark.parametrize("visit_count", [True, 1.0, 0, -1])
def test_peer_group_resume_guard_rejects_invalid_current_visit(
    visit_count: object,
) -> None:
    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        _running_peer_group_state(visit_count=visit_count),
        projection=_peer_group_projection(),
    )

    assert (guard or {}).get("kind") == "integrity_error"


@pytest.mark.parametrize(
    ("current_kind", "projected_kind"),
    [
        (PEER_GROUP_KIND, "provider_supervision"),
        ("provider_supervision", PEER_GROUP_KIND),
    ],
)
def test_peer_group_resume_guard_requires_exact_projected_node_type(
    current_kind: str,
    projected_kind: str,
) -> None:
    state = _running_peer_group_state()
    current_step = state["current_step"]
    assert isinstance(current_step, dict)
    current_step["type"] = current_kind

    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        state,
        projection=_peer_group_projection(projected_kind),
    )

    assert (guard or {}).get("kind") == "integrity_error"


def test_peer_group_resume_guard_rejects_missing_projection_entry() -> None:
    state = _running_peer_group_state()
    current_step = state["current_step"]
    assert isinstance(current_step, dict)
    current_step.update(
        {
            "name": "Missing Peers",
            "index": 1,
            "step_id": "root.missing-peers",
        }
    )

    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        state,
        projection=_peer_group_projection(),
    )

    assert (guard or {}).get("kind") == "integrity_error"


def test_peer_group_resume_guard_does_not_capture_supervision_cursor() -> None:
    guard = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        {
            "status": "running",
            "steps": {},
            "current_step": {
                "name": "Peers",
                "index": 0,
                "type": "provider_supervision",
                "status": "running",
                "step_id": "root.peers",
                "visit_count": 2,
            },
        },
        projection=_peer_group_projection("provider_supervision"),
    )

    assert guard is None


def _attempt_scope(
    *,
    run_id: str,
    visit_count: int,
) -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": run_id,
            "resume_scope": {
                "root_workflow_file": "workflow.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "root.peers",
            "enclosing_step": {
                "step_name": "Peers",
                "step_id": "root.peers",
                "visit_count": visit_count,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def test_peer_group_force_restart_derives_wholly_new_member_attempt_identities() -> None:
    interrupted = _attempt_scope(run_id="interrupted-run", visit_count=2)
    restarted = _attempt_scope(run_id="force-restarted-run", visit_count=1)

    identities = (
        provider_attempts.derive_provider_peer_group_member_scope(
            interrupted,
            member_id="planner",
        ),
        provider_attempts.derive_provider_peer_group_member_scope(
            interrupted,
            member_id="reviewer",
        ),
        provider_attempts.derive_provider_peer_group_member_scope(
            restarted,
            member_id="planner",
        ),
        provider_attempts.derive_provider_peer_group_member_scope(
            restarted,
            member_id="reviewer",
        ),
    )

    assert len({scope.key for scope in identities}) == len(identities)
    assert len({scope.runtime_step_id for scope in identities[:2]}) == 2
    assert identities[0].enclosing_step.visit_count == 2
    assert identities[2].enclosing_step.visit_count == 1


def test_peer_group_member_scope_cannot_retarget_an_existing_member_attempt() -> None:
    base = _attempt_scope(run_id="run", visit_count=1)
    member = provider_attempts.derive_provider_peer_group_member_scope(
        base,
        member_id="planner",
    )

    with pytest.raises(ValueError, match="already qualified"):
        provider_attempts.derive_provider_peer_group_member_scope(
            member,
            member_id="reviewer",
        )


def test_executor_recovery_retains_partial_peer_visit_and_clears_exact_step(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; interrupted peer group\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="interrupted-peer-group")
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Peers": 2})
    manager.start_step(
        "Peers",
        0,
        PEER_GROUP_KIND,
        step_id="root.peers",
        visit_count=2,
    )
    visit_root = (
        manager.run_root
        / "provider-peer-group"
        / "root.peers"
        / "visits"
        / "2"
    )
    partial_ledger = (
        visit_root
        / "members"
        / "planner"
        / "attempt-1"
        / "injected-messages.jsonl"
    )
    partial_evidence = (
        visit_root
        / "members"
        / "planner"
        / "attempt-1"
        / "evidence.json"
    )
    partial_ledger.parent.mkdir(parents=True)
    partial_ledger.write_text('{"row_kind":"header"}\n', encoding="ascii")
    partial_evidence.write_text('{"status":"partial"}', encoding="ascii")
    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = manager

    result = WorkflowExecutor._recover_interrupted_provider_resume_guard(
        executor,
        manager.load().to_dict(),
        {
            "kind": "rerun_interrupted_visit",
            "step_name": "Peers",
            "step_id": "root.peers",
            "node_id": "root.peers",
            "visit_count": 2,
        },
        family="peer_group",
    )

    persisted = manager.load()
    metadata_path = (
        manager.run_root
        / "provider-peer-group"
        / "root.peers"
        / "visit-metadata"
        / "2.json"
    )
    assert result is None
    assert persisted.status == "running"
    assert persisted.current_step is None
    assert persisted.error is None
    assert partial_ledger.read_text(encoding="ascii") == (
        '{"row_kind":"header"}\n'
    )
    assert partial_evidence.read_text(encoding="ascii") == (
        '{"status":"partial"}'
    )
    assert manager.read_runtime_sidecar_json(metadata_path) is None


def test_interrupted_peer_group_visit_reruns_fresh_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from orchestrator.workflow.provider_peer_group import (
        coordinator as coordinator_module,
    )
    from orchestrator.workflow.provider_peer_group.bindings import (
        WorkflowProviderPeerGroupBindings,
    )
    from orchestrator.workflow.provider_peer_group.ledger import (
        PeerMessageLedger,
    )
    from tests.test_workflow_lisp_provider_peer_group_e2e import (
        _compile_peer_group,
        _install_controlled_public_adapters,
        _public_two_member_source,
    )

    compiled = _compile_peer_group(
        tmp_path,
        source=_public_two_member_source(),
        validate_shared=True,
        member_ids=("planner", "reviewer"),
    )
    bundle = compiled.validated_bundles["orchestrate"]
    workflow_path = tmp_path / "provider_peer_group.orc"
    interrupted_run_id = "interrupted-peer-group-lifecycle"
    manager = StateManager(tmp_path, run_id=interrupted_run_id)
    manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
    )
    interrupted_allocations = []

    class InterruptAfterAllocationCoordinator:
        def __init__(self, bindings) -> None:
            self.bindings = bindings

        def run(self):
            interrupted_allocations.append(
                self.bindings.allocate_group()
            )
            raise KeyboardInterrupt

    monkeypatch.setattr(
        coordinator_module,
        "ProviderPeerGroupCoordinator",
        InterruptAfterAllocationCoordinator,
    )
    executor = WorkflowExecutor(
        workflow=bundle,
        workspace=tmp_path,
        state_manager=manager,
        provider_observation_enabled=False,
        step_heartbeat_interval_sec=0,
    )
    _register_peer_test_providers(executor)

    with pytest.raises(KeyboardInterrupt):
        executor.execute()

    [interrupted_allocation] = interrupted_allocations
    interrupted_state = manager.load()
    assert interrupted_state.current_step is not None
    step_name = interrupted_state.current_step["name"]
    step_id = interrupted_state.current_step["step_id"]
    assert step_name not in interrupted_state.steps
    assert interrupted_state.current_step == {
        "name": step_name,
        "index": 0,
        "type": PEER_GROUP_KIND,
        "status": "running",
        "step_id": step_id,
        "visit_count": 1,
        "started_at": interrupted_state.current_step["started_at"],
        "last_heartbeat_at": interrupted_state.current_step[
            "last_heartbeat_at"
        ],
    }
    interrupted_visit_root = interrupted_allocation.realized_paths.visit_root
    interrupted_planner, interrupted_reviewer = (
        interrupted_allocation.members
    )
    partial_ledger = PeerMessageLedger.create(
        interrupted_reviewer.realized_paths.injected_messages_path,
        group_visit=interrupted_allocation.runtime.visit,
        receiver_attempt=interrupted_reviewer.runtime.attempt,
    )
    partial_ledger.append_recorded(
        coordinator_sequence=1,
        request_id="discarded-request",
        message_id="discarded-message",
        sender_attempt=interrupted_planner.runtime.attempt,
        content="immutable partial message",
    )
    partial_ledger.finalize()
    interrupted_reviewer.realized_paths.provisional_bundle_path.write_bytes(
        b'"discarded provisional result"'
    )
    interrupted_reviewer.realized_paths.evidence_path.write_bytes(
        b'{"status":"partial"}'
    )
    interrupted_visit_snapshot = _run_tree_snapshot(
        interrupted_visit_root
    )
    interrupted_attempt_allocations = deepcopy(
        interrupted_state.provider_attempt_allocations
    )
    controlled = _install_controlled_public_adapters(
        monkeypatch,
        member_ids=("planner", "reviewer"),
        values={
            "planner": "planner",
            "reviewer": "reviewer",
        },
    )
    monkeypatch.setattr(
        coordinator_module,
        "ProviderPeerGroupCoordinator",
        ProviderPeerGroupCoordinator,
    )
    fresh_allocations = []
    original_allocate_group = (
        WorkflowProviderPeerGroupBindings.allocate_group
    )

    def capture_fresh_allocation(self):
        allocation = original_allocate_group(self)
        fresh_allocations.append(allocation)
        return allocation

    monkeypatch.setattr(
        WorkflowProviderPeerGroupBindings,
        "allocate_group",
        capture_fresh_allocation,
    )
    record_before_offer: list[tuple[str, list[str]]] = []
    original_create_adapter = (
        WorkflowProviderPeerGroupBindings.create_adapter
    )

    def create_adapter_with_ledger_probe(self, member):
        adapter = original_create_adapter(self, member)
        original_offer = adapter.offer

        def offer_after_record(
            handle,
            literal_message,
            *,
            deadline,
        ):
            rows = [
                json.loads(line)
                for line in (
                    member.realized_paths.injected_messages_path
                ).read_text(encoding="ascii").splitlines()
            ]
            row_kinds = [row["row_kind"] for row in rows]
            assert row_kinds == ["header", "recorded"]
            record_before_offer.append(
                (member.runtime.attempt.member_id, row_kinds)
            )
            return original_offer(
                handle,
                literal_message,
                deadline=deadline,
            )

        adapter.offer = offer_after_record
        return adapter

    monkeypatch.setattr(
        WorkflowProviderPeerGroupBindings,
        "create_adapter",
        create_adapter_with_ledger_probe,
    )
    real_executor = WorkflowExecutor

    def resumed_executor(**kwargs):
        created = real_executor(
            **kwargs,
            provider_observation_enabled=False,
            step_heartbeat_interval_sec=0,
        )
        _register_peer_test_providers(created)
        return created

    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.WARNING), patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ), patch(
        "orchestrator.cli.commands.resume.WorkflowExecutor",
        side_effect=resumed_executor,
    ):
        assert (
            resume_workflow(
                run_id=interrupted_run_id,
                force_restart=False,
            )
            == 0
        )

    fresh_state = manager.load()
    assert fresh_state.status == "completed"
    assert fresh_state.steps[step_name]["status"] == "completed"
    assert fresh_state.steps[step_name]["visit_count"] == 2
    assert fresh_state.steps[step_name]["artifacts"] == {
        "__result__": "reviewer"
    }
    [fresh_allocation] = fresh_allocations
    assert fresh_allocation.runtime.visit.run_id == interrupted_run_id
    assert fresh_allocation.runtime.visit.visit_count == 2
    assert fresh_allocation.runtime.visit != (
        interrupted_allocation.runtime.visit
    )
    assert fresh_allocation.endpoint.endpoint_instance_id != (
        interrupted_allocation.endpoint.endpoint_instance_id
    )
    assert fresh_allocation.endpoint_socket_path != (
        interrupted_allocation.endpoint_socket_path
    )
    assert {
        member.runtime.attempt.attempt_scope_key
        for member in fresh_allocation.members
    }.isdisjoint(
        {
            member.runtime.attempt.attempt_scope_key
            for member in interrupted_allocation.members
        }
    )
    assert {
        member.invocation.invocation_id
        for member in fresh_allocation.members
    }.isdisjoint(
        {
            member.invocation.invocation_id
            for member in interrupted_allocation.members
        }
    )
    assert set(fresh_allocation.realized_paths.leaf_paths()).isdisjoint(
        interrupted_allocation.realized_paths.leaf_paths()
    )
    assert _run_tree_snapshot(interrupted_visit_root) == (
        interrupted_visit_snapshot
    )
    assert record_before_offer == [
        ("reviewer", ["header", "recorded"])
    ]
    for scope_key, allocation in interrupted_attempt_allocations.items():
        assert (
            fresh_state.provider_attempt_allocations[scope_key]
            == allocation
        )
    terminal_evidence_path = (
        manager.run_root
        / fresh_state.steps[step_name]["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    assert terminal_evidence_path.is_file()
    terminal_evidence = json.loads(
        terminal_evidence_path.read_text(encoding="ascii")
    )
    assert terminal_evidence["group_visit"]["run_id"] == interrupted_run_id
    assert terminal_evidence["group_visit"] != (
        interrupted_allocation.runtime.visit.to_dict()
    )
    assert {
        member["attempt"]["attempt_scope_key"]
        for member in terminal_evidence["members"]
    }.isdisjoint(
        {
            member.runtime.attempt.attempt_scope_key
            for member in interrupted_allocation.members
        }
    )
    assert set(controlled.adapters) == {"planner", "reviewer"}
    assert all(
        adapter.error is None and adapter.joined
        for adapter in controlled.adapters.values()
    )
    rerun_records = [
        record
        for record in caplog.records
        if getattr(record, "orchestrator_diagnostic", None)
        == "provider_attempt_interrupted_rerun"
    ]
    assert len(rerun_records) == 1
    assert rerun_records[0].provider_family == "peer_group"
    assert rerun_records[0].provider_step_id == step_id
    assert rerun_records[0].discarded_visit == 1
    assert rerun_records[0].next_visit == 2
