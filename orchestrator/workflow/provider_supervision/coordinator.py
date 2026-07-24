"""Serial provider-supervision coordinator for the bounded CONTINUE path."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Protocol

from .bindings import (
    ProviderSupervisionAttemptBinding,
    ProviderSupervisionInvocationSnapshot,
    ProviderSupervisionMemberRequest,
    ProviderSupervisionObservationBinding,
    ProviderSupervisionObservationInjection,
    ProviderSupervisionTurnBinding,
)
from .directive import (
    ProviderSteeringDirective,
    ProviderSteeringDirectiveVariant,
)


class ProviderSupervisionCoordinatorBindings(Protocol):
    """Workflow-owned operations invoked only by the serial coordinator."""

    def assert_current_step(
        self,
        *,
        step_name: str,
        node_id: str,
        visit_count: int,
    ) -> None: ...

    def derive_turn_bindings(
        self,
        *,
        config: Any,
        visit_count: int,
    ) -> dict[str, ProviderSupervisionTurnBinding]: ...

    def open_observation(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderSupervisionObservationBinding: ...

    def compose_prompt(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        observation_injection: ProviderSupervisionObservationInjection | None,
    ) -> str: ...

    def allocate_attempt(
        self,
        *,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderSupervisionAttemptBinding: ...

    def prepare_invocation(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> Any: ...

    def create_control(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> Any: ...

    def execute_member(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> Any: ...

    def observation_is_healthy(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> bool: ...

    def validate_member_bundle(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> Any: ...

    def evaluate_settlement(
        self,
        *,
        config: Any,
        resolved_bindings: dict[str, Any],
    ) -> Any: ...

    def validate_settlement(self, *, config: Any, value: Any) -> Any: ...

    def finalize_settlement(
        self,
        *,
        config: Any,
        selected_request: ProviderSupervisionMemberRequest,
        directive_request: ProviderSupervisionMemberRequest,
        selected_value: Any,
        directive_value: ProviderSteeringDirective,
        settlement_value: Any,
    ) -> dict[str, Any]: ...

    def close_observation(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> None: ...

    def failure_result(self, *, code: str, message: str) -> dict[str, Any]: ...


class ProviderSupervisionCoordinator:
    """Prepare serially, execute concurrently, and settle once."""

    def __init__(
        self,
        bindings: ProviderSupervisionCoordinatorBindings,
    ) -> None:
        self._bindings = bindings

    def run_continue(
        self,
        config: Any,
        *,
        step_name: str,
        visit_count: int,
    ) -> dict[str, Any]:
        """Run the two initial turns and accept only a validated CONTINUE."""

        observations: list[ProviderSupervisionObservationBinding] = []
        finalization_started = False
        try:
            self._bindings.assert_current_step(
                step_name=step_name,
                node_id=config.node_id,
                visit_count=visit_count,
            )
            turns = self._bindings.derive_turn_bindings(
                config=config,
                visit_count=visit_count,
            )
            worker_turn = turns["worker_fresh"]
            supervisor_turn = turns["supervisor_directive"]
            self._validate_initial_turns(config, worker_turn, supervisor_turn)

            worker_observation = self._bindings.open_observation(worker_turn)
            observations.append(worker_observation)
            supervisor_observation = self._bindings.open_observation(
                supervisor_turn
            )
            observations.append(supervisor_observation)
            if not all(
                self._bindings.observation_is_healthy(observation)
                for observation in observations
            ):
                raise _CoordinatorFailure(
                    "provider_supervision_observation_unavailable",
                    "both initial observation panes must be healthy before launch",
                )

            worker_prompt = self._bindings.compose_prompt(
                member=config.worker,
                turn=worker_turn,
                observation_injection=None,
            )
            observation_injection = ProviderSupervisionObservationInjection(
                observer_member_id=config.supervisor.member_id,
                observed_member_id=config.worker.member_id,
                socket_path=str(worker_observation.socket_path),
                target=worker_observation.target,
            )
            supervisor_prompt = self._bindings.compose_prompt(
                member=config.supervisor,
                turn=supervisor_turn,
                observation_injection=observation_injection,
            )

            worker_attempt = self._bindings.allocate_attempt(
                turn=worker_turn,
                prompt=worker_prompt,
            )
            supervisor_attempt = self._bindings.allocate_attempt(
                turn=supervisor_turn,
                prompt=supervisor_prompt,
            )

            worker_request = ProviderSupervisionMemberRequest(
                member_id=config.worker.member_id,
                turn=worker_turn,
                observation=worker_observation,
                attempt=worker_attempt,
                invocation=ProviderSupervisionInvocationSnapshot.from_invocation(
                    self._bindings.prepare_invocation(
                        member=config.worker,
                        turn=worker_turn,
                        prompt=worker_prompt,
                    )
                ),
                control=self._bindings.create_control(worker_turn),
            )
            supervisor_request = ProviderSupervisionMemberRequest(
                member_id=config.supervisor.member_id,
                turn=supervisor_turn,
                observation=supervisor_observation,
                attempt=supervisor_attempt,
                invocation=ProviderSupervisionInvocationSnapshot.from_invocation(
                    self._bindings.prepare_invocation(
                        member=config.supervisor,
                        turn=supervisor_turn,
                        prompt=supervisor_prompt,
                    )
                ),
                control=self._bindings.create_control(supervisor_turn),
            )

            with ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="provider-supervision",
            ) as members:
                worker_future = members.submit(
                    self._bindings.execute_member,
                    worker_request,
                )
                supervisor_future = members.submit(
                    self._bindings.execute_member,
                    supervisor_request,
                )
                self._attach_execution_future(
                    worker_request.control,
                    worker_future,
                )
                self._attach_execution_future(
                    supervisor_request.control,
                    supervisor_future,
                )
                supervisor_execution = supervisor_future.result()
                worker_execution = worker_future.result()

            self._require_success(
                supervisor_execution,
                role="supervisor_directive",
            )
            self._require_success(worker_execution, role="worker_fresh")
            if not all(
                self._bindings.observation_is_healthy(observation)
                for observation in observations
            ):
                raise _CoordinatorFailure(
                    "provider_supervision_observation_lost",
                    "an initial observation pane was lost before arbitration",
                )

            raw_directive = self._bindings.validate_member_bundle(
                supervisor_request
            )
            try:
                directive = ProviderSteeringDirective.from_dict(raw_directive)
            except ValueError as exc:
                raise _CoordinatorFailure(
                    "provider_supervision_directive_invalid",
                    str(exc),
                ) from exc
            if directive.variant is not ProviderSteeringDirectiveVariant.CONTINUE:
                raise _CoordinatorFailure(
                    "provider_supervision_steer_not_available",
                    "STEER is not available in the CONTINUE coordinator",
                )

            selected_value = self._bindings.validate_member_bundle(
                worker_request
            )
            settlement_value = self._bindings.evaluate_settlement(
                config=config,
                resolved_bindings={
                    config.worker.member_id: selected_value,
                    config.supervisor.member_id: directive.to_dict(),
                },
            )
            settlement_value = self._bindings.validate_settlement(
                config=config,
                value=settlement_value,
            )
            self._bindings.assert_current_step(
                step_name=step_name,
                node_id=config.node_id,
                visit_count=visit_count,
            )
            finalization_started = True
            return self._bindings.finalize_settlement(
                config=config,
                selected_request=worker_request,
                directive_request=supervisor_request,
                selected_value=selected_value,
                directive_value=directive,
                settlement_value=settlement_value,
            )
        except _CoordinatorFailure as exc:
            if finalization_started:
                raise
            return self._bindings.failure_result(
                code=exc.code,
                message=str(exc),
            )
        except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
            if finalization_started:
                raise
            return self._bindings.failure_result(
                code="provider_supervision_failed",
                message=str(exc),
            )
        finally:
            for observation in observations:
                try:
                    self._bindings.close_observation(observation)
                except Exception:
                    pass

    @staticmethod
    def _validate_initial_turns(
        config: Any,
        worker: ProviderSupervisionTurnBinding,
        supervisor: ProviderSupervisionTurnBinding,
    ) -> None:
        if (
            worker.member_id != config.worker.member_id
            or worker.turn_role != "worker_fresh"
            or supervisor.member_id != config.supervisor.member_id
            or supervisor.turn_role != "supervisor_directive"
        ):
            raise _CoordinatorFailure(
                "provider_supervision_binding_invalid",
                "initial member-turn bindings contradict the executable config",
            )
        paths = {
            worker.evidence_path,
            worker.provisional_bundle_path,
            supervisor.evidence_path,
            supervisor.provisional_bundle_path,
        }
        if (
            len(paths) != 4
            or worker.runtime_step_id == supervisor.runtime_step_id
        ):
            raise _CoordinatorFailure(
                "provider_supervision_binding_collision",
                "initial member-turn identities or paths collide",
            )

    @staticmethod
    def _require_success(result: Any, *, role: str) -> None:
        if not bool(getattr(result, "is_promotable", False)):
            raise _CoordinatorFailure(
                "provider_supervision_member_failed",
                f"{role} execution did not complete successfully",
            )

    @staticmethod
    def _attach_execution_future(control: Any, future: Any) -> None:
        attach = getattr(control, "attach_execution_future", None)
        if not callable(attach):
            raise _CoordinatorFailure(
                "provider_supervision_control_invalid",
                "member control cannot attach its execution future",
            )
        attach(future)


class _CoordinatorFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
