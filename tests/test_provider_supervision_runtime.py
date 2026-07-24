"""Single-writer runtime tests for the provider-supervision CONTINUE path."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from orchestrator.deps.injector import DependencyInjector
from orchestrator.deps.resolver import DependencyResolver
from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.providers.types import InputMode, ProviderInvocation
from orchestrator.state import StateManager, StepResult
from orchestrator.variables.substitution import VariableSubstitutor
from orchestrator.workflow.call_frame_state import _CallFrameStateManager
from orchestrator.workflow.dataflow import DataflowManager
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.provider_supervision.bindings import (
    ProviderSupervisionAttemptBinding,
    ProviderSupervisionMemberRequest,
    ProviderSupervisionObservationBinding,
    ProviderSupervisionObservationInjection,
    ProviderSupervisionTurnBinding,
    WorkflowProviderSupervisionBindings,
)
from orchestrator.workflow.provider_supervision.coordinator import (
    ProviderSupervisionCoordinator,
)
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor


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


class _RealBindingObservation:
    def __init__(self, target: str, socket_path: Path) -> None:
        self.target = target
        self.socket_path = socket_path
        self.finalized = False

    def check_health(self) -> bool:
        return not self.finalized

    def finalize(self) -> None:
        self.finalized = True


class _RealBindingObservationManager:
    def __init__(self) -> None:
        self.index = 0
        self.handles: list[_RealBindingObservation] = []

    def next_invocation_id(self) -> str:
        self.index += 1
        return f"invocation-{self.index}"

    def open_observation(
        self,
        *,
        invocation_id: str,
        member_id: str,
        turn_id: str,
    ) -> _RealBindingObservation:
        del invocation_id, member_id
        handle = _RealBindingObservation(
            f"pane:{turn_id}",
            Path("/tmp/provider-supervision-test.sock"),
        )
        self.handles.append(handle)
        return handle


class _RealBindingProviderExecutor:
    def __init__(self) -> None:
        self.prompts: dict[str, str] = {}
        self.paths: list[Path] = []
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def prepare_invocation(
        self,
        *,
        provider_name: str,
        prompt_content: str,
        env: dict[str, str],
        session_request: Any,
        **_kwargs: Any,
    ) -> tuple[ProviderInvocation, None]:
        return (
            ProviderInvocation(
                command=["provider", provider_name],
                input_mode=InputMode.STDIN,
                prompt=prompt_content,
                env=env,
                session_request=session_request,
            ),
            None,
        )

    def execute(
        self,
        invocation: ProviderInvocation,
        **_kwargs: Any,
    ) -> ProviderExecutionResult:
        provider_name = invocation.command[-1]
        output_path = Path(
            invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        )
        with self._lock:
            self.prompts[provider_name] = invocation.prompt or ""
            self.paths.append(output_path)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.04)
        output_path.write_text(
            (
                '{"variant":"CONTINUE"}'
                if provider_name == "supervisor-provider"
                else '"fresh-value"'
            ),
            encoding="utf-8",
        )
        with self._lock:
            self.active -= 1
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=40,
        )


class _RealBindingExecutor:
    def __init__(
        self,
        workspace: Path,
        manager: StateManager,
    ) -> None:
        self.workspace = workspace
        self.state_manager = manager
        self.provider_observation_manager = (
            _RealBindingObservationManager()
        )
        self.provider_executor = _RealBindingProviderExecutor()
        self.dependency_injector = DependencyInjector(str(workspace))
        self.dependency_resolver = DependencyResolver(str(workspace))
        self.variable_substitutor = VariableSubstitutor()
        self.prompt_composer = PromptComposer(
            workspace=workspace,
            asset_resolver=None,
        )
        self.debug = False
        self.stream_output = False
        self.finalize_calls = 0

    def _provider_attempt_scope(self, **kwargs: Any) -> Any:
        return WorkflowExecutor._provider_attempt_scope(self, **kwargs)

    def _compose_provider_attempt_for_step(
        self,
        step: dict[str, Any],
        _context: dict[str, Any],
        _state: dict[str, Any],
        *,
        output_contract_step: dict[str, Any],
        **_kwargs: Any,
    ) -> tuple[str, None, None]:
        contract = (
            output_contract_step.get("output_bundle")
            or output_contract_step.get("variant_output")
        )
        assert isinstance(contract, dict)
        return (
            f"member:{step['provider']}\ncontract:{json.dumps(contract, sort_keys=True)}",
            None,
            None,
        )

    def _create_provider_context(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {}

    def _build_substitution_variables(
        self,
        _context: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return {"context": state.get("context", {})}

    def _resolve_typed_content_dependencies(
        self,
        **kwargs: Any,
    ) -> Any:
        return WorkflowExecutor._resolve_typed_content_dependencies(
            self,
            **kwargs,
        )

    def _uses_qualified_identities(self) -> bool:
        return False

    def _resolve_provider_name_for_step(
        self,
        step: dict[str, Any],
        _context: dict[str, Any],
    ) -> tuple[str, None]:
        return step["provider"], None

    def _atomic_write_bytes(self, path: Path, content: bytes) -> None:
        path.write_bytes(content)

    def _finalize_provider_supervision_settlement(
        self,
        _step: Any,
        state: dict[str, Any],
        *,
        step_name: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        self.finalize_calls += 1
        result = {
            **result,
            "name": step_name,
            "step_id": "root.live",
            "visit_count": 1,
        }
        state.setdefault("steps", {})[step_name] = result
        self.state_manager.finalize_step_with_dataflow(
            step_name,
            StepResult(
                status=result["status"],
                name=step_name,
                step_id="root.live",
                exit_code=result["exit_code"],
                duration_ms=result["duration_ms"],
                artifacts=result.get("artifacts"),
                error=result.get("error"),
                debug=result.get("debug"),
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


def _config_with_prompt_snapshot_owners(config: Any) -> Any:
    def member_with_contract(member: Any, *, origin: str) -> Any:
        contract = _build_compiler_prompt_dependency_contract(
            required_binding_refs=(),
            optional_binding_refs=("context.prompt_dependency",),
            position=PromptDependencyPosition.PREPEND,
            instruction=None,
            source_origin_key=origin,
            source_workflow_bytes=b"; generated test workflow\n",
        )
        provider_config = replace(
            member.provider_config,
            depends_on={
                "required": [],
                "optional": ["${context.prompt_dependency}"],
                "inject": {
                    "mode": "content",
                    "position": "prepend",
                },
            },
            compiler_prompt_dependency_contract=contract,
        )
        return replace(member, provider_config=provider_config)

    return replace(
        config,
        worker=member_with_contract(
            config.worker,
            origin="source:worker:prompt-dependencies",
        ),
        supervisor=member_with_contract(
            config.supervisor,
            origin="source:supervisor:prompt-dependencies",
        ),
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


def test_provider_supervision_top_level_dispatch_uses_coordinator_result_once() -> None:
    executor = object.__new__(WorkflowExecutor)
    finalized = {
        "status": "completed",
        "exit_code": 0,
        "artifacts": {"__result__": "selected"},
    }
    calls: list[tuple[Any, ...]] = []
    executor._execution_kind_for_step = (  # type: ignore[method-assign]
        lambda _step: ExecutableNodeKind.PROVIDER_SUPERVISION
    )
    executor._execute_provider_supervision = (  # type: ignore[attr-defined]
        lambda step, state, **kwargs: (
            calls.append((step, state, kwargs)),
            finalized,
        )[1]
    )
    state = {"steps": {}, "step_visits": {"Live": 1}}
    step = {"name": "Live", "step_id": "root.live"}

    result = WorkflowExecutor._run_top_level_step(
        executor,
        step,
        state,
        step_name="Live",
    )

    assert result is finalized
    assert calls == [
        (
            step,
            state,
            {"step_name": "Live"},
        )
    ]


def test_provider_supervision_nested_loop_is_recognized_and_fails_closed(
    tmp_path: Path,
) -> None:
    executor = object.__new__(WorkflowExecutor)
    launches: list[str] = []
    executor._typed_execution_step = lambda step: step  # type: ignore[method-assign]
    executor._build_loop_scope = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: {
            "parent_steps": {},
            "self_steps": {},
            "root_steps": {},
        }
    )
    executor._execution_kind_for_step = (  # type: ignore[method-assign]
        lambda _step: ExecutableNodeKind.PROVIDER_SUPERVISION
    )
    executor._execute_provider_supervision = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: launches.append("provider") or {}
    )
    executor._record_published_artifacts = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    executor._attach_outcome = (  # type: ignore[method-assign]
        lambda _step, result, **_kwargs: result
    )
    executor._finalize_consumes = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    executor._emit_step_summary = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    loop_updates: list[Any] = []
    executor.state_manager = SimpleNamespace(
        update_loop_step=lambda *args: loop_updates.append(args)
    )
    state: dict[str, Any] = {"steps": {}}
    iteration_state: dict[str, Any] = {}

    result = WorkflowExecutor._execute_nested_loop_step(
        executor,
        {"name": "NestedLive", "step_id": "root.loop.live"},
        {},
        state,
        iteration_state,
        {},
        runtime_step_id="root.loop#0.live",
        loop_name="Loop",
        iteration_index=0,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_supervision_nested_atomicity_unavailable"
    )
    assert launches == []
    assert len(loop_updates) == 1


def test_provider_supervision_call_frame_fails_before_runtime_activity() -> None:
    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = object.__new__(_CallFrameStateManager)
    activity: list[str] = []
    executor._executable_node_for_step = (  # type: ignore[method-assign]
        lambda _step: activity.append("config") or None
    )
    executor._require_provider_supervision_observation_manager = (  # type: ignore[method-assign]
        lambda: activity.append("pane") or None
    )
    executor._persist_step_result = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: activity.append("persist") or {}
    )
    executor._contract_violation_result = (  # type: ignore[method-assign]
        lambda message, context: {
            "status": "failed",
            "exit_code": 2,
            "error": {
                "type": "contract_violation",
                "message": message,
                "context": context,
            },
        }
    )

    with pytest.raises(
        RuntimeError,
        match="provider_supervision_atomic_finalizer_unavailable",
    ):
        WorkflowExecutor._execute_provider_supervision(
            executor,
            {"name": "ImportedLive", "step_id": "import.live"},
            {"step_visits": {"ImportedLive": 1}},
            step_name="ImportedLive",
        )

    assert activity == []


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
    manager.initialize("workflow.yaml")
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


def test_workflow_executor_persists_provider_supervision_current_step_before_runtime_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.lowering import build_loaded_workflow_bundle
    from orchestrator.workflow.surface_ast import (
        SurfaceStep,
        SurfaceStepCommonConfig,
        SurfaceStepKind,
        SurfaceWorkflow,
        WorkflowProvenance,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )

    workflow_path = tmp_path / "workflow.orc"
    workflow_path.write_text(
        "; generated provider-supervision test workflow\n",
        encoding="utf-8",
    )
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    provenance = WorkflowProvenance(
        workflow_path=workflow_path,
        source_root=tmp_path,
        frontend_kind="workflow_lisp",
    )
    surface = SurfaceWorkflow(
        version="2.15",
        name="generated-live",
        steps=(
            SurfaceStep(
                name="Live",
                step_id="root.live",
                kind=SurfaceStepKind.PROVIDER_SUPERVISION,
                common=SurfaceStepCommonConfig(timeout_sec=60),
                provider_supervision=config,
            ),
        ),
        provenance=provenance,
    )
    bundle = build_loaded_workflow_bundle(surface, imports={})
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-production-cursor",
    )
    manager.initialize(
        "workflow.orc",
        context={
            "prompt_dependency": "inputs/intentionally-absent.md",
        },
    )
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        manager,
        step_heartbeat_interval_sec=0,
    )
    executor.provider_observation_manager = (
        _RealBindingObservationManager()
    )
    executor.provider_executor = _RealBindingProviderExecutor()

    events: list[str] = []
    events_lock = threading.Lock()

    def assert_persisted_current_step(event: str) -> None:
        persisted = json.loads(
            manager.state_file.read_text(encoding="utf-8")
        )
        current_step = persisted.get("current_step")
        assert isinstance(current_step, dict)
        assert {
            key: current_step.get(key)
            for key in (
                "name",
                "index",
                "type",
                "status",
                "step_id",
                "visit_count",
            )
        } == {
            "name": "Live",
            "index": 0,
            "type": "provider_supervision",
            "status": "running",
            "step_id": "root.live",
            "visit_count": 1,
        }
        with events_lock:
            events.append(event)

    open_observation = (
        WorkflowProviderSupervisionBindings.open_observation
    )
    allocate_attempt = (
        WorkflowProviderSupervisionBindings.allocate_attempt
    )
    execute_member = (
        WorkflowProviderSupervisionBindings.execute_member
    )

    def checked_open_observation(
        bindings: WorkflowProviderSupervisionBindings,
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderSupervisionObservationBinding:
        assert_persisted_current_step("pane")
        return open_observation(bindings, turn)

    def checked_allocate_attempt(
        bindings: WorkflowProviderSupervisionBindings,
        *,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderSupervisionAttemptBinding:
        assert_persisted_current_step("attempt")
        return allocate_attempt(
            bindings,
            turn=turn,
            prompt=prompt,
        )

    def checked_execute_member(
        bindings: WorkflowProviderSupervisionBindings,
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        assert_persisted_current_step("provider")
        return execute_member(bindings, request)

    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "open_observation",
        checked_open_observation,
    )
    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "allocate_attempt",
        checked_allocate_attempt,
    )
    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "execute_member",
        checked_execute_member,
    )

    state = executor.execute()

    assert state["status"] == "completed"
    assert state["steps"]["Live"]["status"] == "completed"
    assert events.count("pane") == 2
    assert events.count("attempt") == 2
    assert events.count("provider") == 2
    persisted = manager.load()
    assert persisted.current_step is None
    assert len(persisted.provider_attempt_allocations) == 2


def _atomic_finalizer_executor(
    tmp_path: Path,
    manager: StateManager,
) -> WorkflowExecutor:
    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = manager
    executor.dataflow_manager = DataflowManager(
        workspace=tmp_path,
        artifact_registry={},
        workflow_version="2.15",
        uses_qualified_identities=lambda: False,
        workflow_version_at_least=lambda _version: True,
        step_id_resolver=lambda step: str(step.get("step_id")),
        contract_violation_result=lambda message, context: {
            "status": "failed",
            "exit_code": 2,
            "error": {"message": message, "context": context},
        },
        persist_state=lambda state: manager.update_dataflow_state(
            state.get("artifact_versions", {}),
            state.get("artifact_consumes", {}),
            state.get("private_artifact_versions", {}),
            state.get("private_artifact_consumes", {}),
        ),
        substitute_path_template=lambda path, *_args, **_kwargs: (
            path,
            None,
        ),
        resolve_workspace_path=lambda path: tmp_path / path,
        current_step_index=lambda: 0,
    )
    executor._record_published_artifacts = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    executor._attach_outcome = (  # type: ignore[method-assign]
        lambda _step, result: dict(result)
    )
    executor._step_id = lambda _step: "root.live"  # type: ignore[method-assign]
    executor._emit_step_summary = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    return executor


def test_provider_supervision_pending_consumes_share_one_terminal_state_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-atomic-consumes",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    writes = 0
    original_write = manager._write_state

    def count_write() -> None:
        nonlocal writes
        writes += 1
        original_write()

    monkeypatch.setattr(manager, "_write_state", count_write)
    state = manager.load().to_dict()
    state["_pending_artifact_consumes"] = {
        "Live": {"input_artifact": 3},
    }
    state["_resolved_consumes"] = {
        "Live": {"input_artifact": "value"},
    }
    executor = _atomic_finalizer_executor(tmp_path, manager)

    result = WorkflowExecutor._finalize_provider_supervision_settlement(
        executor,
        {"name": "Live", "step_id": "root.live"},
        state,
        step_name="Live",
        result={
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 1,
            "artifacts": {"__result__": "selected"},
        },
    )

    assert result["status"] == "completed"
    assert writes == 1
    persisted = manager.load()
    assert persisted.artifact_consumes["Live"] == {
        "input_artifact": 3,
    }
    assert persisted.artifact_consumes["__global__"] == {
        "input_artifact": 3,
    }


def test_provider_supervision_rejects_current_step_drift_before_settlement_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-current-step-drift",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1, "Other": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    manager.start_step(
        "Other",
        1,
        "provider",
        step_id="root.other",
        visit_count=1,
    )
    writes = 0
    original_write = manager._write_state

    def count_write() -> None:
        nonlocal writes
        writes += 1
        original_write()

    monkeypatch.setattr(manager, "_write_state", count_write)
    executor = _atomic_finalizer_executor(tmp_path, manager)

    with pytest.raises(
        ValueError,
        match="current_step changed before atomic settlement",
    ):
        WorkflowExecutor._finalize_provider_supervision_settlement(
            executor,
            {"name": "Live", "step_id": "root.live"},
            state,
            step_name="Live",
            result={
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 1,
                "artifacts": {"__result__": "selected"},
            },
        )

    assert writes == 0
    assert "Live" not in manager.load().steps


def test_continue_real_binding_allocates_durable_attempts_and_validates_bundles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-binding",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    state["context"] = {
        "prompt_dependency": "inputs/intentionally-absent.md",
    }
    executor = _RealBindingExecutor(tmp_path, manager)
    suffix_inputs: list[tuple[dict[str, Any], str]] = []
    apply_output_suffix = (
        executor.prompt_composer.apply_output_contract_prompt_suffix
    )

    def record_output_suffix(
        step: dict[str, Any],
        prompt: str,
    ) -> str:
        suffix_inputs.append((step, prompt))
        return apply_output_suffix(step, prompt)

    monkeypatch.setattr(
        executor.prompt_composer,
        "apply_output_contract_prompt_suffix",
        record_output_suffix,
    )
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )

    result = ProviderSupervisionCoordinator(bindings).run_continue(
        config,
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "completed"
    assert result["artifacts"] == {"__result__": "fresh-value"}
    assert executor.finalize_calls == 1
    assert executor.provider_executor.max_active == 2
    assert len(set(executor.provider_executor.paths)) == 2
    assert all(path.exists() for path in executor.provider_executor.paths)
    socket_path = "/tmp/provider-supervision-test.sock"
    assert "pane:worker_fresh" not in executor.provider_executor.prompts[
        "worker-provider"
    ]
    assert socket_path not in executor.provider_executor.prompts[
        "worker-provider"
    ]
    assert "pane:worker_fresh" in executor.provider_executor.prompts[
        "supervisor-provider"
    ]
    assert socket_path in executor.provider_executor.prompts[
        "supervisor-provider"
    ]
    worker_suffix_input = next(
        prompt
        for step, prompt in suffix_inputs
        if "output_bundle" in step
    )
    supervisor_suffix_input = next(
        prompt
        for step, prompt in suffix_inputs
        if "variant_output" in step
    )
    assert "pane:worker_fresh" not in worker_suffix_input
    assert socket_path not in worker_suffix_input
    assert "pane:worker_fresh" in supervisor_suffix_input
    assert socket_path in supervisor_suffix_input
    assert set(result["debug"]["provider_supervision"]) == {
        "selected_attempt",
        "directive_attempt",
    }
    persisted = manager.load()
    assert persisted.current_step is None
    allocations = persisted.provider_attempt_allocations
    assert len(allocations) == 2
    assert all(
        set(entry["scope"]) == {
            "run_id",
            "resume_scope",
            "runtime_step_id",
            "enclosing_step",
            "loop_iteration",
            "adjudication_subject",
        }
        for entry in allocations.values()
    )
    assert all(
        [event["event"] for event in entry["events"]]
        == ["allocated", "evidence_published"]
        for entry in allocations.values()
    )
    evidence = sorted(
        manager.run_root.glob(
            "provider-supervision/root.live/visits/1/"
            "members/*/turns/*/evidence.json"
        )
    )
    assert len(evidence) == 2
    assert {
        json.loads(path.read_text(encoding="ascii"))["schema"]
        for path in evidence
    } == {"workflow_prompt_dependency_evidence.functional.v1"}
    published_evidence = sorted(
        manager.run_root.glob(
            "workflow_lisp/prompt_dependencies/*/*/attempt-*.json"
        )
    )
    assert len(published_evidence) == 2
    assert {path.read_bytes() for path in evidence} == {
        path.read_bytes() for path in published_evidence
    }
    state_text = manager.state_file.read_text(encoding="utf-8")
    assert "pane:worker_fresh" not in state_text
    assert socket_path not in state_text
    persisted_debug = manager.load().steps["Live"]["debug"]
    assert isinstance(persisted_debug, dict)
    assert set(persisted_debug["provider_supervision"]) == {
        "selected_attempt",
        "directive_attempt",
    }


def test_continue_real_binding_rejects_missing_compiler_prompt_snapshot_owner(
    tmp_path: Path,
) -> None:
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-missing-prompt-owner",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    executor = _RealBindingExecutor(tmp_path, manager)
    config = _provider_supervision_config()
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )

    result = ProviderSupervisionCoordinator(bindings).run_continue(
        config,
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_failed"
    assert "compiler prompt-dependency contract" in result["error"]["message"]
    assert manager.load().provider_attempt_allocations == {}
    assert executor.provider_executor.prompts == {}


@pytest.mark.parametrize("fresh_bundle_failure", ["missing", "invalid"])
def test_continue_real_binding_rejects_unusable_fresh_bundle_without_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fresh_bundle_failure: str,
) -> None:
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id=f"provider-supervision-fresh-{fresh_bundle_failure}",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    state["context"] = {
        "prompt_dependency": "inputs/intentionally-absent.md",
    }
    executor = _RealBindingExecutor(tmp_path, manager)
    execute = executor.provider_executor.execute

    def execute_with_unusable_fresh_bundle(
        invocation: ProviderInvocation,
        **kwargs: Any,
    ) -> ProviderExecutionResult:
        execution = execute(invocation, **kwargs)
        if invocation.command[-1] == "worker-provider":
            output_path = Path(
                invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
            )
            if fresh_bundle_failure == "missing":
                output_path.unlink()
            else:
                output_path.write_text("42", encoding="utf-8")
        return execution

    monkeypatch.setattr(
        executor.provider_executor,
        "execute",
        execute_with_unusable_fresh_bundle,
    )
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )

    result = ProviderSupervisionCoordinator(bindings).run_continue(
        config,
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert "artifacts" not in result
    persisted = manager.load()
    assert persisted.steps["Live"]["status"] == "failed"
    assert persisted.steps["Live"].get("artifacts") is None
    assert persisted.artifact_versions == {}
    assert persisted.private_artifact_versions == {}


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
