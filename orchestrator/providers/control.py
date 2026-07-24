"""Thread-safe cancellation and terminal proof for one provider invocation."""

from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Literal, Mapping

from .session_transport import SessionIdentitySnapshot


ProviderControlState = Literal["NEW", "BOUND", "TERMINAL"]
ProviderTerminalDisposition = Literal[
    "natural_exit",
    "cancelled",
    "spawn_failed",
    "boundary_failed",
]


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_value(nested_value)
                for key, nested_value in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    return value


def _copy_session_snapshot(
    snapshot: SessionIdentitySnapshot,
) -> SessionIdentitySnapshot:
    error = snapshot.error
    return SessionIdentitySnapshot(
        status=snapshot.status,
        session_ids=tuple(snapshot.session_ids),
        terminal_seen=bool(snapshot.terminal_seen),
        error=(
            MappingProxyType(
                {
                    key: _freeze_value(value)
                    for key, value in error.items()
                }
            )
            if error is not None
            else None
        ),
        resume_boundary_seen=bool(snapshot.resume_boundary_seen),
    )


@dataclass(frozen=True)
class ProviderCancellationResult:
    """One immutable disposition and proof for a controlled invocation."""

    disposition: ProviderTerminalDisposition
    pgid: int | None
    leader_return_code: int | None
    leader_reaped: bool
    pgid_empty: bool
    capture_threads_joined: bool
    execution_joined: bool
    final_session_snapshot: SessionIdentitySnapshot | None
    final_identity_valid: bool
    proof_complete: bool
    term_sent: bool
    kill_sent: bool
    natural_exit_with_lingering_group: bool
    cancellation_reason: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class _ProviderExecutionBoundary:
    """Complete executor-owned boundary facts awaiting Future completion."""

    disposition: ProviderTerminalDisposition
    pgid: int | None
    leader_return_code: int | None
    leader_reaped: bool
    pgid_empty: bool
    capture_threads_joined: bool
    final_session_snapshot: SessionIdentitySnapshot | None
    final_identity_valid: bool
    boundary_complete: bool
    term_sent: bool
    kill_sent: bool
    natural_exit_with_lingering_group: bool
    cancellation_reason: str | None
    error: str | None


