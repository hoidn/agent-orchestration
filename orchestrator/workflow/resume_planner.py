"""Resume restart planning helpers for workflow execution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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
    ) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart."""
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

    def detect_interrupted_provider_session_visit(
        self,
        state: Dict[str, Any],
        steps: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Detect whether resume must quarantine an interrupted provider-session visit."""
        error = state.get("error")
        if isinstance(error, dict) and error.get("type") == self.QUARANTINE_ERROR_TYPE:
            return {"kind": "existing_quarantine", "error": error}

        current_step = state.get("current_step")
        if not isinstance(current_step, dict) or current_step.get("status") != "running":
            return None

        current_index = current_step.get("index")
        step_name = current_step.get("name")
        if not isinstance(step_name, str) or not step_name:
            return None

        step: Optional[Dict[str, Any]] = None
        if isinstance(current_index, int) and 0 <= current_index < len(steps):
            candidate = steps[current_index]
            if isinstance(candidate, dict):
                step = candidate
        if step is None:
            for candidate in steps:
                if isinstance(candidate, dict) and candidate.get("name") == step_name:
                    step = candidate
                    break
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
