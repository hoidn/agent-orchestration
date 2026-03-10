"""Resume restart planning helpers for workflow execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .state_projection import WorkflowStateProjection


class ResumeStateIntegrityError(RuntimeError):
    """Raised when persisted compatibility surfaces disagree during resume."""

    def __init__(self, message: str, *, context: Dict[str, Any]):
        super().__init__(message)
        self.context = context


@dataclass(frozen=True)
class _ProjectedCurrentStep:
    node_id: str
    presentation_key: str
    execution_index: int


class ResumePlanner:
    """Determine where a resumed run should re-enter top-level execution."""

    QUARANTINE_ERROR_TYPE = "provider_session_interrupted_visit_quarantined"

    def entry_is_terminal(self, entry: Any) -> bool:
        """Return True when persisted step state is fully completed/skipped."""
        if isinstance(entry, dict):
            status = entry.get("status")
            if isinstance(status, str):
                return status in ["completed", "skipped"]
            if not entry:
                return False
            return all(self.entry_is_terminal(value) for value in entry.values())
        if isinstance(entry, list):
            return all(self.entry_is_terminal(value) for value in entry)
        return False

    def determine_restart_index(
        self,
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart."""
        if projection is not None:
            restart_node_id = self.determine_restart_node_id(state, steps, projection=projection)
            if not isinstance(restart_node_id, str):
                return None
            entry = projection.entries_by_node_id.get(restart_node_id)
            if entry is None:
                return None
            if isinstance(entry.compatibility_index, int):
                return entry.compatibility_index
            if isinstance(entry.finalization_index, int):
                return len(projection.node_id_by_compatibility_index) + entry.finalization_index
            return None

        return self._determine_restart_index_legacy(state, steps)

    def determine_restart_node_id(
        self,
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[str]:
        """Determine the top-level executable node id where resumed execution should restart."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        current_step = state.get("current_step")
        if isinstance(current_step, dict):
            projected_current_step = self._projected_current_step(current_step, projection)
            if projected_current_step is not None:
                current_result = steps_state.get(projected_current_step.presentation_key)
                if not self.entry_is_terminal(current_result):
                    return projected_current_step.node_id
            if projection is not None:
                current_index = current_step.get("index")
                current_status = current_step.get("status")
                if isinstance(current_index, int) and current_status == "running":
                    node_id = projection.node_id_for_execution_index(current_index)
                    if isinstance(node_id, str):
                        entry = projection.entries_by_node_id.get(node_id)
                        if entry is not None:
                            current_result = steps_state.get(entry.presentation_key)
                            if not self.entry_is_terminal(current_result):
                                return node_id

        if projection is not None:
            for node_id in projection.ordered_execution_node_ids():
                entry = projection.entries_by_node_id.get(node_id)
                if entry is None:
                    continue
                step_name = entry.presentation_key
                if self.for_each_has_pending_work(state, step_name):
                    return node_id
                if self.repeat_until_has_pending_work(state, step_name):
                    return node_id
                step_result = steps_state.get(step_name)
                if step_result is None:
                    return node_id
                if not self.entry_is_terminal(step_result):
                    return node_id
            return None

        restart_index = self._determine_restart_index_legacy(state, steps)
        if not isinstance(restart_index, int):
            return None
        if 0 <= restart_index < len(steps):
            step = steps[restart_index]
            step_id = step.get("step_id")
            if isinstance(step_id, str) and step_id:
                return step_id
        return None

    def _determine_restart_index_legacy(
        self,
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
    ) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart via legacy scans."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        current_step = state.get("current_step")
        if isinstance(current_step, dict):
            current_index = current_step.get("index")
            current_status = current_step.get("status")
            if isinstance(current_index, int) and current_status == "running":
                if 0 <= current_index < len(steps):
                    current_step_name = steps[current_index].get("name", f"step_{current_index}")
                    if self.for_each_has_pending_work(state, current_step_name):
                        return current_index
                    if self.repeat_until_has_pending_work(state, current_step_name):
                        return current_index
                    current_result = steps_state.get(current_step_name)
                    if not self.entry_is_terminal(current_result):
                        return current_index

        for step_index, step in enumerate(steps):
            step_name = step.get("name", f"step_{step_index}")
            if self.for_each_has_pending_work(state, step_name):
                return step_index
            if self.repeat_until_has_pending_work(state, step_name):
                return step_index
            step_result = steps_state.get(step_name)
            if step_result is None:
                return step_index
            if not self.entry_is_terminal(step_result):
                return step_index

        return None

    def _projected_current_step(
        self,
        current_step: Dict[str, Any],
        projection: Optional[WorkflowStateProjection],
    ) -> Optional[_ProjectedCurrentStep]:
        if projection is None:
            return None
        step_id = current_step.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            return None
        entry = projection.entry_for_step_id(step_id)
        if entry is None:
            raise ResumeStateIntegrityError(
                f"Persisted current_step.step_id '{step_id}' is not present in the current workflow projection.",
                context={
                    "step_id": step_id,
                    "field": "step_id",
                    "expected": "known projection step_id",
                    "actual": step_id,
                },
            )
        execution_index = projection.execution_index_for_step_id(step_id)
        if not isinstance(execution_index, int):
            raise ResumeStateIntegrityError(
                f"Persisted current_step.step_id '{step_id}' does not map to a resumable workflow execution index.",
                context={
                    "step_id": step_id,
                    "field": "step_id",
                    "expected": "workflow execution index",
                    "actual": None,
                },
            )
        presentation_key = entry.presentation_key
        current_name = current_step.get("name")
        if isinstance(current_name, str) and current_name and current_name != presentation_key:
            raise ResumeStateIntegrityError(
                "Persisted current_step.name does not match the projection entry for current_step.step_id.",
                context={
                    "step_id": step_id,
                    "field": "name",
                    "expected": presentation_key,
                    "actual": current_name,
                },
            )
        current_index = current_step.get("index")
        if isinstance(current_index, int) and current_index != execution_index:
            raise ResumeStateIntegrityError(
                "Persisted current_step.index does not match the projection entry for current_step.step_id.",
                context={
                    "step_id": step_id,
                    "field": "index",
                    "expected": execution_index,
                    "actual": current_index,
                },
            )
        return _ProjectedCurrentStep(
            node_id=entry.node_id,
            presentation_key=presentation_key,
            execution_index=execution_index,
        )

    def _resolve_provider_session_step(
        self,
        current_step: Dict[str, Any],
        steps: List[Dict[str, Any]],
        projection: Optional[WorkflowStateProjection],
    ) -> Optional[Dict[str, Any]]:
        if projection is not None:
            step_id = current_step.get("step_id")
            if isinstance(step_id, str) and step_id:
                projected_index = projection.execution_index_for_step_id(step_id)
                if isinstance(projected_index, int) and 0 <= projected_index < len(steps):
                    candidate = steps[projected_index]
                    if isinstance(candidate, dict):
                        return candidate
        current_index = current_step.get("index")
        if isinstance(current_index, int) and 0 <= current_index < len(steps):
            candidate = steps[current_index]
            if isinstance(candidate, dict):
                return candidate
        step_name = current_step.get("name")
        if isinstance(step_name, str) and step_name:
            for candidate in steps:
                if isinstance(candidate, dict) and candidate.get("name") == step_name:
                    return candidate
        return None

    def _projection_integrity_error(
        self,
        current_step: Dict[str, Any],
        exc: ResumeStateIntegrityError,
    ) -> Dict[str, Any]:
        return {
            "kind": "integrity_error",
            "message": str(exc),
            "step_name": current_step.get("name"),
            "step_id": current_step.get("step_id"),
            "visit_count": current_step.get("visit_count"),
            "context": dict(exc.context),
        }

    def detect_interrupted_provider_session_visit(
        self,
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect whether resume must quarantine an interrupted provider-session visit."""
        error = state.get("error")
        if isinstance(error, dict) and error.get("type") == self.QUARANTINE_ERROR_TYPE:
            return {"kind": "existing_quarantine", "error": error}

        current_step = state.get("current_step")
        if not isinstance(current_step, dict) or current_step.get("status") != "running":
            return None

        step_name = current_step.get("name")
        if not isinstance(step_name, str) or not step_name:
            return None

        try:
            step = self._resolve_provider_session_step(current_step, steps, projection)
            if isinstance(step, dict) and isinstance(step.get("provider_session"), dict):
                self._projected_current_step(current_step, projection)
        except ResumeStateIntegrityError as exc:
            return self._projection_integrity_error(current_step, exc)
        if not isinstance(step, dict):
            return None

        provider_session = step.get("provider_session")
        if not isinstance(provider_session, dict):
            return None

        step_id = current_step.get("step_id")
        visit_count = current_step.get("visit_count")
        if not isinstance(step_id, str) or not step_id:
            return {
                "kind": "integrity_error",
                "message": "Interrupted provider-session visit is missing current_step.step_id",
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }
        if not isinstance(visit_count, int):
            return {
                "kind": "integrity_error",
                "message": "Interrupted provider-session visit is missing an integer current_step.visit_count",
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }

        steps_state = state.get("steps", {})
        step_result = steps_state.get(step_name) if isinstance(steps_state, dict) else None
        if (
            isinstance(step_result, dict)
            and step_result.get("step_id") == step_id
            and step_result.get("visit_count") == visit_count
            and self.entry_is_terminal(step_result)
        ):
            return None

        return {
            "kind": "quarantine",
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": visit_count,
            "provider": step.get("provider"),
            "mode": provider_session.get("mode"),
        }

    def for_each_has_pending_work(self, state: Dict[str, Any], step_name: str) -> bool:
        """Return True when persisted loop bookkeeping shows unfinished iterations."""
        for_each_state = state.get("for_each", {})
        if not isinstance(for_each_state, dict):
            return False

        progress = for_each_state.get(step_name)
        if not isinstance(progress, dict):
            return False

        current_index = progress.get("current_index")
        if isinstance(current_index, int):
            return True

        items = progress.get("items")
        if not isinstance(items, list):
            return False

        completed_indices = {
            index
            for index in progress.get("completed_indices", [])
            if isinstance(index, int) and 0 <= index < len(items)
        }
        if len(completed_indices) < len(items):
            return True

        steps_state = state.get("steps", {})
        if isinstance(steps_state, dict):
            loop_results = steps_state.get(step_name)
            if isinstance(loop_results, list) and len(loop_results) < len(items):
                return True

        return False

    def repeat_until_has_pending_work(self, state: Dict[str, Any], step_name: str) -> bool:
        """Return True when persisted repeat_until bookkeeping shows unfinished iterations."""
        repeat_until_state = state.get("repeat_until", {})
        if not isinstance(repeat_until_state, dict):
            return False

        progress = repeat_until_state.get(step_name)
        if not isinstance(progress, dict):
            return False

        current_iteration = progress.get("current_iteration")
        if isinstance(current_iteration, int):
            return True

        steps_state = state.get("steps", {})
        step_result = steps_state.get(step_name) if isinstance(steps_state, dict) else None
        return isinstance(step_result, dict) and not self.entry_is_terminal(step_result)
