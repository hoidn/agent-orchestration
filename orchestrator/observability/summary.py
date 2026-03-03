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
        snapshot_path.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

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
                        "error": prepare_error
                        or {"message": "failed to create summary invocation"},
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
            error_path.write_text(
                json.dumps(error_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            return False

        stdout = getattr(exec_result, "stdout", b"")
        if isinstance(stdout, (bytes, bytearray)):
            summary_text = stdout.decode("utf-8", errors="replace")
        else:
            summary_text = str(stdout)

        summary_path.write_text(
            summary_text if summary_text.endswith("\n") else summary_text + "\n", encoding="utf-8"
        )
        return True

    def _build_prompt(self, snapshot: Dict[str, Any]) -> str:
        full_body = json.dumps(snapshot, indent=2, sort_keys=True)
        is_truncated = len(full_body) > self.max_input_chars
        body = full_body[: self.max_input_chars] if is_truncated else full_body
        return (
            "You are writing a post-mortem for one workflow step.\n"
            "Primary goal: evaluate execution quality and reliability, not just restate outputs.\n\n"
            "Style requirements:\n"
            "- Prefer narrative analysis over checklist/template output.\n"
            "- Do not use markdown tables.\n"
            "- Avoid generic filler language.\n"
            "- Distinguish facts from inferences.\n"
            "- If uncertain, state uncertainty and alternative hypotheses.\n\n"
            "Use this markdown structure (headings required):\n"
            "## <Step Name> — Postmortem\n"
            "### Outcome and Plan Conformance\n"
            "### Mistakes and Failure Modes\n"
            "### Recovery and Adaptation\n"
            "### Stalls and Blockers\n"
            "### Evidence and Confidence\n"
            "### Recommended Next Actions\n\n"
            "Content requirements:\n"
            "- Assess whether the step conformed to declared intent/plan visible in prompt, consumes, and outputs.\n"
            "- Identify concrete mistakes (wrong scope, stale artifacts, incomplete execution, invalid assumptions, etc.).\n"
            "- Explain recovery attempts and whether they actually resolved issues.\n"
            "- State where the step got stuck and why.\n"
            "- Cite concrete values when present (status, exit_code, duration_ms, paths, artifacts, errors, commands/prompts).\n"
            "- Call out contradictions and missing evidence explicitly.\n"
            "- If data is missing, write `not present in snapshot` rather than guessing.\n"
            "- Do not invent execution results.\n"
            f"- Snapshot truncated: {'yes' if is_truncated else 'no'}.\n\n"
            "Snapshot JSON:\n"
            "```json\n"
            f"{body}\n"
            "```"
        )

    @staticmethod
    def _safe_name(step_name: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", step_name)
