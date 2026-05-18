"""Live current-step notes from bounded provider transport tails."""

from __future__ import annotations

import hashlib
import json
import threading
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
    ) -> None:
        self.aggregate_run_root = Path(aggregate_run_root)
        self.provider_executor = provider_executor
        self.provider_name = provider_name
        self.interval_sec = max(0.1, float(interval_sec))
        self.timeout_sec = max(1, int(timeout_sec))
        self.max_tail_chars = max(1, int(max_tail_chars))
        self.invocation_context = dict(invocation_context or {})
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
        transport_spool_path: Path,
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
        transport_spool_path: Path,
    ) -> bool:
        """Summarize one changed transport tail and write live-note artifacts."""
        with self._emit_lock:
            tail = self._read_tail(transport_spool_path)
            if not tail.strip():
                return False
            key = (step_id, visit_count, str(transport_spool_path))
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
                    error or {"message": f"live note provider exited {exit_code}"},
                )
                return False

            stdout = getattr(result, "stdout", b"")
            note = stdout.decode("utf-8", errors="replace") if isinstance(stdout, (bytes, bytearray)) else str(stdout)
            self._write_note(
                note=note if note.endswith("\n") else note + "\n",
                step_name=step_name,
                step_id=step_id,
                visit_count=visit_count,
                transport_spool_path=transport_spool_path,
            )
            self._last_digest_by_key[key] = digest
            return True

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
        transport_spool_path: Path,
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
            "source_transport_path": self._run_relative_path(transport_spool_path),
        }
        self._write_json_atomic(metadata_path, payload)

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
            "Provider transport tail:\n"
            f"{tail}"
        )
