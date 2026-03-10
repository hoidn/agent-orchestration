"""Step outcome normalization and persistence helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..state import StateManager, StepResult
from .runtime_types import NormalizedStepOutcome


class OutcomeRecorder:
    """Normalize and persist step results without owning workflow routing."""

    def __init__(
        self,
        *,
        state_manager: StateManager,
        step_id_resolver: Callable[[Dict[str, Any]], str],
        step_type_resolver: Callable[[Dict[str, Any]], str],
        summary_emitter: Callable[[str, Dict[str, Any], Dict[str, Any]], None],
    ) -> None:
        self.state_manager = state_manager
        self.step_id_resolver = step_id_resolver
        self.step_type_resolver = step_type_resolver
        self.summary_emitter = summary_emitter

    def persist_step_result(
        self,
        state: Dict[str, Any],
        step_name: str,
        step: Dict[str, Any],
        result: Dict[str, Any],
        *,
        phase_hint: Optional[str] = None,
        class_hint: Optional[str] = None,
        retryable_hint: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if "steps" not in state:
            state["steps"] = {}

        finalized = self.attach_outcome(step, result, phase_hint, class_hint, retryable_hint)
        finalized.setdefault("name", step_name)
        finalized.setdefault("step_id", self.step_id_resolver(step))
        step_visits = state.get("step_visits", {})
        visit_count = step_visits.get(step_name) if isinstance(step_visits, dict) else None
        if isinstance(visit_count, int):
            finalized.setdefault("visit_count", visit_count)
        state["steps"][step_name] = finalized

        self.state_manager.update_step(step_name, self.to_step_result(finalized, finalized.get("name", step_name)))
        self.summary_emitter(step_name, step, finalized)
        return finalized

    def attach_outcome(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
        phase_hint: Optional[str] = None,
        class_hint: Optional[str] = None,
        retryable_hint: Optional[bool] = None,
    ) -> Dict[str, Any]:
        finalized = dict(result)
        status = finalized.get("status")
        if status is None:
            exit_code = finalized.get("exit_code", 0)
            status = "completed" if exit_code == 0 else "failed"
            finalized["status"] = status

        if status == "skipped":
            finalized["outcome"] = NormalizedStepOutcome(
                status="skipped",
                phase="pre_execution",
                outcome_class="skipped",
                retryable=False,
            ).to_dict()
            return finalized

        if status == "completed":
            finalized["outcome"] = NormalizedStepOutcome(
                status="completed",
                phase="execution",
                outcome_class="completed",
                retryable=False,
            ).to_dict()
            return finalized

        error = finalized.get("error")
        error_type = error.get("type") if isinstance(error, dict) else None
        step_type = self.step_type_resolver(step)
        normalized_class = class_hint
        normalized_phase = phase_hint
        retryable = retryable_hint

        if normalized_class is None:
            if error_type == "assert_failed":
                normalized_class = "assert_failed"
            elif error_type in {
                "call_resume_checksum_mismatch",
                "undefined_variables",
                "missing_secrets",
                "provider_not_found",
                "provider_preparation_failed",
                "substitution_error",
                "validation_error",
            }:
                normalized_class = "pre_execution_failed"
            elif error_type == "contract_violation":
                normalized_class = "contract_violation"
            elif error_type == "timeout" or finalized.get("timed_out") or finalized.get("exit_code") == 124:
                normalized_class = "timeout"
            elif step_type == "provider" and finalized.get("exit_code", 0) != 0:
                normalized_class = "provider_failed"
            elif step_type == "command" and finalized.get("exit_code", 0) != 0:
                normalized_class = "command_failed"
            else:
                normalized_class = "pre_execution_failed"

        if normalized_phase is None:
            if normalized_class in {"assert_failed", "command_failed", "provider_failed", "timeout"}:
                normalized_phase = "execution"
            elif normalized_class == "contract_violation":
                normalized_phase = "post_execution"
            else:
                normalized_phase = "pre_execution"

        if retryable is None:
            retryable = normalized_class == "provider_failed"

        finalized["outcome"] = NormalizedStepOutcome(
            status="failed",
            phase=normalized_phase,
            outcome_class=normalized_class,
            retryable=retryable,
        ).to_dict()
        return finalized

    @staticmethod
    def to_step_result(result: Dict[str, Any], fallback_name: str) -> StepResult:
        """Convert a persisted result payload into the runtime StepResult model."""
        return StepResult(
            status=result.get("status", "completed" if result.get("exit_code", 0) == 0 else "failed"),
            name=result.get("name", fallback_name),
            step_id=result.get("step_id"),
            exit_code=result.get("exit_code", 0),
            duration_ms=result.get("duration_ms", 0),
            output=result.get("output"),
            lines=result.get("lines"),
            json=result.get("json"),
            error=result.get("error"),
            truncated=result.get("truncated", False),
            artifacts=result.get("artifacts"),
            skipped=result.get("skipped", False),
            files=result.get("files"),
            wait_duration_ms=result.get("wait_duration_ms"),
            poll_count=result.get("poll_count"),
            timed_out=result.get("timed_out"),
            outcome=result.get("outcome"),
            visit_count=result.get("visit_count"),
        )
