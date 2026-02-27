"""Per-step summary observer with async/sync execution modes."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Dict

from orchestrator.providers.types import ProviderParams


class SummaryObserver:
    """Runs optional per-step summarization without altering workflow semantics."""

    def __init__(
        self,
        run_root: Path,
        provider_executor: Any,
        provider_name: str,
        mode: str = "async",
        timeout_sec: int = 120,
        best_effort: bool = True,
        max_input_chars: int = 12000,
    ):
        self.run_root = Path(run_root)
        self.provider_executor = provider_executor
        self.provider_name = provider_name
        self.mode = mode
        self.timeout_sec = timeout_sec
        self.best_effort = best_effort
        self.max_input_chars = max_input_chars
        self.summaries_dir = self.run_root / "summaries"
        self.summaries_dir.mkdir(parents=True, exist_ok=True)
        self._threads: list[threading.Thread] = []

    def emit(self, step_name: str, snapshot: Dict[str, Any]) -> None:
        """Emit summary generation for one step."""
        safe = self._safe_name(step_name)
        snapshot_path = self.summaries_dir / f"{safe}.snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        prompt = self._build_prompt(snapshot)

        if self.mode == "async":
            thread = threading.Thread(
                target=self._run_summary,
                args=(safe, prompt),
                daemon=True,
                name=f"summary-{safe}",
            )
            thread.start()
            self._threads.append(thread)
            return

        ok = self._run_summary(safe, prompt)
        if not ok and not self.best_effort:
            raise RuntimeError(f"Summary generation failed for step '{step_name}'")

    def _run_summary(self, safe_step_name: str, prompt: str) -> bool:
        summary_path = self.summaries_dir / f"{safe_step_name}.summary.md"
        error_path = self.summaries_dir / f"{safe_step_name}.error.json"

        invocation, prepare_error = self.provider_executor.prepare_invocation(
            provider_name=self.provider_name,
            params=ProviderParams(params={}),
            context={},
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
            return False

        stdout = getattr(exec_result, "stdout", b"")
        if isinstance(stdout, (bytes, bytearray)):
            summary_text = stdout.decode("utf-8", errors="replace")
        else:
            summary_text = str(stdout)

        summary_path.write_text(summary_text if summary_text.endswith("\n") else summary_text + "\n", encoding="utf-8")
        return True

    def _build_prompt(self, snapshot: Dict[str, Any]) -> str:
        body = json.dumps(snapshot, indent=2, sort_keys=True)
        if len(body) > self.max_input_chars:
            body = body[: self.max_input_chars]
        return (
            "Summarize the following workflow step in concise, factual markdown. "
            "Include what was attempted, key outputs, and current status.\n\n"
            f"{body}"
        )

    @staticmethod
    def _safe_name(step_name: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", step_name)
