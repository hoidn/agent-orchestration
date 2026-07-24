"""Serial provider-supervision coordinator for one bounded directive."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
import threading
import time
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
from .models import classify_provider_supervision_resume_boundary


_CLEANUP_TIMEOUT_SEC = 6.0


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

    def derive_resume_turn_binding(
        self,
        *,
        config: Any,
        visit_count: int,
    ) -> ProviderSupervisionTurnBinding: ...

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

    def compose_resume_prompt(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        guidance: str,
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

    def prepare_resume_invocation(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
        session_id: str,
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
        """Compatibility entrypoint that preserves the Task 7 boundary."""

        return self._run(
            config,
            step_name=step_name,
            visit_count=visit_count,
            allow_steer=False,
            compatibility_timeout_defaults=True,
        )

    def run(
        self,
        config: Any,
        *,
        step_name: str,
        visit_count: int,
    ) -> dict[str, Any]:
        """Run one CONTINUE or one bounded STEER directive."""

        return self._run(
            config,
            step_name=step_name,
            visit_count=visit_count,
            allow_steer=True,
            compatibility_timeout_defaults=False,
        )

    def _run(
        self,
        config: Any,
        *,
        step_name: str,
        visit_count: int,
        allow_steer: bool,
        compatibility_timeout_defaults: bool,
    ) -> dict[str, Any]:
        observations: list[ProviderSupervisionObservationBinding] = []
        requests: list[ProviderSupervisionMemberRequest] = []
        futures: dict[int, Future[Any]] = {}
        members: ThreadPoolExecutor | None = None
        members_shutdown = False
        finalization_started = False
        launch_time = time.monotonic()
        if compatibility_timeout_defaults:
            whole_timeout = float(
                getattr(getattr(config, "common", None), "timeout_sec", 86400)
            )
            worker_timeout = float(
                getattr(config.worker, "timeout_sec", 86400)
            )
            supervisor_timeout = float(
                getattr(config.supervisor, "timeout_sec", 86400)
            )
        else:
            whole_timeout = float(config.common.timeout_sec)
            worker_timeout = float(config.worker.timeout_sec)
            supervisor_timeout = float(config.supervisor.timeout_sec)
        whole_deadline = launch_time + whole_timeout
        worker_deadline = launch_time + worker_timeout
        supervisor_deadline = (
            launch_time + supervisor_timeout
        )
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
            worker_request = self._prepare_request(
                member=config.worker,
                turn=worker_turn,
                observation=worker_observation,
                prompt=worker_prompt,
            )
            supervisor_request = self._prepare_request(
                member=config.supervisor,
                turn=supervisor_turn,
                observation=supervisor_observation,
                prompt=supervisor_prompt,
            )
            requests.extend((worker_request, supervisor_request))

            members = ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="provider-supervision",
            )
            worker_future = self._submit(
                members,
                worker_request,
                futures,
            )
            supervisor_future = self._submit(
                members,
                supervisor_request,
                futures,
            )

            supervisor_execution = self._result_before(
                supervisor_future,
                min(supervisor_deadline, whole_deadline),
                whole_deadline=whole_deadline,
                code="provider_supervision_supervisor_timeout",
            )
            self._require_success(
                supervisor_execution,
                role="supervisor_directive",
            )
            worker_execution: Any | None = None
            if not allow_steer:
                worker_execution = self._result_before(
                    worker_future,
                    min(worker_deadline, whole_deadline),
                    whole_deadline=whole_deadline,
                    code="provider_supervision_worker_timeout",
                )
                self._require_success(
                    worker_execution,
                    role="worker_fresh",
                )
            if not all(
                self._bindings.observation_is_healthy(observation)
                for observation in observations
            ):
                raise _CoordinatorFailure(
                    "provider_supervision_observation_lost",
                    "an initial observation pane was lost before arbitration",
                )
            directive = self._validate_directive(supervisor_request)

            if directive.variant is ProviderSteeringDirectiveVariant.CONTINUE:
                if worker_execution is None:
                    worker_execution = self._result_before(
                        worker_future,
                        min(worker_deadline, whole_deadline),
                        whole_deadline=whole_deadline,
                        code="provider_supervision_worker_timeout",
                    )
                    self._require_success(
                        worker_execution,
                        role="worker_fresh",
                    )
                selected_request = worker_request
                selected_value = self._bindings.validate_member_bundle(
                    worker_request
                )
            else:
                if not allow_steer:
                    raise _CoordinatorFailure(
                        "provider_supervision_steer_not_available",
                        "STEER is not available in the CONTINUE coordinator",
                    )
                if config.max_steers != 1:
                    raise _CoordinatorFailure(
                        "provider_supervision_second_steer_rejected",
                        "provider supervision permits exactly one STEER",
                    )
                selected_request, selected_value = self._run_steer(
                    config=config,
                    visit_count=visit_count,
                    directive=directive,
                    worker_request=worker_request,
                    worker_future=worker_future,
                    worker_deadline=worker_deadline,
                    whole_deadline=whole_deadline,
                    observations=observations,
                    requests=requests,
                    futures=futures,
                    members=members,
                )

            members.shutdown(wait=True, cancel_futures=True)
            members_shutdown = True
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
                selected_request=selected_request,
                directive_request=supervisor_request,
                selected_value=selected_value,
                directive_value=directive,
                settlement_value=settlement_value,
            )
        except _CoordinatorFailure as exc:
            if finalization_started:
                raise
            members_shutdown = members is not None
            self._cleanup_and_join(
                requests=requests,
                futures=futures,
                members=members,
            )
            return self._bindings.failure_result(
                code=exc.code,
                message=str(exc),
            )
        except Exception as exc:
            if finalization_started:
                raise
            members_shutdown = members is not None
            self._cleanup_and_join(
                requests=requests,
                futures=futures,
                members=members,
            )
            return self._bindings.failure_result(
                code="provider_supervision_failed",
                message=str(exc),
            )
        finally:
            if members is not None and not members_shutdown:
                members.shutdown(wait=True, cancel_futures=True)
            for observation in observations:
                try:
                    self._bindings.close_observation(observation)
                except Exception:
                    pass

    def _prepare_request(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        observation: ProviderSupervisionObservationBinding,
        prompt: str,
    ) -> ProviderSupervisionMemberRequest:
        attempt = self._bindings.allocate_attempt(turn=turn, prompt=prompt)
        invocation = self._bindings.prepare_invocation(
            member=member,
            turn=turn,
            prompt=prompt,
        )
        return ProviderSupervisionMemberRequest(
            member_id=member.member_id,
            turn=turn,
            observation=observation,
            attempt=attempt,
            invocation=ProviderSupervisionInvocationSnapshot.from_invocation(
                invocation
            ),
            control=self._bindings.create_control(turn),
        )

    def _submit(
        self,
        members: ThreadPoolExecutor,
        request: ProviderSupervisionMemberRequest,
        futures: dict[int, Future[Any]],
    ) -> Future[Any]:
        future = members.submit(self._bindings.execute_member, request)
        futures[id(request)] = future
        self._attach_execution_future(request.control, future)
        return future

    @staticmethod
    def _result_before(
        future: Future[Any],
        deadline: float,
        *,
        whole_deadline: float,
        code: str,
    ) -> Any:
        observed_at = time.monotonic()
        remaining = deadline - observed_at
        if remaining <= 0:
            raise _CoordinatorFailure(
                (
                    "provider_supervision_step_timeout"
                    if observed_at >= whole_deadline
                    else code
                ),
                "provider supervision deadline expired",
            )
        try:
            return future.result(timeout=remaining)
        except TimeoutError as exc:
            if future.done():
                member_exception = future.exception()
                if member_exception is not None:
                    raise member_exception
            observed_at = time.monotonic()
            raise _CoordinatorFailure(
                (
                    "provider_supervision_step_timeout"
                    if observed_at >= whole_deadline
                    else code
                ),
                "provider supervision deadline expired",
            ) from exc

    def _validate_directive(
        self,
        supervisor_request: ProviderSupervisionMemberRequest,
    ) -> ProviderSteeringDirective:
        raw_directive = self._bindings.validate_member_bundle(
            supervisor_request
        )
        try:
            return ProviderSteeringDirective.from_dict(raw_directive)
        except ValueError as exc:
            raise _CoordinatorFailure(
                "provider_supervision_directive_invalid",
                str(exc),
            ) from exc

    def _run_steer(
        self,
        *,
        config: Any,
        visit_count: int,
        directive: ProviderSteeringDirective,
        worker_request: ProviderSupervisionMemberRequest,
        worker_future: Future[Any],
        worker_deadline: float,
        whole_deadline: float,
        observations: list[ProviderSupervisionObservationBinding],
        requests: list[ProviderSupervisionMemberRequest],
        futures: dict[int, Future[Any]],
        members: ThreadPoolExecutor,
    ) -> tuple[ProviderSupervisionMemberRequest, Any]:
        assert directive.guidance is not None
        initial_session_id: str | None = None
        while True:
            now = time.monotonic()
            terminal_proof = worker_request.control.terminal_result
            worker_execution = (
                worker_future.result()
                if worker_future.done()
                else None
            )
            if terminal_proof is not None and worker_execution is None:
                worker_execution = self._result_before(
                    worker_future,
                    whole_deadline,
                    whole_deadline=whole_deadline,
                    code="provider_supervision_worker_timeout",
                )
                now = time.monotonic()
            if worker_execution is not None:
                self._require_success(
                    worker_execution,
                    role="worker_fresh",
                )
            assessment = classify_provider_supervision_resume_boundary(
                snapshot=(
                    terminal_proof.final_session_snapshot
                    if terminal_proof is not None
                    else worker_request.control.session_snapshot
                ),
                terminal_proof=terminal_proof,
                execution_promotable=(
                    bool(worker_execution.is_promotable)
                    if worker_execution is not None
                    else None
                ),
                member_deadline_live=now < worker_deadline,
                whole_deadline_live=now < whole_deadline,
            )
            if assessment.outcome != "wait":
                if assessment.outcome == "timeout":
                    raise _CoordinatorFailure(
                        (
                            "provider_supervision_step_timeout"
                            if now >= whole_deadline
                            else "provider_supervision_worker_timeout"
                        ),
                        "worker resume boundary deadline expired",
                    )
                if assessment.outcome == "reject":
                    raise _CoordinatorFailure(
                        "provider_supervision_resume_boundary_invalid",
                        "worker resume boundary is not eligible",
                    )
                initial_session_id = assessment.session_id
                break
            time.sleep(
                min(
                    0.01,
                    max(
                        min(worker_deadline, whole_deadline)
                        - time.monotonic(),
                        0.0,
                    ),
                )
            )

        proof = worker_request.control.cancel_and_reap(grace=0.2)
        worker_execution = self._result_before(
            worker_future,
            whole_deadline,
            whole_deadline=whole_deadline,
            code="provider_supervision_worker_timeout",
        )
        now = time.monotonic()
        final_assessment = classify_provider_supervision_resume_boundary(
            snapshot=proof.final_session_snapshot,
            terminal_proof=proof,
            execution_promotable=bool(worker_execution.is_promotable),
            member_deadline_live=now < worker_deadline,
            whole_deadline_live=now < whole_deadline,
        )
        if final_assessment.outcome == "timeout":
            raise _CoordinatorFailure(
                (
                    "provider_supervision_step_timeout"
                    if now >= whole_deadline
                    else "provider_supervision_worker_timeout"
                ),
                "worker resume boundary deadline expired",
            )
        if final_assessment.outcome not in {
            "active_eligible",
            "clean_natural_eligible",
        }:
            raise _CoordinatorFailure(
                "provider_supervision_resume_boundary_invalid",
                "worker final resume boundary is not eligible",
            )
        session_id = final_assessment.session_id
        if (
            session_id is None
            or (
                initial_session_id is not None
                and initial_session_id != session_id
            )
        ):
            raise _CoordinatorFailure(
                "provider_supervision_resume_identity_invalid",
                "worker session identity changed before resume",
            )
        if time.monotonic() >= whole_deadline:
            raise _CoordinatorFailure(
                "provider_supervision_step_timeout",
                "whole-step deadline expired before resume",
            )

        resume_turn = self._bindings.derive_resume_turn_binding(
            config=config,
            visit_count=visit_count,
        )
        self._validate_resume_turn(
            config,
            resume_turn,
            worker_request.turn,
        )
        try:
            resume_observation = self._bindings.open_observation(
                resume_turn
            )
        except Exception:
            resume_observation = None
        if resume_observation is not None:
            observations.append(resume_observation)
        resume_prompt = self._bindings.compose_resume_prompt(
            member=config.worker,
            turn=resume_turn,
            guidance=directive.guidance,
        )
        resume_attempt = self._bindings.allocate_attempt(
            turn=resume_turn,
            prompt=resume_prompt,
        )
        resume_invocation = self._bindings.prepare_resume_invocation(
            member=config.worker,
            turn=resume_turn,
            prompt=resume_prompt,
            session_id=session_id,
        )
        resume_request = ProviderSupervisionMemberRequest(
            member_id=config.worker.member_id,
            turn=resume_turn,
            observation=resume_observation,
            attempt=resume_attempt,
            invocation=ProviderSupervisionInvocationSnapshot.from_invocation(
                resume_invocation
            ),
            control=self._bindings.create_control(resume_turn),
        )
        requests.append(resume_request)
        resume_submit_time = time.monotonic()
        if resume_submit_time >= whole_deadline:
            raise _CoordinatorFailure(
                "provider_supervision_step_timeout",
                "whole-step deadline expired before resume submission",
            )
        if (
            final_assessment.outcome == "active_eligible"
            and resume_submit_time >= worker_deadline
        ):
            raise _CoordinatorFailure(
                "provider_supervision_worker_timeout",
                "worker deadline expired before active resume submission",
            )
        resume_future = self._submit(members, resume_request, futures)
        resume_deadline = min(
            whole_deadline,
            time.monotonic() + float(config.worker.timeout_sec),
        )
        resume_execution = self._result_before(
            resume_future,
            resume_deadline,
            whole_deadline=whole_deadline,
            code="provider_supervision_resume_timeout",
        )
        self._require_success(resume_execution, role="worker_resume")
        self._require_matching_resume_boundary(
            resume_request.control.terminal_result,
            session_id=session_id,
        )
        return (
            resume_request,
            self._bindings.validate_member_bundle(resume_request),
        )

    @staticmethod
    def _validate_resume_turn(
        config: Any,
        resume: ProviderSupervisionTurnBinding,
        fresh: ProviderSupervisionTurnBinding,
    ) -> None:
        if (
            resume.member_id != config.worker.member_id
            or resume.turn_role != "worker_resume"
            or resume.runtime_step_id == fresh.runtime_step_id
            or resume.evidence_path
            in {fresh.evidence_path, fresh.provisional_bundle_path}
            or resume.provisional_bundle_path
            in {fresh.evidence_path, fresh.provisional_bundle_path}
            or resume.evidence_path == resume.provisional_bundle_path
        ):
            raise _CoordinatorFailure(
                "provider_supervision_resume_binding_invalid",
                "resume turn identity or paths are not distinct",
            )

    @staticmethod
    def _require_matching_resume_boundary(
        proof: Any,
        *,
        session_id: str,
    ) -> None:
        snapshot = getattr(proof, "final_session_snapshot", None)
        if (
            proof is None
            or getattr(proof, "disposition", None) != "natural_exit"
            or getattr(proof, "leader_return_code", None) != 0
            or getattr(proof, "proof_complete", None) is not True
            or getattr(proof, "leader_reaped", None) is not True
            or getattr(proof, "pgid_empty", None) is not True
            or getattr(proof, "capture_threads_joined", None) is not True
            or getattr(proof, "execution_joined", None) is not True
            or getattr(proof, "final_identity_valid", None) is not True
            or getattr(
                proof,
                "natural_exit_with_lingering_group",
                None,
            )
            is not False
            or getattr(proof, "error", None) is not None
            or getattr(snapshot, "status", None) != "unique"
            or tuple(getattr(snapshot, "session_ids", ())) != (session_id,)
            or getattr(snapshot, "resume_boundary_seen", None) is not True
            or getattr(snapshot, "terminal_seen", None) is not True
            or getattr(snapshot, "error", None) is not None
        ):
            raise _CoordinatorFailure(
                "provider_supervision_resume_identity_mismatch",
                "native resume did not complete on the exact session identity",
            )

    @staticmethod
    def _cleanup_and_join(
        *,
        requests: list[ProviderSupervisionMemberRequest],
        futures: dict[int, Future[Any]],
        members: ThreadPoolExecutor | None,
    ) -> None:
        cleanup_deadline = time.monotonic() + _CLEANUP_TIMEOUT_SEC
        errors: list[str] = []
        cancellation_results: dict[int, Any] = {}
        cancellation_errors: dict[int, Exception] = {}
        cancellation_lock = threading.Lock()
        launched = [
            request
            for request in requests
            if id(request) in futures
        ]
        active = [
            request
            for request in launched
            if not futures[id(request)].done()
        ]
        for request in active:
            try:
                request.control.request_cancel(
                    reason="provider_supervision_failure",
                    grace=0.2,
                )
            except Exception as exc:
                errors.append(str(exc))

        def cancel_and_reap(
            request: ProviderSupervisionMemberRequest,
        ) -> None:
            try:
                proof = request.control.cancel_and_reap(grace=0.2)
            except Exception as exc:
                with cancellation_lock:
                    cancellation_errors[id(request)] = exc
            else:
                with cancellation_lock:
                    cancellation_results[id(request)] = proof

        cancellation_helpers: dict[int, threading.Thread] = {}
        for request in active:
            helper = threading.Thread(
                target=cancel_and_reap,
                args=(request,),
                name=(
                    "provider-supervision-cleanup-"
                    f"{request.turn.turn_role}"
                ),
                daemon=True,
            )
            cancellation_helpers[id(request)] = helper
            helper.start()

        for request in active:
            helper = cancellation_helpers[id(request)]
            if helper.is_alive():
                helper.join(
                    timeout=max(cleanup_deadline - time.monotonic(), 0.0)
                )
            if helper.is_alive():
                errors.append(
                    f"{request.turn.turn_role} cleanup cancellation timed out"
                )
            else:
                error = cancellation_errors.get(id(request))
                if error is not None:
                    errors.append(str(error))

        for request in launched:
            future = futures[id(request)]
            if not future.done():
                remaining = cleanup_deadline - time.monotonic()
                if remaining <= 0:
                    errors.append(
                        f"{request.turn.turn_role} cleanup future timed out"
                    )
                    continue
                try:
                    future.result(timeout=remaining)
                except TimeoutError:
                    errors.append(
                        f"{request.turn.turn_role} cleanup future timed out"
                    )
                except Exception as exc:
                    if request in active:
                        errors.append(str(exc))
            else:
                try:
                    future.result()
                except Exception as exc:
                    if request in active:
                        errors.append(str(exc))

        for request in active:
            proof = cancellation_results.get(id(request))
            if proof is None:
                errors.append(
                    f"{request.turn.turn_role} cleanup proof is missing"
                )
                continue
            disposition = getattr(proof, "disposition", None)
            pgid = getattr(proof, "pgid", None)
            if (
                getattr(proof, "execution_joined", None) is not True
                or getattr(proof, "capture_threads_joined", None) is not True
                or getattr(
                    proof,
                    "natural_exit_with_lingering_group",
                    None,
                )
                is not False
            ):
                errors.append(
                    f"{request.turn.turn_role} cleanup join proof is incomplete"
                )
                continue
            if pgid is None:
                if disposition != "spawn_failed":
                    errors.append(
                        f"{request.turn.turn_role} cleanup has no process proof"
                    )
                continue
            if (
                getattr(proof, "leader_reaped", None) is not True
                or getattr(proof, "pgid_empty", None) is not True
            ):
                errors.append(
                    f"{request.turn.turn_role} process cleanup is incomplete"
                )
        if members is not None:
            members.shutdown(
                wait=not errors,
                cancel_futures=True,
            )
        if errors:
            raise _CoordinatorCleanupFailure("; ".join(errors))

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


class _CoordinatorCleanupFailure(RuntimeError):
    """Terminal publication is forbidden because cleanup is unproved."""
