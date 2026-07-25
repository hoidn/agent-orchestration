"""Whole-visit resume quarantine for provider peer groups."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
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
            "quarantine",
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
            "quarantine",
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


def test_peer_group_resume_guard_is_sticky_and_does_not_capture_v1_failure() -> None:
    peer_error = {
        "type": "provider_peer_group_interrupted_visit_quarantined",
        "message": "An interrupted provider peer-group visit was quarantined.",
        "context": {
            "step_name": "Peers",
            "step_id": "root.peers",
            "visit_count": 2,
        },
    }
    sticky = ResumePlanner().detect_interrupted_provider_peer_group_visit(
        {"status": "failed", "error": peer_error},
        projection=_peer_group_projection(),
    )
    v1 = ResumePlanner().detect_interrupted_provider_peer_group_visit(
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

    assert sticky == {"kind": "existing_quarantine", "error": peer_error}
    assert v1 is None


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


def test_peer_group_bundle_enables_root_provider_attempt_coordination() -> None:
    group = SimpleNamespace(
        schema_version="provider_peer_group.v1",
        members=(
            SimpleNamespace(
                provider_config=SimpleNamespace(
                    compiler_prompt_dependency_contract=object(),
                )
            ),
            SimpleNamespace(
                provider_config=SimpleNamespace(
                    compiler_prompt_dependency_contract=object(),
                )
            ),
        ),
    )
    bundle = SimpleNamespace(
        ir=SimpleNamespace(
            nodes={
                "peers": SimpleNamespace(
                    execution_config=group,
                )
            }
        ),
        imports={},
    )

    assert (
        provider_attempts.bundle_requires_provider_attempt_coordination(bundle)
        is True
    )


def test_executor_quarantine_retains_partial_peer_visit_and_clears_exact_step(
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

    result = WorkflowExecutor._quarantine_provider_peer_group_resume_guard(
        executor,
        manager.load().to_dict(),
        {
            "kind": "quarantine",
            "step_name": "Peers",
            "step_id": "root.peers",
            "node_id": "root.peers",
            "visit_count": 2,
        },
    )

    persisted = manager.load()
    metadata_path = (
        manager.run_root
        / "provider-peer-group"
        / "root.peers"
        / "visit-metadata"
        / "2.json"
    )
    assert result["status"] == "failed"
    assert persisted.current_step is None
    assert persisted.error == {
        "type": "provider_peer_group_interrupted_visit_quarantined",
        "message": (
            "An interrupted provider peer-group visit was quarantined."
        ),
        "context": {
            "step_name": "Peers",
            "step_id": "root.peers",
            "visit_count": 2,
            "metadata_path": str(metadata_path.resolve()),
            "metadata_synthesized": True,
        },
    }
    assert partial_ledger.read_text(encoding="ascii") == (
        '{"row_kind":"header"}\n'
    )
    assert partial_evidence.read_text(encoding="ascii") == (
        '{"status":"partial"}'
    )
    assert manager.read_runtime_sidecar_json(metadata_path) == {
        "run_id": "interrupted-peer-group",
        "node_id": "root.peers",
        "step_name": "Peers",
        "step_id": "root.peers",
        "visit_count": 2,
        "status": "interrupted",
        "publication_state": "quarantined_interrupted_visit",
        "metadata_synthesized": True,
    }


def test_controller_interruption_quarantines_stickily_and_force_restarts_fresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import (
        coordinator as coordinator_module,
    )

    workflow_path = tmp_path / "peer_group.orc"
    workflow_path.write_text(
        "; typed peer-group lifecycle test\n",
        encoding="utf-8",
    )
    bundle = _peer_group_bundle(workflow_path)
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
    assert "Peers" not in interrupted_state.steps
    assert interrupted_state.current_step == {
        "name": "Peers",
        "index": 0,
        "type": PEER_GROUP_KIND,
        "status": "running",
        "step_id": "root.peers",
        "visit_count": 1,
        "started_at": interrupted_state.current_step["started_at"],
        "last_heartbeat_at": interrupted_state.current_step[
            "last_heartbeat_at"
        ],
    }
    interrupted_visit_root = interrupted_allocation.realized_paths.visit_root
    interrupted_visit_snapshot = _run_tree_snapshot(
        interrupted_visit_root
    )
    interrupted_attempt_allocations = deepcopy(
        interrupted_state.provider_attempt_allocations
    )
    launched_after_interrupt = 0

    class ForbidPeerLaunchCoordinator:
        def __init__(self, _bindings) -> None:
            nonlocal launched_after_interrupt
            launched_after_interrupt += 1
            raise AssertionError(
                "ordinary resume must not relaunch a quarantined peer group"
            )

    monkeypatch.setattr(
        coordinator_module,
        "ProviderPeerGroupCoordinator",
        ForbidPeerLaunchCoordinator,
    )
    monkeypatch.chdir(tmp_path)
    with patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ):
        assert (
            resume_workflow(
                run_id=interrupted_run_id,
                force_restart=False,
            )
            == 1
        )

    quarantined = manager.load()
    assert quarantined.status == "failed"
    assert quarantined.current_step is None
    assert quarantined.error is not None
    assert quarantined.error["type"] == (
        "provider_peer_group_interrupted_visit_quarantined"
    )
    assert launched_after_interrupt == 0
    assert _run_tree_snapshot(interrupted_visit_root) == (
        interrupted_visit_snapshot
    )
    assert quarantined.provider_attempt_allocations == (
        interrupted_attempt_allocations
    )
    quarantined_run_snapshot = _run_tree_snapshot(manager.run_root)
    quarantined_semantics = quarantined.to_dict()

    with patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ):
        assert (
            resume_workflow(
                run_id=interrupted_run_id,
                force_restart=False,
            )
            == 1
        )

    assert launched_after_interrupt == 0
    assert _run_tree_snapshot(manager.run_root) == quarantined_run_snapshot
    assert manager.load().to_dict() == quarantined_semantics

    from tests.test_workflow_lisp_provider_peer_group_e2e import (
        _install_controlled_public_adapters,
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
    real_executor = WorkflowExecutor

    def fresh_executor(**kwargs):
        created = real_executor(
            **kwargs,
            provider_observation_enabled=False,
            step_heartbeat_interval_sec=0,
        )
        _register_peer_test_providers(created)
        return created

    fresh_run_id = "force-restarted-peer-group-lifecycle"
    with patch(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        return_value=bundle,
    ), patch(
        "orchestrator.cli.commands.resume.WorkflowExecutor",
        side_effect=fresh_executor,
    ), patch(
        "uuid.uuid4",
        return_value=SimpleNamespace(hex=fresh_run_id),
    ):
        assert (
            resume_workflow(
                run_id=interrupted_run_id,
                force_restart=True,
            )
            == 0
        )

    fresh_manager = StateManager(tmp_path, run_id=fresh_run_id)
    fresh_state = fresh_manager.load()
    assert fresh_state.status == "completed"
    assert fresh_state.steps["Peers"]["status"] == "completed"
    assert fresh_state.steps["Peers"]["artifacts"] == {
        "__result__": "planner"
    }
    terminal_evidence_path = (
        fresh_manager.run_root
        / fresh_state.steps["Peers"]["debug"]["provider_peer_group"][
            "terminal_evidence_path"
        ]
    )
    assert terminal_evidence_path.is_file()
    terminal_evidence = json.loads(
        terminal_evidence_path.read_text(encoding="ascii")
    )
    assert terminal_evidence["group_visit"]["run_id"] == fresh_run_id
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
    assert _run_tree_snapshot(manager.run_root) == quarantined_run_snapshot
    assert manager.load().to_dict() == quarantined_semantics
