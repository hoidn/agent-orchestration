"""Nested call-frame state persistence for imported workflows.

_CallFrameStateManager mirrors the StateManager subset used by nested workflow
execution. Its sole consumer is calls.py. This module was extracted from
executor.py and must not import executor.py so dependencies continue to point
from the executor toward this leaf module.
"""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..state import ForEachState, RunState, StateManager, StepResult
from .executable_ir import ManagedJobsConfig, ManagedJobsRoutes
from .executor_runtime import ParentCallStateManager
from .loaded_bundle import (
    workflow_context,
    workflow_output_contracts,
    workflow_provenance,
)


def _path_safe_frame_scope_token(frame_id: str) -> str:
    """Return one bounded path-safe token for nested call-frame storage."""

    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    normalized = "".join(char if char in allowed else "_" for char in frame_id).strip("._-")
    while ".." in normalized:
        normalized = normalized.replace("..", "._")
    if not normalized:
        normalized = "call_frame"
    digest = sha256(frame_id.encode("utf-8")).hexdigest()[:12]
    max_prefix_length = 96 - len(digest) - 1
    if len(normalized) > max_prefix_length:
        normalized = normalized[:max_prefix_length].rstrip("._-") or "call_frame"
    return f"{normalized}_{digest}"


def _display_workflow_path(workspace: Path, workflow_path: Any) -> str:
    """Render a workflow path relative to the workspace when possible."""
    path = Path(str(workflow_path)).resolve()
    try:
        return str(path.relative_to(workspace.resolve()))
    except ValueError:
        return str(path)


def _thaw_workflow_value(value: Any) -> Any:
    """Convert frozen AST/IR payloads back into plain JSON-like runtime values."""
    if isinstance(value, Mapping):
        return {str(key): _thaw_workflow_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_workflow_value(item) for item in value]
    if isinstance(value, list):
        return [_thaw_workflow_value(item) for item in value]
    return value


