"""Serialized local owner for one attempt-bound materialization endpoint.

The endpoint owns only ingress, request replay, and receipt delivery. It never
reads or writes workflow state, a phase ledger, adapter state, or coordinator
authority.
"""

from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
import hashlib
import socket
from threading import Condition, Lock, Thread, current_thread
import time
from typing import Any, Literal

from .diagnostics import (
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    diagnostic_definition,
)
from .models import SubmitReceipt
from .protocol import (
    PhasedSubmitProtocolClosedError,
    PhasedSubmitBinding,
    SubmitEndpointLocator,
    SubmitRequest,
    _canonical,
    _decode_frame,
    _read_frame,
    _remaining,
    receipt_to_dict,
)


_ACCEPT_POLL_SECONDS = 0.05
_ADMISSION_LIFECYCLES = frozenset(
    {"INITIAL_MATERIALIZATION_QUEUED", "RETRY_QUEUED"}
)
_PathOwnership = Literal["none", "owned", "maybe_owned"]


def _monotonic_now() -> float:
    return time.monotonic()


def _deadline_positive(deadline: float) -> bool:
    return _monotonic_now() < deadline


def _shutdown_write(connection: socket.socket) -> None:
    connection.shutdown(socket.SHUT_WR)


def protocol_diagnostic(reason: str) -> PhasedDeliveryDiagnostic:
    """Construct one exact content-free runtime endpoint diagnostic."""

    definition = diagnostic_definition(reason)
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value=None,
            summary=reason,
        ),
        primary_source=DiagnosticSource(
            kind="runtime_attempt",
            owner="submit_endpoint",
            path=None,
            span=None,
        ),
        related_sources=(
            DiagnosticSource(
                kind="runtime_attempt",
                owner="runtime_step",
                path=None,
                span=None,
            ),
            DiagnosticSource(
                kind="runtime_attempt",
                owner="phase_lifecycle",
                path=None,
                span=None,
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class SubmitEndpointShutdownOutcome:
    """Internal truthful projection of endpoint-owned shutdown work."""

    queued_requests_rejected: int
    active_requests_drained: int
    listener_closed: bool
    workers_joined: int
    endpoint_zero_survivor_proven: bool

    def __post_init__(self) -> None:
        for field_name in (
            "queued_requests_rejected",
            "active_requests_drained",
            "workers_joined",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise TypeError(f"{field_name} must be a nonnegative integer")
        if type(self.listener_closed) is not bool:
            raise TypeError("listener_closed must be Boolean")
        if type(self.endpoint_zero_survivor_proven) is not bool:
            raise TypeError("endpoint_zero_survivor_proven must be Boolean")
        if self.endpoint_zero_survivor_proven and not self.listener_closed:
            raise ValueError("zero-survivor proof requires a closed listener")


@dataclass(frozen=True, slots=True)
class SubmitEndpointEvent:
    request: SubmitRequest
    submission_ordinal: int
    _waiter: Future[SubmitReceipt] = field(repr=False, compare=False)
    _response_sent: Future[None] = field(repr=False, compare=False)


@dataclass(slots=True)
class _RequestRecord:
    fingerprint: str
    ordinal: int
    event: SubmitEndpointEvent
    receipt: SubmitReceipt | None = None
    drain_counted: bool = False
    rearm_retry: bool = False


class PhasedSubmitEndpoint:
    """One bounded, serialized, attempt-local submit endpoint."""

    def __init__(
        self,
        *,
        binding: PhasedSubmitBinding,
        locator: SubmitEndpointLocator,
        configured_total: int,
    ) -> None:
        if type(binding) is not PhasedSubmitBinding:
            raise TypeError("binding must be an exact PhasedSubmitBinding")
        if type(locator) is not SubmitEndpointLocator:
            raise TypeError("locator must be an exact SubmitEndpointLocator")
        if (
            binding.endpoint_instance_id != locator.endpoint_instance_id
            or binding.socket_path != locator.socket_path
        ):
            raise ValueError("binding and locator do not identify one endpoint")
        if (
            isinstance(configured_total, bool)
            or not isinstance(configured_total, int)
            or configured_total not in {1, 2, 3}
        ):
            raise ValueError("configured_total must be in 1..3")
        self._binding = binding
        self._locator = locator
        self._configured_total = configured_total
        self._lock = Lock()
        self._shutdown_lock = Lock()
        self._condition = Condition(self._lock)
        self._listener: socket.socket | None = None
        self._accept_thread: Thread | None = None
        self._workers: set[Thread] = set()
        self._connections: set[socket.socket] = set()
        self._records: dict[str, _RequestRecord] = {}
        self._pending: list[SubmitEndpointEvent] = []
        self._active: SubmitEndpointEvent | None = None
        self._next_ordinal = 1
        self._last_admitted_ordinal: int | None = None
        self._started = False
        self._closed = False
        self._admission_open = False
        self._admission_stopped = False
        self._lifecycle: str | None = None
        self._path_ownership: _PathOwnership = "none"
        self._queued_rejected = 0
        self._active_drained = 0
        self._worker_count = 0
        self._shutdown_outcome: SubmitEndpointShutdownOutcome | None = None

    @property
    def binding(self) -> PhasedSubmitBinding:
        return self._binding

    @property
    def locator(self) -> SubmitEndpointLocator:
        return self._locator

    def start(self) -> None:
        """Allocate and bind only at the explicit post-provider-start call."""

        _remaining(self._binding.deadline)
        with self._lock:
            if self._started:
                raise RuntimeError("submit endpoint already started")
            if self._closed:
                raise RuntimeError("submit endpoint is closed")
            if self._locator.socket_path.exists():
                raise FileExistsError(self._locator.socket_path)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            bound = False
            try:
                listener.bind(str(self._locator.socket_path))
                bound = True
                self._path_ownership = "maybe_owned"
                listener.listen(8)
                listener.settimeout(
                    min(
                        _ACCEPT_POLL_SECONDS,
                        _remaining(self._binding.deadline),
                    )
                )
                accept_thread = Thread(
                    target=self._accept_loop,
                    name=(
                        "provider-phased-submit-listener-"
                        + self._binding.endpoint_instance_id
                    ),
                    daemon=True,
                )
                self._listener = listener
                self._accept_thread = accept_thread
                self._started = True
                accept_thread.start()
                self._path_ownership = "owned"
            except BaseException:
                self._listener = None
                self._accept_thread = None
                self._started = False
                listener.close()
                if bound:
                    try:
                        self._locator.socket_path.unlink()
                    except FileNotFoundError:
                        self._path_ownership = "none"
                    except OSError:
                        self._path_ownership = "maybe_owned"
                    else:
                        self._path_ownership = "none"
                raise

    def open_admission(self, lifecycle: str) -> None:
        if lifecycle not in _ADMISSION_LIFECYCLES:
            raise ValueError("submit admission lifecycle is invalid")
        with self._lock:
            if not self._started or self._closed:
                raise RuntimeError("submit endpoint is not active")
            if self._admission_stopped:
                raise RuntimeError("submit admission is permanently stopped")
            if not _deadline_positive(self._binding.deadline):
                raise TimeoutError(
                    "whole-attempt deadline exhausted before admission"
                )
            if self._last_admitted_ordinal is None:
                if lifecycle != "INITIAL_MATERIALIZATION_QUEUED":
                    raise RuntimeError(
                        "initial submit admission requires initial lifecycle"
                    )
            else:
                raise RuntimeError(
                    "retry submit admission is endpoint-owned by resolution"
                )
            self._lifecycle = lifecycle
            self._admission_open = True

    def receive_event(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointEvent:
        cutoff = (
            self._binding.deadline
            if deadline is None
            else min(self._binding.deadline, deadline)
        )
        with self._condition:
            while True:
                if self._closed:
                    raise RuntimeError("submit endpoint is closed")
                if self._active is None:
                    while self._pending:
                        event = self._pending.pop(0)
                        record = self._records[event.request.client_request_id]
                        if record.receipt is None:
                            self._active = event
                            return event
                self._condition.wait(timeout=_remaining(cutoff))

    def resolve(
        self,
        event: SubmitEndpointEvent,
        receipt: SubmitReceipt,
        *,
        rearm_retry: bool = False,
    ) -> None:
        if type(event) is not SubmitEndpointEvent:
            raise TypeError("event must be an exact SubmitEndpointEvent")
        if type(receipt) is not SubmitReceipt:
            raise TypeError("receipt must be an exact SubmitReceipt")
        if type(rearm_retry) is not bool:
            raise TypeError("rearm_retry must be a Boolean")
        if rearm_retry and receipt.status != "retry_queued":
            raise ValueError(
                "rearm_retry requires a retry_queued receipt"
            )
        with self._condition:
            record = self._records.get(event.request.client_request_id)
            if (
                record is None
                or record.event is not event
                or self._active is not event
                or record.receipt is not None
            ):
                raise ValueError("submit event is not the active request")
            if (
                receipt.client_request_id != event.request.client_request_id
                or receipt.attempt_scope_sha256
                != self._binding.attempt_scope_sha256
                or receipt.submission_ordinal != event.submission_ordinal
                or receipt.configured_total != self._configured_total
            ):
                raise ValueError("submit receipt does not bind its request")
            record.rearm_retry = rearm_retry
            record.receipt = receipt
            event._waiter.set_result(receipt)
        flushed = False
        try:
            event._response_sent.result(
                timeout=_remaining(self._binding.deadline)
            )
            flushed = True
        except FutureTimeout as exc:
            raise TimeoutError(
                "whole-attempt deadline exhausted before receipt flush"
            ) from exc
        except Exception as exc:
            raise PhasedSubmitProtocolClosedError(
                "submit receipt could not be flushed to its client"
            ) from exc
        finally:
            with self._condition:
                if (
                    flushed
                    and receipt.status == "accepted_closing"
                    and not record.drain_counted
                ):
                    record.drain_counted = True
                    self._active_drained += 1
                if self._active is event:
                    self._active = None
                retry_remains_armed = (
                    record.rearm_retry
                    and self._admission_open
                    and self._lifecycle == "RETRY_QUEUED"
                )
                if not retry_remains_armed:
                    self._lifecycle = None
                self._condition.notify_all()

    def stop_admission(self) -> None:
        """Stop new work and resolve every active/queued request terminally."""

        with self._condition:
            self._admission_open = False
            self._admission_stopped = True
            self._lifecycle = None
            active = self._active
            unresolved = [
                record
                for record in self._records.values()
                if record.receipt is None
            ]
            for record in unresolved:
                receipt = self._failure_receipt_locked(
                    record.event.request.client_request_id,
                    "submit_lifecycle_invalid",
                    ordinal=record.ordinal,
                )
                record.receipt = receipt
                record.event._waiter.set_result(receipt)
                if record.event is active:
                    if not record.drain_counted:
                        record.drain_counted = True
                        self._active_drained += 1
                else:
                    self._queued_rejected += 1
            self._active = None
            self._condition.notify_all()

    def shutdown(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointShutdownOutcome:
        cutoff = (
            self._binding.deadline
            if deadline is None
            else min(self._binding.deadline, deadline)
        )
        with self._shutdown_lock:
            return self._shutdown_serialized(cutoff)

    def _shutdown_serialized(
        self,
        cutoff: float,
    ) -> SubmitEndpointShutdownOutcome:
        with self._lock:
            if (
                self._shutdown_outcome is not None
                and self._shutdown_outcome.endpoint_zero_survivor_proven
            ):
                return self._shutdown_outcome
        self.stop_admission()
        with self._lock:
            self._closed = True
            listener = self._listener
            self._listener = None
            accept_thread = self._accept_thread
            self._condition.notify_all()
        if listener is not None:
            try:
                listener.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            listener.close()

        join_threads: tuple[Any, ...]
        with self._lock:
            worker_threads = tuple(self._workers)
            worker_count = self._worker_count
            join_threads = tuple(
                thread
                for thread in (accept_thread, *worker_threads)
                if thread is not None and thread is not current_thread()
            )
        for thread in join_threads:
            try:
                thread.join(timeout=_remaining(cutoff))
            except TimeoutError:
                break
        listener_closed = listener is None or listener.fileno() == -1
        with self._lock:
            path_ownership = self._path_ownership
        if path_ownership != "none":
            try:
                self._locator.socket_path.unlink()
            except FileNotFoundError:
                with self._lock:
                    self._path_ownership = "none"
            except OSError:
                with self._lock:
                    self._path_ownership = "maybe_owned"
            else:
                with self._lock:
                    self._path_ownership = "none"
        worker_liveness = tuple(
            thread.is_alive() for thread in worker_threads
        )
        live_workers = sum(worker_liveness)
        workers_joined = max(0, worker_count - live_workers)
        accept_thread_alive = (
            accept_thread is not None and accept_thread.is_alive()
        )
        with self._lock:
            owned_path_cleared = self._path_ownership == "none"
        zero_survivors = listener_closed and (
            not accept_thread_alive
            and not any(worker_liveness)
            and owned_path_cleared
        )
        outcome = SubmitEndpointShutdownOutcome(
            queued_requests_rejected=self._queued_rejected,
            active_requests_drained=self._active_drained,
            listener_closed=listener_closed,
            workers_joined=workers_joined,
            endpoint_zero_survivor_proven=zero_survivors,
        )
        with self._lock:
            self._shutdown_outcome = outcome
        return outcome

    def _effective_ordinal_locked(self) -> int:
        if self._active is not None:
            return self._active.submission_ordinal
        if not self._admission_open and self._last_admitted_ordinal is not None:
            return self._last_admitted_ordinal
        return min(
            self._configured_total,
            max(1, self._next_ordinal),
        )

    def _failure_receipt_locked(
        self,
        request_id: str,
        reason: str,
        *,
        ordinal: int | None = None,
    ) -> SubmitReceipt:
        effective = (
            self._effective_ordinal_locked()
            if ordinal is None
            else min(self._configured_total, max(1, ordinal))
        )
        return SubmitReceipt(
            status="failed",
            attempt_scope_sha256=self._binding.attempt_scope_sha256,
            client_request_id=request_id,
            submission_ordinal=effective,
            configured_total=self._configured_total,
            remaining_submissions=self._configured_total - effective,
            diagnostic=protocol_diagnostic(reason),
        )

    def _classify_request_locked(
        self,
        request: SubmitRequest,
    ) -> SubmitReceipt | SubmitEndpointEvent:
        # Permanent stop deliberately wins over every other observation.
        if self._admission_stopped:
            return self._failure_receipt_locked(
                request.client_request_id,
                "submit_lifecycle_invalid",
            )
        if not _deadline_positive(self._binding.deadline):
            return self._failure_receipt_locked(
                request.client_request_id,
                "deadline_exhausted_before_submit",
            )
        fingerprint = hashlib.sha256(
            _canonical(request.to_dict())
        ).hexdigest()
        prior = self._records.get(request.client_request_id)
        in_flight = next(
            (
                record
                for record in self._records.values()
                if not record.event._response_sent.done()
            ),
            None,
        )
        active_boundary = (
            in_flight is not None
            or (
                self._admission_open
                and self._lifecycle in _ADMISSION_LIFECYCLES
            )
        )
        decision: SubmitReceipt | None = None
        if active_boundary:
            if (
                request.attempt_scope_sha256
                != self._binding.attempt_scope_sha256
                or request.binding_token != self._binding.binding_token
            ):
                decision = self._failure_receipt_locked(
                    request.client_request_id,
                    "submit_binding_foreign",
                )
            elif (
                request.endpoint_instance_id
                != self._binding.endpoint_instance_id
            ):
                decision = self._failure_receipt_locked(
                    request.client_request_id,
                    "submit_binding_stale",
                )
            elif prior is not None and prior.fingerprint != fingerprint:
                decision = self._failure_receipt_locked(
                    request.client_request_id,
                    "submit_request_conflict",
                    ordinal=prior.ordinal,
                )
            elif in_flight is not None:
                decision = self._failure_receipt_locked(
                    request.client_request_id,
                    "submit_duplicate_in_flight",
                    ordinal=in_flight.ordinal,
                )
            elif prior is not None and prior.receipt is not None:
                decision = prior.receipt
        else:
            # Transient closure permits only an exact prior replay/conflict.
            if prior is not None and prior.fingerprint != fingerprint:
                decision = self._failure_receipt_locked(
                    request.client_request_id,
                    "submit_request_conflict",
                    ordinal=prior.ordinal,
                )
            elif prior is not None and prior.receipt is not None:
                decision = prior.receipt
            else:
                decision = self._failure_receipt_locked(
                    request.client_request_id,
                    "submit_lifecycle_invalid",
                )
        if decision is None and self._next_ordinal > self._configured_total:
            decision = self._failure_receipt_locked(
                request.client_request_id,
                "submit_lifecycle_invalid",
            )
        if not _deadline_positive(self._binding.deadline):
            return self._failure_receipt_locked(
                request.client_request_id,
                "deadline_exhausted_during_submit",
            )
        if decision is not None:
            return decision
        ordinal = self._next_ordinal
        self._next_ordinal += 1
        self._last_admitted_ordinal = ordinal
        self._admission_open = False
        waiter: Future[SubmitReceipt] = Future()
        response_sent: Future[None] = Future()
        event = SubmitEndpointEvent(
            request=request,
            submission_ordinal=ordinal,
            _waiter=waiter,
            _response_sent=response_sent,
        )
        self._records[request.client_request_id] = _RequestRecord(
            fingerprint=fingerprint,
            ordinal=ordinal,
            event=event,
        )
        self._pending.append(event)
        self._condition.notify_all()
        return event

    def _accept_loop(self) -> None:
        while True:
            with self._lock:
                listener = self._listener
                closed = self._closed
            if closed or listener is None:
                return
            try:
                listener.settimeout(
                    min(
                        _ACCEPT_POLL_SECONDS,
                        _remaining(self._binding.deadline),
                    )
                )
                connection, _address = listener.accept()
            except socket.timeout:
                continue
            except (OSError, TimeoutError):
                return
            worker = Thread(
                target=self._handle_connection,
                args=(connection,),
                name="provider-phased-submit-request",
                daemon=True,
            )
            with self._lock:
                if self._closed:
                    connection.close()
                    return
                self._connections.add(connection)
                self._workers.add(worker)
                try:
                    worker.start()
                except BaseException:
                    self._workers.discard(worker)
                    self._connections.discard(connection)
                    connection.close()
                    continue
                self._worker_count += 1

    def _handle_connection(self, connection: socket.socket) -> None:
        event: SubmitEndpointEvent | None = None
        try:
            with connection:
                request = SubmitRequest.from_dict(
                    _decode_frame(
                        _read_frame(
                            connection,
                            deadline=self._binding.deadline,
                        ),
                        field="submit request",
                    )
                )
                with self._condition:
                    decision = self._classify_request_locked(request)
                if isinstance(decision, SubmitEndpointEvent):
                    event = decision
                    receipt = decision._waiter.result(
                        timeout=_remaining(self._binding.deadline)
                    )
                else:
                    receipt = decision
                connection.settimeout(_remaining(self._binding.deadline))
                encoded_receipt = _canonical(receipt_to_dict(receipt))
                if event is None:
                    connection.sendall(encoded_receipt)
                    _shutdown_write(connection)
                else:
                    with self._condition:
                        record = self._records[
                            event.request.client_request_id
                        ]
                        if (
                            receipt.status == "retry_queued"
                            and (
                                self._admission_stopped
                                or self._closed
                            )
                        ):
                            receipt = self._failure_receipt_locked(
                                event.request.client_request_id,
                                "submit_lifecycle_invalid",
                                ordinal=record.ordinal,
                            )
                            record.receipt = receipt
                            record.rearm_retry = False
                            encoded_receipt = _canonical(
                                receipt_to_dict(receipt)
                            )
                        retry_armed = (
                            record.rearm_retry
                            and not self._admission_stopped
                            and not self._closed
                        )
                        if retry_armed:
                            self._lifecycle = "RETRY_QUEUED"
                            self._admission_open = True
                        connection.sendall(encoded_receipt)
                        _shutdown_write(connection)
                        event._response_sent.set_result(None)
        except (
            FutureTimeout,
            OSError,
            TimeoutError,
            TypeError,
            ValueError,
        ) as exc:
            if event is not None and not event._response_sent.done():
                event._response_sent.set_exception(exc)
        finally:
            with self._lock:
                self._connections.discard(connection)
                self._workers.discard(current_thread())
