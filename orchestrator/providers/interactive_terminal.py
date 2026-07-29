"""Queued interactive provider sessions owned by a private tmux boundary."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping, Protocol, Sequence
import uuid

from .types import (
    InteractiveSessionSupport,
    PreparedProviderPolicy,
    extract_provider_command_placeholders,
    validate_interactive_session_support_capability,
)


_MAX_ENCODED_UNIX_SOCKET_PATH_BYTES = 103
_SUBMIT_KEY_SETTLE_SEC = 0.25
_INTERACTIVE_TERMINAL_ERROR_CODES = frozenset(
    {
        "adapter_already_started",
        "backend_operation_timeout",
        "cleanup_backend_error",
        "cleanup_timeout",
        "close_not_offered",
        "close_offer_timeout",
        "foreign_handle",
        "handle_terminal",
        "interactive_terminal_socket_cleanup_failed",
        "interactive_terminal_start_cleanup_incomplete",
        "key_offer_failed",
        "literal_offer_failed",
        "natural_shutdown_timeout",
        "offer_timeout",
        "pane_lost",
        "pane_start_failed",
        "pane_status_invalid",
        "pane_teardown_failed",
        "pane_teardown_incomplete",
        "process_failed",
        "process_not_live",
        "recorded_exit_status_invalid",
        "recorded_exit_status_unreadable",
        "server_lost",
        "server_start_failed",
        "server_teardown_failed",
        "server_teardown_incomplete",
        "start_timeout",
        "tmux_unavailable",
    }
)


class InteractiveTerminalError(RuntimeError):
    """Typed failure at one interactive-session adapter boundary."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


@dataclass(frozen=True)
class PaneProcessStatus:
    """Authoritative pane-process state without captured screen contents."""

    state: str
    return_code: int | None

    def __post_init__(self) -> None:
        if self.state not in {
            "running",
            "exited_pending",
            "exited",
            "missing",
        }:
            raise ValueError("pane process state is invalid")
        if self.state == "exited":
            if (
                isinstance(self.return_code, bool)
                or not isinstance(self.return_code, int)
            ):
                raise ValueError("exited pane process requires an integer status")
        elif self.return_code is not None:
            raise ValueError("non-exited pane process forbids a return code")


def _parse_tmux_pane_process_status(
    raw: str,
    *,
    recorded_exit_status: str | None,
) -> PaneProcessStatus:
    """Combine pane death with the runtime helper's exact exit-status record."""

    dead, separator, status = raw.strip().partition("|")
    if separator != "|":
        raise InteractiveTerminalError("pane_status_invalid")
    if not dead and not status:
        return PaneProcessStatus(state="missing", return_code=None)
    if dead == "0":
        return PaneProcessStatus(state="running", return_code=None)
    if dead != "1":
        raise InteractiveTerminalError("pane_status_invalid")
    del status
    if recorded_exit_status is None:
        return PaneProcessStatus(
            state="exited_pending",
            return_code=None,
        )
    if not recorded_exit_status.endswith("\n"):
        raise InteractiveTerminalError("recorded_exit_status_invalid")
    canonical = recorded_exit_status[:-1]
    if (
        not canonical
        or "\n" in canonical
        or any(character not in "0123456789" for character in canonical)
        or (len(canonical) > 1 and canonical.startswith("0"))
        or len(canonical) > 3
    ):
        raise InteractiveTerminalError("recorded_exit_status_invalid")
    return_code = int(canonical)
    if return_code > 255:
        raise InteractiveTerminalError("recorded_exit_status_invalid")
    return PaneProcessStatus(state="exited", return_code=return_code)


