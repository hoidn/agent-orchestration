"""Workflow finalization lifecycle helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .runtime_types import RoutingDecision


class FinalizationController:
    """Manage workflow-level finalization bookkeeping without owning execution flow."""

    def __init__(
        self,
        *,
        finalization: Optional[Dict[str, Any]],
        finalization_steps: List[Dict[str, Any]],
        finalization_start_index: int,
        has_workflow_outputs: bool,
        persist_state: Callable[[Dict[str, Any]], None],
        finalization_failure_error: Callable[[Dict[str, Any], str], Dict[str, Any]],
    ) -> None:
        self.finalization = finalization
        self.finalization_steps = finalization_steps
        self.finalization_start_index = finalization_start_index
        self.has_workflow_outputs = has_workflow_outputs
        self.persist_state = persist_state
        self.finalization_failure_error = finalization_failure_error

    def initial_state(self) -> Optional[Dict[str, Any]]:
        """Return durable finalization bookkeeping for workflows with cleanup."""
        if not self.finalization_steps:
            return None
        output_status = "pending" if self.has_workflow_outputs else "not_configured"
        block_token = self.finalization.get("token") if isinstance(self.finalization, dict) else None
        return {
            "block_id": block_token or "finally",
            "status": "pending",
            "body_status": None,
            "current_index": None,
            "completed_indices": [],
            "step_names": [step.get("name") for step in self.finalization_steps if isinstance(step, dict)],
            "workflow_outputs_status": output_status,
        }

    def ensure_state(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ensure run state contains the finalization bookkeeping structure."""
        if not self.finalization_steps:
            return None
        finalization = state.get("finalization")
        if not isinstance(finalization, dict):
            finalization = self.initial_state() or {}
            state["finalization"] = finalization
        finalization.setdefault(
            "block_id",
            self.finalization.get("token") if isinstance(self.finalization, dict) else "finally",
        )
        finalization.setdefault("status", "pending")
        finalization.setdefault("body_status", None)
        finalization.setdefault("current_index", None)
        finalization.setdefault("completed_indices", [])
        finalization.setdefault(
            "step_names",
            [step.get("name") for step in self.finalization_steps if isinstance(step, dict)],
        )
        if "workflow_outputs_status" not in finalization:
            finalization["workflow_outputs_status"] = (
                "pending" if self.has_workflow_outputs else "not_configured"
            )
        return finalization

    def activate(self, state: Dict[str, Any], body_status: str) -> None:
        """Mark finalization as pending/running after the workflow body settles."""
        finalization = self.ensure_state(state)
        if finalization is None:
            return
        finalization["body_status"] = body_status
        if finalization.get("status") == "pending":
            finalization["status"] = "running"
        self.persist_state(state)

    def record_step_start(self, state: Dict[str, Any], final_index: int, body_status: str) -> None:
        """Persist which cleanup step is currently running."""
        finalization = self.ensure_state(state)
        if finalization is None:
            return
        finalization["body_status"] = body_status
        finalization["status"] = "running"
        finalization["current_index"] = final_index
        self.persist_state(state)

    def record_step_result(
        self,
        state: Dict[str, Any],
        final_index: int,
        step_name: str,
        failed: bool,
        result: Any,
        body_status: str,
    ) -> None:
        """Persist one cleanup step outcome for resume and reporting."""
        finalization = self.ensure_state(state)
        if finalization is None:
            return
        completed_indices = finalization.setdefault("completed_indices", [])
        if not failed and final_index not in completed_indices:
            completed_indices.append(final_index)
            completed_indices.sort()
        finalization["body_status"] = body_status
        finalization["current_index"] = None if not failed else final_index
        if failed:
            finalization["status"] = "failed"
            error = result.get("error") if isinstance(result, dict) else None
            finalization["failure"] = {
                "step": step_name,
                "step_id": result.get("step_id") if isinstance(result, dict) else None,
                "error": error,
            }
        elif len(completed_indices) == len(self.finalization_steps):
            finalization["status"] = "completed"
            finalization.pop("failure", None)
        else:
            finalization["status"] = "running"
        self.persist_state(state)

    def record_settled_result(
        self,
        state: Dict[str, Any],
        step_index: int,
        step_name: str,
        body_status: str,
    ) -> None:
        """Project one settled cleanup result into finalization bookkeeping."""
        if not self.is_finalization_step(step_index):
            return
        result = state.get("steps", {}).get(step_name)
        failed = isinstance(result, dict) and result.get("status") == "failed"
        self.record_step_result(
            state,
            step_index - self.finalization_start_index,
            step_name,
            failed,
            result,
            body_status,
        )
        finalization = self.ensure_state(state)
        if failed:
            if body_status == "completed" and isinstance(result, dict):
                state["error"] = self.finalization_failure_error(result, step_name)
            if isinstance(finalization, dict):
                finalization["workflow_outputs_status"] = "suppressed"
                self.persist_state(state)

    def continue_into_finalization(
        self,
        next_step: Optional[str],
        step_index: int,
        terminal_status: str,
        state: Dict[str, Any],
    ) -> RoutingDecision:
        """Redirect body termination into finalization when configured."""
        if next_step not in {"_end", "_stop"}:
            return RoutingDecision(next_step_index=None, terminal_status=terminal_status, should_break=False)
        if next_step == "_stop":
            terminal_status = "failed"
        if self.finalization_steps and step_index < self.finalization_start_index:
            self.activate(state, terminal_status)
            return RoutingDecision(
                next_step_index=self.finalization_start_index,
                terminal_status=terminal_status,
                should_break=False,
            )
        return RoutingDecision(next_step_index=None, terminal_status=terminal_status, should_break=True)

    def is_finalization_step(self, step_index: int) -> bool:
        """Return True when the current step belongs to the appended finalization slice."""
        return bool(self.finalization_steps) and step_index >= self.finalization_start_index
