"""Serialized local owner for one attempt-bound materialization endpoint.

The endpoint owns only ingress, request replay, and receipt delivery. It never
reads or writes workflow state, a phase ledger, adapter state, or coordinator
authority.
"""

from __future__ import annotations

from concurrent.futures import Future, TimeoutError as FutureTimeout
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import os
import socket
import stat
from threading import Condition, Lock, Thread, current_thread
import time
from typing import Any, Literal

from orchestrator.providers import _interactive_terminal_lifecycle as ownership
from orchestrator.providers.interactive_terminal import PhasedFailedCleanupEvidence
from orchestrator.monitor.process import process_start_time_token
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator._common.safe_tree import SafeTreeRejectionError

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
_OWNED_RECORD_FIELDS = {"schema_version", "adapter_token", "boot_id", "controller_pid",
    "controller_start_ticks", "state", "socket_dev", "socket_ino"}


def _socket_name(reservation):
    return "phased-" + reservation.adapter_token + ".sock"


def _socket_identity(files, name):
    try:
        info = files.stat(name)
    except FileNotFoundError:
        return None
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("foreign submit socket type or owner")
    return info.st_dev, info.st_ino


def _read_owned_record(reservation, files):
    try:
        info = files.stat("submit.json")
    except FileNotFoundError:
        return None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise ValueError("foreign submit record file")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate submit record key")
            result[key] = value
        return result
    record = json.loads(files.read("submit.json", max_bytes=8192), object_pairs_hook=unique)
    if (not isinstance(record, dict) or set(record) != _OWNED_RECORD_FIELDS
            or record["schema_version"] != "phased_submit_endpoint.v1"
            or record["adapter_token"] != reservation.adapter_token
            or record["boot_id"] != reservation.boot_id
            or any(type(record[key]) is not int or record[key] <= 0
                for key in ("controller_pid", "controller_start_ticks"))
            or record["state"] not in {"binding", "bound", "closed"}):
        raise ValueError("foreign or invalid submit ownership record")
    pair = record["socket_dev"], record["socket_ino"]
    valid_pair = type(pair[0]) is int and pair[0] >= 0 and type(pair[1]) is int and pair[1] > 0
    if not ((pair == (None, None) and record["state"] != "bound")
            or valid_pair and record["state"] != "binding"):
        raise ValueError("invalid submit socket identity domains")
    return record


def _controller_dead(record):
    token = process_start_time_token(record["controller_pid"])
    if token is not None:
        if int(token) == record["controller_start_ticks"]:
            raise ValueError("submit controller is still alive")
        return
    try:
        os.kill(record["controller_pid"], 0)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise ValueError("submit controller death cannot be proven") from exc
    raise ValueError("submit controller identity is unreadable")


