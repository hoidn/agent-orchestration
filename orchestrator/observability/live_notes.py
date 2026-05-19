"""Live current-step notes from bounded provider transport tails."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from orchestrator.providers.types import ProviderParams


class LiveAgentNoteObserver:
    """Best-effort live note generator for active session provider output."""

    def __init__(
        self,
        *,
        aggregate_run_root: Path,
        provider_executor: Any,
        provider_name: str,
        interval_sec: float = 15.0,
        timeout_sec: int = 30,
        max_tail_chars: int = 6000,
        invocation_context: dict[str, Any] | None = None,
        source: str = "auto",
        tmux_socket: str | None = None,
        tmux_target: str | None = None,
        tmux_capture: Any | None = None,
    ) -> None:
        self.aggregate_run_root = Path(aggregate_run_root)
        self.provider_executor = provider_executor
        self.provider_name = provider_name
        self.interval_sec = max(0.1, float(interval_sec))
        self.timeout_sec = max(1, int(timeout_sec))
        self.max_tail_chars = max(1, int(max_tail_chars))
        self.invocation_context = dict(invocation_context or {})
        self.source = source if source in {"tmux", "transport", "auto"} else "tmux"
        self.tmux_socket = tmux_socket or self._tmux_socket_from_env()
        self.tmux_target = tmux_target
        self._tmux_capture = tmux_capture
        self.summaries_dir = self.aggregate_run_root / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self._last_digest_by_key: dict[tuple[str, int, str], str] = {}
        self._emit_lock = threading.Lock()

    @contextmanager
    def watch(
        self,
        *,
        step_name: str,
        step_id: str,
        visit_count: int,
        transport_spool_path: Path | None = None,
    ) -> Iterator[None]:
        """Run a background live-note loop until the wrapped provider returns."""
        stop_event = threading.Event()

        def _safe_emit() -> None:
            try:
                self.emit_once(
                    step_name=step_name,
                    step_id=step_id,
                    visit_count=visit_count,
                    transport_spool_path=transport_spool_path,
                )
            except Exception as exc:
                self._write_error(
                    step_name,
                    step_id,
                    visit_count,
                    "live_note_observer",
                    {"message": str(exc)},
                )

        def _loop() -> None:
            while not stop_event.wait(self.interval_sec):
                _safe_emit()

        thread = threading.Thread(
            target=_loop,
            name=f"live-agent-note-{step_name}",
            daemon=True,
        )
        thread.start()
        try:
            yield
        finally:
            stop_event.set()
            _safe_emit()
            thread.join(timeout=1.0)

    def emit_once(
        self,
        *,
        step_name: str,
        step_id: str,
        visit_count: int,
        transport_spool_path: Path | None = None,
    ) -> bool:
        """Summarize one changed transport tail and write live-note artifacts."""
        with self._emit_lock:
            tail, source_metadata = self._read_source_tail(transport_spool_path)
            if not tail.strip():
                return False
            source_key = str(source_metadata.get("source_key") or source_metadata.get("source_kind") or "")
            key = (step_id, visit_count, source_key)
            digest = hashlib.sha256(tail.encode("utf-8")).hexdigest()
            if self._last_digest_by_key.get(key) == digest:
                return False

            prompt = self._build_prompt(
                step_name=step_name,
                step_id=step_id,
                visit_count=visit_count,
                tail=tail,
            )
            invocation, prepare_error = self.provider_executor.prepare_invocation(
                provider_name=self.provider_name,
                params=ProviderParams(params={}),
                context=self.invocation_context,
                prompt_content=prompt,
                timeout_sec=self.timeout_sec,
            )
            if prepare_error is not None or invocation is None:
                self._write_error(step_name, step_id, visit_count, "prepare_invocation", prepare_error)
                return False

            result = self.provider_executor.execute(invocation)
            exit_code = int(getattr(result, "exit_code", 1))
            error = getattr(result, "error", None)
            if exit_code != 0 or error is not None:
                self._write_error(
                    step_name,
                    step_id,
                    visit_count,
                    "execute",
                    self._provider_failure_error(result, exit_code),
                )
                return False

            stdout = getattr(result, "stdout", b"")
            note = stdout.decode("utf-8", errors="replace") if isinstance(stdout, (bytes, bytearray)) else str(stdout)
            self._write_note(
                note=note if note.endswith("\n") else note + "\n",
                step_name=step_name,
                step_id=step_id,
                visit_count=visit_count,
                source_metadata=source_metadata,
            )
            self._last_digest_by_key[key] = digest
            return True

    def _read_source_tail(self, transport_spool_path: Path | None) -> tuple[str, dict[str, Any]]:
        if self.source in {"tmux", "auto"}:
            tail, metadata = self._read_tmux_tail()
            if tail.strip() or self.source == "tmux":
                return tail, metadata
        if transport_spool_path is not None:
            return self._read_tail(transport_spool_path), {
                "source_kind": "provider_transport",
                "source_key": str(transport_spool_path),
                "source_transport_path": self._run_relative_path(transport_spool_path),
            }
        return "", {"source_kind": "none", "source_key": "none"}

    def _read_tmux_tail(self) -> tuple[str, dict[str, Any]]:
        socket = self.tmux_socket
        if not socket:
            if self._tmux_capture is not None:
                metadata = {
                    "source_kind": "tmux_pane",
                    "source_key": "tmux:injected",
                    "source_tmux_target": self.tmux_target,
                }
                return str(self._tmux_capture(self.max_tail_chars))[-self.max_tail_chars :], metadata
            return "", {"source_kind": "tmux_pane", "source_key": "tmux:none"}
        target = self.tmux_target or self._resolve_tmux_target(socket, os.getpid())
        metadata = {
            "source_kind": "tmux_pane",
            "source_key": f"tmux:{socket}:{target or ''}",
            "source_tmux_socket": socket,
            "source_tmux_target": target,
        }
        if not target:
            return "", metadata
        if self._tmux_capture is not None:
            return str(self._tmux_capture(self.max_tail_chars))[-self.max_tail_chars :], metadata
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "-S",
                    socket,
                    "capture-pane",
                    "-p",
                    "-J",
                    "-t",
                    target,
                    "-S",
                    "-240",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                timeout=1.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "", metadata
        if result.returncode != 0:
            return "", metadata
        return result.stdout[-self.max_tail_chars :], metadata

    def _read_tail(self, path: Path) -> str:
        try:
            data = Path(path).read_bytes()
        except OSError:
            return ""
        text = data.decode("utf-8", errors="replace")
        return text[-self.max_tail_chars :]

    def _write_note(
        self,
        *,
        note: str,
        step_name: str,
        step_id: str,
        visit_count: int,
        source_metadata: dict[str, Any],
    ) -> None:
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        note_path = self.summaries_dir / "live-current-step.md"
        metadata_path = self.summaries_dir / "live-current-step.json"
        self._write_text_atomic(note_path, note)
        payload = {
            "schema": "orchestrator_live_agent_note/v1",
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": visit_count,
            "provider": self.provider_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        for key in (
            "source_kind",
            "source_transport_path",
            "source_tmux_socket",
            "source_tmux_target",
        ):
            value = source_metadata.get(key)
            if value is not None:
                payload[key] = value
        self._write_json_atomic(metadata_path, payload)
        try:
            (self.summaries_dir / "live-current-step.error.json").unlink()
        except FileNotFoundError:
            pass

    def _tmux_socket_from_env(self) -> str | None:
        tmux = os.environ.get("TMUX")
        if not tmux:
            return None
        socket = tmux.split(",", 1)[0]
        return socket or None

    def _resolve_tmux_target(self, socket: str, pid: int) -> str | None:
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "-S",
                    socket,
                    "list-panes",
                    "-a",
                    "-F",
                    "#{session_name}:#{window_index}.#{pane_index}\t#{pane_pid}",
                ],
                capture_output=True,
                check=False,
                encoding="utf-8",
                timeout=0.5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            target, sep, pane_pid_raw = line.partition("\t")
            if not sep:
                continue
            try:
                pane_pid = int(pane_pid_raw)
            except ValueError:
                continue
            if pid == pane_pid or self._process_is_descendant(pid, pane_pid):
                return target
        return None

    def _process_is_descendant(self, pid: int, ancestor_pid: int) -> bool:
        seen: set[int] = set()
        current = pid
        for _ in range(64):
            if current == ancestor_pid:
                return True
            if current in seen:
                return False
            seen.add(current)
            parent = self._process_parent_pid(current)
            if parent is None or parent <= 0:
                return False
            current = parent
        return False

    def _process_parent_pid(self, pid: int) -> int | None:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except OSError:
            return None
        close_paren = stat.rfind(")")
        if close_paren < 0:
            return None
        fields = stat[close_paren + 2 :].split()
        if len(fields) < 2:
            return None
        try:
            return int(fields[1])
        except ValueError:
            return None

    def _write_error(
        self,
        step_name: str,
        step_id: str,
        visit_count: int,
        stage: str,
        error: Any,
    ) -> None:
        payload = {
            "schema": "orchestrator_live_agent_note_error/v1",
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": visit_count,
            "provider": self.provider_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "error": error,
        }
        self._write_json_atomic(self.summaries_dir / "live-current-step.error.json", payload)

    def _provider_failure_error(self, result: Any, exit_code: int) -> dict[str, Any]:
        raw_error = getattr(result, "error", None)
        if isinstance(raw_error, Mapping):
            payload = dict(raw_error)
        elif raw_error is not None:
            payload = {"message": str(raw_error)}
        else:
            payload = {"message": f"live note provider exited {exit_code}"}
        payload.setdefault("message", f"live note provider exited {exit_code}")
        payload["exit_code"] = exit_code
        stderr = self._stream_text(getattr(result, "stderr", b""))
        stdout = self._stream_text(getattr(result, "stdout", b""))
        if stderr:
            payload["stderr"] = stderr[-2000:]
        if stdout:
            payload["stdout"] = stdout[-2000:]
        return payload

    def _stream_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="replace").strip()
        return str(value).strip()

    def _run_relative_path(self, path: Path) -> str | None:
        try:
            return Path(path).resolve(strict=False).relative_to(
                self.aggregate_run_root.resolve(strict=False)
            ).as_posix()
        except ValueError:
            return None

    def _write_text_atomic(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        self._write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _build_prompt(self, *, step_name: str, step_id: str, visit_count: int, tail: str) -> str:
        return (
            "Write a short live operator note from this partial provider output. "
            "Say what the agent appears to be doing now. Keep it concise, factual, and tentative when needed.\n\n"
            f"Step: {step_name}\n"
            f"Step id: {step_id}\n"
            f"Visit: {visit_count}\n\n"
            "Live output tail:\n"
            f"{tail}"
        )
