"""Single-writer lifecycle tests for one provider peer-group visit."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from concurrent.futures import Future
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Lock, Thread
import time
from typing import Any
from uuid import uuid4

import pytest

import orchestrator.providers.interactive_terminal as interactive_terminal_module
import orchestrator.workflow.provider_peer_group.bindings as peer_bindings
from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalError,
    NaturalShutdownProof,
    OfferReceipt,
)
from orchestrator.providers.types import InteractiveSessionSupport
from orchestrator.workflow.provider_peer_group.bindings import (
    PeerGroupAllocation,
    PeerMemberAllocation,
)
from orchestrator.workflow.provider_peer_group.coordinator import (
    ProviderPeerGroupCoordinator,
)
from orchestrator.workflow.provider_peer_group.models import (
    FrozenPeerMemberResult,
    PeerAcknowledgeReceipt,
    PeerAcknowledgeRequest,
    PeerAttemptIdentity,
    PeerEndpointIdentity,
    PeerFailureReceipt,
    PeerFinishReceipt,
    PeerFinishRequest,
    PeerGroupRuntimeBinding,
    PeerGroupTerminalEvidence,
    PeerGroupVisitIdentity,
    PeerMemberLifecycle,
    PeerMemberRuntimeBinding,
    PeerReadyReceipt,
    PeerReadyRequest,
    PeerReceipt,
    PeerRequest,
    PeerSendReceipt,
    PeerSendRequest,
    PeerSenderBinding,
)
from orchestrator.workflow.provider_peer_group.paths import (
    derive_provider_peer_group_paths,
    realize_provider_peer_group_paths,
)
from orchestrator.workflow.provider_peer_group.protocol import (
    PeerEndpointCloseProof,
    PeerProtocolClosedError,
    PeerProtocolEvent,
    PeerProtocolListener,
)


_WAIT_SECONDS = 2.0
_CLOSED = object()


def _wait_until(predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + _WAIT_SECONDS
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("timed out waiting for coordinator activity")
        time.sleep(0.005)


def _ledger_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="ascii").splitlines()
    ]


class _FakeListener:
    """Queue-backed listener with the exact coordinator-facing surface."""

    def __init__(
        self,
        endpoint_identity: PeerEndpointIdentity,
        socket_path: Path,
    ) -> None:
        self.endpoint_identity = endpoint_identity
        self.socket_path = socket_path
        self.started = Event()
        self.closed = Event()
        self.workers_joined = False
        self.events: Queue[PeerProtocolEvent | BaseException | object] = Queue()
        self.resolutions: list[tuple[PeerProtocolEvent, PeerReceipt]] = []
        self.pending: dict[int, Future[PeerReceipt]] = {}
        self.before_resolve: Callable[
            [PeerProtocolEvent, PeerReceipt], None
        ] | None = None
        self.close_proof = PeerEndpointCloseProof(
            drained=True,
            closed=True,
            workers_joined=True,
        )
        self.close_error: BaseException | None = None
        self._lock = Lock()

    def start(self) -> None:
        self.started.set()

    def submit(
        self,
        request: PeerRequest,
        *,
        endpoint_identity: PeerEndpointIdentity | None = None,
    ) -> Future[PeerReceipt]:
        waiter: Future[PeerReceipt] = Future()
        event = PeerProtocolEvent(
            endpoint_identity=endpoint_identity or self.endpoint_identity,
            request=request,
            _waiter=waiter,
        )
        with self._lock:
            if self.closed.is_set():
                waiter.set_exception(
                    PeerProtocolClosedError("test endpoint is closed")
                )
                return waiter
            self.pending[id(event)] = waiter
        self.events.put(event)
        return waiter

    def receive_event(self, *, timeout_sec: float) -> PeerProtocolEvent:
        try:
            event = self.events.get(timeout=timeout_sec)
        except Empty as exc:
            raise TimeoutError from exc
        if event is _CLOSED:
            raise PeerProtocolClosedError("test endpoint is closed")
        if isinstance(event, BaseException):
            raise event
        assert isinstance(event, PeerProtocolEvent)
        return event

    def resolve(
        self,
        event: PeerProtocolEvent,
        receipt: PeerReceipt,
    ) -> None:
        if self.before_resolve is not None:
            self.before_resolve(event, receipt)
        with self._lock:
            waiter = self.pending.pop(id(event))
            self.resolutions.append((event, receipt))
            waiter.set_result(receipt)

    def fail(self, exc: BaseException) -> None:
        self.events.put(exc)

    def close(self) -> PeerEndpointCloseProof:
        if self.close_error is not None:
            raise self.close_error
        if self.closed.is_set():
            return self.close_proof
        self.closed.set()
        with self._lock:
            waiters = tuple(self.pending.values())
            self.pending.clear()
        for waiter in waiters:
            if not waiter.done():
                waiter.set_exception(
                    PeerProtocolClosedError(
                        "test endpoint closed before receipt"
                    )
                )
        self.events.put(_CLOSED)
        self.workers_joined = self.close_proof.workers_joined
        return self.close_proof


class _FakeAdapter:
    """Complete adapter double; controls failures and natural join timing."""

    def __init__(self, member_id: str, runtime_root: Path) -> None:
        self.member_id = member_id
        self.runtime_root = runtime_root
        self.handle: InteractiveMemberHandle | None = None
        self.calls: list[tuple[str, Any]] = []
        self.offered_literals: list[str] = []
        self.start_entered = Event()
        self.start_gate = Event()
        self.start_gate.set()
        self.close_offered = Event()
        self.close_entered = Event()
        self.close_gate = Event()
        self.close_gate.set()
        self.join_entered = Event()
        self.join_gate = Event()
        self.join_gate.set()
        self.aborted = Event()
        self.start_error: BaseException | None = None
        self.offer_error: BaseException | None = None
        self.close_error: BaseException | None = None
        self.join_error: BaseException | None = None
        self.cleanup_complete = True
        self.on_start: Callable[[], None] | None = None
        self.on_offer: Callable[[str], None] | None = None
        self.on_close: Callable[[], None] | None = None
        self.deadlines: list[tuple[str, float]] = []

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> object:
        self.calls.append(("start", invocation))
        self.deadlines.append(("start", deadline))
        self.start_entered.set()
        if not self.start_gate.wait(_WAIT_SECONDS):
            raise RuntimeError("test start gate timed out")
        if self.on_start is not None:
            self.on_start()
        if self.start_error is not None:
            start_outcome_type = getattr(
                interactive_terminal_module,
                "InteractiveTerminalStartOutcome",
            )
            if (
                isinstance(self.start_error, InteractiveTerminalError)
                and self.start_error.code
                == "interactive_terminal_start_cleanup_incomplete"
            ):
                cleanup_type = getattr(
                    interactive_terminal_module,
                    "PhasedFailedCleanupEvidence",
                )
                return start_outcome_type(
                    status="failed",
                    error_code=self.start_error.code,
                    backend_allocation="possible_or_allocated",
                    cleanup_status="incomplete",
                    provider_zero_survivor_proven=False,
                    proof=cleanup_type(
                        disposition="failed_cleanup",
                        pane_absent=False,
                        server_absent=False,
                        cleanup_complete=False,
                        error_code=self.start_error.code,
                    ),
                )
            if isinstance(self.start_error, InteractiveTerminalError):
                no_allocation_type = getattr(
                    interactive_terminal_module,
                    "NoBackendAllocationProof",
                )
                return start_outcome_type(
                    status="failed",
                    error_code=self.start_error.code,
                    backend_allocation="none",
                    cleanup_status="not_required",
                    provider_zero_survivor_proven=True,
                    proof=no_allocation_type(
                        disposition="no_backend_allocation",
                        backend_resource_allocated=False,
                        proof_complete=True,
                    ),
                )
            raise self.start_error
        handle = InteractiveMemberHandle(
            adapter_instance_id=f"adapter-{self.member_id}",
            handle_id=f"handle-{self.member_id}",
            invocation_id=invocation.invocation_id,
            member_id=invocation.member_id,
            attempt_scope_key=invocation.attempt_scope_key,
            attempt_ordinal=invocation.attempt_ordinal,
            target=f"pane-{self.member_id}",
            socket_path=(
                self.runtime_root / f"{self.member_id}-adapter.sock"
            ),
        )
        self.handle = handle
        start_outcome_type = getattr(
            interactive_terminal_module,
            "InteractiveTerminalStartOutcome",
        )
        return start_outcome_type(status="started", handle=handle)

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        assert handle == self.handle
        self.deadlines.append(("offer", deadline))
        self.calls.append(("offer", literal_message))
        self.offered_literals.append(literal_message)
        if self.on_offer is not None:
            self.on_offer(literal_message)
        if self.offer_error is not None:
            raise self.offer_error
        encoded = literal_message.encode("utf-8")
        return OfferReceipt(
            status="offered",
            handle_id=handle.handle_id,
            byte_count=len(encoded),
            content_sha256=(
                "sha256:" + hashlib.sha256(encoded).hexdigest()
            ),
        )

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt:
        assert handle == self.handle
        self.deadlines.append(("offer_close", deadline))
        self.calls.append(("offer_close", handle.handle_id))
        self.close_entered.set()
        self.close_gate.wait()
        if self.on_close is not None:
            self.on_close()
        if self.close_error is not None:
            raise self.close_error
        self.close_offered.set()
        return CloseOfferReceipt(
            status="close_offered",
            handle_id=handle.handle_id,
        )

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof:
        assert handle == self.handle
        self.calls.append(("join", deadline))
        self.join_entered.set()
        if not self.join_gate.wait(_WAIT_SECONDS):
            raise InteractiveTerminalError("natural_shutdown_timeout")
        if self.join_error is not None:
            raise self.join_error
        return NaturalShutdownProof(
            disposition="natural_exit",
            handle_id=handle.handle_id,
            return_code=0,
            pane_absent=True,
            server_absent=True,
            proof_complete=True,
        )

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof:
        assert handle == self.handle
        self.calls.append(("abort", deadline))
        self.aborted.set()
        return FailedCleanupProof(
            disposition="failed_cleanup",
            handle_id=handle.handle_id,
            pane_absent=self.cleanup_complete,
            server_absent=self.cleanup_complete,
            cleanup_complete=self.cleanup_complete,
            error_code=None if self.cleanup_complete else "cleanup_incomplete",
        )


class _FakeBindings:
    """Deterministic workflow seam; real files remain coordinator authority."""

    def __init__(self, allocation: PeerGroupAllocation) -> None:
        self.allocation = allocation
        self.adapters = {
            member.runtime.attempt.member_id: _FakeAdapter(
                member.runtime.attempt.member_id,
                allocation.realized_paths.visit_root,
            )
            for member in allocation.members
        }
        self.events: list[tuple[Any, ...]] = []
        self.bundle_values: dict[str, Any] = {
            member.runtime.attempt.member_id: {
                "member": member.runtime.attempt.member_id
            }
            for member in allocation.members
        }
        self.bundle_errors: dict[str, BaseException] = {}
        self.success_calls = 0
        self.failure_calls = 0
        self.settlement_order: tuple[str, ...] = ()

    def assert_current_step(self) -> None:
        self.events.append(("assert_current_step",))

    def allocate_group(self) -> PeerGroupAllocation:
        self.events.append(("allocate_group",))
        for member in self.allocation.members:
            path = member.realized_paths.prompt_dependencies_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                json.dumps(
                    {"member": member.runtime.attempt.member_id},
                    sort_keys=True,
                ).encode("ascii")
            )
        return self.allocation

    def reportable_group_identity(self) -> None:
        return None

    def create_adapter(
        self,
        member: PeerMemberAllocation,
    ) -> _FakeAdapter:
        member_id = member.runtime.attempt.member_id
        self.events.append(("create_adapter", member_id))
        return self.adapters[member_id]

    def validate_member_bundle(
        self,
        member: PeerMemberAllocation,
    ) -> FrozenPeerMemberResult:
        member_id = member.runtime.attempt.member_id
        self.events.append(("validate_bundle", member_id))
        if member_id in self.bundle_errors:
            raise self.bundle_errors[member_id]
        return FrozenPeerMemberResult.create(
            attempt=member.runtime.attempt,
            exact_bundle_bytes=(
                member.realized_paths.provisional_bundle_path.read_bytes()
            ),
            value=self.bundle_values[member_id],
        )

    def evaluate_settlement(
        self,
        *,
        resolved_bindings: Mapping[str, Any],
    ) -> Any:
        self.settlement_order = tuple(resolved_bindings)
        self.events.append(("evaluate_settlement", self.settlement_order))
        return list(resolved_bindings.values())

    def validate_settlement(self, *, value: Any) -> Any:
        self.events.append(("validate_settlement",))
        return value

    def finalize_success(
        self,
        *,
        settlement_value: Any,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]:
        self.success_calls += 1
        self.events.append(("finalize_success", evidence))
        return {
            "status": "completed",
            "exit_code": 0,
            "artifacts": {"__result__": settlement_value},
            "evidence": evidence,
        }

    def finalize_failure(
        self,
        *,
        evidence: PeerGroupTerminalEvidence,
    ) -> dict[str, Any]:
        self.failure_calls += 1
        self.events.append(("finalize_failure", evidence))
        return {
            "status": "failed",
            "exit_code": 2,
            "error": dict(evidence.failure or {}),
            "evidence": evidence,
        }


def _allocation(
    tmp_path: Path,
    member_ids: tuple[str, ...] = ("writer", "reviewer"),
    *,
    timeout_sec: float = 30.0,
) -> PeerGroupAllocation:
    visit = PeerGroupVisitIdentity(
        run_id="run-1",
        step_name="Peers",
        node_id="root.peers",
        visit_count=1,
    )
    plan = derive_provider_peer_group_paths(
        node_id=visit.node_id,
        member_ids=member_ids,
    )
    attempts = tuple(
        PeerAttemptIdentity(
            member_id=member_id,
            attempt_scope_key=f"scope-{member_id}",
            attempt_ordinal=index,
        )
        for index, member_id in enumerate(member_ids, start=1)
    )
    runtime_members = tuple(
        PeerMemberRuntimeBinding(
            attempt=attempt,
            timeout_sec=timeout_sec,
            paths=path,
        )
        for attempt, path in zip(attempts, plan.members, strict=True)
    )
    runtime = PeerGroupRuntimeBinding(
        visit=visit,
        members=runtime_members,
        messaging_policy="all_other_members",
        max_steers=0,
    )
    realized = realize_provider_peer_group_paths(
        run_root=tmp_path / "run",
        plan=plan,
        visit_count=visit.visit_count,
        attempt_ordinals={
            attempt.member_id: attempt.attempt_ordinal
            for attempt in attempts
        },
    )
    endpoint = PeerEndpointIdentity(
        group_visit=visit,
        endpoint_instance_id="endpoint-1",
    )
    support = InteractiveSessionSupport(
        schema_version="interactive_terminal_turn_queue.v1",
        turn_boundary_messages=True,
        command=("provider-client", "${PROMPT}"),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )
    members = tuple(
        PeerMemberAllocation(
            runtime=runtime_member,
            realized_paths=paths,
            sender=PeerSenderBinding(
                opaque_binding=f"opaque-{runtime_member.attempt.member_id}",
                attempt=runtime_member.attempt,
                endpoint_instance_id=endpoint.endpoint_instance_id,
            ),
            prompt_snapshot_sha256=(
                "sha256:"
                + hashlib.sha256(
                    json.dumps(
                        {"member": runtime_member.attempt.member_id},
                        sort_keys=True,
                    ).encode("ascii")
                ).hexdigest()
            ),
            invocation=InteractiveMemberInvocation(
                invocation_id=(
                    f"invocation-{runtime_member.attempt.member_id}"
                ),
                member_id=runtime_member.attempt.member_id,
                attempt_scope_key=runtime_member.attempt.attempt_scope_key,
                attempt_ordinal=runtime_member.attempt.attempt_ordinal,
                resolved_command=(
                    "provider-client",
                    "--prompt",
                    runtime_member.attempt.member_id,
                ),
                cwd=tmp_path,
                env={
                    "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(
                        paths.provisional_bundle_path
                    )
                },
                support=support,
            ),
        )
        for runtime_member, paths in zip(
            runtime_members,
            realized.members,
            strict=True,
        )
    )
    return PeerGroupAllocation(
        runtime=runtime,
        realized_paths=realized,
        endpoint=endpoint,
        endpoint_socket_path=(
            tmp_path.resolve() / "runtime" / "peer.sock"
        ),
        members=members,
    )


def test_endpoint_socket_path_falls_back_and_real_listener_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_tempdir = tmp_path / ("configured-" + ("x" * 120))
    long_tempdir.mkdir()
    monkeypatch.setattr(
        peer_bindings.tempfile,
        "gettempdir",
        lambda: str(long_tempdir),
    )
    base_endpoint = _allocation(tmp_path).endpoint
    paths: list[Path] = []

    for visit_count in (1, 2):
        endpoint = replace(
            base_endpoint,
            group_visit=replace(
                base_endpoint.group_visit,
                visit_count=visit_count,
            ),
            endpoint_instance_id=uuid4().hex,
        )
        path = peer_bindings._provider_peer_endpoint_socket_path(
            endpoint.endpoint_instance_id
        )
        paths.append(path)
        assert path.parent == Path("/tmp")
        assert len(os.fsencode(path)) <= 103

        listener = PeerProtocolListener(endpoint, path)
        listener.start()
        assert path.exists()
        proof = listener.close()

        assert proof == PeerEndpointCloseProof(
            drained=True,
            closed=True,
            workers_joined=True,
        )
        assert not path.exists()

    assert paths[0] != paths[1]


def test_endpoint_socket_path_rejects_exhausted_candidates_before_listener(
    tmp_path: Path,
) -> None:
    long_roots = tuple(
        tmp_path / (label + ("x" * 120))
        for label in ("first-", "second-")
    )
    for root in long_roots:
        root.mkdir()

    with pytest.raises(
        ValueError,
        match="^provider_peer_group_endpoint_path_unavailable$",
    ):
        peer_bindings._provider_peer_endpoint_socket_path(
            uuid4().hex,
            candidate_roots=long_roots,
        )


@dataclass
class _Harness:
    allocation: PeerGroupAllocation
    bindings: _FakeBindings
    listener: _FakeListener
    coordinator: ProviderPeerGroupCoordinator
    outcome: Future[dict[str, Any]]
    thread: Thread

    def sender(self, member_id: str) -> str:
        return next(
            member.sender.opaque_binding
            for member in self.allocation.members
            if member.runtime.attempt.member_id == member_id
        )

    def member(self, member_id: str) -> PeerMemberAllocation:
        return next(
            member
            for member in self.allocation.members
            if member.runtime.attempt.member_id == member_id
        )

    def write_bundles(self) -> None:
        for member in self.allocation.members:
            path = member.realized_paths.provisional_bundle_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(
                json.dumps(
                    {"result": member.runtime.attempt.member_id},
                    sort_keys=True,
                ).encode("ascii")
            )

    def ready(self) -> None:
        futures = [
            self.listener.submit(
                PeerReadyRequest(
                    request_id=f"ready-{member.runtime.attempt.member_id}",
                    sender_binding=member.sender.opaque_binding,
                )
            )
            for member in self.allocation.members
        ]
        assert all(
            isinstance(future.result(_WAIT_SECONDS), PeerReadyReceipt)
            for future in futures
        )

    def finish_all(self) -> None:
        self.write_bundles()
        futures = [
            self.listener.submit(
                PeerFinishRequest(
                    request_id=f"finish-{member.runtime.attempt.member_id}",
                    sender_binding=member.sender.opaque_binding,
                )
            )
            for member in self.allocation.members
        ]
        assert all(
            isinstance(future.result(_WAIT_SECONDS), PeerFinishReceipt)
            for future in futures
        )


@contextmanager
def _running_group(
    tmp_path: Path,
    member_ids: tuple[str, ...] = ("writer", "reviewer"),
    *,
    configure: Callable[[_FakeBindings], None] | None = None,
    timeout_sec: float = 30.0,
) -> Iterator[_Harness]:
    allocation = _allocation(
        tmp_path,
        member_ids,
        timeout_sec=timeout_sec,
    )
    bindings = _FakeBindings(allocation)
    if configure is not None:
        configure(bindings)
    listener = _FakeListener(
        allocation.endpoint,
        allocation.endpoint_socket_path,
    )

    def listener_factory(
        endpoint: PeerEndpointIdentity,
        socket_path: Path,
    ) -> _FakeListener:
        assert endpoint == allocation.endpoint
        assert socket_path == allocation.endpoint_socket_path
        return listener

    coordinator = ProviderPeerGroupCoordinator(
        bindings,
        listener_factory,
        bindings.create_adapter,
        monotonic=time.monotonic,
    )
    outcome: Future[dict[str, Any]] = Future()

    def run() -> None:
        try:
            outcome.set_result(coordinator.run())
        except BaseException as exc:
            outcome.set_exception(exc)

    thread = Thread(target=run, name="test-peer-coordinator", daemon=True)
    thread.start()
    harness = _Harness(
        allocation,
        bindings,
        listener,
        coordinator,
        outcome,
        thread,
    )
    try:
        _wait_until(listener.started.is_set)
        yield harness
    finally:
        for adapter in bindings.adapters.values():
            adapter.start_gate.set()
            adapter.close_gate.set()
            adapter.join_gate.set()
        listener.close()
        thread.join(timeout=_WAIT_SECONDS)


def test_all_members_are_allocated_before_the_first_launch(
    tmp_path: Path,
) -> None:
    allocation_checked = Event()

    def configure(bindings: _FakeBindings) -> None:
        def assert_complete_allocation() -> None:
            allocation = bindings.allocation
            assert all(
                member.realized_paths.prompt_dependencies_path.is_file()
                for member in allocation.members
            )
            assert all(
                member.realized_paths.injected_messages_path.is_file()
                for member in allocation.members
            )
            assert all(
                _ledger_rows(
                    member.realized_paths.injected_messages_path
                )[0]["row_kind"]
                == "header"
                for member in allocation.members
            )
            assert all(
                member.invocation.env[
                    "ORCHESTRATOR_OUTPUT_BUNDLE_PATH"
                ]
                == str(member.realized_paths.provisional_bundle_path)
                for member in allocation.members
            )
            allocation_checked.set()

        bindings.adapters["writer"].on_start = assert_complete_allocation

    with _running_group(
        tmp_path,
        ("writer", "reviewer", "critic"),
        configure=configure,
    ) as group:
        _wait_until(
            lambda: all(
                adapter.handle is not None
                for adapter in group.bindings.adapters.values()
            )
        )
        assert allocation_checked.is_set()
        group.ready()
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


def test_start_cleanup_incomplete_propagates_after_cleanup_without_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allocation = _allocation(
        tmp_path,
        ("writer", "reviewer", "critic"),
    )
    bindings = _FakeBindings(allocation)
    listener = _FakeListener(
        allocation.endpoint,
        allocation.endpoint_socket_path,
    )
    startup_error = InteractiveTerminalError(
        "interactive_terminal_start_cleanup_incomplete"
    )
    bindings.adapters["critic"].start_error = startup_error
    cleanup_order: list[str] = []
    close_listener = listener.close

    def record_endpoint_close() -> PeerEndpointCloseProof:
        cleanup_order.append("endpoint")
        return close_listener()

    monkeypatch.setattr(listener, "close", record_endpoint_close)
    for member_id in ("writer", "reviewer"):
        adapter = bindings.adapters[member_id]
        abort_member = adapter.abort

        def record_abort(
            handle: InteractiveMemberHandle,
            deadline: float,
            *,
            _member_id: str = member_id,
            _abort: Callable[
                [InteractiveMemberHandle, float],
                FailedCleanupProof,
            ] = abort_member,
        ) -> FailedCleanupProof:
            cleanup_order.append(f"abort:{_member_id}")
            return _abort(handle, deadline)

        monkeypatch.setattr(adapter, "abort", record_abort)
    coordinator = ProviderPeerGroupCoordinator(
        bindings,
        lambda _endpoint, _path: listener,
        bindings.create_adapter,
    )

    with pytest.raises(InteractiveTerminalError) as exc_info:
        coordinator.run()

    assert exc_info.value.code == startup_error.code
    assert listener.closed.is_set()
    assert listener.workers_joined is True
    assert cleanup_order[0] == "endpoint"
    assert set(cleanup_order[1:]) == {
        "abort:writer",
        "abort:reviewer",
    }
    assert all(
        bindings.adapters[member_id].aborted.is_set()
        for member_id in ("writer", "reviewer")
    )
    abort_deadlines = tuple(
        next(
            call[1]
            for call in bindings.adapters[member_id].calls
            if call[0] == "abort"
        )
        for member_id in ("writer", "reviewer")
    )
    assert abort_deadlines[0] == abort_deadlines[1]
    assert bindings.adapters["critic"].handle is None
    assert all(
        call[0] != "abort"
        for call in bindings.adapters["critic"].calls
    )
    assert bindings.success_calls == 0
    assert bindings.failure_calls == 0
    assert all(
        event[0] != "finalize_failure" for event in bindings.events
    )
    assert not allocation.realized_paths.terminal_evidence_path.exists()
    assert all(
        not member.realized_paths.evidence_path.exists()
        for member in allocation.members
    )


def test_prompt_snapshot_digest_is_checked_before_any_launch(
    tmp_path: Path,
) -> None:
    allocation = _allocation(tmp_path)
    bindings = _FakeBindings(allocation)
    listener = _FakeListener(
        allocation.endpoint,
        allocation.endpoint_socket_path,
    )
    allocate_group = bindings.allocate_group

    def allocate_tampered_group() -> PeerGroupAllocation:
        result = allocate_group()
        result.members[0].realized_paths.prompt_dependencies_path.write_bytes(
            b"tampered"
        )
        return result

    bindings.allocate_group = allocate_tampered_group  # type: ignore[method-assign]
    coordinator = ProviderPeerGroupCoordinator(
        bindings,
        lambda _endpoint, _path: listener,
        bindings.create_adapter,
    )

    result = coordinator.run()

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "provider_peer_group_prompt_snapshot_mismatch",
        "message": "prompt snapshot changed for writer",
    }
    assert bindings.failure_calls == 1
    assert bindings.success_calls == 0
    assert all(
        not adapter.calls for adapter in bindings.adapters.values()
    )
    assert all(
        not member.realized_paths.injected_messages_path.exists()
        for member in allocation.members
    )


def test_adapter_preparation_failure_finalizes_the_allocated_group_once(
    tmp_path: Path,
) -> None:
    allocation = _allocation(tmp_path)
    bindings = _FakeBindings(allocation)
    adapter_attempts: list[str] = []

    def fail_adapter(member: PeerMemberAllocation) -> _FakeAdapter:
        adapter_attempts.append(member.runtime.attempt.member_id)
        raise ValueError("adapter preparation failed")

    def forbid_listener(*_args: Any) -> _FakeListener:
        raise AssertionError("preparation failure must not create ingress")

    result = ProviderPeerGroupCoordinator(
        bindings,
        forbid_listener,
        fail_adapter,
    ).run()

    assert result["status"] == "failed"
    assert result["error"] == {
        "code": "provider_peer_group_failed",
        "message": "adapter preparation failed",
    }
    assert adapter_attempts == ["writer"]
    assert bindings.failure_calls == 1
    assert bindings.success_calls == 0
    assert all(
        not adapter.calls for adapter in bindings.adapters.values()
    )
    evidence = result["evidence"]
    assert isinstance(evidence, PeerGroupTerminalEvidence)
    assert evidence.group_visit == allocation.runtime.visit
    assert tuple(member.attempt for member in evidence.members) == tuple(
        member.runtime.attempt for member in allocation.members
    )
    assert all(
        member.lifecycle is PeerMemberLifecycle.FAILED
        for member in evidence.members
    )


def test_group_allocation_rejects_ambiguous_sender_bindings(
    tmp_path: Path,
) -> None:
    allocation = _allocation(tmp_path)
    first, second = allocation.members
    ambiguous_second = replace(
        second,
        sender=replace(
            second.sender,
            opaque_binding=first.sender.opaque_binding,
        ),
    )

    with pytest.raises(ValueError, match="sender bindings"):
        replace(
            allocation,
            members=(first, ambiguous_second),
        )


def test_ready_is_one_group_barrier(tmp_path: Path) -> None:
    with _running_group(
        tmp_path,
        ("writer", "reviewer", "critic"),
    ) as group:
        first = group.listener.submit(
            PeerReadyRequest("ready-writer", group.sender("writer"))
        )
        second = group.listener.submit(
            PeerReadyRequest("ready-reviewer", group.sender("reviewer"))
        )
        _wait_until(lambda: len(group.listener.pending) == 2)
        time.sleep(0.02)
        assert not first.done()
        assert not second.done()

        third = group.listener.submit(
            PeerReadyRequest("ready-critic", group.sender("critic"))
        )

        assert isinstance(first.result(_WAIT_SECONDS), PeerReadyReceipt)
        assert isinstance(second.result(_WAIT_SECONDS), PeerReadyReceipt)
        assert isinstance(third.result(_WAIT_SECONDS), PeerReadyReceipt)
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


def test_peer_coordinator_passes_one_member_deadline_to_start_offer_and_close(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        sent = group.listener.submit(
            PeerSendRequest(
                "deadline-send",
                group.sender("writer"),
                "reviewer",
                "deadline-preserving message",
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(sent, PeerSendReceipt)
        acknowledged = group.listener.submit(
            PeerAcknowledgeRequest(
                "deadline-ack",
                group.sender("reviewer"),
                sent.message_id,
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(acknowledged, PeerAcknowledgeReceipt)
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"

        for adapter in group.bindings.adapters.values():
            assert adapter.deadlines
            [deadline] = {
                value for _operation, value in adapter.deadlines
            }
            assert deadline > time.monotonic()
        reviewer_deadlines = [
            operation
            for operation, _deadline
            in group.bindings.adapters["reviewer"].deadlines
        ]
        assert reviewer_deadlines == ["start", "offer", "offer_close"]


def test_ready_barrier_publishes_no_mixed_active_snapshot(
    tmp_path: Path,
) -> None:
    with _running_group(
        tmp_path,
        ("writer", "reviewer", "critic"),
    ) as group:
        snapshots: list[dict[str, PeerMemberLifecycle]] = []
        publish = group.coordinator._publish_lifecycle

        def capture(
            members,
            *,
            merge: bool = False,
        ) -> None:
            publish(members, merge=merge)
            snapshots.append(dict(group.coordinator.lifecycle_snapshot))

        group.coordinator._publish_lifecycle = capture  # type: ignore[method-assign]
        group.ready()

        assert not any(
            PeerMemberLifecycle.ACTIVE in snapshot.values()
            and PeerMemberLifecycle.READY_WAITING in snapshot.values()
            for snapshot in snapshots
        )
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


def test_send_before_the_group_barrier_fails_without_a_ledger_row(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        reviewer = group.member("reviewer")
        receipt = group.listener.submit(
            PeerSendRequest(
                "send-before-ready",
                group.sender("writer"),
                "reviewer",
                "too early",
            )
        ).result(_WAIT_SECONDS)

        assert isinstance(receipt, PeerFailureReceipt)
        assert [
            row["row_kind"]
            for row in _ledger_rows(
                reviewer.realized_paths.injected_messages_path
            )
        ] == ["header"]
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "failed"


def test_barrier_failure_resolves_waiters_and_joins_resources(
    tmp_path: Path,
) -> None:
    allocation = _allocation(tmp_path)
    bindings = _FakeBindings(allocation)
    bindings.adapters["writer"].start_gate.clear()
    bindings.adapters["reviewer"].start_error = InteractiveTerminalError(
        "pane_start_failed"
    )
    listener = _FakeListener(
        allocation.endpoint,
        allocation.endpoint_socket_path,
    )
    coordinator = ProviderPeerGroupCoordinator(
        bindings,
        lambda _endpoint, _path: listener,
        bindings.create_adapter,
        monotonic=time.monotonic,
    )
    outcome: Future[dict[str, Any]] = Future()
    thread = Thread(
        target=lambda: outcome.set_result(coordinator.run()),
        daemon=True,
    )
    thread.start()
    assert bindings.adapters["writer"].start_entered.wait(_WAIT_SECONDS)
    waiter = listener.submit(
        PeerReadyRequest("ready-writer", "opaque-writer")
    )
    bindings.adapters["writer"].start_gate.set()

    result = outcome.result(_WAIT_SECONDS)

    assert result["status"] == "failed"
    assert waiter.done()
    with pytest.raises(PeerProtocolClosedError):
        waiter.result()
    assert bindings.adapters["writer"].aborted.is_set()
    assert listener.closed.is_set()
    assert listener.workers_joined
    assert bindings.success_calls == 0
    thread.join(_WAIT_SECONDS)


def test_send_records_before_offer_and_offers_before_success(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        receiver = group.member("reviewer")
        ledger_path = receiver.realized_paths.injected_messages_path
        adapter = group.bindings.adapters["reviewer"]
        observed: list[str] = []

        def inspect_before_offer(literal: str) -> None:
            rows = _ledger_rows(ledger_path)
            assert [row["row_kind"] for row in rows] == [
                "header",
                "recorded",
            ]
            assert rows[-1]["sender_attempt"]["member_id"] == "writer"
            assert rows[-1]["receiver_attempt"]["member_id"] == "reviewer"
            assert rows[-1]["content"] == "hello\nλ"
            assert literal.endswith("hello\nλ")
            observed.append("recorded")

        def inspect_before_success(
            event: PeerProtocolEvent,
            receipt: PeerReceipt,
        ) -> None:
            if isinstance(receipt, PeerSendReceipt):
                assert [
                    row["row_kind"] for row in _ledger_rows(ledger_path)
                ] == ["header", "recorded", "offered"]
                observed.append("offered")

        adapter.on_offer = inspect_before_offer
        group.listener.before_resolve = inspect_before_success
        receipt = group.listener.submit(
            PeerSendRequest(
                request_id="send-1",
                sender_binding=group.sender("writer"),
                target_binding="reviewer",
                message="hello\nλ",
            )
        ).result(_WAIT_SECONDS)

        assert isinstance(receipt, PeerSendReceipt)
        assert observed == ["recorded", "offered"]
        group.listener.submit(
            PeerAcknowledgeRequest(
                "ack-1",
                group.sender("reviewer"),
                receipt.message_id,
            )
        ).result(_WAIT_SECONDS)
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


@pytest.mark.parametrize(
    ("sender", "target", "stale_sender"),
    (
        ("writer", "writer", False),
        ("writer", "missing", False),
        ("writer", "reviewer", True),
    ),
    ids=("self", "unknown-target", "stale-sender"),
)
def test_rejected_sends_have_no_ledger_or_adapter_effect(
    tmp_path: Path,
    sender: str,
    target: str,
    stale_sender: bool,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        reviewer = group.member("reviewer")
        before = _ledger_rows(
            reviewer.realized_paths.injected_messages_path
        )
        future = group.listener.submit(
            PeerSendRequest(
                request_id="rejected-send",
                sender_binding=(
                    "opaque-stale"
                    if stale_sender
                    else group.sender(sender)
                ),
                target_binding=target,
                message="must not deliver",
            ),
        )

        receipt = future.result(_WAIT_SECONDS)

        assert isinstance(receipt, PeerFailureReceipt)
        assert (
            _ledger_rows(reviewer.realized_paths.injected_messages_path)
            == before
        )
        assert not group.bindings.adapters["reviewer"].offered_literals
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "failed"
        assert group.bindings.success_calls == 0


def test_offer_failure_is_durable_and_fails_the_group(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        group.bindings.adapters["reviewer"].offer_error = (
            InteractiveTerminalError("offer_failed")
        )
        future = group.listener.submit(
            PeerSendRequest(
                "send-fails",
                group.sender("writer"),
                "reviewer",
                "hello",
            )
        )

        receipt = future.result(_WAIT_SECONDS)
        result = group.outcome.result(_WAIT_SECONDS)
        rows = _ledger_rows(
            group.member("reviewer").realized_paths.injected_messages_path
        )

        assert isinstance(receipt, PeerFailureReceipt)
        assert [row["row_kind"] for row in rows] == [
            "header",
            "recorded",
            "offer_failed",
        ]
        assert result["status"] == "failed"
        assert group.bindings.success_calls == 0


def test_ack_is_bound_to_the_exact_receiver_attempt(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        sent = group.listener.submit(
            PeerSendRequest(
                "send-1",
                group.sender("writer"),
                "reviewer",
                "hello",
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(sent, PeerSendReceipt)
        acknowledged = group.listener.submit(
            PeerAcknowledgeRequest(
                "ack-1",
                group.sender("reviewer"),
                sent.message_id,
            )
        ).result(_WAIT_SECONDS)

        assert acknowledged == PeerAcknowledgeReceipt(
            "ack-1",
            sent.message_id,
        )
        assert _ledger_rows(
            group.member("reviewer").realized_paths.injected_messages_path
        )[-1]["row_kind"] == "receiver_acknowledged"
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


def test_second_ack_request_for_one_message_fails_the_group(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        sent = group.listener.submit(
            PeerSendRequest(
                "send-1",
                group.sender("writer"),
                "reviewer",
                "hello",
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(sent, PeerSendReceipt)
        group.listener.submit(
            PeerAcknowledgeRequest(
                "ack-1",
                group.sender("reviewer"),
                sent.message_id,
            )
        ).result(_WAIT_SECONDS)

        duplicate = group.listener.submit(
            PeerAcknowledgeRequest(
                "ack-2",
                group.sender("reviewer"),
                sent.message_id,
            )
        ).result(_WAIT_SECONDS)

        assert isinstance(duplicate, PeerFailureReceipt)
        rows = _ledger_rows(
            group.member("reviewer").realized_paths.injected_messages_path
        )
        assert sum(
            row["row_kind"] == "receiver_acknowledged"
            for row in rows
        ) == 1
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "failed"


@pytest.mark.parametrize("wrong_member", ("writer", "critic"))
def test_unknown_or_wrong_attempt_ack_fails_closed(
    tmp_path: Path,
    wrong_member: str,
) -> None:
    member_ids = (
        ("writer", "reviewer")
        if wrong_member == "writer"
        else ("writer", "reviewer", "critic")
    )
    with _running_group(tmp_path, member_ids) as group:
        group.ready()
        message_id = (
            group.listener.submit(
                PeerSendRequest(
                    "send-1",
                    group.sender("writer"),
                    "reviewer",
                    "hello",
                )
            )
            .result(_WAIT_SECONDS)
            .message_id  # type: ignore[union-attr]
        )
        if wrong_member == "critic":
            sender_binding = group.sender("critic")
            ack_id = message_id
        else:
            sender_binding = group.sender("reviewer")
            ack_id = "unknown-message"
        receipt = group.listener.submit(
            PeerAcknowledgeRequest(
                "bad-ack",
                sender_binding,
                ack_id,
            )
        ).result(_WAIT_SECONDS)

        assert isinstance(receipt, PeerFailureReceipt)
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "failed"
        assert group.bindings.success_calls == 0


def test_request_replay_is_exact_and_idempotent(tmp_path: Path) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        request = PeerSendRequest(
            "send-once",
            group.sender("writer"),
            "reviewer",
            "hello",
        )
        first = group.listener.submit(request).result(_WAIT_SECONDS)
        replay = group.listener.submit(request).result(_WAIT_SECONDS)

        assert replay == first
        assert len(group.bindings.adapters["reviewer"].offered_literals) == 1
        assert [
            row["row_kind"]
            for row in _ledger_rows(
                group.member(
                    "reviewer"
                ).realized_paths.injected_messages_path
            )
        ] == ["header", "recorded", "offered"]

        conflict = group.listener.submit(
            PeerSendRequest(
                "send-once",
                group.sender("writer"),
                "reviewer",
                "different",
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(conflict, PeerFailureReceipt)
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "failed"


def test_concurrent_senders_share_one_total_order(tmp_path: Path) -> None:
    with _running_group(
        tmp_path,
        ("writer", "reviewer", "critic"),
    ) as group:
        group.ready()
        gate = Event()
        futures: list[Future[PeerReceipt]] = []
        lock = Lock()

        def submit(sender: str, request_id: str) -> None:
            gate.wait()
            future = group.listener.submit(
                PeerSendRequest(
                    request_id,
                    group.sender(sender),
                    "reviewer",
                    f"from-{sender}",
                )
            )
            with lock:
                futures.append(future)

        threads = [
            Thread(target=submit, args=("writer", "send-writer")),
            Thread(target=submit, args=("critic", "send-critic")),
        ]
        for thread in threads:
            thread.start()
        gate.set()
        for thread in threads:
            thread.join(_WAIT_SECONDS)
        receipts = [future.result(_WAIT_SECONDS) for future in futures]
        assert all(isinstance(item, PeerSendReceipt) for item in receipts)

        rows = _ledger_rows(
            group.member("reviewer").realized_paths.injected_messages_path
        )
        recorded_ids = [
            row["message_id"]
            for row in rows
            if row["row_kind"] == "recorded"
        ]
        offered_ids = [
            row["message_id"]
            for row in rows
            if row["row_kind"] == "offered"
        ]
        adapter_ids = [
            literal.splitlines()[1].removeprefix("message_id: ")
            for literal in group.bindings.adapters[
                "reviewer"
            ].offered_literals
        ]
        assert recorded_ids == offered_ids == adapter_ids
        assert len(set(recorded_ids)) == 2

        for receipt in receipts:
            assert isinstance(receipt, PeerSendReceipt)
            group.listener.submit(
                PeerAcknowledgeRequest(
                    f"ack-{receipt.message_id}",
                    group.sender("reviewer"),
                    receipt.message_id,
                )
            ).result(_WAIT_SECONDS)
        group.finish_all()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


def test_pending_finish_stays_active_until_incoming_ack(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        group.write_bundles()
        sent = group.listener.submit(
            PeerSendRequest(
                "send-1",
                group.sender("writer"),
                "reviewer",
                "hello",
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(sent, PeerSendReceipt)
        pending = group.listener.submit(
            PeerFinishRequest(
                "finish-pending",
                group.sender("reviewer"),
            )
        ).result(_WAIT_SECONDS)

        assert pending == PeerFinishReceipt.pending(
            "finish-pending",
            (sent.message_id,),
        )
        assert (
            "validate_bundle",
            "reviewer",
        ) not in group.bindings.events
        assert not group.bindings.adapters["reviewer"].close_offered.is_set()

        group.listener.submit(
            PeerAcknowledgeRequest(
                "ack-1",
                group.sender("reviewer"),
                sent.message_id,
            )
        ).result(_WAIT_SECONDS)
        closed = group.listener.submit(
            PeerFinishRequest(
                "finish-reviewer-retry",
                group.sender("reviewer"),
            )
        ).result(_WAIT_SECONDS)
        assert closed == PeerFinishReceipt.close_offered(
            "finish-reviewer-retry"
        )
        writer_closed = group.listener.submit(
            PeerFinishRequest(
                "finish-writer",
                group.sender("writer"),
            )
        ).result(_WAIT_SECONDS)
        assert isinstance(writer_closed, PeerFinishReceipt)
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "completed"


def test_finish_first_rejects_later_send_without_a_row(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        group.write_bundles()
        reviewer_adapter = group.bindings.adapters["reviewer"]
        reviewer_adapter.join_gate.clear()
        finish = group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        )
        assert finish.result(_WAIT_SECONDS) == PeerFinishReceipt.close_offered(
            "finish-reviewer"
        )
        assert reviewer_adapter.join_entered.wait(_WAIT_SECONDS)
        before = _ledger_rows(
            group.member("reviewer").realized_paths.injected_messages_path
        )

        rejected = group.listener.submit(
            PeerSendRequest(
                "send-too-late",
                group.sender("writer"),
                "reviewer",
                "late",
            )
        ).result(_WAIT_SECONDS)

        assert isinstance(rejected, PeerFailureReceipt)
        assert (
            _ledger_rows(
                group.member(
                    "reviewer"
                ).realized_paths.injected_messages_path
            )
            == before
        )
        reviewer_adapter.join_gate.set()
        assert group.outcome.result(_WAIT_SECONDS)["status"] == "failed"


def test_finish_freezes_then_receipts_before_natural_join(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        group.write_bundles()
        adapter = group.bindings.adapters["reviewer"]
        adapter.join_gate.clear()
        finish = group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        )

        assert finish.result(_WAIT_SECONDS) == PeerFinishReceipt.close_offered(
            "finish-reviewer"
        )
        assert adapter.close_offered.is_set()
        assert adapter.join_entered.wait(_WAIT_SECONDS)
        assert not group.outcome.done()
        assert ("validate_bundle", "reviewer") in group.bindings.events

        group.member(
            "reviewer"
        ).realized_paths.provisional_bundle_path.write_bytes(b'"mutated"')
        adapter.join_gate.set()
        group.listener.submit(
            PeerFinishRequest("finish-writer", group.sender("writer"))
        ).result(_WAIT_SECONDS)
        result = group.outcome.result(_WAIT_SECONDS)

        assert result["status"] == "completed"
        evidence = result["evidence"]
        reviewer_evidence = next(
            member
            for member in evidence.members
            if member.attempt.member_id == "reviewer"
        )
        original = json.dumps(
            {"result": "reviewer"},
            sort_keys=True,
        ).encode("ascii")
        assert reviewer_evidence.frozen_bundle_sha256 == (
            "sha256:" + hashlib.sha256(original).hexdigest()
        )


def test_settlement_waits_for_every_join_and_preserves_authored_order(
    tmp_path: Path,
) -> None:
    member_ids = ("writer", "reviewer", "critic")
    with _running_group(tmp_path, member_ids) as group:
        group.ready()
        group.write_bundles()
        held = group.bindings.adapters["critic"]
        held.join_gate.clear()
        finishes = [
            group.listener.submit(
                PeerFinishRequest(
                    f"finish-{member_id}",
                    group.sender(member_id),
                )
            )
            for member_id in member_ids
        ]
        assert all(
            isinstance(future.result(_WAIT_SECONDS), PeerFinishReceipt)
            for future in finishes
        )
        assert held.join_entered.wait(_WAIT_SECONDS)
        assert not group.outcome.done()
        assert group.bindings.success_calls == 0

        held.join_gate.set()
        result = group.outcome.result(_WAIT_SECONDS)

        assert result["status"] == "completed"
        assert group.bindings.settlement_order == member_ids
        assert group.bindings.success_calls == 1
        assert group.bindings.failure_calls == 0
        assert sum(
            event == ("assert_current_step",)
            for event in group.bindings.events
        ) == 2
        assert group.listener.closed.is_set()
        assert result["evidence"].endpoint_workers_joined is True


def test_incomplete_endpoint_close_proof_prevents_settlement_publication(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.listener.close_proof = PeerEndpointCloseProof(
            drained=True,
            closed=True,
            workers_joined=False,
        )
        group.ready()
        group.finish_all()

        with pytest.raises(RuntimeError, match="endpoint cleanup proof"):
            group.outcome.result(_WAIT_SECONDS)
        assert group.bindings.success_calls == 0
        assert group.bindings.failure_calls == 0


def test_endpoint_close_exception_prevents_terminal_finalization(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.listener.close_error = RuntimeError("listener close failed")
        group.ready()
        group.write_bundles()
        group.bindings.bundle_errors["reviewer"] = ValueError(
            "invalid typed bundle"
        )
        group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        )

        try:
            with pytest.raises(RuntimeError, match="endpoint cleanup failed"):
                group.outcome.result(_WAIT_SECONDS)
        finally:
            group.listener.close_error = None
        assert group.bindings.success_calls == 0
        assert group.bindings.failure_calls == 0


@pytest.mark.parametrize(
    "failure_point",
    (
        "invalid-bundle",
        "early-exit",
        "close-timeout",
        "join-timeout",
    ),
)
def test_finish_failures_cleanup_and_never_publish_settlement(
    tmp_path: Path,
    failure_point: str,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        group.write_bundles()
        adapter = group.bindings.adapters["reviewer"]
        if failure_point == "invalid-bundle":
            group.bindings.bundle_errors["reviewer"] = ValueError(
                "invalid typed bundle"
            )
        elif failure_point == "early-exit":
            adapter.close_error = InteractiveTerminalError("pane_lost")
        elif failure_point == "close-timeout":
            adapter.close_error = InteractiveTerminalError(
                "close_offer_timeout"
            )
        else:
            adapter.join_error = InteractiveTerminalError(
                "natural_shutdown_timeout"
            )
        receipt = group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        ).result(_WAIT_SECONDS)
        result = group.outcome.result(_WAIT_SECONDS)

        if failure_point == "join-timeout":
            assert isinstance(receipt, PeerFinishReceipt)
            assert receipt.status == "close_offered"
        else:
            assert isinstance(receipt, PeerFailureReceipt)
        assert result["status"] == "failed"
        assert group.bindings.success_calls == 0
        assert group.bindings.failure_calls == 1
        assert all(
            adapter.aborted.is_set()
            for adapter in group.bindings.adapters.values()
            if adapter.handle is not None
        )
        assert result["evidence"].settlement_sha256 is None


def test_incomplete_failure_cleanup_prevents_terminal_finalization(
    tmp_path: Path,
) -> None:
    with _running_group(tmp_path) as group:
        group.ready()
        group.write_bundles()
        group.bindings.bundle_errors["reviewer"] = ValueError(
            "invalid typed bundle"
        )
        for adapter in group.bindings.adapters.values():
            adapter.cleanup_complete = False

        group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        )
        with pytest.raises(RuntimeError, match="cleanup proof"):
            group.outcome.result(_WAIT_SECONDS)

        assert group.bindings.success_calls == 0
        assert group.bindings.failure_calls == 0
        assert all(
            adapter.aborted.is_set()
            for adapter in group.bindings.adapters.values()
            if adapter.handle is not None
        )


def test_stuck_join_cannot_block_failure_cleanup_past_its_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import coordinator

    monkeypatch.setattr(coordinator, "_CLEANUP_TIMEOUT_SECONDS", 0.05)
    with _running_group(tmp_path) as group:
        group.ready()
        group.write_bundles()
        reviewer = group.bindings.adapters["reviewer"]
        reviewer.join_gate.clear()
        finish = group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        )
        assert finish.result(_WAIT_SECONDS) == PeerFinishReceipt.close_offered(
            "finish-reviewer"
        )
        assert reviewer.join_entered.wait(_WAIT_SECONDS)

        group.listener.submit(
            PeerSendRequest(
                "send-to-closing",
                group.sender("writer"),
                "reviewer",
                "too late",
            )
        )
        with pytest.raises(RuntimeError, match="join cleanup"):
            group.outcome.result(0.5)

        assert group.bindings.success_calls == 0
        assert group.bindings.failure_calls == 0


def test_blocked_close_offer_is_bounded_and_prevents_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import coordinator

    monkeypatch.setattr(coordinator, "_CLEANUP_TIMEOUT_SECONDS", 0.05)
    with _running_group(tmp_path, timeout_sec=0.2) as group:
        group.ready()
        group.write_bundles()
        reviewer = group.bindings.adapters["reviewer"]
        reviewer.close_gate.clear()
        finish = group.listener.submit(
            PeerFinishRequest("finish-reviewer", group.sender("reviewer"))
        )
        assert reviewer.close_entered.wait(_WAIT_SECONDS)

        with pytest.raises(RuntimeError, match="close cleanup"):
            group.outcome.result(0.5)
        assert isinstance(finish.result(_WAIT_SECONDS), PeerFailureReceipt)
        assert group.bindings.success_calls == 0
        assert group.bindings.failure_calls == 0


def _workflow_peer_bindings(
    tmp_path: Path,
) -> tuple[Any, Any, Any, Any]:
    from orchestrator.deps.injector import DependencyInjector
    from orchestrator.deps.resolver import DependencyResolver
    from orchestrator.providers import (
        InputMode,
        ProviderRegistry,
        ProviderTemplate,
    )
    from orchestrator.providers.executor import ProviderExecutor
    from orchestrator.state import StateManager
    from orchestrator.variables.substitution import VariableSubstitutor
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow.prompting import PromptComposer
    from orchestrator.workflow.provider_peer_group.bindings import (
        WorkflowProviderPeerGroupBindings,
    )
    from tests.test_provider_peer_group_ir import _config

    config = _config(member_ids=("author", "reviewer"))
    workflow_path = tmp_path / "workflow.orc"
    workflow_path.write_text("; peer binding test\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="peer-binding-run")
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Peers": 1})
    manager.start_step(
        "Peers",
        0,
        "provider_peer_group",
        step_id=config.node_id,
        visit_count=1,
    )
    registry = ProviderRegistry()
    support = InteractiveSessionSupport(
        schema_version="interactive_terminal_turn_queue.v1",
        turn_boundary_messages=True,
        command=("interactive-provider", "${PROMPT}"),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )
    for member in config.members:
        registry.register(
            ProviderTemplate(
                name=member.provider_config.provider,
                command=["ordinary-provider", "${PROMPT}"],
                input_mode=InputMode.ARGV,
                interactive_session_support=support,
            )
        )

    class _Executor:
        def __init__(self) -> None:
            self.workspace = tmp_path
            self.state_manager = manager
            self.provider_executor = ProviderExecutor(tmp_path, registry)
            self.dependency_injector = DependencyInjector(str(tmp_path))
            self.dependency_resolver = DependencyResolver(str(tmp_path))
            self.variable_substitutor = VariableSubstitutor()
            self.prompt_composer = PromptComposer(
                workspace=tmp_path,
                asset_resolver=None,
            )
            self.finalized: list[dict[str, Any]] = []

        def _provider_attempt_scope(self, **kwargs: Any) -> Any:
            return WorkflowExecutor._provider_attempt_scope(
                self,  # pyright: ignore[reportArgumentType]
                **kwargs,
            )

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
                self,  # type: ignore[arg-type]
                **kwargs,
            )

        def _compose_provider_attempt_for_step(
            self,
            step: dict[str, Any],
            _context: dict[str, Any],
            _state: dict[str, Any],
            **_kwargs: Any,
        ) -> tuple[str, None, None]:
            return f"member provider: {step['provider']}", None, None

        def _create_provider_context(
            self,
            *_args: Any,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            return {}

        def _resolve_provider_name_for_step(
            self,
            step: dict[str, Any],
            _context: dict[str, Any],
        ) -> tuple[str, None]:
            return step["provider"], None

        def _uses_qualified_identities(self) -> bool:
            return False

        def _finalize_provider_peer_group_settlement(
            self,
            _step: Any,
            _state: dict[str, Any],
            *,
            step_name: str,
            result: dict[str, Any],
        ) -> dict[str, Any]:
            assert step_name == "Peers"
            self.finalized.append(result)
            return result

    executor = _Executor()
    state = manager.load().to_dict()
    bindings = WorkflowProviderPeerGroupBindings(
        executor,
        step={"name": "Peers", "step_id": config.node_id},
        state=state,
        config=config,
        step_name="Peers",
        runtime_step_id=config.node_id,
        visit_count=1,
    )
    return config, manager, executor, bindings


def _failed_group_evidence(
    allocation: PeerGroupAllocation,
    *,
    code: str = "test_failure",
    message: str = "bounded failure",
) -> PeerGroupTerminalEvidence:
    from orchestrator.workflow.provider_peer_group.models import (
        PeerMemberTerminalEvidence,
    )

    return PeerGroupTerminalEvidence(
        outcome="failed",
        group_visit=allocation.runtime.visit,
        members=tuple(
            PeerMemberTerminalEvidence(
                attempt=member.runtime.attempt,
                lifecycle=PeerMemberLifecycle.FAILED,
                ledger=None,
                frozen_bundle_sha256=None,
                natural_shutdown=None,
                failed_cleanup=None,
            )
            for member in allocation.members
        ),
        endpoint_drained=True,
        endpoint_closed=True,
        endpoint_workers_joined=True,
        settlement_sha256=None,
        failure={"code": code, "message": message},
        terminal_at="2026-07-25T12:00:00+00:00",
    )


def test_workflow_peer_bindings_allocate_freeze_and_finalize_exact_visit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _config, manager, executor, bindings = _workflow_peer_bindings(tmp_path)
    atomic_writes: list[Path] = []
    original_atomic_write_bytes = peer_bindings.atomic_write_bytes

    def track_atomic_write(path: Path, content: bytes) -> None:
        atomic_writes.append(path)
        original_atomic_write_bytes(path, content)

    monkeypatch.setattr(
        peer_bindings,
        "atomic_write_bytes",
        track_atomic_write,
    )

    bindings.assert_current_step()
    allocation = bindings.allocate_group()

    assert tuple(
        member.runtime.attempt.member_id for member in allocation.members
    ) == ("author", "reviewer")
    assert all(
        member.runtime.attempt.attempt_ordinal == 1
        and member.realized_paths.prompt_dependencies_path.is_file()
        and member.prompt_snapshot_sha256
        == "sha256:"
        + hashlib.sha256(
            member.realized_paths.prompt_dependencies_path.read_bytes()
        ).hexdigest()
        and member.invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        == str(member.realized_paths.provisional_bundle_path)
        and "ORCHESTRATOR_ACTIVE_PEER_BINDING" in member.invocation.env
        for member in allocation.members
    )
    author = allocation.members[0]
    author.realized_paths.provisional_bundle_path.write_text(
        '"author-result"',
        encoding="utf-8",
    )
    frozen = bindings.validate_member_bundle(author)
    assert frozen.value == "author-result"
    assert frozen.exact_bundle_bytes == b'"author-result"'
    assert bindings.evaluate_settlement(
        resolved_bindings={
            "author": "author-result",
            "reviewer": "reviewer-result",
        }
    ) == "author-result"
    assert bindings.validate_settlement(value="author-result") == (
        "author-result"
    )

    evidence = _failed_group_evidence(allocation)
    result = bindings.finalize_failure(evidence=evidence)

    assert result["status"] == "failed"
    assert result["debug"]["provider_peer_group"] == {
        "terminal_evidence_path": (
            allocation.realized_paths.terminal_evidence_path.relative_to(
                manager.run_root
            ).as_posix()
        ),
        "terminal_evidence_schema_version": evidence.schema_version,
        "outcome": "failed",
    }
    assert json.loads(
        allocation.realized_paths.terminal_evidence_path.read_text(
            encoding="ascii"
        )
    ) == evidence.to_dict()
    assert [
        json.loads(path.read_text(encoding="ascii"))
        for path in (
            member.realized_paths.evidence_path
            for member in allocation.members
        )
    ] == [member.to_dict() for member in evidence.members]
    assert atomic_writes[-3:] == [
        allocation.members[0].realized_paths.evidence_path,
        allocation.members[1].realized_paths.evidence_path,
        allocation.realized_paths.terminal_evidence_path,
    ]
    assert executor.finalized == [result]


def test_workflow_peer_adapter_reuses_allocated_short_socket_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.provider_peer_group import bindings as module

    _config, _manager, _executor, bindings = _workflow_peer_bindings(
        tmp_path
    )
    allocation = bindings.allocate_group()
    member = allocation.members[0]
    captured: list[tuple[Path, Path]] = []
    sentinel = object()

    def build_adapter(
        runtime_root: Path,
        *,
        socket_root: Path,
    ) -> object:
        captured.append((runtime_root, socket_root))
        return sentinel

    monkeypatch.setattr(
        module,
        "InteractiveTerminalTurnQueueAdapter",
        build_adapter,
    )

    assert bindings.create_adapter(member) is sentinel
    assert captured == [
        (
            member.realized_paths.evidence_path.parent
            / "interactive-terminal",
            allocation.endpoint_socket_path.parent,
        )
    ]


def test_workflow_peer_adapter_requires_reportable_group_identity(
    tmp_path: Path,
) -> None:
    _config, _manager, _executor, bindings = _workflow_peer_bindings(
        tmp_path
    )
    foreign_member = _allocation(tmp_path / "foreign").members[0]

    with pytest.raises(
        ValueError,
        match="^provider peer group reportable identity is missing$",
    ):
        bindings.create_adapter(foreign_member)


def test_stale_visit_preimage_consumes_zero_attempt_ordinals(
    tmp_path: Path,
) -> None:
    config, manager, executor, bindings = _workflow_peer_bindings(tmp_path)
    stale = realize_provider_peer_group_paths(
        run_root=manager.run_root,
        plan=config.paths,
        visit_count=1,
        attempt_ordinals={
            member.member_id: 1 for member in config.members
        },
    ).visit_root
    stale.mkdir(parents=True)
    (stale / "stale").write_text("occupied", encoding="utf-8")

    with pytest.raises(FileExistsError, match="visit root is nonempty"):
        bindings.allocate_group()

    assert manager.load().provider_attempt_allocations == {}
    assert executor.finalized == []


def test_later_member_preparation_failure_is_terminal_and_reportable(
    tmp_path: Path,
) -> None:
    _config, _manager, executor, bindings = _workflow_peer_bindings(tmp_path)
    original = bindings._allocate_member

    def fail_later_member(**kwargs: Any) -> PeerMemberAllocation:
        if kwargs["member"].member_id == "reviewer":
            raise ValueError("reviewer preparation failed")
        return original(**kwargs)

    bindings._allocate_member = fail_later_member

    def forbid_listener(*_args: Any) -> Any:
        raise AssertionError("prelaunch failure must not start ingress")

    result = ProviderPeerGroupCoordinator(
        bindings,
        forbid_listener,
    ).run()
    reservation = bindings.reportable_group_identity()

    assert result["status"] == "failed"
    assert result["error"] == {
        "type": "provider_peer_group_failed",
        "message": "reviewer preparation failed",
    }
    assert reservation is not None
    assert json.loads(
        reservation.realized_paths.terminal_evidence_path.read_text(
            encoding="ascii"
        )
    )["failure"] == {
        "code": "provider_peer_group_failed",
        "message": "reviewer preparation failed",
    }
    assert all(
        member.evidence_path.is_file()
        for member in reservation.realized_paths.members
    )
    assert executor.finalized == [result]


def test_member_terminal_evidence_is_no_replace(
    tmp_path: Path,
) -> None:
    _config, _manager, executor, bindings = _workflow_peer_bindings(tmp_path)
    allocation = bindings.allocate_group()
    evidence = _failed_group_evidence(allocation)
    occupied = allocation.members[0].realized_paths.evidence_path
    occupied.parent.mkdir(parents=True, exist_ok=True)
    occupied.write_text('{"stale":true}', encoding="ascii")

    with pytest.raises(ValueError, match="evidence preimage exists"):
        bindings.finalize_failure(evidence=evidence)

    assert occupied.read_text(encoding="ascii") == '{"stale":true}'
    assert not allocation.realized_paths.terminal_evidence_path.exists()
    assert executor.finalized == []
