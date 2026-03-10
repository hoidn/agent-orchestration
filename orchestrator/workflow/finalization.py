"""Workflow finalization lifecycle helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .runtime_types import RoutingDecision
from .state_projection import WorkflowStateProjection


class FinalizationController:
    """Manage workflow-level finalization bookkeeping without owning execution flow."""

    def __init__(
        self,
        *,
        finalization: Optional[Dict[str, Any]],
        finalization_steps: List[Dict[str, Any]],
        finalization_start_index: int,
        finalization_step_count: Optional[int] = None,
        finalization_node_ids: Optional[List[str]] = None,
        finalization_entry_node_id: Optional[str] = None,
        projection: Optional[WorkflowStateProjection] = None,
        has_workflow_outputs: bool,
        persist_state: Callable[[Dict[str, Any]], None],
        finalization_failure_error: Callable[[Dict[str, Any], str], Dict[str, Any]],
    ) -> None:
        self.finalization = finalization
        self.finalization_steps = finalization_steps
        self.finalization_start_index = finalization_start_index
        self.finalization_node_ids = tuple(
            node_id for node_id in (finalization_node_ids or []) if isinstance(node_id, str)
        )
        self.finalization_step_count = (
            finalization_step_count
            if isinstance(finalization_step_count, int)
            else len(self.finalization_node_ids) or len(self.finalization_steps)
        )
        self.finalization_node_id_set = set(self.finalization_node_ids)
        self.finalization_entry_node_id = finalization_entry_node_id
        self.projection = projection
        self.has_workflow_outputs = has_workflow_outputs
        self.persist_state = persist_state
        self.finalization_failure_error = finalization_failure_error

    def _block_id(self) -> str:
        """Return the stable persisted block id for workflow finalization."""
        if isinstance(self.finalization, dict):
            for key in ("token", "id"):
                value = self.finalization.get(key)
                if isinstance(value, str) and value:
                    return value
        return "finally"

    def _configured_step_names(self) -> List[str]:
        """Return projected finalization presentation keys when available."""
        if self.projection is not None and self.finalization_node_ids:
            names = [
                self.projection.presentation_key_by_node_id.get(node_id)
                for node_id in self.finalization_node_ids
            ]
            return [name for name in names if isinstance(name, str)]
        return [step.get("name") for step in self.finalization_steps if isinstance(step, dict)]

    def _finalization_index_for(
        self,
        *,
        step_index: Optional[int] = None,
        step_node_id: Optional[str] = None,
    ) -> Optional[int]:
        """Return the local finalization index for one execution position."""
        if (
            isinstance(step_node_id, str)
            and self.projection is not None
            and step_node_id in self.projection.finalization_index_by_node_id
        ):
            return self.projection.finalization_index_by_node_id[step_node_id]
        if isinstance(step_index, int) and self.is_finalization_step(step_index=step_index):
            return step_index - self.finalization_start_index
        return None

    def initial_state(self) -> Optional[Dict[str, Any]]:
        """Return durable finalization bookkeeping for workflows with cleanup."""
        if self.finalization_step_count <= 0:
            return None
        output_status = "pending" if self.has_workflow_outputs else "not_configured"
        return {
            "block_id": self._block_id(),
            "status": "pending",
            "body_status": None,
            "current_index": None,
            "completed_indices": [],
            "step_names": self._configured_step_names(),
            "workflow_outputs_status": output_status,
        }

    def ensure_state(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ensure run state contains the finalization bookkeeping structure."""
        if self.finalization_step_count <= 0:
            return None
        finalization = state.get("finalization")
        if not isinstance(finalization, dict):
            finalization = self.initial_state() or {}
            state["finalization"] = finalization
        finalization.setdefault("block_id", self._block_id())
        finalization.setdefault("status", "pending")
        finalization.setdefault("body_status", None)
        finalization.setdefault("current_index", None)
        finalization.setdefault("completed_indices", [])
        finalization.setdefault(
            "step_names",
            self._configured_step_names(),
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
        elif len(completed_indices) == self.finalization_step_count:
            finalization["status"] = "completed"
            finalization.pop("failure", None)
        else:
            finalization["status"] = "running"
        self.persist_state(state)

    def record_settled_result(
        self,
        state: Dict[str, Any],
        step_index: Optional[int],
        step_name: str,
        body_status: str,
        *,
        step_node_id: Optional[str] = None,
    ) -> None:
        """Project one settled cleanup result into finalization bookkeeping."""
        final_index = self._finalization_index_for(step_index=step_index, step_node_id=step_node_id)
        if final_index is None:
            return
        result = state.get("steps", {}).get(step_name)
        failed = isinstance(result, dict) and result.get("status") == "failed"
        self.record_step_result(
            state,
            final_index,
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
        step_index: Optional[int],
        terminal_status: str,
        state: Dict[str, Any],
        *,
        step_node_id: Optional[str] = None,
    ) -> RoutingDecision:
        """Redirect body termination into finalization when configured."""
        if next_step not in {"_end", "_stop"}:
            return RoutingDecision(terminal_status=terminal_status, should_break=False)
        if next_step == "_stop":
            terminal_status = "failed"
        if self.finalization_step_count > 0 and not self.is_finalization_step(
            step_index=step_index,
            step_node_id=step_node_id,
        ):
            self.activate(state, terminal_status)
            if isinstance(self.finalization_entry_node_id, str) and self.finalization_entry_node_id:
                return RoutingDecision(
                    next_node_id=self.finalization_entry_node_id,
                    terminal_status=terminal_status,
                    should_break=False,
                )
            return RoutingDecision(
                next_step_index=self.finalization_start_index,
                terminal_status=terminal_status,
                should_break=False,
            )
        return RoutingDecision(terminal_status=terminal_status, should_break=True)

    def is_finalization_step(
        self,
        *,
        step_index: Optional[int] = None,
        step_node_id: Optional[str] = None,
    ) -> bool:
        """Return True when the current step belongs to the appended finalization slice."""
        if isinstance(step_node_id, str) and self.finalization_node_id_set:
            return step_node_id in self.finalization_node_id_set
        return (
            self.finalization_step_count > 0
            and isinstance(step_index, int)
            and step_index >= self.finalization_start_index
        )
