"""Single-writer runtime tests for the provider-supervision CONTINUE path."""

from __future__ import annotations

from dataclasses import (
    FrozenInstanceError,
)
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.providers.types import InputMode, ProviderInvocation
from tests.historical_state import write_historical_state
from orchestrator.state import StateManager, StepResult
from orchestrator.workflow.provider_supervision.bindings import (
    ProviderSupervisionAttemptBinding,
    ProviderSupervisionMemberRequest,
    ProviderSupervisionObservationBinding,
    ProviderSupervisionObservationInjection,
    ProviderSupervisionTurnBinding,
)
from orchestrator.workflow.provider_supervision.coordinator import (
    ProviderSupervisionCoordinator,
)
from orchestrator.workflow.workspace_files import WorkspaceFiles


_TEST_RESULT_OWNERS: list[WorkspaceFiles] = []


class _Observation:
    def __init__(self, target: str, socket_path: Path) -> None:
        self.target = target
        self.socket_path = socket_path


class _Control:
    def __init__(self) -> None:
        self.future: Any = None

    def attach_execution_future(self, future: Any) -> None:
        assert self.future is None
        self.future = future


class _ContinueBindings:
    """Deterministic host seam whose event log exposes coordinator ordering."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        worker_document: Any = "fresh-value",
        directive_document: Any = None,
        unhealthy_turn: str | None = None,
        allocation_failure_turn: str | None = None,
    ) -> None:
        self.tmp_path = tmp_path
        self.worker_document = worker_document
        self.directive_document = (
            {"variant": "CONTINUE"}
            if directive_document is None
            else directive_document
        )
        self.events: list[tuple[Any, ...]] = []
        self.requests: list[ProviderSupervisionMemberRequest] = []
        self.execution_threads: list[int] = []
        self._event_lock = threading.Lock()
        self._active = 0
        self.max_active = 0
        self.finalize_calls = 0
        self.unhealthy_turn = unhealthy_turn
        self.allocation_failure_turn = allocation_failure_turn

    def assert_current_step(
        self,
        *,
        step_name: str,
        node_id: str,
        visit_count: int,
    ) -> None:
        self.events.append(("current_step", step_name, node_id, visit_count))

    def derive_turn_bindings(
        self,
        *,
        config: Any,
        visit_count: int,
    ) -> dict[str, ProviderSupervisionTurnBinding]:
        self.events.append(("paths_and_metadata", visit_count))
        turns: dict[str, ProviderSupervisionTurnBinding] = {}
        for role, member_id in (
            ("worker_fresh", config.worker.member_id),
            ("supervisor_directive", config.supervisor.member_id),
        ):
            turns[role] = ProviderSupervisionTurnBinding(
                member_id=member_id,
                turn_role=role,
                runtime_step_id=f"{config.node_id}:{role}",
                evidence_path=self.tmp_path / role / "evidence.json",
                provisional_bundle_path=(
                    self.tmp_path / role / "provisional-result.json"
                ),
            )
        return turns

    def open_observation(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderSupervisionObservationBinding:
        self.events.append(("open_pane", turn.turn_role))
        if turn.turn_role == self.allocation_failure_turn:
            raise RuntimeError("pane allocation failed")
        handle = _Observation(
            f"pane:{turn.turn_role}",
            self.tmp_path / "observation.sock",
        )
        return ProviderSupervisionObservationBinding(
            member_id=turn.member_id,
            turn_role=turn.turn_role,
            target=handle.target,
            socket_path=handle.socket_path,
            handle=handle,
        )

    def compose_prompt(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        observation_injection: ProviderSupervisionObservationInjection | None,
    ) -> str:
        observed_target = (
            observation_injection.target
            if observation_injection is not None
            else None
        )
        self.events.append(
            (
                "compose_prompt",
                turn.turn_role,
                (
                    observation_injection.to_dict()
                    if observation_injection is not None
                    else None
                ),
            )
        )
        return f"prompt:{member.member_id}:{observed_target or '-'}"

    def allocate_attempt(
        self,
        *,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderSupervisionAttemptBinding:
        self.events.append(("allocate_attempt_snapshot", turn.turn_role))
        return ProviderSupervisionAttemptBinding(
            scope_key=f"scope:{turn.turn_role}",
            ordinal=1,
            snapshot_key=f"snapshot:{turn.turn_role}:{prompt}",
        )

    def prepare_invocation(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> Any:
        self.events.append(("prepare_invocation", turn.turn_role))
        return ProviderInvocation(
            command=["provider", member.member_id],
            input_mode=InputMode.STDIN,
            prompt=prompt,
            env={
                "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(
                    turn.provisional_bundle_path
                )
            },
            metadata={"turn": {"role": turn.turn_role}},
        )

    def create_control(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> _Control:
        self.events.append(("create_control", turn.turn_role))
        return _Control()

    def execute_member(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        invocation = request.invocation.materialize()
        with self._event_lock:
            self.events.append(("execute_start", request.turn.turn_role))
            self.requests.append(request)
            self.execution_threads.append(threading.get_ident())
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            assert invocation.prompt is not None
        time.sleep(0.04)
        with self._event_lock:
            self._active -= 1
            self.events.append(("execute_end", request.turn.turn_role))
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=40,
        )

    def observation_is_healthy(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> bool:
        self.events.append(("pane_health", observation.turn_role))
        return observation.turn_role != self.unhealthy_turn

    def validate_member_bundle(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> Any:
        self.events.append(("validate_bundle", request.turn.turn_role))
        if request.turn.turn_role == "supervisor_directive":
            return self.directive_document
        return self.worker_document

    def evaluate_settlement(
        self,
        *,
        config: Any,
        resolved_bindings: dict[str, Any],
    ) -> Any:
        self.events.append(("evaluate_settlement",))
        return resolved_bindings[config.worker.member_id]

    def validate_settlement(self, *, config: Any, value: Any) -> Any:
        self.events.append(("validate_settlement",))
        return value

    def finalize_settlement(
        self,
        *,
        config: Any,
        selected_request: ProviderSupervisionMemberRequest,
        directive_request: ProviderSupervisionMemberRequest,
        selected_value: Any,
        directive_value: Any,
        settlement_value: Any,
    ) -> dict[str, Any]:
        self.finalize_calls += 1
        self.events.append(("finalize",))
        return {
            "status": "completed",
            "exit_code": 0,
            "artifacts": {"__result__": settlement_value},
            "selected_attempt": selected_request.attempt.scope_key,
            "directive_attempt": directive_request.attempt.scope_key,
            "directive": directive_value.to_dict(),
        }

    def close_observation(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> None:
        self.events.append(("close_pane", observation.turn_role))

    def failure_result(self, *, code: str, message: str) -> dict[str, Any]:
        self.events.append(("failure", code))
        return {
            "status": "failed",
            "exit_code": 2,
            "error": {"type": code, "message": message},
        }


class _StateManagerContinueBindings(_ContinueBindings):
    def __init__(self, tmp_path: Path, manager: StateManager) -> None:
        super().__init__(tmp_path)
        self.manager = manager

    def assert_current_step(
        self,
        *,
        step_name: str,
        node_id: str,
        visit_count: int,
    ) -> None:
        current = self.manager.load().current_step
        assert current is not None
        assert current["name"] == step_name
        assert current["step_id"] == node_id
        assert current["visit_count"] == visit_count
        super().assert_current_step(
            step_name=step_name,
            node_id=node_id,
            visit_count=visit_count,
        )

    def finalize_settlement(self, **kwargs: Any) -> dict[str, Any]:
        result = super().finalize_settlement(**kwargs)
        self.manager.finalize_step_with_dataflow(
            "Live",
            StepResult(
                status="completed",
                name="Live",
                step_id="root.live",
                exit_code=0,
                duration_ms=0,
                artifacts=result["artifacts"],
                visit_count=1,
            ),
            artifact_versions={},
            artifact_consumes={},
            private_artifact_versions={},
            private_artifact_consumes={},
            expected_step_id="root.live",
            expected_visit_count=1,
        )
        return result


def _config() -> Any:
    return SimpleNamespace(
        node_id="root.live",
        worker=SimpleNamespace(member_id="worker"),
        supervisor=SimpleNamespace(member_id="supervisor"),
    )


def _event_index(
    events: list[tuple[Any, ...]],
    name: str,
    role: str | None = None,
) -> int:
    for index, event in enumerate(events):
        if event[0] == name and (role is None or event[1] == role):
            return index
    raise AssertionError(f"missing event {name!r} for {role!r}: {events!r}")


def test_continue_prepares_both_members_before_concurrent_launch(
    tmp_path: Path,
) -> None:
    host = _ContinueBindings(tmp_path)

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=3,
    )

    assert result["status"] == "completed"
    assert host.max_active == 2
    assert all(thread_id != threading.get_ident() for thread_id in host.execution_threads)
    assert len(host.requests) == 2

    events = host.events
    current = _event_index(events, "current_step")
    paths = _event_index(events, "paths_and_metadata")
    worker_pane = _event_index(events, "open_pane", "worker_fresh")
    supervisor_pane = _event_index(events, "open_pane", "supervisor_directive")
    worker_prompt = _event_index(events, "compose_prompt", "worker_fresh")
    supervisor_prompt = _event_index(
        events, "compose_prompt", "supervisor_directive"
    )
    worker_attempt = _event_index(
        events, "allocate_attempt_snapshot", "worker_fresh"
    )
    supervisor_attempt = _event_index(
        events, "allocate_attempt_snapshot", "supervisor_directive"
    )
    first_execute = min(
        _event_index(events, "execute_start", "worker_fresh"),
        _event_index(events, "execute_start", "supervisor_directive"),
    )
    assert current < paths < worker_pane < supervisor_pane
    assert supervisor_pane < worker_prompt < supervisor_prompt
    assert supervisor_prompt < worker_attempt < supervisor_attempt < first_execute
    assert events[worker_prompt] == ("compose_prompt", "worker_fresh", None)
    assert events[supervisor_prompt] == (
        "compose_prompt",
        "supervisor_directive",
        {
            "schema_version": "provider_supervision_observation_injection.v1",
            "kind": "live_provider_observation_target",
            "observer_member_id": "supervisor",
            "observed_member_id": "worker",
            "socket_path": str(tmp_path / "observation.sock"),
            "target": "pane:worker_fresh",
        },
    )


def test_continue_member_requests_are_frozen_unique_and_state_free(
    tmp_path: Path,
) -> None:
    host = _ContinueBindings(tmp_path)

    ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    worker, supervisor = sorted(
        host.requests,
        key=lambda request: request.turn.turn_role,
    )
    assert worker.turn.runtime_step_id != supervisor.turn.runtime_step_id
    assert worker.turn.evidence_path != supervisor.turn.evidence_path
    assert (
        worker.turn.provisional_bundle_path
        != supervisor.turn.provisional_bundle_path
    )
    assert worker.attempt.scope_key != supervisor.attempt.scope_key
    assert worker.attempt.snapshot_key != supervisor.attempt.snapshot_key
    assert not hasattr(worker, "state_manager")
    assert isinstance(worker.invocation.command, tuple)
    with pytest.raises(TypeError):
        worker.invocation.env["MUTATE"] = "forbidden"
    with pytest.raises(TypeError):
        worker.invocation.metadata["turn"]["role"] = "mutated"
    with pytest.raises(FrozenInstanceError):
        worker.invocation = object()


@pytest.mark.parametrize(
    ("allocation_failure_turn", "unhealthy_turn"),
    [
        ("worker_fresh", None),
        ("supervisor_directive", None),
        (None, "worker_fresh"),
        (None, "supervisor_directive"),
    ],
)
def test_continue_initial_pane_failure_is_load_bearing_before_launch(
    tmp_path: Path,
    allocation_failure_turn: str | None,
    unhealthy_turn: str | None,
) -> None:
    host = _ContinueBindings(
        tmp_path,
        allocation_failure_turn=allocation_failure_turn,
        unhealthy_turn=unhealthy_turn,
    )

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert not any(event[0] == "compose_prompt" for event in host.events)
    assert not any(event[0] == "execute_start" for event in host.events)
    assert host.finalize_calls == 0


def test_continue_pane_loss_after_launch_before_arbitration_fails_group(
    tmp_path: Path,
) -> None:
    host = _ContinueBindings(tmp_path)
    health_checks: dict[str, int] = {}
    check_health = host.observation_is_healthy

    def lose_worker_before_arbitration(
        observation: ProviderSupervisionObservationBinding,
    ) -> bool:
        role = observation.turn_role
        health_checks[role] = health_checks.get(role, 0) + 1
        healthy = check_health(observation)
        if role == "worker_fresh" and health_checks[role] > 1:
            return False
        return healthy

    host.observation_is_healthy = (  # type: ignore[method-assign]
        lose_worker_before_arbitration
    )

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_supervision_observation_lost"
    )
    assert any(event[0] == "execute_start" for event in host.events)
    assert not any(event[0] == "validate_bundle" for event in host.events)
    assert host.finalize_calls == 0


def test_continue_pane_loss_after_valid_directive_is_evidence_only(
    tmp_path: Path,
) -> None:
    host = _ContinueBindings(tmp_path)
    pane_lost = False
    validate_bundle = host.validate_member_bundle
    check_health = host.observation_is_healthy

    def validate_then_lose(
        request: ProviderSupervisionMemberRequest,
    ) -> Any:
        nonlocal pane_lost
        value = validate_bundle(request)
        if request.turn.turn_role == "worker_fresh":
            pane_lost = True
            host.events.append(("pane_lost_after_directive",))
        return value

    def reflect_late_loss(
        observation: ProviderSupervisionObservationBinding,
    ) -> bool:
        if pane_lost and observation.turn_role == "worker_fresh":
            return False
        return check_health(observation)

    host.validate_member_bundle = validate_then_lose  # type: ignore[method-assign]
    host.observation_is_healthy = reflect_late_loss  # type: ignore[method-assign]

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "completed"
    directive_validated = _event_index(
        host.events,
        "validate_bundle",
        "supervisor_directive",
    )
    pane_loss = _event_index(host.events, "pane_lost_after_directive")
    finalization = _event_index(host.events, "finalize")
    assert directive_validated < pane_loss < finalization
    assert not any(
        event[0] == "pane_health"
        for event in host.events[pane_loss + 1 :]
    )
    assert host.finalize_calls == 1


def test_continue_selects_fresh_and_finalizes_exactly_once(
    tmp_path: Path,
) -> None:
    host = _ContinueBindings(tmp_path, worker_document={"answer": 42})

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["artifacts"] == {"__result__": {"answer": 42}}
    assert result["directive"] == {"variant": "CONTINUE"}
    assert host.finalize_calls == 1
    assert [event for event in host.events if event[0] == "validate_bundle"] == [
        ("validate_bundle", "supervisor_directive"),
        ("validate_bundle", "worker_fresh"),
    ]
    assert _event_index(host.events, "finalize") < _event_index(
        host.events, "close_pane", "worker_fresh"
    )


def test_continue_real_state_manager_has_one_current_step_and_atomic_settlement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text("version: '1.0'\nname: test\nsteps: []\n")
    manager = StateManager(tmp_path, run_id="provider-supervision-state")
    write_historical_state(manager, "workflow.yaml")
    manager.update_control_flow_counters(0, {"Live": 1})
    writes: list[dict[str, Any] | None] = []
    original_write = manager._write_state

    def count_write() -> None:
        writes.append(
            None
            if manager.state is None or manager.state.current_step is None
            else dict(manager.state.current_step)
        )
        original_write()

    monkeypatch.setattr(manager, "_write_state", count_write)
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    host = _StateManagerContinueBindings(tmp_path, manager)

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "completed"
    assert len(writes) == 2
    assert writes[0] is not None
    assert writes[0]["type"] == "provider_supervision"
    assert writes[1] is None
    persisted = manager.load()
    assert persisted.current_step is None
    assert persisted.steps["Live"]["artifacts"] == {
        "__result__": "fresh-value"
    }


@pytest.mark.parametrize(
    "directive",
    [
        {"variant": "CONTINUE", "guidance": "forbidden"},
        {"variant": "CONTINUE", "extra": True},
        {"variant": "UNKNOWN"},
    ],
)
def test_continue_rejects_non_exact_directive_without_settlement(
    tmp_path: Path,
    directive: Any,
) -> None:
    host = _ContinueBindings(tmp_path, directive_document=directive)

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert host.finalize_calls == 0
    assert ("validate_bundle", "worker_fresh") not in host.events


@pytest.mark.parametrize("failure_kind", ["missing", "invalid"])
def test_continue_requires_valid_fresh_bundle_without_publication(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    host = _ContinueBindings(tmp_path)
    original_validate = host.validate_member_bundle

    def reject_worker(request: ProviderSupervisionMemberRequest) -> Any:
        if request.turn.turn_role == "worker_fresh":
            raise ValueError(f"{failure_kind} fresh bundle")
        return original_validate(request)

    host.validate_member_bundle = reject_worker  # type: ignore[method-assign]

    result = ProviderSupervisionCoordinator(host).run_continue(
        _config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert host.finalize_calls == 0
    assert not any(event[0] == "finalize" for event in host.events)