@dataclass(frozen=True)
class InteractiveMemberInvocation:
    """One fully resolved immutable launch request for an exact attempt."""

    invocation_id: str
    member_id: str
    attempt_scope_key: str
    attempt_ordinal: int
    resolved_command: tuple[str, ...]
    cwd: Path | None
    env: Mapping[str, str]
    support: InteractiveSessionSupport
    pre_prompt_command: tuple[str, ...] | None = None
    prepared_provider_policy: PreparedProviderPolicy | None = None

    def __post_init__(self) -> None:
        for field_name in ("invocation_id", "member_id", "attempt_scope_key"):
            _nonempty(getattr(self, field_name), field_name)
        if (
            isinstance(self.attempt_ordinal, bool)
            or not isinstance(self.attempt_ordinal, int)
            or self.attempt_ordinal < 0
        ):
            raise ValueError("attempt_ordinal must be a non-negative integer")

        if not isinstance(self.support, InteractiveSessionSupport):
            raise ValueError("support must be an InteractiveSessionSupport")
        support_errors = validate_interactive_session_support_capability(
            self.support
        )
        if support_errors:
            raise ValueError(
                "invalid interactive session support: "
                + "; ".join(support_errors)
            )
        if (
            self.prepared_provider_policy is not None
            and type(self.prepared_provider_policy)
            is not PreparedProviderPolicy
        ):
            raise ValueError(
                "prepared_provider_policy must be exact when present"
            )

        command = self.resolved_command
        if isinstance(command, list):
            command = tuple(command)
            object.__setattr__(self, "resolved_command", command)
        if (
            not isinstance(command, tuple)
            or not command
            or any(
                not isinstance(token, str) or not token
                for token in command
            )
        ):
            raise ValueError(
                "resolved_command must be a non-empty tuple of non-empty strings"
            )
        prompt_token_index = next(
            index
            for index, token in enumerate(self.support.command)
            if "PROMPT" in extract_provider_command_placeholders(token)
        )
        if any(
            "${" in token and index != prompt_token_index
            for index, token in enumerate(command)
        ):
            raise ValueError("resolved_command must not contain placeholders")

        pre_prompt_command = self.pre_prompt_command
        if pre_prompt_command is not None:
            if isinstance(pre_prompt_command, list):
                pre_prompt_command = tuple(pre_prompt_command)
                object.__setattr__(
                    self,
                    "pre_prompt_command",
                    pre_prompt_command,
                )
            if (
                not isinstance(pre_prompt_command, tuple)
                or not pre_prompt_command
                or any(
                    not isinstance(token, str) or not token
                    for token in pre_prompt_command
                )
            ):
                raise ValueError(
                    "pre_prompt_command must be a non-empty tuple of "
                    "non-empty strings"
                )
            placeholders = tuple(
                placeholder
                for token in pre_prompt_command
                for placeholder in extract_provider_command_placeholders(
                    token
                )
            )
            if placeholders != ("PROMPT",):
                raise ValueError(
                    "pre_prompt_command requires exactly one unresolved "
                    "PROMPT placeholder"
                )

        cwd = self.cwd
        if cwd is not None:
            object.__setattr__(self, "cwd", Path(cwd))

        if not isinstance(self.env, Mapping):
            raise ValueError("env must be a string mapping")
        copied_env = dict(self.env)
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            for key, value in copied_env.items()
        ):
            raise ValueError("env must be a string mapping")
        object.__setattr__(self, "env", MappingProxyType(copied_env))


@dataclass(frozen=True)
class InteractiveMemberHandle:
    """Opaque adapter-local binding for one exact provider attempt."""

    adapter_instance_id: str
    handle_id: str
    invocation_id: str
    member_id: str
    attempt_scope_key: str
    attempt_ordinal: int
    target: str
    socket_path: Path


@dataclass(frozen=True)
class OfferReceipt:
    """Proof that literal bytes and declared submit keys were offered."""

    status: str
    handle_id: str
    byte_count: int
    content_sha256: str


@dataclass(frozen=True)
class CloseOfferReceipt:
    """Proof that the provider-declared normal close was offered."""

    status: str
    handle_id: str


@dataclass(frozen=True)
class NaturalShutdownProof:
    """Complete natural client/pane/server shutdown proof."""

    disposition: str
    handle_id: str
    return_code: int
    pane_absent: bool
    server_absent: bool
    proof_complete: bool


@dataclass(frozen=True)
class FailedCleanupProof:
    """Cleanup evidence for an already-failed interactive attempt."""

    disposition: str
    handle_id: str
    pane_absent: bool
    server_absent: bool
    cleanup_complete: bool
    error_code: str | None


@dataclass(frozen=True, slots=True)
class NoBackendAllocationProof:
    """Explicit proof that start selected no backend action."""

    disposition: str
    backend_resource_allocated: bool
    proof_complete: bool

    def __post_init__(self) -> None:
        if self.disposition != "no_backend_allocation":
            raise ValueError("no-allocation disposition is invalid")
        if self.backend_resource_allocated is not False:
            raise ValueError("no-allocation proof must deny backend allocation")
        if self.proof_complete is not True:
            raise ValueError("no-allocation proof must be complete")


