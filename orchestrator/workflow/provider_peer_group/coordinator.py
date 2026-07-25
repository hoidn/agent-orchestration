"""Single-writer coordinator for one cooperative provider peer-group visit."""

from __future__ import annotations

from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    TimeoutError as FutureTimeoutError,
    wait,
)
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import time
from threading import Lock
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

from ...providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    NaturalShutdownProof,
    OfferReceipt,
)
from ..pure_expr import canonical_json_for_pure_value
from .bindings import (
    PeerDeliveryFrame,
    PeerGroupAllocation,
    PeerGroupReportableIdentity,
    PeerInteractiveAdapter,
    PeerMemberAllocation,
    ProviderPeerGroupCoordinatorBindings,
)
from .ledger import PeerMessageLedger
from .models import (
    FrozenPeerMemberResult,
    PeerAcknowledgeReceipt,
    PeerAcknowledgeRequest,
    PeerFailureReceipt,
    PeerFinishReceipt,
    PeerFinishRequest,
    PeerGroupTerminalEvidence,
    PeerMemberLifecycle,
    PeerMemberTerminalEvidence,
    PeerMemberTerminalEvidence,
    PeerReadyReceipt,
    PeerReadyRequest,
    PeerReceipt,
    PeerRequest,
    PeerSendReceipt,
    PeerSendRequest,
)
from .protocol import (
    PeerEndpointCloseProof,
    PeerProtocolClosedError,
    PeerProtocolEvent,
    PeerProtocolListener,
)


_EVENT_POLL_SECONDS = 0.05
_CLEANUP_TIMEOUT_SECONDS = 6.0


class PeerProtocolEndpoint(Protocol):
    endpoint_identity: Any
    socket_path: Any

    def start(self) -> None: ...

    def receive_event(self, *, timeout_sec: float) -> PeerProtocolEvent: ...

    def resolve(
        self,
        event: PeerProtocolEvent,
        receipt: PeerReceipt,
    ) -> None: ...

    def close(self) -> PeerEndpointCloseProof: ...


PeerProtocolEndpointFactory = Callable[
    [Any, Any],
    PeerProtocolEndpoint,
]
PeerInteractiveAdapterFactory = Callable[
    [PeerMemberAllocation],
    PeerInteractiveAdapter,
]


@dataclass
class _Replay:
    payload: bytes
    events: list[PeerProtocolEvent] = field(default_factory=list)
    receipt: PeerReceipt | None = None


@dataclass
class _Message:
    message_id: str
    sender_member_id: str
    receiver_member_id: str
    coordinator_sequence: int
    acknowledged: bool = False


@dataclass
class _Member:
    allocation: PeerMemberAllocation
    adapter: PeerInteractiveAdapter
    ledger: PeerMessageLedger
    deadline: float
    lifecycle: PeerMemberLifecycle = PeerMemberLifecycle.ALLOCATED
    handle: InteractiveMemberHandle | None = None
    frozen_result: FrozenPeerMemberResult | None = None
    natural_shutdown: NaturalShutdownProof | None = None
    failed_cleanup: FailedCleanupProof | None = None
    ledger_summary: Any = None
    ready_request_id: str | None = None
    incoming_message_ids: list[str] = field(default_factory=list)
    close_future: Future[CloseOfferReceipt] | None = None
    join_future: Future[NaturalShutdownProof] | None = None

    @property
    def member_id(self) -> str:
        return self.allocation.runtime.attempt.member_id