def _managed_jobs_config_from_step(step: Mapping[str, Any]) -> Optional[ManagedJobsConfig]:
    node = step.get("managed_jobs")
    if not isinstance(node, Mapping):
        return None
    routes = node.get("on")
    if not isinstance(routes, Mapping):
        return None
    try:
        return ManagedJobsConfig(
            policy=str(node["policy"]),
            watch_roots=tuple(str(item) for item in node["watch_roots"]),
            backend=str(node["backend"]),
            poll_budget_sec=int(node["poll_budget_sec"]),
            on=ManagedJobsRoutes(
                complete=str(routes["complete"]),
                failed=str(routes["failed"]),
                invalid=str(routes["invalid"]),
                outstanding=str(routes["outstanding"]),
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


class _CallFrameStateManager:
    """Persist a nested workflow state snapshot under the parent run state."""

    def __init__(
        self,
        *,
        parent_manager: ParentCallStateManager,
        workflow: Any,
        frame_id: str,
        call_step_name: str,
        call_step_id: str,
        import_alias: str,
        bound_inputs: Dict[str, Any],
        existing_frame: Optional[Dict[str, Any]] = None,
        observability: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.parent_manager = parent_manager
        self.workspace = parent_manager.workspace
        self.workflow = workflow
        self.frame_id = frame_id
        self.call_step_name = call_step_name
        self.call_step_id = call_step_id
        self.import_alias = import_alias
        self.run_id = parent_manager.run_id
        frame_root_name = _path_safe_frame_scope_token(frame_id)
        self.run_root = parent_manager.run_root / "call_frames" / frame_root_name
        self.logs_dir = self.run_root / "logs"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        recorded_validation = (
            existing_frame.get("bound_input_resume_validation")
            if isinstance(existing_frame, dict)
            else None
        )
        if isinstance(recorded_validation, dict):
            self.bound_input_resume_validation = dict(recorded_validation)
        else:
            self.bound_input_resume_validation = {
                "status": "fresh",
                "diagnostics": [],
            }

        existing_state = existing_frame.get("state") if isinstance(existing_frame, dict) else None
        if isinstance(existing_state, dict):
            self.state = RunState.from_dict(existing_state)
        else:
            provenance = workflow_provenance(workflow)
            workflow_path = str(provenance.workflow_path) if provenance is not None else ""
            workflow_checksum = ""
            if isinstance(workflow_path, str) and workflow_path:
                workflow_checksum = parent_manager.calculate_checksum(Path(workflow_path))
            now = datetime.now(timezone.utc).isoformat()
            self.state = RunState(
                schema_version=StateManager.SCHEMA_VERSION,
                run_id=self.run_id,
                workflow_file=_display_workflow_path(self.workspace, workflow_path) if workflow_path else "",
                workflow_checksum=workflow_checksum,
                started_at=now,
                updated_at=now,
                status="running",
                run_root=str(self.run_root),
                context=dict(workflow_context(workflow)),
                bound_inputs=dict(bound_inputs),
                observability=observability,
            )
        self._persist()

    def _snapshot(self) -> Dict[str, Any]:
        """Build the persisted call-frame metadata snapshot."""
        finalization = self.state.finalization if isinstance(self.state.finalization, dict) else {}
        body_status = finalization.get("body_status")
        finalization_status = finalization.get("status", "not_configured") if finalization else "not_configured"
        has_outputs = bool(workflow_output_contracts(self.workflow))
        if finalization:
            export_status = finalization.get(
                "workflow_outputs_status",
                "pending" if has_outputs else "not_configured",
            )
        elif has_outputs:
            export_status = "completed" if self.state.status == "completed" else "suppressed"
        else:
            export_status = "not_configured"
        if body_status is None and self.state.status in {"completed", "failed"}:
            body_status = self.state.status

        return {
            "call_frame_id": self.frame_id,
            "call_step_name": self.call_step_name,
            "call_step_id": self.call_step_id,
            "import_alias": self.import_alias,
            "workflow_file": self.state.workflow_file,
            "status": self.state.status,
            "body_status": body_status,
            "finalization_status": finalization_status,
            "export_status": export_status,
            "bound_inputs": dict(self.state.bound_inputs),
            "bound_input_resume_validation": dict(self.bound_input_resume_validation),
            "current_step": self.state.current_step,
            "state": self.state.to_dict(),
        }

    def _persist(self) -> None:
        self.parent_manager.update_call_frame(self.frame_id, self._snapshot())

    def _write_state(self) -> None:
        """Persist the nested call-frame state through the parent manager."""
        self._persist()

    def update_bound_input_resume_validation(
        self,
        *,
        status: str,
        diagnostics: Optional[list[str]] = None,
    ) -> None:
        self.bound_input_resume_validation = {
            "status": status,
            "diagnostics": list(diagnostics or []),
        }
        self._persist()

    def load(self) -> RunState:
        return self.state

    def calculate_checksum(self, workflow_path: Path) -> str:
        """Delegate checksum calculation so nested call frames can nest again."""
        return self.parent_manager.calculate_checksum(workflow_path)

    def read_runtime_sidecar_json(self, path: Path | str) -> Optional[Dict[str, Any]]:
        return self.parent_manager.read_runtime_sidecar_json(path)

    def write_runtime_sidecar_json(self, path: Path | str, payload: Dict[str, Any]) -> None:
        self.parent_manager.write_runtime_sidecar_json(path, payload)

    def workflow_lisp_checkpoint_shadow_report_path(self) -> Path:
        return self.parent_manager.workflow_lisp_checkpoint_shadow_report_path()

    def backup_state(self, step_name: str) -> None:
        del step_name

    def update_step(self, step_name: str, result: StepResult) -> None:
        self.state.steps[step_name] = result
        if (
            self.state.current_step is not None
            and self.state.current_step.get("name") == step_name
        ):
            self.state.current_step = None
        self._persist()

    def update_loop_step(self, loop_name: str, index: int, step_name: str, result: StepResult) -> None:
        self.state.steps[f"{loop_name}[{index}].{step_name}"] = result
        self._persist()

    def clear_loop_step(self, loop_name: str, index: int, step_name: str) -> None:
        self.state.steps.pop(f"{loop_name}[{index}].{step_name}", None)
        self._persist()

    def update_loop_results(self, loop_name: str, loop_results: List[Dict[str, Any]]) -> None:
        self.state.steps[loop_name] = loop_results
        self._persist()

    def update_for_each(self, loop_name: str, state: ForEachState) -> None:
        self.state.for_each[loop_name] = state
        self._persist()

    def update_repeat_until_state(
        self,
        loop_name: str,
        progress: Dict[str, Any],
        frame_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.state.repeat_until[loop_name] = progress
        if frame_result is not None:
            self.state.steps[loop_name] = frame_result
        self._persist()

    def update_dataflow_state(
        self,
        artifact_versions: Dict[str, List[Dict[str, Any]]],
        artifact_consumes: Dict[str, Dict[str, int]],
        private_artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        private_artifact_consumes: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> None:
        self.state.artifact_versions = artifact_versions
        self.state.artifact_consumes = artifact_consumes
        if private_artifact_versions is not None:
            self.state.private_artifact_versions = private_artifact_versions
        if private_artifact_consumes is not None:
            self.state.private_artifact_consumes = private_artifact_consumes
        self._persist()

    def update_call_frame(self, frame_id: str, frame_state: Dict[str, Any]) -> None:
        self.state.call_frames[frame_id] = frame_state
        self._persist()

    def update_workflow_outputs(self, workflow_outputs: Dict[str, Any]) -> None:
        self.state.workflow_outputs = workflow_outputs
        self._persist()

    def update_finalization_state(self, finalization: Dict[str, Any]) -> None:
        self.state.finalization = finalization
        self._persist()

    def update_run_error(self, error: Optional[Dict[str, Any]]) -> None:
        self.state.error = error
        self._persist()

    def update_control_flow_counters(
        self,
        transition_count: int,
        step_visits: Dict[str, int],
    ) -> None:
        self.state.transition_count = transition_count
        self.state.step_visits = step_visits
        self._persist()

    def update_status(self, status: str) -> None:
        self.state.status = status
        self._persist()

    def fail_run(
        self,
        error: Dict[str, Any],
        *,
        clear_current_step: bool = False,
        expected_step_id: Optional[str] = None,
        expected_visit_count: Optional[int] = None,
    ) -> None:
        self.state.status = "failed"
        self.state.error = error
        if clear_current_step and isinstance(self.state.current_step, dict):
            current_step = self.state.current_step
            if expected_step_id is not None and current_step.get("step_id") != expected_step_id:
                self._persist()
                return
            if (
                expected_visit_count is not None
                and current_step.get("visit_count") != expected_visit_count
            ):
                self._persist()
                return
            self.state.current_step = None
        elif isinstance(self.state.current_step, dict):
            self.state.current_step["status"] = "failed"
            self.state.current_step["failed_at"] = datetime.now(timezone.utc).isoformat()
        self._persist()

    def start_step(
        self,
        step_name: str,
        step_index: int,
        step_type: str,
        step_id: Optional[str] = None,
        visit_count: Optional[int] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.state.current_step = {
            "name": step_name,
            "index": step_index,
            "type": step_type,
            "status": "running",
            "started_at": now,
            "last_heartbeat_at": now,
        }
        if step_id:
            self.state.current_step["step_id"] = step_id
        if visit_count is not None:
            self.state.current_step["visit_count"] = visit_count
        self._persist()

    def heartbeat_step(self, step_name: Optional[str] = None) -> None:
        if self.state.current_step is None:
            return
        if step_name and self.state.current_step.get("name") != step_name:
            return
        self.state.current_step["last_heartbeat_at"] = datetime.now(timezone.utc).isoformat()
        self._persist()

    def clear_current_step(
        self,
        step_name: Optional[str] = None,
        *,
        preserve_managed_recovery: bool = False,
    ) -> None:
        if self.state.current_step is None:
            return
        if step_name and self.state.current_step.get("name") != step_name:
            return
        managed_jobs = self.state.current_step.get("managed_jobs")
        if (
            preserve_managed_recovery
            and isinstance(managed_jobs, dict)
            and managed_jobs.get("phase") == "recovery"
        ):
            return
        self.state.current_step = None
        self._persist()