@dataclass(frozen=True, slots=True)
class PhasedFailedCleanupEvidence:
    """Handle-free cleanup observations admitted by phased delivery."""

    disposition: str
    pane_absent: bool
    server_absent: bool
    cleanup_complete: bool
    error_code: str | None

    def __post_init__(self) -> None:
        if self.disposition != "failed_cleanup":
            raise ValueError("failed cleanup disposition is invalid")
        for field_name in (
            "pane_absent",
            "server_absent",
            "cleanup_complete",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(
                    f"failed cleanup {field_name} must be boolean"
                )
        if self.error_code is not None and (
            not isinstance(self.error_code, str)
            or self.error_code not in _INTERACTIVE_TERMINAL_ERROR_CODES
        ):
            raise ValueError("failed cleanup error_code is invalid")
        complete = (
            self.pane_absent is True
            and self.server_absent is True
            and self.error_code is None
        )
        if self.cleanup_complete is not complete:
            raise ValueError("failed cleanup completeness is inconsistent")


def project_phased_failed_cleanup_evidence(
    proof: object,
    *,
    active_handle_id: str,
) -> PhasedFailedCleanupEvidence | None:
    """Project an exact active-handle proof without side effects or inference."""

    if (
        type(proof) is not FailedCleanupProof
        or not isinstance(active_handle_id, str)
        or not active_handle_id
        or proof.handle_id != active_handle_id
        or proof.disposition != "failed_cleanup"
        or not isinstance(proof.handle_id, str)
        or not proof.handle_id
        or any(
            not isinstance(getattr(proof, field_name), bool)
            for field_name in (
                "pane_absent",
                "server_absent",
                "cleanup_complete",
            )
        )
        or (
            proof.error_code is not None
            and (
                not isinstance(proof.error_code, str)
                or proof.error_code not in _INTERACTIVE_TERMINAL_ERROR_CODES
            )
        )
    ):
        return None
    try:
        return PhasedFailedCleanupEvidence(
            disposition=proof.disposition,
            pane_absent=proof.pane_absent,
            server_absent=proof.server_absent,
            cleanup_complete=proof.cleanup_complete,
            error_code=proof.error_code,
        )
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class InteractiveTerminalStartOutcome:
    """Closed success-or-proof result for one adapter start boundary."""

    status: str
    handle: InteractiveMemberHandle | None = None
    error_code: str | None = None
    backend_allocation: str | None = None
    cleanup_status: str | None = None
    provider_zero_survivor_proven: bool | None = None
    proof: NoBackendAllocationProof | PhasedFailedCleanupEvidence | None = None

    def __post_init__(self) -> None:
        if self.status == "started":
            if type(self.handle) is not InteractiveMemberHandle:
                raise ValueError("started outcome requires an exact handle")
            if any(
                value is not None
                for value in (
                    self.error_code,
                    self.backend_allocation,
                    self.cleanup_status,
                    self.provider_zero_survivor_proven,
                    self.proof,
                )
            ):
                raise ValueError("started outcome forbids failure fields")
            return
        if self.status != "failed" or self.handle is not None:
            raise ValueError("start outcome variant is invalid")
        if (
            not isinstance(self.error_code, str)
            or self.error_code not in _INTERACTIVE_TERMINAL_ERROR_CODES
            or not isinstance(self.provider_zero_survivor_proven, bool)
        ):
            raise ValueError("failed start outcome fields are invalid")
        if (
            self.backend_allocation == "none"
            and self.cleanup_status == "not_required"
            and self.provider_zero_survivor_proven is True
            and type(self.proof) is NoBackendAllocationProof
        ):
            return
        if (
            self.backend_allocation == "possible_or_allocated"
            and self.cleanup_status == "completed"
            and self.provider_zero_survivor_proven is True
            and type(self.proof) is PhasedFailedCleanupEvidence
            and self.proof.cleanup_complete is True
        ):
            return
        if (
            self.backend_allocation == "possible_or_allocated"
            and self.cleanup_status == "incomplete"
            and self.provider_zero_survivor_proven is False
            and type(self.proof) is PhasedFailedCleanupEvidence
            and self.proof.cleanup_complete is False
        ):
            return
        raise ValueError("failed start outcome combination is invalid")

    def to_dict(self) -> dict[str, object]:
        if self.status == "started":
            assert self.handle is not None
            return {"status": "started", "handle": self.handle}
        assert self.error_code is not None
        assert self.backend_allocation is not None
        assert self.cleanup_status is not None
        assert self.provider_zero_survivor_proven is not None
        assert self.proof is not None
        return {
            "status": "failed",
            "error_code": self.error_code,
            "backend_allocation": self.backend_allocation,
            "cleanup_status": self.cleanup_status,
            "provider_zero_survivor_proven": (
                self.provider_zero_survivor_proven
            ),
            "proof": self.proof,
        }


def _failed_start_outcome(
    error_code: str,
    proof: PhasedFailedCleanupEvidence,
) -> InteractiveTerminalStartOutcome:
    if proof.cleanup_complete is not True:
        error_code = "interactive_terminal_start_cleanup_incomplete"
        proof = PhasedFailedCleanupEvidence(
            disposition="failed_cleanup",
            pane_absent=proof.pane_absent,
            server_absent=proof.server_absent,
            cleanup_complete=False,
            error_code=error_code,
        )
    return InteractiveTerminalStartOutcome(
        status="failed",
        error_code=error_code,
        backend_allocation="possible_or_allocated",
        cleanup_status=(
            "completed" if proof.cleanup_complete else "incomplete"
        ),
        provider_zero_survivor_proven=proof.cleanup_complete,
        proof=proof,
    )


class _InteractiveTerminalBackend(Protocol):
    def start_server(
        self,
        socket_path: Path,
        session_name: str,
        *,
        env: dict[str, str],
        timeout_sec: float,
    ) -> None: ...

    def start_pane(
        self,
        socket_path: Path,
        session_name: str,
        command: Sequence[str],
        *,
        cwd: Path | None,
        exit_status_path: Path,
        timeout_sec: float,
    ) -> str: ...

    def pane_process_status(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> PaneProcessStatus: ...

    def server_alive(
        self,
        socket_path: Path,
        session_name: str,
        *,
        timeout_sec: float,
    ) -> bool: ...

    def offer_literal(
        self,
        socket_path: Path,
        target: str,
        literal_text: str,
        *,
        timeout_sec: float,
    ) -> None: ...

    def offer_keys(
        self,
        socket_path: Path,
        target: str,
        keys: Sequence[str],
        *,
        timeout_sec: float,
    ) -> None: ...

    def close_pane(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> None: ...

    def close_server(
        self,
        socket_path: Path,
        *,
        timeout_sec: float,
    ) -> None: ...


class _TmuxInteractiveTerminalBackend:
    """Small tmux transport that never reads or interprets pane text."""

    _KEYS = MappingProxyType({"ENTER": "Enter", "TAB": "Tab"})

    def __init__(self, executable: str = "tmux") -> None:
        self._executable = executable
        self._exit_status_paths: dict[tuple[Path, str], Path] = {}

    def _run(
        self,
        socket_path: Path,
        *args: str,
        input_bytes: bytes | None = None,
        process_env: dict[str, str] | None = None,
        timeout_sec: float,
    ) -> subprocess.CompletedProcess[bytes]:
        if timeout_sec <= 0:
            raise InteractiveTerminalError("backend_operation_timeout")
        try:
            return subprocess.run(
                [self._executable, "-S", str(socket_path), *args],
                env=process_env,
                input=input_bytes,
                check=False,
                capture_output=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise InteractiveTerminalError(
                "backend_operation_timeout",
                "tmux interactive command exceeded its operation deadline",
            ) from exc
        except OSError as exc:
            raise InteractiveTerminalError(
                "tmux_unavailable",
                "tmux interactive command could not start",
            ) from exc

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InteractiveTerminalError("backend_operation_timeout")
        return remaining

    def start_server(
        self,
        socket_path: Path,
        session_name: str,
        *,
        env: dict[str, str],
        timeout_sec: float,
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        created = self._run(
            socket_path,
            "new-session",
            "-d",
            "-s",
            session_name,
            "-n",
            "anchor",
            process_env=dict(env),
            timeout_sec=self._remaining(deadline),
        )
        if created.returncode != 0:
            raise InteractiveTerminalError("server_start_failed")
        retained = self._run(
            socket_path,
            "set-window-option",
            "-g",
            "remain-on-exit",
            "on",
            timeout_sec=self._remaining(deadline),
        )
        if retained.returncode != 0:
            try:
                self.close_server(
                    socket_path,
                    timeout_sec=self._remaining(deadline),
                )
            except InteractiveTerminalError:
                pass
            raise InteractiveTerminalError("server_start_failed")

    def start_pane(
        self,
        socket_path: Path,
        session_name: str,
        command: Sequence[str],
        *,
        cwd: Path | None,
        exit_status_path: Path,
        timeout_sec: float,
    ) -> str:
        if exit_status_path.exists():
            raise InteractiveTerminalError("pane_start_failed")
        deadline = time.monotonic() + timeout_sec
        args = [
            "new-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:",
            "-n",
            "provider-interactive",
        ]
        if cwd is not None:
            args.extend(("-c", str(cwd)))
        helper = (
            'status_path=$1; shift; "$@"; status=$?; '
            'temporary="${status_path}.tmp.$$"; '
            '(umask 077; printf "%s\\n" "$status" > "$temporary") '
            '&& mv "$temporary" "$status_path"; exit "$status"'
        )
        wrapped_command = (
            "sh",
            "-c",
            helper,
            "orc-interactive-exit",
            str(exit_status_path),
            *tuple(command),
        )
        args.append("exec " + shlex.join(wrapped_command))
        completed = self._run(
            socket_path,
            *args,
            timeout_sec=self._remaining(deadline),
        )
        target = completed.stdout.decode("utf-8", errors="replace").strip()
        if completed.returncode != 0 or not target:
            raise InteractiveTerminalError("pane_start_failed")
        self._exit_status_paths[(socket_path, target)] = exit_status_path
        if (
            self.pane_process_status(
                socket_path,
                target,
                timeout_sec=self._remaining(deadline),
            ).state
            != "running"
        ):
            raise InteractiveTerminalError("pane_start_failed")
        return target

    def pane_process_status(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> PaneProcessStatus:
        completed = self._run(
            socket_path,
            "display-message",
            "-p",
            "-t",
            target,
            "#{pane_dead}|#{pane_dead_status}",
            timeout_sec=timeout_sec,
        )
        if completed.returncode != 0:
            return PaneProcessStatus(state="missing", return_code=None)
        raw = completed.stdout.decode("utf-8", errors="replace")
        recorded_exit_status: str | None = None
        status_path = self._exit_status_paths.get((socket_path, target))
        if status_path is not None and status_path.exists():
            try:
                recorded_exit_status = status_path.read_text(
                    encoding="ascii"
                )
            except (OSError, UnicodeError) as exc:
                raise InteractiveTerminalError(
                    "recorded_exit_status_unreadable"
                ) from exc
        return _parse_tmux_pane_process_status(
            raw,
            recorded_exit_status=recorded_exit_status,
        )

    def server_alive(
        self,
        socket_path: Path,
        session_name: str,
        *,
        timeout_sec: float,
    ) -> bool:
        return (
            self._run(
                socket_path,
                "has-session",
                "-t",
                session_name,
                timeout_sec=timeout_sec,
            ).returncode
            == 0
        )

    def offer_literal(
        self,
        socket_path: Path,
        target: str,
        literal_text: str,
        *,
        timeout_sec: float,
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        buffer_name = "orc-peer-input"
        loaded = self._run(
            socket_path,
            "load-buffer",
            "-b",
            buffer_name,
            "-",
            input_bytes=literal_text.encode("utf-8"),
            timeout_sec=self._remaining(deadline),
        )
        if loaded.returncode != 0:
            raise InteractiveTerminalError("literal_offer_failed")
        pasted = self._run(
            socket_path,
            "paste-buffer",
            "-d",
            "-b",
            buffer_name,
            "-t",
            target,
            timeout_sec=self._remaining(deadline),
        )
        if pasted.returncode != 0:
            raise InteractiveTerminalError("literal_offer_failed")

    def offer_keys(
        self,
        socket_path: Path,
        target: str,
        keys: Sequence[str],
        *,
        timeout_sec: float,
    ) -> None:
        try:
            tmux_keys = tuple(self._KEYS[key] for key in keys)
        except KeyError as exc:
            raise InteractiveTerminalError("key_offer_failed") from exc
        completed = self._run(
            socket_path,
            "send-keys",
            "-t",
            target,
            *tmux_keys,
            timeout_sec=timeout_sec,
        )
        if completed.returncode != 0:
            raise InteractiveTerminalError("key_offer_failed")

    def close_pane(
        self,
        socket_path: Path,
        target: str,
        *,
        timeout_sec: float,
    ) -> None:
        completed = self._run(
            socket_path,
            "kill-pane",
            "-t",
            target,
            timeout_sec=timeout_sec,
        )
        if completed.returncode != 0:
            raise InteractiveTerminalError("pane_teardown_failed")

    def close_server(
        self,
        socket_path: Path,
        *,
        timeout_sec: float,
    ) -> None:
        completed = self._run(
            socket_path,
            "kill-server",
            timeout_sec=timeout_sec,
        )
        if completed.returncode != 0:
            raise InteractiveTerminalError("server_teardown_failed")


class InteractiveTerminalTurnQueueAdapter:
    """Own one interactive client and offer only queued natural-turn input."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        socket_root: Path | None = None,
        backend: _InteractiveTerminalBackend | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        wait: Callable[[float], None] = time.sleep,
        poll_interval_sec: float = 0.05,
        operation_timeout_sec: float = 5.0,
    ) -> None:
        if (
            isinstance(poll_interval_sec, bool)
            or not isinstance(poll_interval_sec, (int, float))
            or poll_interval_sec <= 0
            or not math.isfinite(poll_interval_sec)
        ):
            raise ValueError("poll_interval_sec must be positive")
        if (
            isinstance(operation_timeout_sec, bool)
            or not isinstance(operation_timeout_sec, (int, float))
            or operation_timeout_sec <= 0
            or not math.isfinite(operation_timeout_sec)
        ):
            raise ValueError("operation_timeout_sec must be positive")
        root = Path(runtime_root)
        token = uuid.uuid4().hex
        if socket_root is None:
            root.mkdir(parents=True, exist_ok=True)
            selected_socket_root = root
        else:
            selected_socket_root = Path(socket_root)
        try:
            selected_socket_root = selected_socket_root.resolve(strict=True)
            socket_path = (
                selected_socket_root / f"orc-peer-{token}.sock"
            )
            socket_path_available = (
                selected_socket_root.is_dir()
                and os.access(
                    selected_socket_root,
                    os.W_OK | os.X_OK,
                )
                and len(os.fsencode(socket_path))
                <= _MAX_ENCODED_UNIX_SOCKET_PATH_BYTES
                and not socket_path.exists()
                and not socket_path.is_symlink()
            )
        except (OSError, RuntimeError, TypeError, UnicodeError):
            socket_path_available = False
        if not socket_path_available:
            raise InteractiveTerminalError(
                "interactive_terminal_socket_path_unavailable"
            )
        root.mkdir(parents=True, exist_ok=True)
        state_directory = Path(
            tempfile.mkdtemp(prefix="orc-peer-", dir=root)
        )
        self._socket_path = socket_path
        self._exit_status_path = state_directory / "provider.exit-status"
        self._session_name = f"orc-peer-{token[:12]}"
        self._adapter_instance_id = token
        self._backend = backend or _TmuxInteractiveTerminalBackend()
        self._monotonic = monotonic
        self._wait = wait
        self._poll_interval_sec = float(poll_interval_sec)
        self._operation_timeout_sec = float(operation_timeout_sec)
        self._lock = threading.RLock()
        self._handle: InteractiveMemberHandle | None = None
        self._support: InteractiveSessionSupport | None = None
        self._state = "created"
        self._natural_proof: NaturalShutdownProof | None = None
        self._cleanup_proof: FailedCleanupProof | None = None

    def prove_no_backend_allocation(
        self,
    ) -> NoBackendAllocationProof:
        """Prove from adapter lifecycle that no backend action has begun."""

        with self._lock:
            if self._state != "created" or self._handle is not None:
                raise InteractiveTerminalError("handle_terminal")
            return NoBackendAllocationProof(
                disposition="no_backend_allocation",
                backend_resource_allocated=False,
                proof_complete=True,
            )

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome:
        if not isinstance(invocation, InteractiveMemberInvocation):
            raise TypeError("invocation must be an InteractiveMemberInvocation")
        self._validate_deadline(deadline)
        with self._lock:
            if self._state != "created":
                raise InteractiveTerminalError("adapter_already_started")
            target: str | None = None
            backend_action_started = False
            try:
                start_server_timeout = self._remaining(
                    deadline,
                    timeout_code="start_timeout",
                )
                backend_action_started = True
                self._backend.start_server(
                    self._socket_path,
                    self._session_name,
                    env=dict(invocation.env),
                    timeout_sec=start_server_timeout,
                )
                target = self._backend.start_pane(
                    self._socket_path,
                    self._session_name,
                    invocation.resolved_command,
                    cwd=invocation.cwd,
                    exit_status_path=self._exit_status_path,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="start_timeout",
                    ),
                )
                if (
                    not self._backend.server_alive(
                        self._socket_path,
                        self._session_name,
                        timeout_sec=self._remaining(
                            deadline,
                            timeout_code="start_timeout",
                        ),
                    )
                    or self._backend.pane_process_status(
                        self._socket_path,
                        target,
                        timeout_sec=self._remaining(
                            deadline,
                            timeout_code="start_timeout",
                        ),
                    ).state
                    != "running"
                ):
                    raise InteractiveTerminalError("pane_start_failed")
            except InteractiveTerminalError as exc:
                self._state = "failed"
                if exc.code == "start_timeout" and not backend_action_started:
                    return InteractiveTerminalStartOutcome(
                        status="failed",
                        error_code="start_timeout",
                        backend_allocation="none",
                        cleanup_status="not_required",
                        provider_zero_survivor_proven=True,
                        proof=NoBackendAllocationProof(
                            disposition="no_backend_allocation",
                            backend_resource_allocated=False,
                            proof_complete=True,
                        ),
                    )
                failure_code = (
                    "start_timeout"
                    if exc.code == "backend_operation_timeout"
                    else (
                        exc.code
                        if exc.code in _INTERACTIVE_TERMINAL_ERROR_CODES
                        else "pane_start_failed"
                    )
                )
                proof = self._cleanup_start_failure(
                    deadline=deadline,
                    target=target,
                )
                return _failed_start_outcome(failure_code, proof)
            except Exception:
                self._state = "failed"
                proof = self._cleanup_start_failure(
                    deadline=deadline,
                    target=target,
                )
                return _failed_start_outcome("pane_start_failed", proof)

            handle = InteractiveMemberHandle(
                adapter_instance_id=self._adapter_instance_id,
                handle_id=uuid.uuid4().hex,
                invocation_id=invocation.invocation_id,
                member_id=invocation.member_id,
                attempt_scope_key=invocation.attempt_scope_key,
                attempt_ordinal=invocation.attempt_ordinal,
                target=target,
                socket_path=self._socket_path,
            )
            self._handle = handle
            self._support = invocation.support
            self._state = "live"
            return InteractiveTerminalStartOutcome(
                status="started",
                handle=handle,
            )

    def probe_process_status(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> PaneProcessStatus:
        """Read process liveness once without joining or changing lifecycle."""

        self._validate_deadline(deadline)
        with self._lock:
            self._require_handle(handle)
            if self._state not in {"live", "closing"}:
                raise InteractiveTerminalError("handle_terminal")
            try:
                status = self._backend.pane_process_status(
                    self._socket_path,
                    handle.target,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="backend_operation_timeout",
                    ),
                )
            except InteractiveTerminalError:
                raise
            if type(status) is not PaneProcessStatus:
                raise InteractiveTerminalError("pane_status_invalid")
            if status.state == "missing":
                raise InteractiveTerminalError("pane_lost")
            return status

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        if not isinstance(literal_message, str):
            raise TypeError("literal_message must be a string")
        self._validate_deadline(deadline)
        with self._lock:
            self._require_handle(handle)
            if self._state != "live":
                raise InteractiveTerminalError("handle_terminal")
            try:
                self._require_live_process(
                    handle,
                    deadline=deadline,
                    timeout_code="offer_timeout",
                )
                assert self._support is not None
                self._backend.offer_literal(
                    self._socket_path,
                    handle.target,
                    literal_message,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="offer_timeout",
                    ),
                )
                self._offer_declared_submit_keys(
                    handle,
                    self._support.message_submit_keys,
                    deadline=deadline,
                    timeout_code="offer_timeout",
                )
            except InteractiveTerminalError as exc:
                if exc.code in {
                    "backend_operation_timeout",
                    "offer_timeout",
                }:
                    self._state = "failed"
                    if exc.code == "offer_timeout":
                        raise
                    raise InteractiveTerminalError(
                        "offer_timeout"
                    ) from exc
                raise
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
        self._validate_deadline(deadline)
        with self._lock:
            self._require_handle(handle)
            if self._state != "live":
                raise InteractiveTerminalError("handle_terminal")
            try:
                self._require_live_process(
                    handle,
                    deadline=deadline,
                    timeout_code="close_offer_timeout",
                )
                assert self._support is not None
                self._backend.offer_literal(
                    self._socket_path,
                    handle.target,
                    self._support.graceful_close_text,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="close_offer_timeout",
                    ),
                )
                self._offer_declared_submit_keys(
                    handle,
                    self._support.graceful_close_submit_keys,
                    deadline=deadline,
                    timeout_code="close_offer_timeout",
                )
            except InteractiveTerminalError as exc:
                if exc.code in {
                    "backend_operation_timeout",
                    "close_offer_timeout",
                }:
                    self._state = "failed"
                    if exc.code == "close_offer_timeout":
                        raise
                    raise InteractiveTerminalError(
                        "close_offer_timeout"
                    ) from exc
                raise
            self._state = "closing"
            return CloseOfferReceipt(
                status="close_offered",
                handle_id=handle.handle_id,
            )

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof:
        self._validate_deadline(deadline)
        with self._lock:
            self._require_handle(handle)
            if self._natural_proof is not None:
                return self._natural_proof
            if self._state != "closing":
                raise InteractiveTerminalError("close_not_offered")

            while True:
                try:
                    status = self._backend.pane_process_status(
                        self._socket_path,
                        handle.target,
                        timeout_sec=self._remaining(
                            deadline,
                            timeout_code="natural_shutdown_timeout",
                        ),
                    )
                except InteractiveTerminalError as exc:
                    self._state = "failed"
                    if exc.code == "backend_operation_timeout":
                        raise InteractiveTerminalError(
                            "natural_shutdown_timeout"
                        ) from exc
                    raise
                if status.state == "missing":
                    self._state = "failed"
                    raise InteractiveTerminalError("pane_lost")
                if status.state == "exited":
                    if status.return_code != 0:
                        self._state = "failed"
                        raise InteractiveTerminalError("process_failed")
                    break
                now = self._monotonic()
                if now >= deadline:
                    self._state = "failed"
                    raise InteractiveTerminalError(
                        "natural_shutdown_timeout"
                    )
                self._wait(
                    min(self._poll_interval_sec, max(0.0, deadline - now))
                )

            try:
                self._backend.close_pane(
                    self._socket_path,
                    handle.target,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="natural_shutdown_timeout",
                    ),
                )
                pane_absent = (
                    self._backend.pane_process_status(
                        self._socket_path,
                        handle.target,
                        timeout_sec=self._remaining(
                            deadline,
                            timeout_code="natural_shutdown_timeout",
                        ),
                    ).state
                    == "missing"
                )
                if not pane_absent:
                    raise InteractiveTerminalError(
                        "pane_teardown_incomplete"
                    )
                self._backend.close_server(
                    self._socket_path,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="natural_shutdown_timeout",
                    ),
                )
                server_absent = not self._backend.server_alive(
                    self._socket_path,
                    self._session_name,
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code="natural_shutdown_timeout",
                    ),
                )
                if not server_absent:
                    raise InteractiveTerminalError(
                        "server_teardown_incomplete"
                    )
                self._remove_socket_after_server_absent()
            except InteractiveTerminalError as exc:
                self._state = "failed"
                if exc.code == "backend_operation_timeout":
                    raise InteractiveTerminalError(
                        "natural_shutdown_timeout"
                    ) from exc
                raise

            proof = NaturalShutdownProof(
                disposition="natural_exit",
                handle_id=handle.handle_id,
                return_code=0,
                pane_absent=True,
                server_absent=True,
                proof_complete=True,
            )
            self._natural_proof = proof
            self._state = "terminal"
            return proof

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof:
        self._validate_deadline(deadline)
        with self._lock:
            self._require_handle(handle)
            if self._cleanup_proof is not None:
                return self._cleanup_proof
            if self._natural_proof is not None:
                raise InteractiveTerminalError("handle_terminal")

            first_error: str | None = None
            pane_absent = False
            server_absent = False

            def remember_error(exc: Exception) -> None:
                nonlocal first_error
                if first_error is not None:
                    return
                if isinstance(exc, InteractiveTerminalError):
                    first_error = exc.code
                else:
                    first_error = "cleanup_backend_error"

            def remaining() -> float | None:
                nonlocal first_error
                value = deadline - self._monotonic()
                if value <= 0:
                    if first_error is None:
                        first_error = "cleanup_timeout"
                    return None
                return min(value, self._operation_timeout_sec)

            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    pane_status = self._backend.pane_process_status(
                        self._socket_path,
                        handle.target,
                        timeout_sec=timeout_sec,
                    )
                    if pane_status.state == "missing":
                        pane_absent = True
            except Exception as exc:
                remember_error(exc)

            if not pane_absent:
                try:
                    timeout_sec = remaining()
                    if timeout_sec is not None:
                        self._backend.close_pane(
                            self._socket_path,
                            handle.target,
                            timeout_sec=timeout_sec,
                        )
                except Exception as exc:
                    remember_error(exc)

            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    pane_absent = (
                        self._backend.pane_process_status(
                            self._socket_path,
                            handle.target,
                            timeout_sec=timeout_sec,
                        ).state
                        == "missing"
                    )
            except Exception as exc:
                remember_error(exc)

            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    server_absent = not self._backend.server_alive(
                        self._socket_path,
                        self._session_name,
                        timeout_sec=timeout_sec,
                    )
            except Exception as exc:
                remember_error(exc)

            if not server_absent:
                try:
                    timeout_sec = remaining()
                    if timeout_sec is not None:
                        self._backend.close_server(
                            self._socket_path,
                            timeout_sec=timeout_sec,
                        )
                except Exception as exc:
                    remember_error(exc)

            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    server_absent = not self._backend.server_alive(
                        self._socket_path,
                        self._session_name,
                        timeout_sec=timeout_sec,
                    )
            except Exception as exc:
                remember_error(exc)

            if server_absent:
                try:
                    self._remove_socket_after_server_absent()
                except Exception as exc:
                    remember_error(exc)

            cleanup_complete = (
                pane_absent
                and server_absent
                and first_error is None
            )
            proof = FailedCleanupProof(
                disposition="failed_cleanup",
                handle_id=handle.handle_id,
                pane_absent=pane_absent,
                server_absent=server_absent,
                cleanup_complete=cleanup_complete,
                error_code=first_error,
            )
            self._cleanup_proof = proof
            self._state = "terminal"
            return proof

    def _require_handle(self, handle: InteractiveMemberHandle) -> None:
        if not isinstance(handle, InteractiveMemberHandle):
            raise InteractiveTerminalError("foreign_handle")
        active = self._handle
        if (
            active is None
            or handle.adapter_instance_id != self._adapter_instance_id
            or handle != active
        ):
            raise InteractiveTerminalError("foreign_handle")

    def _require_live_process(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
        timeout_code: str,
    ) -> None:
        if not self._backend.server_alive(
            self._socket_path,
            self._session_name,
            timeout_sec=self._remaining(
                deadline,
                timeout_code=timeout_code,
            ),
        ):
            self._state = "failed"
            raise InteractiveTerminalError("server_lost")
        status = self._backend.pane_process_status(
            self._socket_path,
            handle.target,
            timeout_sec=self._remaining(
                deadline,
                timeout_code=timeout_code,
            ),
        )
        if status.state == "missing":
            self._state = "failed"
            raise InteractiveTerminalError("pane_lost")
        if status.state != "running":
            self._state = "failed"
            raise InteractiveTerminalError("process_not_live")

    def _offer_declared_submit_keys(
        self,
        handle: InteractiveMemberHandle,
        keys: Sequence[str],
        *,
        deadline: float,
        timeout_code: str,
    ) -> None:
        for key in keys:
            remaining = deadline - self._monotonic()
            if remaining <= _SUBMIT_KEY_SETTLE_SEC:
                raise InteractiveTerminalError(timeout_code)
            self._wait(_SUBMIT_KEY_SETTLE_SEC)
            try:
                self._backend.offer_keys(
                    self._socket_path,
                    handle.target,
                    (key,),
                    timeout_sec=self._remaining(
                        deadline,
                        timeout_code=timeout_code,
                    ),
                )
            except InteractiveTerminalError:
                self._state = "failed"
                raise

    def _cleanup_start_failure(
        self,
        *,
        deadline: float,
        target: str | None,
    ) -> PhasedFailedCleanupEvidence:
        pane_absent = False
        server_absent = False
        cleanup_error = False

        def remaining() -> float | None:
            nonlocal cleanup_error
            value = deadline - self._monotonic()
            if value <= 0:
                cleanup_error = True
                return None
            return min(value, self._operation_timeout_sec)

        if target is not None:
            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    pane_absent = (
                        self._backend.pane_process_status(
                            self._socket_path,
                            target,
                            timeout_sec=timeout_sec,
                        ).state
                        == "missing"
                    )
            except Exception:
                cleanup_error = True
            if not pane_absent:
                try:
                    timeout_sec = remaining()
                    if timeout_sec is not None:
                        self._backend.close_pane(
                            self._socket_path,
                            target,
                            timeout_sec=timeout_sec,
                        )
                except Exception:
                    cleanup_error = True
                try:
                    timeout_sec = remaining()
                    if timeout_sec is not None:
                        pane_absent = (
                            self._backend.pane_process_status(
                                self._socket_path,
                                target,
                                timeout_sec=timeout_sec,
                            ).state
                            == "missing"
                        )
                except Exception:
                    cleanup_error = True

        try:
            timeout_sec = remaining()
            if timeout_sec is not None:
                server_absent = not self._backend.server_alive(
                    self._socket_path,
                    self._session_name,
                    timeout_sec=timeout_sec,
                )
        except Exception:
            cleanup_error = True
        if not server_absent:
            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    self._backend.close_server(
                        self._socket_path,
                        timeout_sec=timeout_sec,
                    )
            except Exception:
                cleanup_error = True
            try:
                timeout_sec = remaining()
                if timeout_sec is not None:
                    server_absent = not self._backend.server_alive(
                        self._socket_path,
                        self._session_name,
                        timeout_sec=timeout_sec,
                    )
            except Exception:
                cleanup_error = True
        if server_absent and target is None:
            pane_absent = True
        if server_absent:
            try:
                self._remove_socket_after_server_absent()
            except Exception:
                cleanup_error = True

        cleanup_complete = (
            pane_absent and server_absent and not cleanup_error
        )
        return PhasedFailedCleanupEvidence(
            disposition="failed_cleanup",
            pane_absent=pane_absent,
            server_absent=server_absent,
            cleanup_complete=cleanup_complete,
            error_code=(
                None
                if cleanup_complete
                else "interactive_terminal_start_cleanup_incomplete"
            ),
        )

    def _remove_socket_after_server_absent(self) -> None:
        try:
            self._socket_path.unlink(missing_ok=True)
            socket_absent = (
                not self._socket_path.exists()
                and not self._socket_path.is_symlink()
            )
        except OSError as exc:
            raise InteractiveTerminalError(
                "interactive_terminal_socket_cleanup_failed"
            ) from exc
        if not socket_absent:
            raise InteractiveTerminalError(
                "interactive_terminal_socket_cleanup_failed"
            )

    def _remaining(
        self,
        deadline: float,
        *,
        timeout_code: str,
    ) -> float:
        remaining = deadline - self._monotonic()
        if remaining <= 0:
            raise InteractiveTerminalError(timeout_code)
        return min(remaining, self._operation_timeout_sec)

    @staticmethod
    def _validate_deadline(deadline: float) -> None:
        if (
            isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
            or not math.isfinite(deadline)
        ):
            raise ValueError("deadline must be a monotonic timestamp")