class _CoordinatorFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ProviderPeerGroupCoordinator:
    """Own every mutable lifecycle, delivery, and settlement decision."""

    def __init__(
        self,
        bindings: ProviderPeerGroupCoordinatorBindings,
        listener_factory: PeerProtocolEndpointFactory = PeerProtocolListener,
        adapter_factory: PeerInteractiveAdapterFactory | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        event_poll_sec: float = _EVENT_POLL_SECONDS,
    ) -> None:
        if not callable(listener_factory):
            raise TypeError("listener_factory must be callable")
        if not callable(monotonic) or not callable(clock):
            raise TypeError("coordinator clocks must be callable")
        if (
            isinstance(event_poll_sec, bool)
            or not isinstance(event_poll_sec, (int, float))
            or event_poll_sec <= 0
        ):
            raise ValueError("event_poll_sec must be positive")
        self._bindings = bindings
        self._listener_factory = listener_factory
        self._adapter_factory = (
            bindings.create_adapter
            if adapter_factory is None
            else adapter_factory
        )
        self._monotonic = monotonic
        self._clock = clock
        self._event_poll_sec = float(event_poll_sec)
        self._snapshot_lock = Lock()
        self._lifecycle_snapshot: Mapping[str, PeerMemberLifecycle] = (
            MappingProxyType({})
        )

    @property
    def lifecycle_snapshot(self) -> Mapping[str, PeerMemberLifecycle]:
        with self._snapshot_lock:
            return MappingProxyType(dict(self._lifecycle_snapshot))

    def run(self) -> dict[str, Any]:
        allocation: PeerGroupAllocation | None = None
        endpoint: PeerProtocolEndpoint | None = None
        endpoint_proof: PeerEndpointCloseProof | None = None
        members: tuple[_Member, ...] = ()
        joins: ThreadPoolExecutor | None = None
        replays: dict[str, _Replay] = {}
        messages: dict[str, _Message] = {}
        coordinator_sequence = 0
        finalization_started = False
        try:
            self._bindings.assert_current_step()
            allocation = self._bindings.allocate_group()
            if not isinstance(allocation, PeerGroupAllocation):
                raise _CoordinatorFailure(
                    "provider_peer_group_allocation_invalid",
                    "coordinator allocation is not a PeerGroupAllocation",
                )
            started_at = self._monotonic()
            members = self._prepare_members(
                allocation,
                started_at=started_at,
            )
            self._publish_lifecycle(members)
            endpoint = self._listener_factory(
                allocation.endpoint,
                allocation.endpoint_socket_path,
            )
            if (
                endpoint.endpoint_identity != allocation.endpoint
                or endpoint.socket_path != allocation.endpoint_socket_path
            ):
                raise _CoordinatorFailure(
                    "provider_peer_group_endpoint_invalid",
                    "endpoint identity does not match the allocation",
                )
            endpoint.start()
            self._launch_members(members)
            joins = ThreadPoolExecutor(
                max_workers=len(members),
                thread_name_prefix="provider-peer-join",
            )
            members_by_sender = {
                member.allocation.sender.opaque_binding: member
                for member in members
            }
            members_by_id = {
                member.member_id: member for member in members
            }

            while not all(
                member.lifecycle is PeerMemberLifecycle.TERMINAL
                for member in members
            ):
                self._collect_completed_joins(members)
                if all(
                    member.lifecycle is PeerMemberLifecycle.TERMINAL
                    for member in members
                ):
                    break
                remaining = self._remaining_before_deadline(members)
                try:
                    event = endpoint.receive_event(
                        timeout_sec=min(
                            self._event_poll_sec,
                            remaining,
                        )
                    )
                except TimeoutError:
                    continue
                except PeerProtocolClosedError as exc:
                    raise _CoordinatorFailure(
                        "provider_peer_group_endpoint_closed",
                        str(exc),
                    ) from exc
                coordinator_sequence = self._handle_protocol_event(
                    endpoint=endpoint,
                    event=event,
                    members=members,
                    members_by_sender=members_by_sender,
                    members_by_id=members_by_id,
                    replays=replays,
                    messages=messages,
                    joins=joins,
                    coordinator_sequence=coordinator_sequence,
                )

            joins.shutdown(wait=True, cancel_futures=True)
            joins = None
            self._finalize_ledgers(members)
            endpoint_proof = endpoint.close()
            self._require_complete_endpoint_proof(endpoint_proof)
            endpoint = None
            resolved_bindings = {
                member.member_id: self._require_frozen_result(member).value
                for member in members
            }
            settlement_value = self._bindings.evaluate_settlement(
                resolved_bindings=resolved_bindings
            )
            settlement_value = self._bindings.validate_settlement(
                value=settlement_value
            )
            evidence = self._completed_evidence(
                allocation=allocation,
                members=members,
                endpoint_proof=endpoint_proof,
                settlement_value=settlement_value,
            )
            self._bindings.assert_current_step()
            finalization_started = True
            return self._bindings.finalize_success(
                settlement_value=settlement_value,
                evidence=evidence,
            )
        except _CoordinatorFailure as exc:
            if finalization_started:
                raise
            if allocation is None:
                result = self._finalize_reportable_preparation_failure(
                    code=exc.code,
                    message=str(exc),
                )
                if result is not None:
                    return result
                raise
            if not members:
                result = self._finalize_reportable_preparation_failure(
                    code=exc.code,
                    message=str(exc),
                    identity=allocation,
                )
                if result is not None:
                    return result
                raise
            return self._finalize_failure(
                allocation=allocation,
                members=members,
                endpoint=endpoint,
                endpoint_proof=endpoint_proof,
                joins=joins,
                replays=replays,
                code=exc.code,
                message=str(exc),
            )
        except Exception as exc:
            if finalization_started:
                raise
            if allocation is None:
                result = self._finalize_reportable_preparation_failure(
                    code="provider_peer_group_failed",
                    message=str(exc) or type(exc).__name__,
                )
                if result is not None:
                    return result
                raise
            if not members:
                result = self._finalize_reportable_preparation_failure(
                    code="provider_peer_group_failed",
                    message=str(exc) or type(exc).__name__,
                    identity=allocation,
                )
                if result is not None:
                    return result
                raise
            return self._finalize_failure(
                allocation=allocation,
                members=members,
                endpoint=endpoint,
                endpoint_proof=endpoint_proof,
                joins=joins,
                replays=replays,
                code="provider_peer_group_failed",
                message=str(exc) or type(exc).__name__,
            )

    def _finalize_reportable_preparation_failure(
        self,
        *,
        code: str,
        message: str,
        identity: PeerGroupReportableIdentity | PeerGroupAllocation | None = None,
    ) -> dict[str, Any] | None:
        if identity is None:
            getter = getattr(
                self._bindings,
                "reportable_group_identity",
                None,
            )
            if not callable(getter):
                return None
            candidate = getter()
            if candidate is None:
                return None
            if not isinstance(
                candidate,
                (PeerGroupReportableIdentity, PeerGroupAllocation),
            ):
                raise _CoordinatorFailure(
                    "provider_peer_group_allocation_invalid",
                    "reportable group identity is invalid",
                )
            identity = candidate
        evidence = PeerGroupTerminalEvidence(
            outcome="failed",
            group_visit=identity.runtime.visit,
            members=tuple(
                PeerMemberTerminalEvidence(
                    attempt=member.attempt,
                    lifecycle=PeerMemberLifecycle.FAILED,
                    ledger=None,
                    frozen_bundle_sha256=None,
                    natural_shutdown=None,
                    failed_cleanup=None,
                )
                for member in identity.runtime.members
            ),
            endpoint_drained=True,
            endpoint_closed=True,
            endpoint_workers_joined=True,
            settlement_sha256=None,
            failure={"code": code, "message": message},
            terminal_at=self._timestamp(),
        )
        self._bindings.assert_current_step()
        return self._bindings.finalize_failure(evidence=evidence)

    def _prepare_members(
        self,
        allocation: PeerGroupAllocation,
        *,
        started_at: float,
    ) -> tuple[_Member, ...]:
        for member in allocation.members:
            snapshot_path = member.realized_paths.prompt_dependencies_path
            if not snapshot_path.is_file():
                raise _CoordinatorFailure(
                    "provider_peer_group_prompt_snapshot_missing",
                    f"prompt snapshot is missing for {member.runtime.attempt.member_id}",
                )
            snapshot_digest = (
                "sha256:"
                + hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            )
            if snapshot_digest != member.prompt_snapshot_sha256:
                raise _CoordinatorFailure(
                    "provider_peer_group_prompt_snapshot_mismatch",
                    f"prompt snapshot changed for {member.runtime.attempt.member_id}",
                )
            if (
                member.realized_paths.provisional_bundle_path.exists()
                or member.realized_paths.evidence_path.exists()
                or member.realized_paths.injected_messages_path.exists()
            ):
                raise _CoordinatorFailure(
                    "provider_peer_group_path_preoccupied",
                    f"member paths are preoccupied for {member.runtime.attempt.member_id}",
                )

        ledgers: list[PeerMessageLedger] = []
        try:
            for member in allocation.members:
                ledgers.append(
                    PeerMessageLedger.create(
                        member.realized_paths.injected_messages_path,
                        group_visit=allocation.runtime.visit,
                        receiver_attempt=member.runtime.attempt,
                    )
                )
            adapters = tuple(
                self._adapter_factory(member)
                for member in allocation.members
            )
            if any(
                not isinstance(adapter, PeerInteractiveAdapter)
                for adapter in adapters
            ):
                raise _CoordinatorFailure(
                    "provider_peer_group_adapter_invalid",
                    "every member adapter must implement the closed surface",
                )
        except BaseException:
            for ledger in ledgers:
                try:
                    ledger.finalize()
                except Exception:
                    pass
            raise
        return tuple(
            _Member(
                allocation=member,
                adapter=adapter,
                ledger=ledger,
                deadline=started_at + float(member.runtime.timeout_sec),
            )
            for member, adapter, ledger in zip(
                allocation.members,
                adapters,
                ledgers,
                strict=True,
            )
        )

    def _launch_members(self, members: tuple[_Member, ...]) -> None:
        handles: list[InteractiveMemberHandle] = []
        for member in members:
            self._transition(member, PeerMemberLifecycle.STARTING)
            handle = member.adapter.start(member.allocation.invocation)
            self._require_matching_handle(member, handle)
            member.handle = handle
            handles.append(handle)
        if (
            len({handle.handle_id for handle in handles}) != len(handles)
            or len({handle.adapter_instance_id for handle in handles})
            != len(handles)
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_handle_collision",
                "member adapter and handle identities must be distinct",
            )

    def _handle_protocol_event(
        self,
        *,
        endpoint: PeerProtocolEndpoint,
        event: PeerProtocolEvent,
        members: tuple[_Member, ...],
        members_by_sender: Mapping[str, _Member],
        members_by_id: Mapping[str, _Member],
        replays: dict[str, _Replay],
        messages: dict[str, _Message],
        joins: ThreadPoolExecutor,
        coordinator_sequence: int,
    ) -> int:
        if event.endpoint_identity != endpoint.endpoint_identity:
            endpoint.resolve(
                event,
                PeerFailureReceipt(
                    request_kind=event.request.kind,
                    request_id=event.request.request_id,
                    error_code="event_endpoint_mismatch",
                    retryable=False,
                ),
            )
            raise _CoordinatorFailure(
                "provider_peer_group_event_endpoint_mismatch",
                "protocol event belongs to a different endpoint",
            )
        request = event.request
        payload = self._canonical_request(request)
        existing = replays.get(request.request_id)
        if existing is not None:
            if existing.payload != payload:
                endpoint.resolve(
                    event,
                    PeerFailureReceipt(
                        request_kind=request.kind,
                        request_id=request.request_id,
                        error_code="request_id_conflict",
                        retryable=False,
                    ),
                )
                raise _CoordinatorFailure(
                    "provider_peer_group_request_id_conflict",
                    "client request id was reused with different content",
                )
            if existing.receipt is None:
                existing.events.append(event)
            else:
                endpoint.resolve(event, existing.receipt)
            return coordinator_sequence

        replay = _Replay(payload=payload, events=[event])
        replays[request.request_id] = replay
        sender = members_by_sender.get(request.sender_binding)
        if sender is None:
            self._complete(
                endpoint,
                replay,
                PeerFailureReceipt(
                    request_kind=request.kind,
                    request_id=request.request_id,
                    error_code="sender_binding_invalid",
                    retryable=False,
                ),
            )
            raise _CoordinatorFailure(
                "provider_peer_group_sender_binding_invalid",
                "protocol sender binding is not active for this endpoint",
            )

        if isinstance(request, PeerReadyRequest):
            self._handle_ready(
                endpoint=endpoint,
                request=request,
                replay=replay,
                sender=sender,
                members=members,
                replays=replays,
            )
            return coordinator_sequence
        if isinstance(request, PeerSendRequest):
            return self._handle_send(
                endpoint=endpoint,
                request=request,
                replay=replay,
                sender=sender,
                members_by_id=members_by_id,
                messages=messages,
                coordinator_sequence=coordinator_sequence,
            )
        if isinstance(request, PeerAcknowledgeRequest):
            self._handle_ack(
                endpoint=endpoint,
                request=request,
                replay=replay,
                sender=sender,
                messages=messages,
            )
            return coordinator_sequence
        if isinstance(request, PeerFinishRequest):
            self._handle_finish(
                endpoint=endpoint,
                request=request,
                replay=replay,
                sender=sender,
                messages=messages,
                joins=joins,
                members=members,
            )
            return coordinator_sequence
        raise _CoordinatorFailure(
            "provider_peer_group_request_invalid",
            "protocol request variant is unsupported",
        )

    def _handle_ready(
        self,
        *,
        endpoint: PeerProtocolEndpoint,
        request: PeerReadyRequest,
        replay: _Replay,
        sender: _Member,
        members: tuple[_Member, ...],
        replays: Mapping[str, _Replay],
    ) -> None:
        if sender.lifecycle is not PeerMemberLifecycle.STARTING:
            self._reject(
                endpoint,
                replay,
                request,
                "member_not_starting",
            )
            return
        self._transition(sender, PeerMemberLifecycle.READY_WAITING)
        sender.ready_request_id = request.request_id
        if not all(
            member.lifecycle is PeerMemberLifecycle.READY_WAITING
            for member in members
        ):
            return
        self._transition_group(members, PeerMemberLifecycle.ACTIVE)
        for member in members:
            assert member.ready_request_id is not None
            ready_replay = replays[member.ready_request_id]
            self._complete(
                endpoint,
                ready_replay,
                PeerReadyReceipt(member.ready_request_id),
            )

    def _handle_send(
        self,
        *,
        endpoint: PeerProtocolEndpoint,
        request: PeerSendRequest,
        replay: _Replay,
        sender: _Member,
        members_by_id: Mapping[str, _Member],
        messages: dict[str, _Message],
        coordinator_sequence: int,
    ) -> int:
        if sender.lifecycle is not PeerMemberLifecycle.ACTIVE:
            self._reject(
                endpoint,
                replay,
                request,
                "sender_not_active",
            )
            raise _CoordinatorFailure(
                "provider_peer_group_send_rejected",
                "peer send sender is not active",
            )
        target = members_by_id.get(request.target_binding)
        if target is None:
            self._reject(
                endpoint,
                replay,
                request,
                "target_unknown",
            )
            raise _CoordinatorFailure(
                "provider_peer_group_send_rejected",
                "peer send target is unknown",
            )
        if target is sender:
            self._reject(
                endpoint,
                replay,
                request,
                "self_target_rejected",
            )
            raise _CoordinatorFailure(
                "provider_peer_group_send_rejected",
                "peer send cannot target its sender",
            )
        if target.lifecycle is not PeerMemberLifecycle.ACTIVE:
            self._reject(
                endpoint,
                replay,
                request,
                "target_not_active",
            )
            raise _CoordinatorFailure(
                "provider_peer_group_send_rejected",
                "peer send target is not active",
            )

        coordinator_sequence += 1
        message_id = (
            f"{endpoint.endpoint_identity.endpoint_instance_id}:"
            f"{coordinator_sequence}"
        )
        frame = PeerDeliveryFrame(
            message_id=message_id,
            sender_member_id=sender.member_id,
            content=request.message,
        )
        content_sha256 = target.ledger.append_recorded(
            coordinator_sequence=coordinator_sequence,
            request_id=request.request_id,
            message_id=message_id,
            sender_attempt=sender.allocation.runtime.attempt,
            content=request.message,
        )
        assert target.handle is not None
        try:
            offered = target.adapter.offer(
                target.handle,
                frame.render(),
            )
            self._require_offer_receipt(
                target,
                offered,
                frame=frame,
            )
        except Exception as exc:
            error_code = getattr(exc, "code", "offer_failed")
            target.ledger.append_offer_failed(
                message_id=message_id,
                error_code=str(error_code),
                message=str(exc) or str(error_code),
            )
            self._complete(
                endpoint,
                replay,
                PeerFailureReceipt(
                    request_kind=request.kind,
                    request_id=request.request_id,
                    error_code="offer_failed",
                    retryable=False,
                ),
            )
            raise _CoordinatorFailure(
                "provider_peer_group_offer_failed",
                str(exc) or "peer message offer failed",
            ) from exc
        target.ledger.append_offered(
            message_id=message_id,
            adapter_instance_id=target.handle.adapter_instance_id,
            handle_id=target.handle.handle_id,
            byte_count=len(request.message.encode("utf-8")),
            content_sha256=content_sha256,
        )
        messages[message_id] = _Message(
            message_id=message_id,
            sender_member_id=sender.member_id,
            receiver_member_id=target.member_id,
            coordinator_sequence=coordinator_sequence,
        )
        target.incoming_message_ids.append(message_id)
        self._complete(
            endpoint,
            replay,
            PeerSendReceipt(request.request_id, message_id),
        )
        return coordinator_sequence

    def _handle_ack(
        self,
        *,
        endpoint: PeerProtocolEndpoint,
        request: PeerAcknowledgeRequest,
        replay: _Replay,
        sender: _Member,
        messages: Mapping[str, _Message],
    ) -> None:
        if sender.lifecycle is not PeerMemberLifecycle.ACTIVE:
            self._reject(
                endpoint,
                replay,
                request,
                "receiver_not_active",
            )
            return
        message = messages.get(request.message_id)
        if (
            message is None
            or message.receiver_member_id != sender.member_id
            or message.acknowledged
        ):
            self._complete(
                endpoint,
                replay,
                PeerFailureReceipt(
                    request_kind=request.kind,
                    request_id=request.request_id,
                    error_code="acknowledgement_invalid",
                    retryable=False,
                ),
            )
            raise _CoordinatorFailure(
                "provider_peer_group_acknowledgement_invalid",
                "message acknowledgement does not match the receiver attempt",
            )
        sender.ledger.append_receiver_acknowledged(
            request_id=request.request_id,
            message_id=request.message_id,
            receiver_attempt=sender.allocation.runtime.attempt,
        )
        message.acknowledged = True
        self._complete(
            endpoint,
            replay,
            PeerAcknowledgeReceipt(
                request.request_id,
                request.message_id,
            ),
        )

    def _handle_finish(
        self,
        *,
        endpoint: PeerProtocolEndpoint,
        request: PeerFinishRequest,
        replay: _Replay,
        sender: _Member,
        messages: Mapping[str, _Message],
        joins: ThreadPoolExecutor,
        members: tuple[_Member, ...],
    ) -> None:
        if sender.lifecycle is not PeerMemberLifecycle.ACTIVE:
            self._reject(
                endpoint,
                replay,
                request,
                "member_not_active",
            )
            return
        pending = tuple(
            message_id
            for message_id in sender.incoming_message_ids
            if not messages[message_id].acknowledged
        )
        if pending:
            self._complete(
                endpoint,
                replay,
                PeerFinishReceipt.pending(
                    request.request_id,
                    pending,
                ),
            )
            return
        frozen = self._bindings.validate_member_bundle(sender.allocation)
        if (
            not isinstance(frozen, FrozenPeerMemberResult)
            or frozen.attempt != sender.allocation.runtime.attempt
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_member_bundle_invalid",
                f"frozen bundle does not match {sender.member_id}",
            )
        self._transition(
            sender,
            PeerMemberLifecycle.FINISH_REQUESTED,
        )
        assert sender.handle is not None
        sender.close_future = joins.submit(
            sender.adapter.offer_close,
            sender.handle,
        )
        try:
            close_receipt = sender.close_future.result(
                timeout=self._remaining_before_deadline(members)
            )
        except FutureTimeoutError as exc:
            raise _CoordinatorFailure(
                "provider_peer_group_close_timeout",
                (
                    "graceful close offer exceeded the applicable "
                    "member deadline"
                ),
            ) from exc
        self._require_close_receipt(sender, close_receipt)
        sender.close_future = None
        sender.frozen_result = frozen
        self._transition(sender, PeerMemberLifecycle.CLOSING)
        self._complete(
            endpoint,
            replay,
            PeerFinishReceipt.close_offered(request.request_id),
        )
        sender.join_future = joins.submit(
            sender.adapter.join,
            sender.handle,
            sender.deadline,
        )

    def _collect_completed_joins(
        self,
        members: tuple[_Member, ...],
    ) -> None:
        for member in members:
            future = member.join_future
            if (
                member.lifecycle is not PeerMemberLifecycle.CLOSING
                or future is None
                or not future.done()
            ):
                continue
            proof = future.result()
            self._require_natural_shutdown(member, proof)
            member.natural_shutdown = proof
            member.join_future = None
            self._transition(member, PeerMemberLifecycle.TERMINAL)

    def _remaining_before_deadline(
        self,
        members: tuple[_Member, ...],
    ) -> float:
        live = [
            member.deadline
            for member in members
            if member.lifecycle
            not in {
                PeerMemberLifecycle.TERMINAL,
                PeerMemberLifecycle.FAILED,
            }
        ]
        if not live:
            return self._event_poll_sec
        remaining = min(live) - self._monotonic()
        if remaining <= 0:
            raise _CoordinatorFailure(
                "provider_peer_group_member_timeout",
                "a provider peer member deadline expired",
            )
        return remaining

    def _finalize_failure(
        self,
        *,
        allocation: PeerGroupAllocation,
        members: tuple[_Member, ...],
        endpoint: PeerProtocolEndpoint | None,
        endpoint_proof: PeerEndpointCloseProof | None,
        joins: ThreadPoolExecutor | None,
        replays: Mapping[str, _Replay],
        code: str,
        message: str,
    ) -> dict[str, Any]:
        cleanup_errors: list[str] = []
        if endpoint is not None:
            self._resolve_pending_failures(endpoint, replays, code)
            try:
                endpoint_proof = endpoint.close()
            except Exception as exc:
                endpoint_proof = PeerEndpointCloseProof(
                    drained=False,
                    closed=False,
                    workers_joined=False,
                )
                cleanup_errors.append(
                    f"endpoint cleanup failed: {exc}"
                )
        if endpoint_proof is None:
            endpoint_proof = PeerEndpointCloseProof(
                drained=True,
                closed=True,
                workers_joined=True,
            )
        elif (
            endpoint_proof.drained is not True
            or endpoint_proof.closed is not True
            or endpoint_proof.workers_joined is not True
        ):
            cleanup_errors.append(
                "endpoint cleanup proof is incomplete"
            )

        cleanup_deadline = self._monotonic() + _CLEANUP_TIMEOUT_SECONDS
        for member in members:
            future = member.join_future
            if future is None or not future.done():
                continue
            try:
                proof = future.result()
                self._require_natural_shutdown(member, proof)
            except Exception:
                continue
            member.natural_shutdown = proof
            member.join_future = None
            self._transition(member, PeerMemberLifecycle.TERMINAL)

        cleanup_pool = ThreadPoolExecutor(
            max_workers=max(1, len(members)),
            thread_name_prefix="provider-peer-abort",
        )
        abort_futures: dict[Future[FailedCleanupProof], _Member] = {}
        for member in members:
            if member.lifecycle is PeerMemberLifecycle.TERMINAL:
                continue
            handle = member.handle
            if handle is not None:
                future = cleanup_pool.submit(
                    member.adapter.abort,
                    handle,
                    cleanup_deadline,
                )
                abort_futures[future] = member
            member.frozen_result = None
            self._transition(member, PeerMemberLifecycle.FAILED)

        lifecycle_futures: dict[Future[Any], tuple[str, _Member]] = {}
        for member in members:
            if member.close_future is not None:
                lifecycle_futures[member.close_future] = (
                    "close",
                    member,
                )
            if member.join_future is not None:
                lifecycle_futures[member.join_future] = (
                    "join",
                    member,
                )
        all_cleanup_futures = tuple(
            (*abort_futures, *lifecycle_futures)
        )
        remaining = max(
            0.0,
            cleanup_deadline - self._monotonic(),
        )
        _done, pending = wait(all_cleanup_futures, timeout=remaining)
        cleanup_pool.shutdown(wait=False, cancel_futures=True)
        if joins is not None:
            joins.shutdown(wait=False, cancel_futures=True)

        for future, member in abort_futures.items():
            if future in pending:
                cleanup_errors.append(
                    f"{member.member_id} cleanup proof exceeded its deadline"
                )
                continue
            try:
                proof = future.result()
                if not isinstance(proof, FailedCleanupProof):
                    raise ValueError("cleanup proof is invalid")
                handle = member.handle
                assert handle is not None
                if proof.handle_id != handle.handle_id:
                    raise ValueError(
                        "cleanup proof handle does not match"
                    )
                if (
                    proof.disposition != "failed_cleanup"
                    or proof.pane_absent is not True
                    or proof.server_absent is not True
                    or proof.cleanup_complete is not True
                    or proof.error_code is not None
                ):
                    raise ValueError(
                        "cleanup proof is incomplete"
                    )
                member.failed_cleanup = proof
            except Exception as exc:
                member.failed_cleanup = None
                cleanup_errors.append(
                    f"{member.member_id} cleanup proof failed: {exc}"
                )

        for future in pending:
            lifecycle = lifecycle_futures.get(future)
            if lifecycle is None:
                continue
            operation, member = lifecycle
            cleanup_errors.append(
                f"{member.member_id} {operation} cleanup exceeded its deadline"
            )
        self._finalize_ledgers(members, tolerate_failure=True)
        if cleanup_errors:
            raise _CoordinatorFailure(
                "provider_peer_group_cleanup_incomplete",
                "; ".join(cleanup_errors),
            )
        evidence = PeerGroupTerminalEvidence(
            outcome="failed",
            group_visit=allocation.runtime.visit,
            members=tuple(
                self._member_evidence(member) for member in members
            ),
            endpoint_drained=endpoint_proof.drained,
            endpoint_closed=endpoint_proof.closed,
            endpoint_workers_joined=endpoint_proof.workers_joined,
            settlement_sha256=None,
            failure={"code": code, "message": message},
            terminal_at=self._timestamp(),
        )
        self._bindings.assert_current_step()
        return self._bindings.finalize_failure(evidence=evidence)

    def _completed_evidence(
        self,
        *,
        allocation: PeerGroupAllocation,
        members: tuple[_Member, ...],
        endpoint_proof: PeerEndpointCloseProof,
        settlement_value: Any,
    ) -> PeerGroupTerminalEvidence:
        settlement_bytes = canonical_json_for_pure_value(
            settlement_value
        ).encode("utf-8")
        return PeerGroupTerminalEvidence(
            outcome="completed",
            group_visit=allocation.runtime.visit,
            members=tuple(
                self._member_evidence(member) for member in members
            ),
            endpoint_drained=endpoint_proof.drained,
            endpoint_closed=endpoint_proof.closed,
            endpoint_workers_joined=endpoint_proof.workers_joined,
            settlement_sha256=(
                "sha256:" + hashlib.sha256(settlement_bytes).hexdigest()
            ),
            failure=None,
            terminal_at=self._timestamp(),
        )

    def _member_evidence(
        self,
        member: _Member,
    ) -> PeerMemberTerminalEvidence:
        return PeerMemberTerminalEvidence(
            attempt=member.allocation.runtime.attempt,
            lifecycle=member.lifecycle,
            ledger=member.ledger_summary,
            frozen_bundle_sha256=(
                None
                if member.frozen_result is None
                else member.frozen_result.bundle_sha256
            ),
            natural_shutdown=member.natural_shutdown,
            failed_cleanup=member.failed_cleanup,
        )

    def _finalize_ledgers(
        self,
        members: tuple[_Member, ...],
        *,
        tolerate_failure: bool = False,
    ) -> None:
        for member in members:
            if member.ledger_summary is not None:
                continue
            try:
                member.ledger_summary = member.ledger.finalize()
            except Exception:
                if not tolerate_failure:
                    raise

    def _resolve_pending_failures(
        self,
        endpoint: PeerProtocolEndpoint,
        replays: Mapping[str, _Replay],
        error_code: str,
    ) -> None:
        for request_id, replay in replays.items():
            if replay.receipt is not None or not replay.events:
                continue
            request = replay.events[0].request
            receipt = PeerFailureReceipt(
                request_kind=request.kind,
                request_id=request_id,
                error_code=error_code,
                retryable=False,
            )
            try:
                self._complete(endpoint, replay, receipt)
            except Exception:
                pass

    def _complete(
        self,
        endpoint: PeerProtocolEndpoint,
        replay: _Replay,
        receipt: PeerReceipt,
    ) -> None:
        replay.receipt = receipt
        events = tuple(replay.events)
        replay.events.clear()
        for event in events:
            endpoint.resolve(event, receipt)

    def _reject(
        self,
        endpoint: PeerProtocolEndpoint,
        replay: _Replay,
        request: PeerRequest,
        error_code: str,
    ) -> None:
        self._complete(
            endpoint,
            replay,
            PeerFailureReceipt(
                request_kind=request.kind,
                request_id=request.request_id,
                error_code=error_code,
                retryable=False,
            ),
        )

    def _transition(
        self,
        member: _Member,
        target: PeerMemberLifecycle,
    ) -> None:
        if not member.lifecycle.can_transition_to(target):
            raise _CoordinatorFailure(
                "provider_peer_group_lifecycle_invalid",
                (
                    f"{member.member_id} cannot transition from "
                    f"{member.lifecycle.value} to {target.value}"
                ),
            )
        member.lifecycle = target
        self._publish_lifecycle((member,), merge=True)

    def _transition_group(
        self,
        members: tuple[_Member, ...],
        target: PeerMemberLifecycle,
    ) -> None:
        for member in members:
            if not member.lifecycle.can_transition_to(target):
                raise _CoordinatorFailure(
                    "provider_peer_group_lifecycle_invalid",
                    (
                        f"{member.member_id} cannot transition from "
                        f"{member.lifecycle.value} to {target.value}"
                    ),
                )
        for member in members:
            member.lifecycle = target
        self._publish_lifecycle(members, merge=True)

    def _publish_lifecycle(
        self,
        members: tuple[_Member, ...],
        *,
        merge: bool = False,
    ) -> None:
        with self._snapshot_lock:
            values = (
                dict(self._lifecycle_snapshot) if merge else {}
            )
            values.update(
                {
                    member.member_id: member.lifecycle
                    for member in members
                }
            )
            self._lifecycle_snapshot = MappingProxyType(values)

    @staticmethod
    def _canonical_request(request: PeerRequest) -> bytes:
        return json.dumps(
            request.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")

    @staticmethod
    def _require_matching_handle(
        member: _Member,
        handle: Any,
    ) -> None:
        attempt = member.allocation.runtime.attempt
        invocation = member.allocation.invocation
        if (
            not isinstance(handle, InteractiveMemberHandle)
            or handle.invocation_id != invocation.invocation_id
            or handle.member_id != attempt.member_id
            or handle.attempt_scope_key != attempt.attempt_scope_key
            or handle.attempt_ordinal != attempt.attempt_ordinal
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_handle_invalid",
                f"adapter handle does not match {attempt.member_id}",
            )

    @staticmethod
    def _require_offer_receipt(
        member: _Member,
        receipt: Any,
        *,
        frame: PeerDeliveryFrame,
    ) -> None:
        assert member.handle is not None
        if (
            not isinstance(receipt, OfferReceipt)
            or receipt.status != "offered"
            or receipt.handle_id != member.handle.handle_id
            or receipt.byte_count != frame.rendered_byte_count
            or receipt.content_sha256 != frame.rendered_sha256
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_offer_receipt_invalid",
                "adapter offer receipt does not bind the framed message",
            )

    @staticmethod
    def _require_close_receipt(
        member: _Member,
        receipt: Any,
    ) -> None:
        assert member.handle is not None
        if (
            not isinstance(receipt, CloseOfferReceipt)
            or receipt.status != "close_offered"
            or receipt.handle_id != member.handle.handle_id
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_close_receipt_invalid",
                "adapter close receipt does not match the member handle",
            )

    @staticmethod
    def _require_natural_shutdown(
        member: _Member,
        proof: Any,
    ) -> None:
        assert member.handle is not None
        if (
            not isinstance(proof, NaturalShutdownProof)
            or proof.handle_id != member.handle.handle_id
            or proof.disposition != "natural_exit"
            or proof.return_code != 0
            or proof.pane_absent is not True
            or proof.server_absent is not True
            or proof.proof_complete is not True
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_natural_shutdown_invalid",
                f"natural shutdown proof is invalid for {member.member_id}",
            )

    @staticmethod
    def _require_frozen_result(
        member: _Member,
    ) -> FrozenPeerMemberResult:
        if member.frozen_result is None:
            raise _CoordinatorFailure(
                "provider_peer_group_frozen_result_missing",
                f"frozen result is missing for {member.member_id}",
            )
        return member.frozen_result

    @staticmethod
    def _require_complete_endpoint_proof(
        proof: Any,
    ) -> None:
        if (
            not isinstance(proof, PeerEndpointCloseProof)
            or proof.drained is not True
            or proof.closed is not True
            or proof.workers_joined is not True
        ):
            raise _CoordinatorFailure(
                "provider_peer_group_endpoint_cleanup_incomplete",
                "peer endpoint cleanup proof is incomplete",
            )

    def _timestamp(self) -> str:
        value = self._clock()
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                "coordinator clock must return an aware datetime"
            )
        return value.isoformat()


__all__ = [
    "PeerProtocolEndpoint",
    "ProviderPeerGroupCoordinator",
]