class ProviderExecutionControl:
    """Coordinate cancellation without taking ownership of ``Popen.wait``."""

    _DEFAULT_CANCELLATION_GRACE_SEC = 0.2
    _FINALIZATION_TIMEOUT_SEC = 5.0
    _POLL_INTERVAL_SEC = 0.01

    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._state: ProviderControlState = "NEW"
        self._process: Any = None
        self._pgid: int | None = None
        self._cancellation_requested = False
        self._cancellation_reason: str | None = None
        self._cancellation_requested_before_bind = False
        self._cancellation_grace_sec = (
            self._DEFAULT_CANCELLATION_GRACE_SEC
        )
        self._cancellation_applied_before_completion = False
        self._cancellation_application_unproved = False
        self._term_attempted_at: float | None = None
        self._term_applied_at: float | None = None
        self._term_sent = False
        self._kill_sent = False
        self._kill_attempted = False
        self._group_term_attempted = False
        self._group_kill_attempted = False
        self._leader_term_attempted = False
        self._leader_kill_attempted = False
        self._leader_return_code: int | None = None
        self._leader_reaped = False
        self._pgid_empty = False
        self._capture_threads_joined = False
        self._missing_terminal_eof_preceded_cancellation = False
        self._identity_required = False
        self._session_snapshot: SessionIdentitySnapshot | None = None
        self._natural_exit_with_lingering_group = False
        self._signal_error: str | None = None
        self._execution_future: Any = None
        self._execution_future_attached = False
        self._execution_future_done = False
        self._spawn_claimed = False
        self._boundary: _ProviderExecutionBoundary | None = None
        self._pending_terminal_result: ProviderCancellationResult | None = None
        self._terminal_result: ProviderCancellationResult | None = None

    @property
    def state(self) -> ProviderControlState:
        with self._condition:
            return self._state

    @property
    def cancellation_requested(self) -> bool:
        with self._condition:
            return self._cancellation_requested

    @property
    def cancellation_reason(self) -> str | None:
        with self._condition:
            return self._cancellation_reason

    def classify_stdin_broken_pipe(
        self,
        *,
        failure_grace: float,
    ) -> bool:
        """Linearize a broken stdin pipe against applied cancellation."""
        if failure_grace < 0:
            raise ValueError("stdin failure grace must be non-negative")
        with self._condition:
            expected = self._cancellation_applied_before_completion
            if (
                not expected
                and (
                    self._terminal_result is None
                    or (
                        self._pgid is not None
                        and not self._leader_reaped
                    )
                )
            ):
                self._request_cancel_locked(
                    reason="stdin_writer_failure",
                    grace=failure_grace,
                )
            return expected

    @property
    def session_snapshot(self) -> SessionIdentitySnapshot | None:
        with self._condition:
            return self._session_snapshot

    @property
    def terminal_result(self) -> ProviderCancellationResult | None:
        with self._condition:
            return self._terminal_result

    def attach_execution_future(self, future: Any) -> None:
        """Attach the one Future whose done state proves executor completion."""
        add_done_callback = getattr(future, "add_done_callback", None)
        done = getattr(future, "done", None)
        if not callable(add_done_callback) or not callable(done):
            raise TypeError(
                "provider execution future must expose done and add_done_callback"
            )

        with self._condition:
            if self._execution_future_attached:
                raise RuntimeError("provider execution future is already attached")
            self._execution_future_attached = True
            self._execution_future = future
            cancel_queued_execution = (
                self._queued_execution_future_locked() is not None
            )

        add_done_callback(self._execution_future_completed)
        if cancel_queued_execution:
            try:
                future.cancel()
            except Exception:
                pass

    def claim_spawn(self) -> None:
        """Claim this fresh control for exactly one executor launch."""
        with self._condition:
            if self._state != "NEW" or self._terminal_result is not None:
                raise RuntimeError(
                    f"provider execution control cannot spawn from {self._state}"
                )
            if self._spawn_claimed:
                raise RuntimeError(
                    "provider execution control launch is already claimed"
                )
            self._spawn_claimed = True

    def bind(self, process: Any, pgid: int) -> None:
        """Bind exactly one successfully spawned process and owned process group."""
        if not isinstance(pgid, int) or pgid <= 0:
            raise ValueError("provider process group id must be a positive integer")
        process_pid = getattr(process, "pid", None)
        if not isinstance(process_pid, int) or process_pid <= 0:
            raise ValueError("provider process must expose a positive pid")

        with self._condition:
            if self._state != "NEW":
                raise RuntimeError(
                    f"provider execution control cannot bind from {self._state}"
                )
            self._process = process
            self._pgid = pgid
            self._state = "BOUND"
            self._condition.notify_all()

    def record_bind_failure(
        self,
        *,
        process: Any,
        pgid: int,
        return_code: int | None,
        leader_reaped: bool,
        pgid_empty: bool,
        term_sent: bool,
        kill_sent: bool,
        error: BaseException | str,
    ) -> ProviderCancellationResult:
        """Record emergency BOUND proof when normal binding was rejected."""
        with self._condition:
            if self._terminal_result is not None:
                return self._terminal_result
            if self._pending_terminal_result is not None:
                return self._pending_terminal_result
            if self._state not in {"NEW", "BOUND"}:
                raise RuntimeError(
                    "provider bind failure requires a live launch control"
                )
            self._process = process
            self._pgid = pgid
            self._state = "BOUND"
            self._condition.notify_all()
            self._leader_return_code = return_code
            self._leader_reaped = bool(leader_reaped)
            self._pgid_empty = bool(pgid_empty)
            self._capture_threads_joined = True
            self._term_sent = bool(term_sent)
            self._kill_sent = bool(kill_sent)
            final_identity_valid = not self._identity_required
            result = ProviderCancellationResult(
                disposition="boundary_failed",
                pgid=pgid,
                leader_return_code=return_code,
                leader_reaped=self._leader_reaped,
                pgid_empty=self._pgid_empty,
                capture_threads_joined=True,
                execution_joined=self._execution_future_done,
                final_session_snapshot=self._session_snapshot,
                final_identity_valid=final_identity_valid,
                proof_complete=False,
                term_sent=self._term_sent,
                kill_sent=self._kill_sent,
                natural_exit_with_lingering_group=False,
                cancellation_reason=self._cancellation_reason,
                error=f"provider process bind failed: {error}",
            )
            if (
                self._execution_future_attached
                and not self._execution_future_done
            ):
                self._pending_terminal_result = result
                self._condition.notify_all()
                return result
            return self._freeze_terminal_locked(result)

    def publish_session_snapshot(
        self,
        snapshot: SessionIdentitySnapshot,
    ) -> None:
        """Publish one detached immutable identity snapshot to waiting callers."""
        if not isinstance(snapshot, SessionIdentitySnapshot):
            raise TypeError("session snapshot must be a SessionIdentitySnapshot")
        frozen_snapshot = _copy_session_snapshot(snapshot)
        with self._condition:
            if self._state == "TERMINAL":
                return
            self._identity_required = True
            self._session_snapshot = frozen_snapshot
            self._condition.notify_all()

    def record_missing_terminal_at_session_stdout_eof(
        self,
        snapshot: SessionIdentitySnapshot,
    ) -> None:
        """Record exact session EOF without a terminal marker."""
        if not isinstance(snapshot, SessionIdentitySnapshot):
            raise TypeError("session snapshot must be a SessionIdentitySnapshot")
        if snapshot.terminal_seen:
            raise ValueError(
                "missing-terminal EOF cannot contain a terminal marker"
            )
        with self._condition:
            if self._terminal_result is not None:
                return
            if not self._cancellation_requested:
                self._missing_terminal_eof_preceded_cancellation = True
            self._condition.notify_all()

    def spawn_failed(self, error: BaseException | str) -> ProviderCancellationResult:
        """Terminalize a process-creation failure without entering ``BOUND``."""
        with self._condition:
            if self._terminal_result is not None:
                return self._terminal_result
            if self._pending_terminal_result is not None:
                return self._pending_terminal_result
            if self._state != "NEW":
                raise RuntimeError(
                    "spawn failure is valid only before process binding"
                )
            self._capture_threads_joined = True
            result = ProviderCancellationResult(
                disposition="spawn_failed",
                pgid=None,
                leader_return_code=None,
                leader_reaped=False,
                pgid_empty=False,
                capture_threads_joined=True,
                execution_joined=self._execution_future_done,
                final_session_snapshot=self._session_snapshot,
                final_identity_valid=not self._identity_required,
                proof_complete=False,
                term_sent=False,
                kill_sent=False,
                natural_exit_with_lingering_group=False,
                cancellation_reason=self._cancellation_reason,
                error=str(error),
            )
            if (
                self._execution_future_attached
                and not self._execution_future_done
            ):
                self._pending_terminal_result = result
                self._condition.notify_all()
                return result
            return self._freeze_terminal_locked(result)

    def request_cancel(
        self,
        *,
        reason: str = "external",
        grace: float | None = None,
    ) -> None:
        """Latch cancellation for the executor-owned wait loop."""
        if grace is not None and grace < 0:
            raise ValueError("cancellation grace must be non-negative")
        future_to_cancel: Any = None
        with self._condition:
            if self._terminal_result is not None:
                return
            self._request_cancel_locked(reason=reason, grace=grace)
            future_to_cancel = self._queued_execution_future_locked()
        self._cancel_future(future_to_cancel)

    def force_kill(self) -> None:
        """Ask the executor-owned wait loop to escalate without delay."""
        future_to_cancel: Any = None
        with self._condition:
            if self._terminal_result is not None:
                return
            self._request_cancel_locked(
                reason=self._cancellation_reason or "external",
                grace=0.0,
            )
            future_to_cancel = self._queued_execution_future_locked()
        self._cancel_future(future_to_cancel)

    def apply_pending_cancellation_after_incomplete_probe(self) -> None:
        """Apply pending signals after the executor observed an incomplete wait."""
        with self._condition:
            if (
                self._pgid is None
                or self._leader_reaped
                or not self._cancellation_requested
            ):
                return

            now = time.monotonic()
            if self._term_attempted_at is None:
                self._term_attempted_at = now
                applied = self._send_signal_locked(signal.SIGTERM)
                if not applied:
                    applied = self._send_leader_signal_locked(signal.SIGTERM)
                if applied:
                    self._cancellation_applied_before_completion = True
                    self._term_applied_at = now
                else:
                    self._cancellation_application_unproved = True
            elif (
                not self._kill_attempted
                and now - self._term_attempted_at
                >= self._cancellation_grace_sec
            ):
                self._kill_attempted = True
                applied = self._send_signal_locked(signal.SIGKILL)
                if not applied:
                    applied = self._send_leader_signal_locked(signal.SIGKILL)
                if applied:
                    self._cancellation_applied_before_completion = True
                else:
                    self._cancellation_application_unproved = True
            self._condition.notify_all()

    def record_leader_reaped(
        self,
        return_code: int,
        *,
        cleanup_grace: float = 0.2,
    ) -> bool:
        """Record the executor-owned wait and clean any residual owned group."""
        with self._condition:
            if self._process is None or self._pgid is None:
                raise RuntimeError(
                    "provider leader can be reaped only after process binding"
                )
            if self._leader_reaped:
                if self._leader_return_code != return_code:
                    raise RuntimeError("provider leader return code changed")
                return self._probe_group_empty_locked()
            self._leader_return_code = return_code
            self._leader_reaped = True
            group_empty = self._probe_group_empty_locked()
            if (
                not group_empty
                and not self._cancellation_applied_before_completion
            ):
                self._natural_exit_with_lingering_group = True
            if not group_empty:
                self._send_signal_locked(signal.SIGTERM)
            self._condition.notify_all()

        if group_empty:
            return True
        if self._wait_for_group_empty(
            cleanup_grace,
            honor_cancellation_grace=(
                self._cancellation_applied_before_completion
            ),
        ):
            return True
        with self._condition:
            self._send_signal_locked(signal.SIGKILL)
            self._condition.notify_all()
        return self._wait_for_group_empty(max(cleanup_grace, 0.2))

    def record_execution_boundary(
        self,
        *,
        capture_threads_joined: bool,
        final_identity_valid: bool,
        transport_failed: bool = False,
        boundary_error: str | None = None,
    ) -> _ProviderExecutionBoundary | ProviderCancellationResult:
        """Record executor-owned facts before the attached Future can complete."""
        with self._condition:
            if self._process is None or self._pgid is None:
                raise RuntimeError(
                    "provider boundary can be recorded only after process binding"
                )
            if self._boundary is not None:
                if self._terminal_result is not None:
                    return self._terminal_result
                raise RuntimeError("provider execution boundary is already recorded")

            self._capture_threads_joined = bool(capture_threads_joined)
            self._pgid_empty = self._probe_group_empty_locked()
            identity_valid = bool(final_identity_valid) and (
                not self._identity_required
                or (
                    self._session_snapshot is not None
                    and self._session_snapshot.status == "unique"
                )
            )
            cancellation_unproved = (
                self._cancellation_application_unproved
                or (
                    self._cancellation_requested_before_bind
                    and not self._cancellation_applied_before_completion
                )
            )
            boundary_complete = (
                self._leader_reaped
                and self._pgid_empty
                and self._capture_threads_joined
                and identity_valid
                and not self._natural_exit_with_lingering_group
                and not cancellation_unproved
                and self._signal_error is None
                and boundary_error is None
            )
            if not boundary_complete:
                disposition: ProviderTerminalDisposition = "boundary_failed"
            elif (
                transport_failed
                and self._missing_terminal_eof_preceded_cancellation
            ):
                disposition = "natural_exit"
            elif self._cancellation_applied_before_completion:
                disposition = "cancelled"
            else:
                disposition = "natural_exit"

            proof_error = self._proof_error_locked(identity_valid)
            if boundary_error is not None and proof_error is not None:
                error = f"{boundary_error}; {proof_error}"
            else:
                error = boundary_error or proof_error
            boundary = _ProviderExecutionBoundary(
                disposition=disposition,
                pgid=self._pgid,
                leader_return_code=self._leader_return_code,
                leader_reaped=self._leader_reaped,
                pgid_empty=self._pgid_empty,
                capture_threads_joined=self._capture_threads_joined,
                final_session_snapshot=self._session_snapshot,
                final_identity_valid=identity_valid,
                boundary_complete=boundary_complete,
                term_sent=self._term_sent,
                kill_sent=self._kill_sent,
                natural_exit_with_lingering_group=(
                    self._natural_exit_with_lingering_group
                ),
                cancellation_reason=self._cancellation_reason,
                error=error,
            )
            self._boundary = boundary
            if (
                self._terminal_result is None
                and self._execution_future_done
            ):
                self._freeze_boundary_result_locked(boundary)
            self._condition.notify_all()
            return self._terminal_result or boundary

    def cancel_and_reap(
        self,
        grace: float,
    ) -> ProviderCancellationResult:
        """Idempotently cancel, await executor-owned reaping, and return proof."""
        if grace < 0:
            raise ValueError("cancellation grace must be non-negative")

        future_to_cancel: Any = None
        with self._condition:
            if self._terminal_result is not None:
                return self._terminal_result
            if self._boundary is None:
                self._request_cancel_locked(
                    reason="external",
                    grace=grace,
                )
                future_to_cancel = self._queued_execution_future_locked()

        self._cancel_future(future_to_cancel)

        with self._condition:
            if self._terminal_result is not None:
                return self._terminal_result
            if self._boundary is None:
                while (
                    self._state == "NEW"
                    and self._terminal_result is None
                ):
                    self._condition.wait()
                if self._terminal_result is not None:
                    return self._terminal_result

                term_deadline = time.monotonic() + grace
                while (
                    self._terminal_result is None
                    and self._boundary is None
                ):
                    remaining = term_deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._condition.wait(timeout=remaining)
                if self._terminal_result is not None:
                    return self._terminal_result

            final_deadline = (
                time.monotonic() + self._FINALIZATION_TIMEOUT_SEC
            )
            while self._terminal_result is None:
                remaining = final_deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=remaining)
            if self._terminal_result is not None:
                return self._terminal_result

            return self._freeze_unjoined_failure_locked()

    def _execution_future_completed(self, future: Any) -> None:
        """Freeze a successful boundary only after its attached Future is done."""
        with self._condition:
            if future is not self._execution_future:
                return
            try:
                future_done = bool(future.done())
            except Exception:
                future_done = False
            if not future_done:
                if self._signal_error is None:
                    self._signal_error = (
                        "provider execution future callback ran before completion"
                    )
                self._condition.notify_all()
                return
            self._execution_future_done = True
            if (
                self._boundary is not None
                and self._terminal_result is None
            ):
                self._freeze_boundary_result_locked(self._boundary)
                return
            if (
                self._pending_terminal_result is not None
                and self._terminal_result is None
            ):
                self._freeze_terminal_locked(
                    replace(
                        self._pending_terminal_result,
                        execution_joined=True,
                    )
                )
                return
            if (
                self._state == "NEW"
                and self._terminal_result is None
            ):
                if future.cancelled():
                    launch_error = (
                        "provider execution future was cancelled before "
                        "process binding"
                    )
                else:
                    try:
                        future_error = future.exception()
                    except Exception as exc:
                        future_error = exc
                    if future_error is None:
                        launch_error = (
                            "provider execution completed before process binding"
                        )
                    else:
                        launch_error = (
                            "provider execution failed before process binding: "
                            f"{future_error}"
                        )
                self.spawn_failed(launch_error)
                return
            self._condition.notify_all()

    def _freeze_boundary_result_locked(
        self,
        boundary: _ProviderExecutionBoundary,
    ) -> ProviderCancellationResult:
        execution_joined = self._execution_future_done
        proof_complete = boundary.boundary_complete and execution_joined
        disposition = (
            boundary.disposition
            if proof_complete or boundary.disposition == "boundary_failed"
            else "boundary_failed"
        )
        error = boundary.error
        if not execution_joined and error is None:
            error = "provider execution future was not joined"
        result = ProviderCancellationResult(
            disposition=disposition,
            pgid=boundary.pgid,
            leader_return_code=boundary.leader_return_code,
            leader_reaped=boundary.leader_reaped,
            pgid_empty=boundary.pgid_empty,
            capture_threads_joined=boundary.capture_threads_joined,
            execution_joined=execution_joined,
            final_session_snapshot=boundary.final_session_snapshot,
            final_identity_valid=boundary.final_identity_valid,
            proof_complete=proof_complete,
            term_sent=boundary.term_sent,
            kill_sent=boundary.kill_sent,
            natural_exit_with_lingering_group=(
                boundary.natural_exit_with_lingering_group
            ),
            cancellation_reason=boundary.cancellation_reason,
            error=error,
        )
        return self._freeze_terminal_locked(result)

    def _freeze_unjoined_failure_locked(self) -> ProviderCancellationResult:
        boundary = self._boundary
        if boundary is not None:
            pgid = boundary.pgid
            leader_return_code = boundary.leader_return_code
            leader_reaped = boundary.leader_reaped
            pgid_empty = boundary.pgid_empty
            capture_threads_joined = boundary.capture_threads_joined
            final_session_snapshot = boundary.final_session_snapshot
            final_identity_valid = boundary.final_identity_valid
            natural_lingering = boundary.natural_exit_with_lingering_group
        else:
            pgid = self._pgid
            leader_return_code = self._leader_return_code
            leader_reaped = self._leader_reaped
            pgid_empty = self._probe_group_empty_locked()
            capture_threads_joined = self._capture_threads_joined
            final_session_snapshot = self._session_snapshot
            final_identity_valid = (
                not self._identity_required
                or (
                    self._session_snapshot is not None
                    and self._session_snapshot.status == "unique"
                )
            )
            natural_lingering = self._natural_exit_with_lingering_group

        if not self._execution_future_attached:
            join_error = "provider execution future was not attached"
        elif not self._execution_future_done:
            join_error = "provider execution future was not joined"
        else:
            join_error = "provider executor did not record a complete boundary"
        primary_error = (
            boundary.error
            if boundary is not None
            else (
                self._pending_terminal_result.error
                if self._pending_terminal_result is not None
                else self._proof_error_locked(final_identity_valid)
            )
        )
        error = (
            join_error
            if primary_error is None
            else f"{primary_error}; {join_error}"
        )
        result = ProviderCancellationResult(
            disposition="boundary_failed",
            pgid=pgid,
            leader_return_code=leader_return_code,
            leader_reaped=leader_reaped,
            pgid_empty=pgid_empty,
            capture_threads_joined=capture_threads_joined,
            execution_joined=self._execution_future_done,
            final_session_snapshot=final_session_snapshot,
            final_identity_valid=final_identity_valid,
            proof_complete=False,
            term_sent=self._term_sent,
            kill_sent=self._kill_sent,
            natural_exit_with_lingering_group=natural_lingering,
            cancellation_reason=self._cancellation_reason,
            error=error,
        )
        return self._freeze_terminal_locked(result)

    def _request_cancel_locked(
        self,
        *,
        reason: str,
        grace: float | None,
    ) -> None:
        if not self._cancellation_requested:
            self._cancellation_requested_before_bind = self._state == "NEW"
            self._cancellation_requested = True
            self._cancellation_reason = reason
            self._cancellation_grace_sec = (
                self._DEFAULT_CANCELLATION_GRACE_SEC
                if grace is None
                else grace
            )
        elif grace is not None:
            self._cancellation_grace_sec = min(
                self._cancellation_grace_sec,
                grace,
            )
        self._condition.notify_all()

    def _queued_execution_future_locked(self) -> Any:
        if (
            not self._cancellation_requested
            or self._state != "NEW"
            or self._spawn_claimed
            or not self._execution_future_attached
            or self._execution_future_done
        ):
            return None
        return self._execution_future

    @staticmethod
    def _cancel_future(future: Any) -> None:
        if future is None:
            return
        try:
            future.cancel()
        except Exception:
            pass

    def _send_leader_signal_locked(self, sig: signal.Signals) -> bool:
        if self._process is None or self._leader_reaped:
            return False
        if sig == signal.SIGTERM:
            if self._leader_term_attempted:
                return False
            self._leader_term_attempted = True
            method_name = "terminate"
        elif sig == signal.SIGKILL:
            if self._leader_kill_attempted:
                return False
            self._leader_kill_attempted = True
            method_name = "kill"
        else:
            return False

        method = getattr(self._process, method_name, None)
        if not callable(method):
            return False
        try:
            method()
        except ProcessLookupError:
            return False
        except Exception as exc:
            if self._signal_error is None:
                self._signal_error = (
                    f"failed to signal provider process leader "
                    f"{self._process.pid}: {exc}"
                )
            return False
        return True

    def _send_signal_locked(self, sig: signal.Signals) -> bool:
        if self._pgid is None:
            return False
        if sig == signal.SIGTERM:
            if self._group_term_attempted:
                return self._term_sent
            self._group_term_attempted = True
        elif sig == signal.SIGKILL:
            if self._group_kill_attempted:
                return self._kill_sent
            self._group_kill_attempted = True

        try:
            os.killpg(self._pgid, sig)
        except ProcessLookupError:
            self._pgid_empty = True
            return False
        except OSError as exc:
            if self._signal_error is None:
                self._signal_error = (
                    f"failed to signal provider process group {self._pgid}: {exc}"
                )
            return False
        if sig == signal.SIGTERM:
            self._term_sent = True
        elif sig == signal.SIGKILL:
            self._kill_sent = True
        return True

    def _probe_group_empty_locked(self) -> bool:
        if self._pgid is None:
            return False
        try:
            os.killpg(self._pgid, 0)
        except ProcessLookupError:
            self._pgid_empty = True
            return True
        except OSError as exc:
            self._pgid_empty = False
            if self._signal_error is None:
                self._signal_error = (
                    f"failed to inspect provider process group {self._pgid}: {exc}"
                )
            return False
        self._pgid_empty = False
        return False

    def _wait_for_group_empty(
        self,
        timeout: float,
        *,
        honor_cancellation_grace: bool = False,
    ) -> bool:
        fallback_deadline = time.monotonic() + max(timeout, 0.0)
        while True:
            with self._condition:
                if self._probe_group_empty_locked():
                    self._condition.notify_all()
                    return True
                deadline = fallback_deadline
                if (
                    honor_cancellation_grace
                    and self._term_applied_at is not None
                ):
                    deadline = (
                        self._term_applied_at
                        + self._cancellation_grace_sec
                    )
            now = time.monotonic()
            if now >= deadline:
                return False
            time.sleep(
                min(
                    self._POLL_INTERVAL_SEC,
                    max(deadline - now, 0.0),
                )
            )

    def _proof_error_locked(self, identity_valid: bool) -> str | None:
        if self._signal_error is not None:
            return self._signal_error
        if self._cancellation_application_unproved:
            return "provider cancellation application could not be proved"
        if (
            self._cancellation_requested_before_bind
            and not self._cancellation_applied_before_completion
        ):
            return "provider cancellation requested before bind was not applied"
        if self._natural_exit_with_lingering_group:
            return "provider leader exited while its owned process group was non-empty"
        if not self._leader_reaped:
            return "provider process leader was not reaped"
        if not self._pgid_empty:
            return "provider process group is not empty"
        if not self._capture_threads_joined:
            return "provider capture threads were not joined"
        if not identity_valid:
            return "provider final session identity is not valid"
        return None

    def _freeze_terminal_locked(
        self,
        result: ProviderCancellationResult,
    ) -> ProviderCancellationResult:
        if self._terminal_result is not None:
            return self._terminal_result
        self._terminal_result = result
        self._state = "TERMINAL"
        self._condition.notify_all()
        return result


__all__ = [
    "ProviderCancellationResult",
    "ProviderExecutionControl",
]
