"""Per-step summary observer with async/sync execution modes."""

from __future__ import annotations

import json
import posixpath
import re
import threading
from pathlib import Path
from typing import Any, Dict

from orchestrator.providers.types import ProviderParams


class SummaryObserver:
    """Runs optional per-step summarization without altering workflow semantics."""

    _index_lock = threading.Lock()

    def __init__(
        self,
        run_root: Path,
        provider_executor: Any,
        provider_name: str,
        mode: str = "async",
        timeout_sec: int = 120,
        best_effort: bool = True,
        max_input_chars: int = 12000,
        profile: str = "basic",
        invocation_context: Dict[str, Any] | None = None,
        aggregate_run_root: Path | None = None,
    ):
        self.run_root = Path(run_root)
        self.aggregate_run_root = Path(aggregate_run_root) if aggregate_run_root is not None else self.run_root
        self.provider_executor = provider_executor
        self.provider_name = provider_name
        self.mode = mode
        self.timeout_sec = timeout_sec
        self.best_effort = best_effort
        self.max_input_chars = max_input_chars
        self.profile = profile if profile in {"basic", "phase-performance"} else "basic"
        self.invocation_context = dict(invocation_context or {})
        self.summaries_dir = self.run_root / "summaries"
        self.aggregate_summaries_dir = self.aggregate_run_root / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self.aggregate_summaries_dir.mkdir(parents=True, exist_ok=True)
        self._threads: list[threading.Thread] = []

    def emit(self, step_name: str, snapshot: Dict[str, Any], *, summary_kind: str = "step") -> None:
        """Emit summary generation for one step."""
        if summary_kind not in {"step", "provider", "phase"}:
            summary_kind = "step"
        safe = self._safe_name(step_name)
        stem = self._file_stem(safe, summary_kind)
        snapshot_path = self.summaries_dir / f"{stem}.snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        prompt = self._build_prompt(snapshot, summary_kind=summary_kind)
        entry = {
            "step_name": step_name,
            "kind": summary_kind,
            "profile": self.profile,
            "status": self._snapshot_status(snapshot),
            "duration_ms": self._snapshot_duration_ms(snapshot),
            "snapshot_path": str(snapshot_path.relative_to(self.run_root)),
            "summary_path": str((self.summaries_dir / f"{stem}.summary.md").relative_to(self.run_root)),
            "error_path": None,
        }

        if self.mode == "async":
            thread = threading.Thread(
                target=self._run_summary,
                args=(stem, prompt, entry),
                daemon=True,
                name=f"summary-{stem}",
            )
            thread.start()
            self._threads.append(thread)
            return

        ok = self._run_summary(stem, prompt, entry)
        if not ok and not self.best_effort:
            raise RuntimeError(f"Summary generation failed for step '{step_name}'")

    def _run_summary(self, stem: str, prompt: str, entry: Dict[str, Any]) -> bool:
        summary_path = self.summaries_dir / f"{stem}.summary.md"
        error_path = self.summaries_dir / f"{stem}.error.json"

        invocation, prepare_error = self.provider_executor.prepare_invocation(
            provider_name=self.provider_name,
            params=ProviderParams(params={}),
            context=self.invocation_context,
            prompt_content=prompt,
            timeout_sec=self.timeout_sec,
        )

        if prepare_error is not None or invocation is None:
            error_path.write_text(
                json.dumps(
                    {
                        "stage": "prepare_invocation",
                        "exit_code": 2,
                        "error": prepare_error or {"message": "failed to create summary invocation"},
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            self._record_index_entry(entry, error_path=error_path)
            self._record_aggregate_index_entry(entry, error_path=error_path)
            return False

        exec_result = self.provider_executor.execute(invocation)
        exit_code = int(getattr(exec_result, "exit_code", 1))
        error = getattr(exec_result, "error", None)

        if exit_code != 0 or error is not None:
            error_payload = {
                "stage": "execute",
                "exit_code": exit_code,
                "error": error,
                "stderr": getattr(exec_result, "stderr", b"").decode("utf-8", errors="replace")
                if isinstance(getattr(exec_result, "stderr", b""), (bytes, bytearray))
                else str(getattr(exec_result, "stderr", "")),
            }
            error_path.write_text(json.dumps(error_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._record_index_entry(entry, error_path=error_path)
            self._record_aggregate_index_entry(entry, error_path=error_path)
            return False

        stdout = getattr(exec_result, "stdout", b"")
        if isinstance(stdout, (bytes, bytearray)):
            summary_text = stdout.decode("utf-8", errors="replace")
        else:
            summary_text = str(stdout)

        summary_path.write_text(summary_text if summary_text.endswith("\n") else summary_text + "\n", encoding="utf-8")
        self._record_index_entry(entry)
        self._record_aggregate_index_entry(entry)
        return True

    def _build_prompt(self, snapshot: Dict[str, Any], *, summary_kind: str = "step") -> str:
        body = json.dumps(snapshot, indent=2, sort_keys=True)
        if len(body) > self.max_input_chars:
            body = body[: self.max_input_chars]
        if self.profile == "phase-performance" and summary_kind == "provider":
            return (
                "Summarize this provider step in concise, factual markdown. "
                "Include what the provider was asked to do, whether it completed, failed, or was skipped, "
                "key artifacts or outputs, and an advisory performance judgment covering duration, "
                "timeout pressure, retry/fix risk, and evidence sufficiency. "
                "This summary is observability-only; do not suggest workflow control-flow decisions as if "
                "they have already happened.\n\n"
                f"{body}"
            )
        if self.profile == "phase-performance" and summary_kind == "phase":
            return (
                "Summarize this workflow phase boundary in concise, factual markdown. "
                "Include phase outcome, notable child outputs if present, work that advanced, blocking or "
                "follow-up signals, and an advisory performance judgment covering elapsed time, "
                "retries/failures, and whether evidence is sufficient for a human reviewer. "
                "This summary is observability-only and must not be treated as workflow state.\n\n"
                f"{body}"
            )
        return (
            "Summarize the following workflow step in concise, factual markdown. "
            "Include what was attempted, key outputs, and current status.\n\n"
            f"{body}"
        )

    def _record_index_entry(self, entry: Dict[str, Any], *, error_path: Path | None = None) -> None:
        if self._same_run_root(self.run_root, self.aggregate_run_root):
            return
        if error_path is not None:
            entry = dict(entry)
            entry["error_path"] = str(error_path.relative_to(self.run_root))
            entry["summary_path"] = None
        self._append_index_entry(
            index_path=self.summaries_dir / "index.json",
            entry=entry,
            root=self.run_root,
            render_human_files=False,
        )

    def _record_aggregate_index_entry(self, entry: Dict[str, Any], *, error_path: Path | None = None) -> None:
        aggregate_entry = dict(entry)
        for key in ("snapshot_path", "summary_path"):
            value = aggregate_entry.get(key)
            if isinstance(value, str) and value:
                aggregate_entry[key] = self._local_rel_to_aggregate_rel(value)
        if error_path is not None:
            aggregate_entry["error_path"] = self._relative_to_run_root(error_path, self.aggregate_run_root)
            aggregate_entry["summary_path"] = None
        else:
            value = aggregate_entry.get("error_path")
            if isinstance(value, str) and value:
                aggregate_entry["error_path"] = self._local_rel_to_aggregate_rel(value)
        aggregate_entry["frame_root"] = self._frame_root_rel()
        self._append_index_entry(
            index_path=self.aggregate_summaries_dir / "index.json",
            entry=aggregate_entry,
            root=self.aggregate_run_root,
            render_human_files=True,
        )

    def _append_index_entry(
        self,
        *,
        index_path: Path,
        entry: Dict[str, Any],
        root: Path,
        render_human_files: bool,
    ) -> None:
        with self._index_lock:
            payload = self._read_index(index_path)
            payload["run_root"] = str(root)
            entries = payload.setdefault("entries", [])
            if not isinstance(entries, list):
                entries = []
                payload["entries"] = entries
            entries.append(entry)
            tmp_path = index_path.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp_path.replace(index_path)
            if render_human_files:
                self._render_root_hub(payload)

    @staticmethod
    def _read_index(index_path: Path) -> Dict[str, Any]:
        if index_path.exists():
            try:
                payload = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = {"schema": "orchestrator_summary_index/v1", "entries": []}
        else:
            payload = {"schema": "orchestrator_summary_index/v1", "entries": []}
        return payload

    def _render_root_hub(self, payload: Dict[str, Any]) -> None:
        entries = payload.get("entries")
        if not isinstance(entries, list):
            entries = []
        self._write_readme(entries)
        self._write_run_summary(entries)

    def _write_readme(self, entries: list[Any]) -> None:
        lines = [
            "# Run Summaries",
            "",
            "This directory is the user-facing index for generated workflow summaries.",
            "Detailed summary files remain beside the run or call frame that produced them.",
            "",
        ]
        grouped = {"provider": [], "phase": [], "step": []}
        for entry in entries:
            if isinstance(entry, dict):
                grouped.setdefault(str(entry.get("kind", "step")), []).append(entry)
        for kind, title in (("provider", "Provider Steps"), ("phase", "Phase Boundaries"), ("step", "Other Steps")):
            kind_entries = grouped.get(kind, [])
            if not kind_entries:
                continue
            lines.extend([f"## {title}", ""])
            for entry in kind_entries:
                lines.append(self._readme_entry_line(entry))
            lines.append("")
        (self.aggregate_summaries_dir / "README.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _write_run_summary(self, entries: list[Any]) -> None:
        lines = [
            "# Run Summary",
            "",
            "Generated summary rollup. This file is observability-only and is not workflow state.",
            "",
        ]
        if not entries:
            lines.append("No summaries have been generated yet.")
        else:
            lines.append("## Generated Summaries")
            lines.append("")
            for entry in entries:
                if isinstance(entry, dict):
                    lines.append(self._readme_entry_line(entry))
        (self.aggregate_summaries_dir / "run-summary.md").write_text(
            "\n".join(lines).rstrip() + "\n",
            encoding="utf-8",
        )

    def _readme_entry_line(self, entry: Dict[str, Any]) -> str:
        name = str(entry.get("step_name", "unknown"))
        kind = str(entry.get("kind", "step"))
        status = entry.get("status") or "unknown"
        duration = entry.get("duration_ms")
        duration_text = f", {duration} ms" if duration is not None else ""
        error_path = entry.get("error_path")
        if isinstance(error_path, str) and error_path:
            link = posixpath.relpath(error_path, start="summaries")
            return f"- {name} ({kind}): {status}{duration_text} - [summary error]({link})"
        summary_path = entry.get("summary_path")
        if isinstance(summary_path, str) and summary_path:
            link = posixpath.relpath(summary_path, start="summaries")
            return f"- {name} ({kind}): {status}{duration_text} - [summary]({link})"
        return f"- {name} ({kind}): {status}{duration_text}"

    def _local_rel_to_aggregate_rel(self, relative_path: str) -> str:
        return self._relative_to_run_root(self.run_root / relative_path, self.aggregate_run_root)

    def _frame_root_rel(self) -> str:
        return self._relative_to_run_root(self.run_root, self.aggregate_run_root)

    @staticmethod
    def _relative_to_run_root(path: Path, root: Path) -> str:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()

    @staticmethod
    def _same_run_root(left: Path, right: Path) -> bool:
        try:
            return left.resolve() == right.resolve()
        except OSError:
            return left == right

    def _file_stem(self, safe_step_name: str, summary_kind: str) -> str:
        if self.profile == "basic" and summary_kind == "step":
            return safe_step_name
        return f"{safe_step_name}.{summary_kind}"

    @staticmethod
    def _snapshot_status(snapshot: Dict[str, Any]) -> Any:
        step = snapshot.get("step") if isinstance(snapshot, dict) else None
        output = step.get("output") if isinstance(step, dict) else None
        return output.get("status") if isinstance(output, dict) else None

    @staticmethod
    def _snapshot_duration_ms(snapshot: Dict[str, Any]) -> Any:
        step = snapshot.get("step") if isinstance(snapshot, dict) else None
        output = step.get("output") if isinstance(step, dict) else None
        return output.get("duration_ms") if isinstance(output, dict) else None

    @staticmethod
    def _safe_name(step_name: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", step_name)
