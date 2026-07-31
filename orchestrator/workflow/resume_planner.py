"""Resume restart planning helpers for workflow execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from .._common.status import is_step_settled
from .state_projection import CompatibilityNodeProjection, WorkflowStateProjection


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

    @staticmethod
    def entry_status_is_terminal(status: object) -> bool:
        """Return True for the resume-owned completed/skipped scalar rule."""
        return status in ("completed", "skipped")

    def entry_is_terminal(self, entry: Any) -> bool:
        """Return True when persisted step state is fully completed/skipped."""
        if isinstance(entry, dict):
            status = entry.get("status")
            if isinstance(status, str):
                return self.entry_status_is_terminal(status)
            if not entry:
                return False
            return all(self.entry_is_terminal(value) for value in entry.values())
        if isinstance(entry, list):
            return all(self.entry_is_terminal(value) for value in entry)
        return False

    def determine_restart_index(
        self,
        state: Dict[str, Any],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

        restart_node_id = self.determine_restart_node_id(state, projection=projection)
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

    def determine_restart_node_id(
        self,
        state: Dict[str, Any],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[str]:
        """Determine the top-level executable node id where resumed execution should restart."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

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
            if self._provider_visit_gap_has_pending_work(
                state,
                entry,
                step_result,
            ):
                return node_id
            if not self.entry_is_terminal(step_result):
                return node_id

        return None

    def _provider_visit_gap_has_pending_work(
        self,
        state: Dict[str, Any],
        entry: CompatibilityNodeProjection,
        step_result: Any,
    ) -> bool:
        """Keep a cleared interrupted provider visit eligible for restart."""
        if entry.step_definition.report_kind not in {
            "provider",
            "provider_supervision",
            "provider_peer_group",
        }:
            return False
        step_visits = state.get("step_visits")
        persisted_visit_count = (
            step_visits.get(entry.presentation_key)
            if isinstance(step_visits, dict)
            else None
        )
        if (
            isinstance(persisted_visit_count, bool)
            or not isinstance(persisted_visit_count, int)
            or persisted_visit_count <= 0
        ):
            return False
        if step_result is None:
            return True
        if not self.entry_is_terminal(step_result):
            return False
        result_visit_count = (
            step_result.get("visit_count")
            if isinstance(step_result, dict)
            else None
        )
        if (
            isinstance(result_visit_count, bool)
            or not isinstance(result_visit_count, int)
            or result_visit_count <= 0
        ):
            return False
        return persisted_visit_count > result_visit_count

    def determine_lexical_restore_decision(
        self,
        state: Dict[str, Any],
        *,
        runtime_plan: Any,
        state_manager: Any,
        executable_workflow: Any | None = None,
        loaded_workflow: Any | None = None,
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Any:
        """Return one additive lexical-restore decision for the current resume point."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

        restart_node_id = self.determine_restart_node_id(state, projection=projection)
        if not isinstance(restart_node_id, str):
            return None

        from orchestrator.workflow_lisp.lexical_checkpoint_restore import select_restore_candidate

        return select_restore_candidate(
            state_manager=state_manager,
            runtime_plan=runtime_plan,
            state=state,
            restart_node_id=restart_node_id,
            executable_workflow=executable_workflow,
            loaded_workflow=loaded_workflow,
        )

    def determine_default_resume_decision(
        self,
        state: Dict[str, Any],
        *,
        restart_node_id: str | None,
        runtime_plan: Any,
        state_manager: Any,
        executable_workflow: Any | None = None,
        loaded_workflow: Any | None = None,
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Dict[str, Any]:
        """Return one R6 default-resume decision for the current resume point."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

        from orchestrator.workflow_lisp.lexical_checkpoint_default_resume import (
            determine_runtime_default_resume_decision,
        )

        decision = determine_runtime_default_resume_decision(
            state=state,
            runtime_plan=runtime_plan,
            restart_node_id=restart_node_id,
            state_manager=state_manager,
            loaded_workflow=loaded_workflow,
            executable_workflow=executable_workflow,
        )
        entry = (
            projection.entries_by_node_id.get(restart_node_id)
            if isinstance(restart_node_id, str)
            else None
        )
        steps = state.get("steps")
        step_result = (
            steps.get(entry.presentation_key)
            if entry is not None and isinstance(steps, dict)
            else None
        )
        diagnostics = tuple(decision.get("diagnostics", ()) or ())
        diagnostic_codes = {
            item.get("code") if isinstance(item, dict) else item
            for item in diagnostics
        }
        if (
            entry is not None
            and self._provider_visit_gap_has_pending_work(
                state,
                entry,
                step_result,
            )
            and decision.get("mode") == "FAIL_CLOSED"
            and diagnostic_codes
            == {"lexical_default_resume_prior_boundary_missing"}
        ):
            decision = dict(decision)
            decision.update(
                {
                    "mode": "LEXICAL_CHECKPOINT_DEFAULT",
                    "restore_decision": None,
                    "restore_candidate": None,
                    "checkpoint_id": None,
                    "record_id": None,
                    "source_map_origin_key": None,
                    "selection_reason": (
                        "validated_interrupted_provider_visit"
                    ),
                    "compatibility_reason": (
                        "provider_interrupted_rerun"
                    ),
                    "diagnostics": [],
                }
            )
        return decision

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

    def _interrupted_provider_result_relation(
        self,
        state: Dict[str, Any],
        *,
        step_name: str,
        step_id: str,
        visit_count: int,
    ) -> str:
        """Classify the latest same-name result against one live visit."""

        steps_state = state.get("steps", {})
        step_result = (
            steps_state.get(step_name)
            if isinstance(steps_state, dict)
            else None
        )
        if step_result is None:
            return "absent"
        if (
            not isinstance(step_result, dict)
            or not is_step_settled(step_result.get("status"), raise_on_unhashable=True)
            or step_result.get("step_id") != step_id
        ):
            return "integrity_error"
        result_visit_count = step_result.get("visit_count")
        if (
            isinstance(result_visit_count, bool)
            or not isinstance(result_visit_count, int)
            or result_visit_count <= 0
            or result_visit_count > visit_count
        ):
            return "integrity_error"
        if result_visit_count == visit_count:
            return "exact_terminal"
        return "older_terminal"

    def detect_interrupted_provider_session_visit(
        self,
        state: Dict[str, Any],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect whether resume must rerun an interrupted provider-session visit."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

        current_step = state.get("current_step")
        if not isinstance(current_step, dict) or current_step.get("status") != "running":
            return None

        projected_current_step = None
        projection_entry = None
        step_id = current_step.get("step_id")
        if isinstance(step_id, str) and step_id:
            projection_entry = projection.entry_for_step_id(step_id)
        if projection_entry is None:
            current_index = current_step.get("index")
            current_status = current_step.get("status")
            if isinstance(current_index, int) and current_status == "running":
                node_id = projection.node_id_for_execution_index(current_index)
                if isinstance(node_id, str):
                    projection_entry = projection.entries_by_node_id.get(node_id)
        if projection_entry is None:
            return None

        step_definition = projection_entry.step_definition
        if not step_definition.provider_session_enabled:
            return None

        try:
            projected_current_step = self._projected_current_step(current_step, projection)
        except ResumeStateIntegrityError as exc:
            return self._projection_integrity_error(current_step, exc)

        step_name = (
            projected_current_step.presentation_key
            if projected_current_step is not None
            else projection_entry.presentation_key
        )
        provider = step_definition.provider
        mode = step_definition.provider_session_mode

        visit_count = current_step.get("visit_count")
        if not isinstance(step_name, str) or not step_name:
            return {
                "kind": "integrity_error",
                "message": "Interrupted provider-session visit is missing a resolvable step presentation key",
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }
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

        result_relation = self._interrupted_provider_result_relation(
            state,
            step_name=step_name,
            step_id=step_id,
            visit_count=visit_count,
        )
        if result_relation == "integrity_error":
            return {
                "kind": "integrity_error",
                "message": (
                    "Provider-session result identity is invalid for the "
                    "interrupted current visit."
                ),
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }
        if result_relation == "exact_terminal":
            return None

        return {
            "kind": "rerun_interrupted_visit",
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": visit_count,
            "provider": provider,
            "mode": mode,
        }

    def detect_interrupted_provider_supervision_visit(
        self,
        state: Dict[str, Any],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect an interrupted provider-supervision visit for a fresh rerun."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

        current_step = state.get("current_step")
        if (
            not isinstance(current_step, dict)
            or current_step.get("status") != "running"
        ):
            return None

        step_id = current_step.get("step_id")
        projection_entry = (
            projection.entry_for_step_id(step_id)
            if isinstance(step_id, str) and step_id
            else None
        )
        current_type = current_step.get("type")
        if projection_entry is None:
            if current_type != "provider_supervision":
                return None
            return {
                "kind": "integrity_error",
                "message": (
                    "Persisted provider-supervision current_step.step_id is "
                    "absent from the authoritative workflow projection."
                ),
                "step_name": current_step.get("name"),
                "step_id": step_id,
                "visit_count": current_step.get("visit_count"),
                "context": {
                    "step_id": step_id,
                    "field": "step_id",
                    "expected": "known provider-supervision projection entry",
                    "actual": step_id,
                },
            }
        projected_type = projection_entry.step_definition.report_kind
        current_is_supervision = current_type == "provider_supervision"
        projected_is_supervision = projected_type == "provider_supervision"
        if current_is_supervision != projected_is_supervision:
            return {
                "kind": "integrity_error",
                "message": (
                    "Persisted current_step.type does not match the "
                    "authoritative provider-supervision projection kind."
                ),
                "step_name": current_step.get("name"),
                "step_id": step_id,
                "visit_count": current_step.get("visit_count"),
                "context": {
                    "step_id": step_id,
                    "field": "type",
                    "expected": projected_type,
                    "actual": current_type,
                },
            }
        if not current_is_supervision:
            return None

        try:
            projected_current_step = self._projected_current_step(
                current_step,
                projection,
            )
        except ResumeStateIntegrityError as exc:
            return self._projection_integrity_error(current_step, exc)
        if projected_current_step is None:
            return None

        step_name = projected_current_step.presentation_key
        visit_count = current_step.get("visit_count")
        if (
            not isinstance(visit_count, int)
            or isinstance(visit_count, bool)
            or visit_count <= 0
        ):
            return {
                "kind": "integrity_error",
                "message": (
                    "Interrupted provider-supervision visit requires a "
                    "positive integer current_step.visit_count"
                ),
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }

        result_relation = self._interrupted_provider_result_relation(
            state,
            step_name=step_name,
            step_id=step_id,
            visit_count=visit_count,
        )
        if result_relation == "integrity_error":
            return {
                "kind": "integrity_error",
                "message": (
                    "Provider-supervision result identity is invalid for the "
                    "interrupted current visit."
                ),
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }
        if result_relation == "exact_terminal":
            return None

        return {
            "kind": "rerun_interrupted_visit",
            "step_name": step_name,
            "step_id": step_id,
            "node_id": projected_current_step.node_id,
            "visit_count": visit_count,
        }

    def detect_interrupted_provider_peer_group_visit(
        self,
        state: Dict[str, Any],
        projection: Optional[WorkflowStateProjection] = None,
    ) -> Optional[Dict[str, Any]]:
        """Detect an interrupted peer-group visit for a fresh whole-group rerun."""
        if not isinstance(projection, WorkflowStateProjection):
            raise TypeError("ResumePlanner requires a WorkflowStateProjection")

        current_step = state.get("current_step")
        if (
            not isinstance(current_step, dict)
            or current_step.get("status") != "running"
        ):
            return None

        step_id = current_step.get("step_id")
        projection_entry = (
            projection.entry_for_step_id(step_id)
            if isinstance(step_id, str) and step_id
            else None
        )
        current_type = current_step.get("type")
        if projection_entry is None:
            if current_type != "provider_peer_group":
                return None
            return {
                "kind": "integrity_error",
                "message": (
                    "Persisted provider-peer-group current_step.step_id is "
                    "absent from the authoritative workflow projection."
                ),
                "step_name": current_step.get("name"),
                "step_id": step_id,
                "visit_count": current_step.get("visit_count"),
                "context": {
                    "step_id": step_id,
                    "field": "step_id",
                    "expected": "known provider-peer-group projection entry",
                    "actual": step_id,
                },
            }

        projected_type = projection_entry.step_definition.report_kind
        current_is_peer_group = current_type == "provider_peer_group"
        projected_is_peer_group = projected_type == "provider_peer_group"
        if current_is_peer_group != projected_is_peer_group:
            return {
                "kind": "integrity_error",
                "message": (
                    "Persisted current_step.type does not match the "
                    "authoritative provider-peer-group projection kind."
                ),
                "step_name": current_step.get("name"),
                "step_id": step_id,
                "visit_count": current_step.get("visit_count"),
                "context": {
                    "step_id": step_id,
                    "field": "type",
                    "expected": projected_type,
                    "actual": current_type,
                },
            }
        if not current_is_peer_group:
            return None

        try:
            projected_current_step = self._projected_current_step(
                current_step,
                projection,
            )
        except ResumeStateIntegrityError as exc:
            return self._projection_integrity_error(current_step, exc)
        if projected_current_step is None:
            return None

        step_name = projected_current_step.presentation_key
        visit_count = current_step.get("visit_count")
        if (
            not isinstance(visit_count, int)
            or isinstance(visit_count, bool)
            or visit_count <= 0
        ):
            return {
                "kind": "integrity_error",
                "message": (
                    "Interrupted provider-peer-group visit requires a "
                    "positive integer current_step.visit_count"
                ),
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }

        result_relation = self._interrupted_provider_result_relation(
            state,
            step_name=step_name,
            step_id=step_id,
            visit_count=visit_count,
        )
        if result_relation == "integrity_error":
            return {
                "kind": "integrity_error",
                "message": (
                    "Provider peer-group result identity is invalid for the "
                    "interrupted current visit."
                ),
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
            }
        if result_relation == "exact_terminal":
            return None

        return {
            "kind": "rerun_interrupted_visit",
            "step_name": step_name,
            "step_id": step_id,
            "node_id": projected_current_step.node_id,
            "visit_count": visit_count,
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
