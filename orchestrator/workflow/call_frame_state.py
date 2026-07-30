"""Nested call-frame state persistence for imported workflows.

_CallFrameStateManager mirrors the StateManager subset used by nested workflow
execution. Its sole consumer is calls.py. This module was extracted from
executor.py and must not import executor.py so dependencies continue to point
from the executor toward this leaf module.
"""

from datetime import datetime, timezone
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from ..state import (
    ForEachState,
    RunState,
    StateManager,
    StepResult,
    _begin_eligible_pure_visit_state,
    _require_interrupted_eligible_pure_visit,
    _settle_eligible_pure_failure_state,
    _settle_eligible_pure_success_state,
)
from .executable_ir import ManagedJobsConfig, ManagedJobsRoutes
from .executor_runtime import ParentCallStateManager
from .loaded_bundle import (
    workflow_context,
    workflow_output_contracts,
    workflow_provenance,
)
from .resume_projection_integrity import ResumeScopePath


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
        resume_scope_path: Optional[ResumeScopePath] = None,
        result_persistence_profile: Optional[str] = None,
    ) -> None:
        from .pure_result_replay import DERIVED_PURE_REPLAY_PROFILE

        if (
            result_persistence_profile is not None
            and result_persistence_profile != DERIVED_PURE_REPLAY_PROFILE
        ):
            raise ValueError("result persistence profile is unsupported")
        existing_state: Optional[Mapping[str, Any]] = None
        if existing_frame is not None:
            if not isinstance(existing_frame, Mapping):
                raise ValueError(
                    "existing call-frame state container is invalid"
                )
            candidate_existing_state = existing_frame.get("state")
            if not isinstance(candidate_existing_state, Mapping):
                raise ValueError(
                    "existing call-frame state is missing or invalid"
                )
            existing_state = candidate_existing_state
        self.parent_manager = parent_manager
        self.workspace = parent_manager.workspace
        self.workflow = workflow
        self.frame_id = frame_id
        self.call_step_name = call_step_name
        self.call_step_id = call_step_id
        self.import_alias = import_alias
        self.resume_scope_path = resume_scope_path
        self.run_id = parent_manager.run_id
        frame_root_name = _path_safe_frame_scope_token(frame_id)
        self.run_root = parent_manager.run_root / "call_frames" / frame_root_name
        self.logs_dir = self.run_root / "logs"
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

        if existing_state is not None:
            self.state = RunState.from_dict(dict(existing_state))
            if (
                result_persistence_profile is not None
                and self.state.result_persistence_profile
                != result_persistence_profile
            ):
                raise ValueError(
                    "existing call-frame result persistence profile "
                    "cannot be changed"
                )
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
                result_persistence_profile=result_persistence_profile,
                run_root=str(self.run_root),
                context=dict(workflow_context(workflow)),
                bound_inputs=dict(bound_inputs),
                observability=observability,
            )
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
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

    def allocate_provider_attempt(
        self,
        scope: Any,
        *,
        prompt_fragment_identity_schema_version: str | None = None,
    ) -> int:
        """Delegate one attempt allocation through the aggregate root owner."""

        from .provider_attempts import resolve_aggregate_run_owner

        owner = resolve_aggregate_run_owner(self)
        return owner.root_manager.allocate_provider_attempt(
            scope,
            prompt_fragment_identity_schema_version=(
                prompt_fragment_identity_schema_version
            ),
            _origin_manager=self,
        )

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

    def _refresh_state_chain_from_root(self) -> None:
        """Refresh every live call-frame manager after one root-owned commit."""

        chain: list[_CallFrameStateManager] = []
        cursor: Any = self
        while isinstance(cursor, _CallFrameStateManager):
            chain.append(cursor)
            cursor = cursor.parent_manager
        if not isinstance(cursor, StateManager) or cursor.state is None:
            raise RuntimeError("call-frame aggregate root is unavailable")
        current = cursor.state
        for child in reversed(chain):
            frame = current.call_frames.get(child.frame_id)
            if not isinstance(frame, dict) or not isinstance(
                frame.get("state"),
                dict,
            ):
                raise RuntimeError("committed call-frame state is unavailable")
            child.state = RunState.from_dict(deepcopy(frame["state"]))
            current = child.state

    def _finalize_with_dataflow(
        self,
        *,
        result_key: str,
        result: StepResult,
        clear_current_step: bool,
        artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]],
        artifact_consumes: Optional[Dict[str, Dict[str, int]]],
        private_artifact_versions: Optional[
            Dict[str, List[Dict[str, Any]]]
        ],
        private_artifact_consumes: Optional[Dict[str, Dict[str, int]]],
        expected_step_id: Optional[str],
        expected_visit_count: Optional[int],
        expected_step_name: Optional[str],
        expected_step_type: Optional[str],
        expected_step_status: Optional[str],
        commit_guard: Optional[Callable[[], bool]],
    ) -> None:
        from .provider_attempts import resolve_aggregate_run_owner

        owner = resolve_aggregate_run_owner(self)

        def authoritative_guard(leaf: RunState) -> bool:
            current = leaf.current_step
            matches = (
                (commit_guard is None or commit_guard() is True)
                and isinstance(current, dict)
            )
            if matches and expected_step_id is not None:
                matches = current.get("step_id") == expected_step_id
            if matches and expected_visit_count is not None:
                matches = (
                    current.get("visit_count") == expected_visit_count
                )
            if matches and expected_step_name is not None:
                matches = current.get("name") == expected_step_name
            if matches and expected_step_type is not None:
                matches = current.get("type") == expected_step_type
            if matches and expected_step_status is not None:
                matches = current.get("status") == expected_step_status
            return bool(matches)

        def mutation(leaf: RunState) -> None:
            leaf.steps[result_key] = result
            if artifact_versions is not None:
                leaf.artifact_versions = artifact_versions
            if artifact_consumes is not None:
                leaf.artifact_consumes = artifact_consumes
            if private_artifact_versions is not None:
                leaf.private_artifact_versions = private_artifact_versions
            if private_artifact_consumes is not None:
                leaf.private_artifact_consumes = private_artifact_consumes
            if clear_current_step:
                leaf.current_step = None

        owner.root_manager._mutate_scoped_state(
            owner.resume_scope_path,
            commit_guard=authoritative_guard,
            mutation=mutation,
        )
        self._refresh_state_chain_from_root()

    def finalize_step_with_dataflow(
        self,
        step_name: str,
        result: StepResult,
        *,
        artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        artifact_consumes: Optional[Dict[str, Dict[str, int]]] = None,
        private_artifact_versions: Optional[
            Dict[str, List[Dict[str, Any]]]
        ] = None,
        private_artifact_consumes: Optional[
            Dict[str, Dict[str, int]]
        ] = None,
        expected_step_id: Optional[str] = None,
        expected_visit_count: Optional[int] = None,
        expected_step_name: Optional[str] = None,
        expected_step_type: Optional[str] = None,
        expected_step_status: Optional[str] = None,
        commit_guard: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._finalize_with_dataflow(
            result_key=step_name,
            result=result,
            clear_current_step=True,
            artifact_versions=artifact_versions,
            artifact_consumes=artifact_consumes,
            private_artifact_versions=private_artifact_versions,
            private_artifact_consumes=private_artifact_consumes,
            expected_step_id=expected_step_id,
            expected_visit_count=expected_visit_count,
            expected_step_name=expected_step_name,
            expected_step_type=expected_step_type,
            expected_step_status=expected_step_status,
            commit_guard=commit_guard,
        )

    def finalize_loop_step_with_dataflow(
        self,
        loop_name: str,
        index: int,
        step_name: str,
        result: StepResult,
        *,
        artifact_versions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        artifact_consumes: Optional[Dict[str, Dict[str, int]]] = None,
        private_artifact_versions: Optional[
            Dict[str, List[Dict[str, Any]]]
        ] = None,
        private_artifact_consumes: Optional[
            Dict[str, Dict[str, int]]
        ] = None,
        expected_enclosing_step_id: Optional[str] = None,
        expected_visit_count: Optional[int] = None,
        expected_enclosing_step_name: Optional[str] = None,
        expected_enclosing_step_type: Optional[str] = None,
        expected_enclosing_step_status: Optional[str] = None,
        commit_guard: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._finalize_with_dataflow(
            result_key=f"{loop_name}[{index}].{step_name}",
            result=result,
            clear_current_step=False,
            artifact_versions=artifact_versions,
            artifact_consumes=artifact_consumes,
            private_artifact_versions=private_artifact_versions,
            private_artifact_consumes=private_artifact_consumes,
            expected_step_id=expected_enclosing_step_id,
            expected_visit_count=expected_visit_count,
            expected_step_name=expected_enclosing_step_name,
            expected_step_type=expected_enclosing_step_type,
            expected_step_status=expected_enclosing_step_status,
            commit_guard=commit_guard,
        )

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

    def update_bound_inputs(self, bound_inputs: Dict[str, Any]) -> None:
        self.state.bound_inputs = dict(bound_inputs)
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

    def _mutate_eligible_pure_state(
        self,
        mutation: Callable[[RunState], Any],
    ) -> Any:
        """Commit one eligible-pure frame mutation through the aggregate root."""

        from .provider_attempts import resolve_aggregate_run_owner

        owner = resolve_aggregate_run_owner(self)
        result: list[Any] = []

        def apply(leaf: RunState) -> None:
            result.append(mutation(leaf))

        try:
            owner.root_manager._mutate_scoped_state(
                owner.resume_scope_path,
                commit_guard=lambda _leaf: True,
                mutation=apply,
            )
        finally:
            self._refresh_state_chain_from_root()
        return result[0] if result else None

    def begin_eligible_pure_visit(
        self,
        *,
        step_name: str,
        step_index: int,
        step_id: str,
    ) -> int:
        """Atomically publish one nested eligible-pure visit and cursor."""

        result = self._mutate_eligible_pure_state(
            lambda state: _begin_eligible_pure_visit_state(
                state,
                step_name=step_name,
                step_index=step_index,
                step_id=step_id,
            )
        )
        if isinstance(result, bool) or not isinstance(result, int):
            raise RuntimeError("eligible pure visit allocation failed")
        return result

    def reuse_interrupted_eligible_pure_visit(
        self,
        witness: Any,
    ) -> int:
        """Validate and reuse one nested interrupted visit read-only."""

        from .provider_attempts import resolve_aggregate_run_owner

        owner = resolve_aggregate_run_owner(self)
        with owner.root_manager._state_mutation():
            self._refresh_state_chain_from_root()
            _require_interrupted_eligible_pure_visit(self.state, witness)
            return witness.visit_count

    def settle_eligible_pure_success(
        self,
        witness: Any,
    ) -> Dict[str, Any]:
        """Atomically replace a nested pure cursor with its exact shell."""

        result = self._mutate_eligible_pure_state(
            lambda state: _settle_eligible_pure_success_state(
                state,
                witness,
            )
        )
        if not isinstance(result, dict):
            raise RuntimeError("eligible pure success settlement failed")
        return result

    def settle_eligible_pure_failure(
        self,
        witness: Any,
        result: StepResult,
    ) -> None:
        """Atomically replace a nested pure cursor with its full failure."""

        self._mutate_eligible_pure_state(
            lambda state: _settle_eligible_pure_failure_state(
                state,
                witness,
                result,
            )
        )

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

    def recover_interrupted_provider_visit(
        self,
        *,
        expected_step_name: str,
        expected_step_id: str,
        expected_visit_count: int,
        expected_status: str = "running",
        legacy_error_type: Optional[str] = None,
    ) -> None:
        """Atomically clear one exact nested interrupted cursor at the root."""

        from .provider_attempts import resolve_aggregate_run_owner

        owner = resolve_aggregate_run_owner(self)
        expected = {
            "name": expected_step_name,
            "step_id": expected_step_id,
            "visit_count": expected_visit_count,
            "status": expected_status,
        }

        def exact_cursor(leaf: RunState) -> bool:
            current = leaf.current_step
            current_matches = isinstance(current, dict) and all(
                current.get(field) == value
                for field, value in expected.items()
            )
            error = leaf.error
            error_context = (
                error.get("context") if isinstance(error, dict) else None
            )
            legacy_matches = (
                current is None
                and isinstance(legacy_error_type, str)
                and isinstance(error, dict)
                and error.get("type") == legacy_error_type
                and isinstance(error_context, dict)
                and error_context.get("step_name") == expected_step_name
                and error_context.get("step_id") == expected_step_id
                and error_context.get("visit_count") == expected_visit_count
            )
            recorded_visit_count = leaf.step_visits.get(expected_step_name)
            return (
                (current_matches or legacy_matches)
                and not isinstance(recorded_visit_count, bool)
                and isinstance(recorded_visit_count, int)
                and recorded_visit_count == expected_visit_count
            )

        def recover(leaf: RunState) -> None:
            leaf.current_step = None
            leaf.error = None
            leaf.status = "running"

        owner.root_manager._mutate_scoped_state(
            owner.resume_scope_path,
            commit_guard=exact_cursor,
            mutation=recover,
        )
        self._refresh_state_chain_from_root()

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