@contextmanager
def _owned_files(reservation, deadline=None):
    with ownership.opened(reservation) as files:
        lease = None
        try:
            if deadline is not None:
                lease = ownership.acquire(reservation, files, deadline)
            yield files
        finally:
            if lease is not None:
                os.close(lease)


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
        reservation=None,
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
        if reservation is not None and locator.socket_path != reservation.path / _socket_name(reservation):
            raise ValueError("submit locator does not bind its private reservation")
        self._reservation = reservation
        self._socket_identity = None
        self._ownership_record = None
        self._path_files = None
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
            try:
                self._path_files = WorkspaceFiles(self._locator.socket_path.parent)
            except SafeTreeRejectionError as exc:
                raise OSError("submit endpoint parent is unavailable or unsafe") from exc
            if self._path_files.exists(self._locator.socket_path.name):
                raise FileExistsError(self._locator.socket_path)
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            bound = False
            try:
                if self._reservation is not None:
                    with _owned_files(self._reservation, self._binding.deadline) as files:
                        if files.exists("submit.json") or files.exists(_socket_name(self._reservation)):
                            raise ValueError("submit ownership already allocated")
                        ticks = process_start_time_token(os.getpid())
                        if ticks is None:
                            raise ValueError("submit controller identity unavailable")
                        self._ownership_record = {"schema_version": "phased_submit_endpoint.v1",
                            "adapter_token": self._reservation.adapter_token, "boot_id": self._reservation.boot_id,
                            "controller_pid": os.getpid(), "controller_start_ticks": int(ticks),
                            "state": "binding", "socket_dev": None, "socket_ino": None}
                        files.write_atomic("submit.json", canonical_json_bytes(self._ownership_record))
                        listener.bind(f"/proc/self/fd/{files.root_fd}/{_socket_name(self._reservation)}")
                        bound = True
                        self._socket_identity = _socket_identity(files, _socket_name(self._reservation))
                        self._path_ownership = "owned"
                        self._ownership_record = {**self._ownership_record, "state": "bound",
                            "socket_dev": self._socket_identity[0], "socket_ino": self._socket_identity[1]}
                        files.write_atomic("submit.json", canonical_json_bytes(self._ownership_record))
                else:
                    listener.bind(str(self._locator.socket_path))
                    self._socket_identity = _socket_identity(self._path_files, self._locator.socket_path.name)
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
                        self._unlink_observed_socket(self._binding.deadline)
                    except FileNotFoundError:
                        self._path_ownership = "none"
                    except OSError:
                        self._path_ownership = "maybe_owned"
                    else:
                        self._path_ownership = "none"
                raise

    def _unlink_observed_socket(self, deadline):
        def remove(files, name):
            actual = _socket_identity(files, name)
            if actual is not None:
                if actual != self._socket_identity:
                    raise OSError("submit socket identity changed")
                if _socket_identity(files, name) != actual:
                    raise OSError("submit socket identity changed before unlink")
                files.unlink(name)
            if files.exists(name):
                raise OSError("submit socket absence unproven")
        if self._reservation is not None:
            with _owned_files(self._reservation, deadline) as files:
                record = _read_owned_record(self._reservation, files)
                if (record is None or self._ownership_record is None
                        or any(record[key] != self._ownership_record[key]
                            for key in ("controller_pid", "controller_start_ticks"))
                        or record["state"] == "closed"):
                    raise OSError("submit ownership changed before unlink")
                if record["state"] == "bound" and self._socket_identity != (
                        record["socket_dev"], record["socket_ino"]):
                    raise OSError("submit observation changed before unlink")
                remove(files, _socket_name(self._reservation))
        else:
            linked = os.stat(self._path_files.workspace, follow_symlinks=False)
            pinned = os.fstat(self._path_files.root_fd)
            if (linked.st_dev, linked.st_ino) != (pinned.st_dev, pinned.st_ino):
                raise OSError("submit parent replaced")
            remove(self._path_files, self._locator.socket_path.name)

    @staticmethod
    def inspect_owned(reservation, *, deadline):
        """Read-only restart admission, before any provider cleanup mutation."""
        ownership.remaining(deadline)
        with _owned_files(reservation) as files:
            record = _read_owned_record(reservation, files)
            observed = _socket_identity(files, _socket_name(reservation))
            if record is None:
                if observed is not None:
                    raise ValueError("submit socket without ownership record")
            elif record["state"] == "closed":
                if observed is not None:
                    raise ValueError("unexpected socket after closed submit record")
            else:
                if record["state"] == "bound" and observed is not None and observed != (
                        record["socket_dev"], record["socket_ino"]):
                    raise ValueError("submit socket was replaced")
                _controller_dead(record)
            ownership.remaining(deadline)
            return record, observed

    @staticmethod
    def recover_owned(reservation, *, deadline, provider_cleanup, admission=None):
        """Remove only the fixed owned endpoint after proven provider cleanup."""
        if type(provider_cleanup) is not PhasedFailedCleanupEvidence or not provider_cleanup.cleanup_complete:
            raise ValueError("provider cleanup must precede endpoint recovery")
        current = PhasedSubmitEndpoint.inspect_owned(reservation, deadline=deadline)
        if admission is not None and current != admission:
            raise ValueError("submit ownership changed during provider cleanup")
        record, observed = current
        with _owned_files(reservation, deadline) as files:
            if (_read_owned_record(reservation, files), _socket_identity(files, _socket_name(reservation))) != current:
                raise ValueError("submit ownership changed before cleanup")
            if observed is not None:
                files.unlink(_socket_name(reservation))
            if files.exists(_socket_name(reservation)):
                raise ValueError("submit socket remains after cleanup")
            if record is not None:
                files.write_atomic("submit.json", canonical_json_bytes({**record, "state": "closed"}))
            ownership.remaining(deadline)
        return True

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
                self._unlink_observed_socket(cutoff)
            except FileNotFoundError:
                with self._lock:
                    self._path_ownership = "none"
            except (OSError, ValueError, RuntimeError):
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
        if zero_survivors and self._reservation is not None and self._ownership_record is not None:
            try:
                with _owned_files(self._reservation, cutoff) as files:
                    record = _read_owned_record(self._reservation, files)
                    if (record is None or record["controller_pid"] != os.getpid()
                            or record["controller_start_ticks"] != int(process_start_time_token(os.getpid()))
                            or files.exists(_socket_name(self._reservation))):
                        raise ValueError("submit ownership changed before closed publication")
                    files.write_atomic("submit.json", canonical_json_bytes({**record, "state": "closed"}))
            except (OSError, ValueError, RuntimeError, TypeError):
                zero_survivors = False
        outcome = SubmitEndpointShutdownOutcome(
            queued_requests_rejected=self._queued_rejected,
            active_requests_drained=self._active_drained,
            listener_closed=listener_closed,
            workers_joined=workers_joined,
            endpoint_zero_survivor_proven=zero_survivors,
        )
        with self._lock:
            self._shutdown_outcome = outcome
        if zero_survivors and self._path_files is not None:
            self._path_files.close()
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
