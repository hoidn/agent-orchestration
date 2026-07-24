"""Observation-only provider panes backed by authoritative display files."""

from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Mapping, Protocol


_RECORD_SCHEMA_VERSION = "provider_observation.v1"


class ProviderObservationError(RuntimeError):
    """Typed failure at an observation-only lifecycle boundary."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)


class _ObservationBackend(Protocol):
    def start_server(self, socket_path: Path, session_name: str) -> None: ...

    def open_pane(
        self,
        socket_path: Path,
        session_name: str,
        display_path: Path,
    ) -> str: ...

    def pane_alive(self, socket_path: Path, target: str) -> bool: ...

    def server_alive(self, socket_path: Path, session_name: str) -> bool: ...

    def close_pane(self, socket_path: Path, target: str) -> None: ...

    def close_server(self, socket_path: Path) -> None: ...


class _TmuxObservationBackend:
    """Small tmux adapter; no captured pane data enters evidence."""

    def __init__(self, executable: str = "tmux") -> None:
        self._executable = executable

    def _run(
        self,
        socket_path: Path,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self._executable, "-S", str(socket_path), *args],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            raise ProviderObservationError(
                "tmux_unavailable",
                "tmux observation command could not start",
            ) from exc

    def start_server(self, socket_path: Path, session_name: str) -> None:
        completed = self._run(
            socket_path,
            "new-session",
            "-d",
            "-s",
            session_name,
            "-n",
            "anchor",
        )
        if completed.returncode != 0:
            raise ProviderObservationError("server_start_failed")

    def open_pane(
        self,
        socket_path: Path,
        session_name: str,
        display_path: Path,
    ) -> str:
        tail_command = (
            "exec tail -n +1 -F -- " + shlex.quote(str(display_path))
        )
        completed = self._run(
            socket_path,
            "new-window",
            "-d",
            "-P",
            "-F",
            "#{pane_id}",
            "-t",
            f"{session_name}:",
            "-n",
            "provider-observation",
            tail_command,
        )
        target = completed.stdout.strip()
        if completed.returncode != 0 or not target:
            raise ProviderObservationError("tail_start_failed")
        if not self.pane_alive(socket_path, target):
            raise ProviderObservationError("tail_start_failed")
        return target

    def pane_alive(self, socket_path: Path, target: str) -> bool:
        completed = self._run(
            socket_path,
            "display-message",
            "-p",
            "-t",
            target,
            "#{pane_id}",
        )
        return completed.returncode == 0 and completed.stdout.strip() == target

    def server_alive(self, socket_path: Path, session_name: str) -> bool:
        return (
            self._run(
                socket_path,
                "has-session",
                "-t",
                session_name,
            ).returncode
            == 0
        )

    def close_pane(self, socket_path: Path, target: str) -> None:
        completed = self._run(socket_path, "kill-pane", "-t", target)
        if completed.returncode != 0:
            raise ProviderObservationError("pane_teardown_failed")

    def close_server(self, socket_path: Path) -> None:
        completed = self._run(socket_path, "kill-server")
        if completed.returncode != 0:
            raise ProviderObservationError("server_teardown_failed")


class ProviderObservationHandle:
    """One process-local live target and its file-backed evidence lifecycle."""

    def __init__(
        self,
        *,
        manager: ProviderObservationManager,
        backend: _ObservationBackend,
        socket_path: Path,
        target: str,
        invocation_id: str,
        member_id: str,
        turn_id: str,
        display_path: Path,
        transcript_path: Path,
        relative_display_path: str,
        relative_transcript_path: str,
    ) -> None:
        self._manager = manager
        self._backend = backend
        self._socket_path = socket_path
        self._target = target
        self._invocation_id = invocation_id
        self._member_id = member_id
        self._turn_id = turn_id
        self._display_path = display_path
        self._transcript_path = transcript_path
        self._relative_display_path = relative_display_path
        self._relative_transcript_path = relative_transcript_path
        self._status = "live"
        self._failure_code: str | None = None
        self._final_record: dict[str, object] | None = None
        self._lock = threading.RLock()

    @property
    def target(self) -> str:
        return self._target

    @property
    def socket_path(self) -> Path:
        return self._socket_path

    @property
    def display_path(self) -> Path:
        return self._display_path

    @property
    def transcript_path(self) -> Path:
        return self._transcript_path

    @property
    def stable_record(self) -> Mapping[str, object]:
        with self._lock:
            if self._final_record is not None:
                return dict(self._final_record)
            return self._build_record()

    def append_display(self, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError("provider observation display data must be bytes")
        if not data:
            return
        with self._lock:
            if self._final_record is not None:
                raise ProviderObservationError("observation_finalized")
            try:
                with self._display_path.open("ab") as stream:
                    stream.write(data)
                    stream.flush()
            except OSError as exc:
                self._fail("display_append_failed")
                raise ProviderObservationError("display_append_failed") from exc

    def check_health(self) -> bool:
        with self._lock:
            if self._final_record is not None:
                return False
            try:
                if not self._backend.server_alive(
                    self._socket_path,
                    self._manager.session_name,
                ):
                    self._fail("server_unavailable")
                    return False
                if not self._backend.pane_alive(
                    self._socket_path,
                    self._target,
                ):
                    self._fail("pane_unavailable")
                    return False
            except ProviderObservationError as exc:
                self._fail(exc.code)
                return False
            return self._failure_code is None

    def finalize(self) -> Mapping[str, object]:
        with self._lock:
            if self._final_record is not None:
                return dict(self._final_record)

            temporary_path = self._transcript_path.with_suffix(
                self._transcript_path.suffix + ".tmp"
            )
            try:
                temporary_path.write_bytes(self._display_path.read_bytes())
                os.replace(temporary_path, self._transcript_path)
            except OSError:
                self._fail("transcript_finalize_failed")
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

            try:
                self._backend.close_pane(
                    self._socket_path,
                    self._target,
                )
            except ProviderObservationError as exc:
                self._fail(exc.code)
            except OSError:
                self._fail("pane_teardown_failed")

            self._status = (
                "failed" if self._failure_code is not None else "finalized"
            )
            self._final_record = self._build_record()
            return dict(self._final_record)

    def close(self) -> Mapping[str, object]:
        return self.finalize()

    def _fail(self, code: str) -> None:
        if self._failure_code is None:
            self._failure_code = code
        self._status = "failed"

    def _build_record(self) -> dict[str, object]:
        return {
            "schema_version": _RECORD_SCHEMA_VERSION,
            "invocation_id": self._invocation_id,
            "member_id": self._member_id,
            "turn_id": self._turn_id,
            "display_path": self._relative_display_path,
            "transcript_path": self._relative_transcript_path,
            "status": self._status,
            "failure_code": self._failure_code,
        }


class ProviderObservationManager:
    """Own one private run-scoped tmux server and distinct observation panes."""

    def __init__(
        self,
        run_root: Path,
        *,
        backend: _ObservationBackend | None = None,
    ) -> None:
        self._run_root = Path(run_root).resolve()
        self._artifact_root = self._run_root / "provider-observation"
        self._display_root = self._artifact_root / "display"
        self._transcript_root = self._artifact_root / "transcripts"
        self._display_root.mkdir(parents=True, exist_ok=True)
        self._transcript_root.mkdir(parents=True, exist_ok=True)

        token = uuid.uuid4().hex[:12]
        self._socket_directory = Path(
            tempfile.mkdtemp(prefix="orc-observe-")
        )
        self._socket_path = self._socket_directory / "tmux.sock"
        self._session_name = f"orc-observe-{token}"
        self._backend = backend or _TmuxObservationBackend()
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._handles: list[ProviderObservationHandle] = []
        self._allocation_index = 0
        self._invocation_index = 0
        self._server_started = False
        self._state = "open"
        self._failure_code: str | None = None

    @property
    def session_name(self) -> str:
        return self._session_name

    @property
    def failure_code(self) -> str | None:
        with self._lock:
            return self._failure_code

    def next_invocation_id(self) -> str:
        """Allocate one stable run-scoped identity for an ordinary invocation."""
        with self._lock:
            if self._state != "open":
                raise ProviderObservationError("manager_closed")
            self._invocation_index += 1
            return f"provider-invocation-{self._invocation_index:06d}"

    def open_observation(
        self,
        *,
        invocation_id: str,
        member_id: str,
        turn_id: str,
    ) -> ProviderObservationHandle:
        for field_name, value in (
            ("invocation_id", invocation_id),
            ("member_id", member_id),
            ("turn_id", turn_id),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")

        with self._lock:
            if self._state != "open":
                raise ProviderObservationError("manager_closed")
            self._ensure_server_locked()
            self._allocation_index += 1
            digest = hashlib.sha256(
                (
                    f"{invocation_id}\0{member_id}\0{turn_id}\0"
                    f"{self._allocation_index}"
                ).encode("utf-8")
            ).hexdigest()[:16]
            stem = f"{self._allocation_index:06d}-{digest}"
            display_path = self._display_root / f"{stem}.display"
            transcript_path = self._transcript_root / f"{stem}.transcript"
            try:
                display_path.touch(exist_ok=False)
            except OSError as exc:
                raise ProviderObservationError(
                    "display_precreate_failed"
                ) from exc

            try:
                target = self._backend.open_pane(
                    self._socket_path,
                    self._session_name,
                    display_path,
                )
            except ProviderObservationError:
                raise
            except (OSError, RuntimeError) as exc:
                raise ProviderObservationError(
                    "pane_allocation_failed"
                ) from exc
            if not isinstance(target, str) or not target:
                raise ProviderObservationError("pane_allocation_failed")

            handle = ProviderObservationHandle(
                manager=self,
                backend=self._backend,
                socket_path=self._socket_path,
                target=target,
                invocation_id=invocation_id,
                member_id=member_id,
                turn_id=turn_id,
                display_path=display_path,
                transcript_path=transcript_path,
                relative_display_path=str(
                    display_path.relative_to(self._run_root)
                ),
                relative_transcript_path=str(
                    transcript_path.relative_to(self._run_root)
                ),
            )
            self._handles.append(handle)
            return handle

    def close(self) -> None:
        with self._condition:
            while self._state == "closing":
                self._condition.wait()
            if self._state == "closed":
                return
            self._state = "closing"
            handles = tuple(self._handles)
            server_started = self._server_started

        for handle in handles:
            handle.finalize()

        server_absent = not server_started
        teardown_failure: str | None = None
        if server_started:
            try:
                self._backend.close_server(self._socket_path)
            except ProviderObservationError as exc:
                teardown_failure = exc.code
            except OSError:
                teardown_failure = "server_teardown_failed"

            try:
                server_absent = not self._backend.server_alive(
                    self._socket_path,
                    self._session_name,
                )
            except (ProviderObservationError, OSError):
                server_absent = False
                if teardown_failure is None:
                    teardown_failure = "server_health_unknown"
            if not server_absent and teardown_failure is None:
                teardown_failure = "server_teardown_incomplete"

        if server_absent:
            shutil.rmtree(self._socket_directory, ignore_errors=True)

        with self._condition:
            if teardown_failure is not None:
                self._failure_code = teardown_failure
            self._state = "closed" if server_absent else "teardown_failed"
            self._condition.notify_all()

    def __enter__(self) -> ProviderObservationManager:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _ensure_server_locked(self) -> None:
        if self._server_started:
            return
        try:
            self._backend.start_server(
                self._socket_path,
                self._session_name,
            )
        except ProviderObservationError:
            raise
        except (OSError, RuntimeError) as exc:
            raise ProviderObservationError("server_start_failed") from exc
        self._server_started = True


__all__ = [
    "ProviderObservationError",
    "ProviderObservationHandle",
    "ProviderObservationManager",
]
