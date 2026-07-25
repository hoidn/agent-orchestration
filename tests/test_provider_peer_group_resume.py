"""Whole-visit resume quarantine for provider peer groups."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executable_ir import WorkflowRegion
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow import provider_attempts
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.state_projection import (
    CompatibilityNodeProjection,
    CompatibilityStepDefinition,
    WorkflowStateProjection,
)


PEER_GROUP_KIND = "provider_peer_group"


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
