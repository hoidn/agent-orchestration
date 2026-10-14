"""Whole-visit resume quarantine for provider peer groups."""

from __future__ import annotations


import pytest

from orchestrator.workflow import provider_attempts
from orchestrator.workflow.provider_attempts import ProviderAttemptScope


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
