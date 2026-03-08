"""
Workflow executor with for-each loop support.
Implements AT-3, AT-13: Dynamic for-each execution with pointer resolution.
"""

import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state import ForEachState, RunState, StateManager, StepResult
from ..exec.step_executor import StepExecutor
from ..exec.retry import RetryPolicy
from ..providers.executor import ProviderExecutor
from ..providers.registry import ProviderRegistry
from ..deps.resolver import DependencyResolver
from ..deps.injector import DependencyInjector
from ..contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
    validate_expected_outputs,
    validate_output_bundle,
)
from ..contracts.prompt_contract import (
    render_consumed_artifacts_block,
    render_output_contract_block,
)
from .pointers import PointerResolver
from .conditions import ConditionEvaluator
from ..security.secrets import SecretsManager
from ..variables.substitution import VariableSubstitutor
from ..observability.summary import SummaryObserver
from .assets import AssetResolutionError, WorkflowAssetResolver
from .identity import iteration_step_id, runtime_step_id
from .predicates import PredicateEvaluationError, resolve_typed_operand
from .references import ReferenceResolutionError, ReferenceResolver
from .signatures import WorkflowSignatureError, resolve_workflow_outputs

logger = logging.getLogger(__name__)


def _display_workflow_path(workspace: Path, workflow_path: Any) -> str:
    """Render a workflow path relative to the workspace when possible."""
    path = Path(str(workflow_path)).resolve()
    try:
        return str(path.relative_to(workspace.resolve()))
    except ValueError:
        return str(path)


class _CallFrameStateManager:
    """Persist a nested workflow state snapshot under the parent run state."""

    def __init__(
        self,
        *,
        parent_manager: StateManager,
        workflow: Dict[str, Any],
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
        frame_root_name = frame_id.replace("/", "_").replace(":", "_")
        self.run_root = parent_manager.run_root / "call_frames" / frame_root_name
        self.logs_dir = self.run_root / "logs"
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)

        existing_state = existing_frame.get("state") if isinstance(existing_frame, dict) else None
        if isinstance(existing_state, dict):
            self.state = RunState.from_dict(existing_state)
        else:
            workflow_path = workflow.get("__workflow_path", "")
            now = datetime.now(timezone.utc).isoformat()
            self.state = RunState(
                schema_version=StateManager.SCHEMA_VERSION,
                run_id=self.run_id,
                workflow_file=_display_workflow_path(self.workspace, workflow_path) if workflow_path else "",
                workflow_checksum="call_frame",
                started_at=now,
                updated_at=now,
                status="running",
                run_root=str(self.run_root),
                context=workflow.get("context", {}),
                bound_inputs=dict(bound_inputs),
                observability=observability,
            )
        self._persist()

    def _snapshot(self) -> Dict[str, Any]:
        """Build the persisted call-frame metadata snapshot."""
        finalization = self.state.finalization if isinstance(self.state.finalization, dict) else {}
        body_status = finalization.get("body_status")
        finalization_status = finalization.get("status", "not_configured") if finalization else "not_configured"
        has_outputs = isinstance(self.workflow.get("outputs"), dict) and bool(self.workflow.get("outputs"))
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
            "current_step": self.state.current_step,
            "state": self.state.to_dict(),
        }

    def _persist(self) -> None:
        self.parent_manager.update_call_frame(self.frame_id, self._snapshot())

    def load(self) -> RunState:
        return self.state

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

    def update_loop_results(self, loop_name: str, loop_results: List[Dict[str, Any]]) -> None:
        self.state.steps[loop_name] = loop_results
        self._persist()

    def update_for_each(self, loop_name: str, state: ForEachState) -> None:
        self.state.for_each[loop_name] = state
        self._persist()

    def update_dataflow_state(
        self,
        artifact_versions: Dict[str, List[Dict[str, Any]]],
        artifact_consumes: Dict[str, Dict[str, int]],
    ) -> None:
        self.state.artifact_versions = artifact_versions
        self.state.artifact_consumes = artifact_consumes
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

    def clear_current_step(self, step_name: Optional[str] = None) -> None:
        if self.state.current_step is None:
            return
        if step_name and self.state.current_step.get("name") != step_name:
            return
        self.state.current_step = None
        self._persist()


class WorkflowExecutor:
    """
    Main workflow execution engine.
    Handles sequential execution, for-each loops, and control flow.
    """

    def __init__(
        self,
        workflow: Dict[str, Any],
        workspace: Path,
        state_manager: StateManager,
        logs_dir: Optional[Path] = None,
        debug: bool = False,
        stream_output: bool = False,
        max_retries: int = 0,
        retry_delay_ms: int = 1000,
        observability: Optional[Dict[str, Any]] = None,
        step_heartbeat_interval_sec: float = 30.0,
    ):
        """
        Initialize workflow executor.

        Args:
            workflow: Validated workflow dictionary
            workspace: Base workspace directory
            state_manager: State persistence manager
            logs_dir: Directory for logs
            debug: Enable debug mode
            stream_output: Stream provider stdout/stderr live without enabling debug mode
        """
        self.workflow = workflow
        self.workspace = workspace
        self.state_manager = state_manager
        self.debug = debug
        self.stream_output = stream_output
        self.observability = observability or {}

        # Initialize secrets manager
        self.secrets_manager = SecretsManager()

        # Initialize provider registry (load from workflow providers if present)
        self.provider_registry = ProviderRegistry()
        if 'providers' in workflow:
            errors = self.provider_registry.register_from_workflow(workflow['providers'])
            if errors:
                raise ValueError(f"Provider registration errors: {'; '.join(errors)}")

        # Initialize sub-executors
        self.step_executor = StepExecutor(workspace, logs_dir, self.secrets_manager)
        self.provider_executor = ProviderExecutor(workspace, self.provider_registry, self.secrets_manager)
        self.dependency_resolver = DependencyResolver(str(workspace))
        self.dependency_injector = DependencyInjector(str(workspace))
        self.condition_evaluator = ConditionEvaluator(workspace)
        self.variable_substitutor = VariableSubstitutor()
        self.reference_resolver = ReferenceResolver()
        self.summary_observer = self._create_summary_observer()
        workflow_path = workflow.get('__workflow_path')
        self.asset_resolver = (
            WorkflowAssetResolver(Path(workflow_path))
            if isinstance(workflow_path, str) and workflow_path
            else None
        )

        # Execution state
        self.current_step = 0
        self.body_steps = workflow.get('steps', [])
        self.finalization = workflow.get('finally') if isinstance(workflow.get('finally'), dict) else None
        self.finalization_steps = (
            self.finalization.get('steps', [])
            if isinstance(self.finalization, dict) and isinstance(self.finalization.get('steps'), list)
            else []
        )
        self.finalization_start_index = len(self.body_steps)
        self.steps = list(self.body_steps) + list(self.finalization_steps)
        self.variables = workflow.get('variables', {})
        self.global_secrets = workflow.get('secrets', [])

        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.step_heartbeat_interval_sec = step_heartbeat_interval_sec

    def _step_id(self, step: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
        """Return the durable identity for a top-level step."""
        return runtime_step_id(step, self.current_step if fallback_index is None else fallback_index)

    def _resume_entry_is_terminal(self, entry: Any) -> bool:
        """Return True when persisted step state is fully completed/skipped for resume purposes."""
        if isinstance(entry, dict):
            status = entry.get("status")
            if isinstance(status, str):
                return status in ["completed", "skipped"]
            if not entry:
                return False
            return all(self._resume_entry_is_terminal(value) for value in entry.values())
        if isinstance(entry, list):
            return all(self._resume_entry_is_terminal(value) for value in entry)
        return False

    def _determine_resume_restart_index(self, state: Dict[str, Any]) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart."""
        steps_state = state.get("steps", {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        current_step = state.get("current_step")
        if isinstance(current_step, dict):
            current_index = current_step.get("index")
            current_status = current_step.get("status")
            if isinstance(current_index, int) and current_status == "running":
                if 0 <= current_index < len(self.steps):
                    current_step_name = self.steps[current_index].get("name", f"step_{current_index}")
                    if self._resume_for_each_has_pending_work(state, current_step_name):
                        return current_index
                    if self._resume_repeat_until_has_pending_work(state, current_step_name):
                        return current_index
                    current_result = steps_state.get(current_step_name)
                    if not self._resume_entry_is_terminal(current_result):
                        return current_index

        for step_index, step in enumerate(self.steps):
            step_name = step.get("name", f"step_{step_index}")
            if self._resume_for_each_has_pending_work(state, step_name):
                return step_index
            if self._resume_repeat_until_has_pending_work(state, step_name):
                return step_index
            step_result = steps_state.get(step_name)
            if step_result is None:
                return step_index
            if not self._resume_entry_is_terminal(step_result):
                return step_index

        return None

    def _resume_for_each_has_pending_work(self, state: Dict[str, Any], step_name: str) -> bool:
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

    def _resume_repeat_until_has_pending_work(self, state: Dict[str, Any], step_name: str) -> bool:
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

        step_result = state.get("steps", {}).get(step_name)
        return isinstance(step_result, dict) and not self._resume_entry_is_terminal(step_result)

    def _uses_qualified_identities(self) -> bool:
        """Return True when this workflow uses the post-Task-6 state model."""
        return self._workflow_version_at_least("2.0")

    def _workflow_version_at_least(self, minimum: str) -> bool:
        """Return True when the loaded workflow version is at least the requested boundary."""
        version = self.workflow.get("version")
        if not isinstance(version, str):
            return False
        try:
            return self._parse_version_tuple(version) >= self._parse_version_tuple(minimum)
        except ValueError:
            return False

    @staticmethod
    def _parse_version_tuple(version: str) -> tuple[int, ...]:
        """Parse a dotted workflow version like 1.1.1 or 2.0 into a comparable tuple."""
        return tuple(int(part) for part in version.split("."))

    def _initial_finalization_state(self) -> Optional[Dict[str, Any]]:
        """Return durable finalization bookkeeping for workflows with cleanup."""
        if not self.finalization_steps:
            return None
        output_status = 'pending' if self.workflow.get('outputs') else 'not_configured'
        block_token = self.finalization.get('token') if isinstance(self.finalization, dict) else None
        return {
            'block_id': block_token or 'finally',
            'status': 'pending',
            'body_status': None,
            'current_index': None,
            'completed_indices': [],
            'step_names': [step.get('name') for step in self.finalization_steps if isinstance(step, dict)],
            'workflow_outputs_status': output_status,
        }

    def _persist_finalization_state(self, state: Dict[str, Any]) -> None:
        """Persist finalization bookkeeping when present."""
        finalization = state.get('finalization')
        if isinstance(finalization, dict):
            self.state_manager.update_finalization_state(finalization)

    def _ensure_finalization_state(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ensure run state contains the finalization bookkeeping structure."""
        if not self.finalization_steps:
            return None
        finalization = state.get('finalization')
        if not isinstance(finalization, dict):
            finalization = self._initial_finalization_state() or {}
            state['finalization'] = finalization
        finalization.setdefault(
            'block_id',
            self.finalization.get('token') if isinstance(self.finalization, dict) else 'finally',
        )
        finalization.setdefault('status', 'pending')
        finalization.setdefault('body_status', None)
        finalization.setdefault('current_index', None)
        finalization.setdefault('completed_indices', [])
        finalization.setdefault('step_names', [
            step.get('name') for step in self.finalization_steps if isinstance(step, dict)
        ])
        if 'workflow_outputs_status' not in finalization:
            finalization['workflow_outputs_status'] = (
                'pending' if self.workflow.get('outputs') else 'not_configured'
            )
        return finalization

    def _activate_finalization(self, state: Dict[str, Any], body_status: str) -> None:
        """Mark finalization as pending/running after the workflow body settles."""
        finalization = self._ensure_finalization_state(state)
        if finalization is None:
            return
        finalization['body_status'] = body_status
        if finalization.get('status') == 'pending':
            finalization['status'] = 'running'
        self._persist_finalization_state(state)

    def _record_finalization_step_start(self, state: Dict[str, Any], final_index: int, body_status: str) -> None:
        """Persist which cleanup step is currently running."""
        finalization = self._ensure_finalization_state(state)
        if finalization is None:
            return
        finalization['body_status'] = body_status
        finalization['status'] = 'running'
        finalization['current_index'] = final_index
        self._persist_finalization_state(state)

    def _record_finalization_step_result(
        self,
        state: Dict[str, Any],
        final_index: int,
        step_name: str,
        failed: bool,
        result: Any,
        body_status: str,
    ) -> None:
        """Persist one cleanup step outcome for resume and reporting."""
        finalization = self._ensure_finalization_state(state)
        if finalization is None:
            return
        completed_indices = finalization.setdefault('completed_indices', [])
        if not failed and final_index not in completed_indices:
            completed_indices.append(final_index)
            completed_indices.sort()
        finalization['body_status'] = body_status
        finalization['current_index'] = None if not failed else final_index
        if failed:
            finalization['status'] = 'failed'
            error = result.get('error') if isinstance(result, dict) else None
            finalization['failure'] = {
                'step': step_name,
                'step_id': result.get('step_id') if isinstance(result, dict) else None,
                'error': error,
            }
        elif len(completed_indices) == len(self.finalization_steps):
            finalization['status'] = 'completed'
            finalization.pop('failure', None)
        else:
            finalization['status'] = 'running'
        self._persist_finalization_state(state)

    def _record_finalization_settled_result(
        self,
        state: Dict[str, Any],
        step_index: int,
        step_name: str,
        body_status: str,
    ) -> None:
        """Project one settled cleanup result into finalization bookkeeping."""
        if not self._is_finalization_step(step_index):
            return
        result = state.get('steps', {}).get(step_name)
        failed = isinstance(result, dict) and result.get('status') == 'failed'
        self._record_finalization_step_result(
            state,
            step_index - self.finalization_start_index,
            step_name,
            failed,
            result,
            body_status,
        )
        finalization = self._ensure_finalization_state(state)
        if failed:
            if body_status == 'completed' and isinstance(result, dict):
                state['error'] = self._finalization_failure_error(result, step_name)
            if isinstance(finalization, dict):
                finalization['workflow_outputs_status'] = 'suppressed'
                self._persist_finalization_state(state)

    def _maybe_continue_into_finalization(
        self,
        next_step: Optional[str],
        step_index: int,
        terminal_status: str,
        state: Dict[str, Any],
    ) -> tuple[Optional[int], str, bool]:
        """Redirect body termination into finalization when configured."""
        if next_step not in {'_end', '_stop'}:
            return None, terminal_status, False
        if next_step == '_stop':
            terminal_status = 'failed'
        if self.finalization_steps and step_index < self.finalization_start_index:
            self._activate_finalization(state, terminal_status)
            return self.finalization_start_index, terminal_status, False
        return None, terminal_status, True

    def _is_finalization_step(self, step_index: int) -> bool:
        """Return True when the current step belongs to the appended finalization slice."""
        return bool(self.finalization_steps) and step_index >= self.finalization_start_index

    def _finalization_failure_error(self, result: Dict[str, Any], step_name: str) -> Dict[str, Any]:
        """Build a dedicated run-level error payload for cleanup failures after body success."""
        return {
            'type': 'finalization_failed',
            'message': 'Workflow finalization failed',
            'context': {
                'scope': 'workflow_finalization',
                'step': step_name,
                'step_id': result.get('step_id'),
                'error': result.get('error'),
            },
        }

    def _persist_workflow_boundary_state(self, state: Dict[str, Any]) -> None:
        """Persist workflow-boundary inputs/outputs and run-level error metadata."""
        bound_inputs = state.get('bound_inputs', {})
        if not isinstance(bound_inputs, dict):
            bound_inputs = {}
            state['bound_inputs'] = bound_inputs

        workflow_outputs = state.get('workflow_outputs', {})
        if not isinstance(workflow_outputs, dict):
            workflow_outputs = {}
            state['workflow_outputs'] = workflow_outputs

        self._persist_finalization_state(state)
        self.state_manager.update_workflow_outputs(workflow_outputs)
        self.state_manager.update_run_error(state.get('error') if isinstance(state.get('error'), dict) else None)

    def execute(self, run_id: Optional[str] = None, on_error: str = 'stop',
                max_retries: Optional[int] = None, retry_delay_ms: Optional[int] = None,
                resume: bool = False) -> Dict[str, Any]:
        """
        Execute the workflow.

        Args:
            run_id: Run identifier
            on_error: Error handling mode ('stop' or 'continue')
            max_retries: Maximum retry attempts (overrides constructor value)
            retry_delay_ms: Retry delay in milliseconds (overrides constructor value)
            resume: If True, skip already completed steps

        Returns:
            Final execution state
        """
        # Override retry config if provided
        if max_retries is not None:
            self.max_retries = max_retries
        if retry_delay_ms is not None:
            self.retry_delay_ms = retry_delay_ms

        # Store resume flag for nested methods
        self.resume_mode = resume
        # Load current state
        run_state = self.state_manager.load()

        # Convert to dict format for internal processing
        state = run_state.to_dict()
        state.setdefault('artifact_versions', {})
        state.setdefault('artifact_consumes', {})
        state.setdefault('transition_count', 0)
        state.setdefault('step_visits', {})
        state.setdefault('bound_inputs', {})
        state.setdefault('workflow_outputs', {})
        state.setdefault('call_frames', {})
        initial_finalization = self._initial_finalization_state()
        if initial_finalization is not None:
            state.setdefault('finalization', initial_finalization)
        state.pop('error', None)
        state['_resolved_consumes'] = {}
        if state.get('status') != 'running':
            self.state_manager.update_status('running')
            state['status'] = 'running'
        terminal_status = 'completed'

        try:
            # Execute steps with control flow support
            resume_restart_index = self._determine_resume_restart_index(state) if resume else None
            step_index = 0
            while step_index < len(self.steps):
                step = self.steps[step_index]
                self.current_step = step_index

                # Check if step should be executed
                step_name = step.get('name', f'step_{step_index}')
                step_id = self._step_id(step, step_index)
                resume_current_step = False
                if resume_restart_index is not None:
                    if step_index < resume_restart_index:
                        logger.info(f"Skipping step before resume restart point: {step_name}")
                        step_index += 1
                        continue
                    if step_index == resume_restart_index:
                        resume_current_step = True
                        resume_restart_index = None

                is_finalization_step = self._is_finalization_step(step_index)
                finalization_body_status = terminal_status
                if is_finalization_step:
                    finalization = self._ensure_finalization_state(state)
                    if isinstance(finalization, dict):
                        body_status = finalization.get('body_status')
                        if isinstance(body_status, str) and body_status:
                            finalization_body_status = body_status
                    self._record_finalization_step_start(
                        state,
                        step_index - self.finalization_start_index,
                        finalization_body_status,
                    )

                transition_guard = self._check_transition_guard(state, step_name)
                if transition_guard is not None:
                    self._persist_step_result(
                        state,
                        step_name,
                        step,
                        transition_guard,
                        phase_hint='pre_execution',
                        class_hint='pre_execution_failed',
                        retryable_hint=False,
                    )
                    self._record_finalization_settled_result(
                        state,
                        step_index,
                        step_name,
                        finalization_body_status,
                    )
                    next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                    finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                        next_step,
                        step_index,
                        terminal_status,
                        state,
                    )
                    if finalization_target is not None:
                        step_index = finalization_target
                        continue
                    if should_break:
                        break

                    target_index = self._resolve_next_step_index(step_index, next_step)
                    if target_index is None:
                        step_index += 1
                    else:
                        self._increment_transition_count(state)
                        step_index = target_index
                    continue

                # Check structured branch guards before the step's own when clause.
                if 'structured_if_guard' in step:
                    variables = self.variable_substitutor.build_variables(
                        run_state=state,
                        context=self.workflow.get('context', {})
                    )
                    guard = step.get('structured_if_guard', {})
                    condition = guard.get('condition') if isinstance(guard, dict) else None
                    invert = bool(guard.get('invert')) if isinstance(guard, dict) else False
                    try:
                        should_execute = self.condition_evaluator.evaluate(condition, variables, state)
                        if invert:
                            should_execute = not should_execute
                    except Exception as e:
                        error_info = {
                            'type': 'predicate_evaluation_failed',
                            'message': f"Condition evaluation failed: {e}",
                            'context': {'condition': condition}
                        }
                        result = {
                            'status': 'failed',
                            'exit_code': 2,
                            'error': error_info
                        }
                        self._persist_step_result(
                            state,
                            step_name,
                            step,
                            result,
                            phase_hint='pre_execution',
                            class_hint='pre_execution_failed',
                            retryable_hint=False,
                        )
                        self._record_finalization_settled_result(
                            state,
                            step_index,
                            step_name,
                            finalization_body_status,
                        )
                        next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                        finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                            next_step,
                            step_index,
                            terminal_status,
                            state,
                        )
                        if finalization_target is not None:
                            step_index = finalization_target
                            continue
                        if should_break:
                            break

                        target_index = self._resolve_next_step_index(step_index, next_step)
                        if target_index is None:
                            step_index += 1
                        else:
                            self._increment_transition_count(state)
                            step_index = target_index
                        continue

                    if not should_execute:
                        result = {
                            'status': 'skipped',
                            'exit_code': 0,
                            'skipped': True
                        }
                        self._persist_step_result(state, step_name, step, result)
                        self._record_finalization_settled_result(
                            state,
                            step_index,
                            step_name,
                            finalization_body_status,
                        )
                        next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                        finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                            next_step,
                            step_index,
                            terminal_status,
                            state,
                        )
                        if finalization_target is not None:
                            step_index = finalization_target
                            continue
                        if should_break:
                            break

                        target_index = self._resolve_next_step_index(step_index, next_step)
                        if target_index is None:
                            step_index += 1
                        else:
                            self._increment_transition_count(state)
                            step_index = target_index
                        continue

                # Check conditional execution (AT-37, AT-46, AT-47)
                if 'when' in step:
                    # Build variables for condition evaluation
                    variables = self.variable_substitutor.build_variables(
                        run_state=state,
                        context=self.workflow.get('context', {})
                    )

                    # Evaluate condition
                    try:
                        should_execute = self.condition_evaluator.evaluate(step['when'], variables, state)
                    except Exception as e:
                        # Condition evaluation error - record and skip
                        error_info = {
                            'type': 'predicate_evaluation_failed',
                            'message': f"Condition evaluation failed: {e}",
                            'context': {'condition': step['when']}
                        }
                        result = {
                            'status': 'failed',
                            'exit_code': 2,
                            'error': error_info
                        }
                        self._persist_step_result(
                            state,
                            step_name,
                            step,
                            result,
                            phase_hint='pre_execution',
                            class_hint='pre_execution_failed',
                            retryable_hint=False,
                        )
                        self._record_finalization_settled_result(
                            state,
                            step_index,
                            step_name,
                            finalization_body_status,
                        )
                        next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                        finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                            next_step,
                            step_index,
                            terminal_status,
                            state,
                        )
                        if finalization_target is not None:
                            step_index = finalization_target
                            continue
                        if should_break:
                            break

                        target_index = self._resolve_next_step_index(step_index, next_step)
                        if target_index is None:
                            step_index += 1
                        else:
                            self._increment_transition_count(state)
                            step_index = target_index
                        continue

                    if not should_execute:
                        # AT-37: Condition false -> step skipped with exit_code 0
                        result = {
                            'status': 'skipped',
                            'exit_code': 0,
                            'skipped': True
                        }
                        self._persist_step_result(state, step_name, step, result)
                        self._record_finalization_settled_result(
                            state,
                            step_index,
                            step_name,
                            finalization_body_status,
                        )
                        next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                        finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                            next_step,
                            step_index,
                            terminal_status,
                            state,
                        )
                        if finalization_target is not None:
                            step_index = finalization_target
                            continue
                        if should_break:
                            break

                        target_index = self._resolve_next_step_index(step_index, next_step)
                        if target_index is None:
                            step_index += 1
                        else:
                            self._increment_transition_count(state)
                            step_index = target_index
                        continue

                # AT-69: Create backup before step execution if debug enabled
                if self.debug:
                    self.state_manager.backup_state(step_name)

                consume_error = self._enforce_consumes_contract(step, step_name, state)
                visit_count = self._increment_step_visit(state, step_name)
                max_visits = step.get('max_visits')
                if isinstance(max_visits, int) and visit_count > max_visits:
                    self._persist_step_result(
                        state,
                        step_name,
                        step,
                        self._cycle_guard_result(
                            step_name=step_name,
                            limit_type='max_visits',
                            limit=max_visits,
                            observed=visit_count,
                        ),
                        phase_hint='pre_execution',
                        class_hint='pre_execution_failed',
                        retryable_hint=False,
                    )
                    self._record_finalization_settled_result(
                        state,
                        step_index,
                        step_name,
                        finalization_body_status,
                    )
                    next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                    finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                        next_step,
                        step_index,
                        terminal_status,
                        state,
                    )
                    if finalization_target is not None:
                        step_index = finalization_target
                        continue
                    if should_break:
                        break

                    target_index = self._resolve_next_step_index(step_index, next_step)
                    if target_index is None:
                        step_index += 1
                    else:
                        self._increment_transition_count(state)
                        step_index = target_index
                    continue

                if consume_error is not None:
                    self._persist_step_result(
                        state,
                        step_name,
                        step,
                        consume_error,
                        phase_hint='pre_execution',
                        class_hint='contract_violation',
                        retryable_hint=False,
                    )
                    self._record_finalization_settled_result(
                        state,
                        step_index,
                        step_name,
                        finalization_body_status,
                    )

                    next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                    finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                        next_step,
                        step_index,
                        terminal_status,
                        state,
                    )
                    if finalization_target is not None:
                        step_index = finalization_target
                        continue
                    if should_break:
                        break
                    target_index = self._resolve_next_step_index(step_index, next_step)
                    if target_index is None:
                        step_index += 1
                    else:
                        self._increment_transition_count(state)
                        step_index = target_index
                    continue

                self.state_manager.start_step(
                    step_name,
                    step_index,
                    self._resolve_step_type(step),
                    step_id=step_id,
                    visit_count=visit_count,
                )

                # Execute based on step type
                with self._step_heartbeat(step_name):
                    if 'for_each' in step:
                        state = self._execute_for_each(step, state, resume=resume_current_step)
                        # Persist the for_each summary array to state manager
                        # The for_each method already updates individual iteration results,
                        # but we also need to persist the summary array result
                        if step_name in state['steps']:
                            loop_results = state['steps'][step_name]
                            # Update state manager with the loop results array
                            # This ensures the array is persisted to disk and tests can access
                            # state['steps']['ProcessFiles'] as expected
                            if isinstance(loop_results, list):
                                self.state_manager.update_loop_results(step_name, loop_results)
                        self._emit_step_summary(
                            step_name,
                            step,
                            state.get('steps', {}).get(step_name, {'status': 'completed'}),
                        )
                    elif 'repeat_until' in step:
                        state = self._execute_repeat_until(step, state, resume=resume_current_step)
                        self._emit_step_summary(
                            step_name,
                            step,
                            state.get('steps', {}).get(step_name, {'status': 'completed'}),
                        )
                    elif 'structured_if_branch' in step:
                        result = self._execute_structured_if_branch(step)
                        self._persist_step_result(state, step_name, step, result)
                    elif 'structured_if_join' in step:
                        result = self._execute_structured_if_join(step, state)
                        self._persist_step_result(state, step_name, step, result)
                    elif 'structured_match_case' in step:
                        result = self._execute_structured_match_case(step)
                        self._persist_step_result(state, step_name, step, result)
                    elif 'structured_match_join' in step:
                        result = self._execute_structured_match_join(step, state)
                        self._persist_step_result(state, step_name, step, result)
                    elif 'wait_for' in step:
                        state = self._execute_wait_for(step, state)
                    elif 'assert' in step:
                        result = self._execute_assert(step, state)
                        self._persist_step_result(state, step_name, step, result)
                    elif 'set_scalar' in step:
                        result = self._execute_set_scalar(step)
                        publish_error = self._record_published_artifacts(step, step_name, result, state)
                        if publish_error is not None:
                            result = publish_error
                        self._persist_step_result(state, step_name, step, result)
                    elif 'increment_scalar' in step:
                        result = self._execute_increment_scalar(step, state)
                        publish_error = self._record_published_artifacts(step, step_name, result, state)
                        if publish_error is not None:
                            result = publish_error
                        self._persist_step_result(state, step_name, step, result)
                    elif 'call' in step:
                        result = self._execute_call(step, state)
                        self._persist_step_result(state, step_name, step, result)
                    elif 'provider' in step:
                        result = self._execute_provider(step, state)
                        publish_error = self._record_published_artifacts(step, step_name, result, state)
                        if publish_error is not None:
                            result = publish_error
                        self._persist_step_result(state, step_name, step, result)
                    elif 'command' in step:
                        result = self._execute_command(step, state)
                        publish_error = self._record_published_artifacts(step, step_name, result, state)
                        if publish_error is not None:
                            result = publish_error
                        self._persist_step_result(state, step_name, step, result)

                # Handle control flow after step execution (AT-56, AT-57, AT-58)
                next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)
                if is_finalization_step:
                    self._record_finalization_settled_result(
                        state,
                        step_index,
                        step_name,
                        finalization_body_status,
                    )
                    finalization_result = state.get('steps', {}).get(step_name)
                    if isinstance(finalization_result, dict) and finalization_result.get('status') == 'failed':
                        if next_step is None:
                            next_step = '_stop'

                finalization_target, terminal_status, should_break = self._maybe_continue_into_finalization(
                    next_step,
                    step_index,
                    terminal_status,
                    state,
                )
                if finalization_target is not None:
                    step_index = finalization_target
                    continue
                if should_break:
                    break
                target_index = self._resolve_next_step_index(step_index, next_step)
                if target_index is not None:
                    self._increment_transition_count(state)
                    step_index = target_index
                else:
                    # Continue to next step
                    step_index += 1
        except Exception:
            terminal_status = 'failed'
            self.state_manager.update_status(terminal_status)
            raise

        finalization = self._ensure_finalization_state(state)

        if terminal_status == 'completed':
            try:
                workflow_outputs = resolve_workflow_outputs(
                    self.workflow.get('outputs'),
                    state,
                    workspace=self.workspace,
                )
            except WorkflowSignatureError as exc:
                terminal_status = 'failed'
                state['error'] = exc.error
                if isinstance(finalization, dict) and self.workflow.get('outputs'):
                    finalization['workflow_outputs_status'] = 'failed'
                    self._persist_finalization_state(state)
            else:
                state['workflow_outputs'] = workflow_outputs
                state.pop('error', None)
                if isinstance(finalization, dict) and self.workflow.get('outputs'):
                    finalization['workflow_outputs_status'] = 'completed'
                    self._persist_finalization_state(state)
        elif isinstance(finalization, dict) and finalization.get('workflow_outputs_status') == 'pending':
            finalization['workflow_outputs_status'] = 'suppressed'
            self._persist_finalization_state(state)

        self._persist_workflow_boundary_state(state)
        self.state_manager.update_status(terminal_status)

        # Preserve historical behavior for stop-on-error returns, which include
        # in-memory step payloads that may not have been mirrored to state.json.
        if terminal_status == 'completed':
            return self.state_manager.load().to_dict()

        state['status'] = terminal_status
        return state

    def _resolve_step_type(self, step: Dict[str, Any]) -> str:
        """Return canonical step type label for runtime lifecycle state."""
        if 'structured_if_branch' in step:
            return 'structured_if_branch'
        if 'structured_if_join' in step:
            return 'structured_if_join'
        if 'structured_match_case' in step:
            return 'structured_match_case'
        if 'structured_match_join' in step:
            return 'structured_match_join'
        if 'provider' in step:
            return 'provider'
        if 'command' in step:
            return 'command'
        if 'wait_for' in step:
            return 'wait_for'
        if 'assert' in step:
            return 'assert'
        if 'set_scalar' in step:
            return 'set_scalar'
        if 'increment_scalar' in step:
            return 'increment_scalar'
        if 'call' in step:
            return 'call'
        if 'for_each' in step:
            return 'for_each'
        if 'repeat_until' in step:
            return 'repeat_until'
        return 'unknown'

    @contextmanager
    def _step_heartbeat(self, step_name: str):
        """Emit periodic state heartbeat updates while a step is executing."""
        interval_sec = float(self.step_heartbeat_interval_sec)
        if interval_sec <= 0:
            try:
                yield
            finally:
                self.state_manager.clear_current_step(step_name)
            return

        stop_event = threading.Event()

        def _heartbeat_loop():
            while not stop_event.wait(interval_sec):
                try:
                    self.state_manager.heartbeat_step(step_name)
                except Exception as exc:
                    logger.debug("Step heartbeat update failed for %s: %s", step_name, exc)

        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            name=f"step-heartbeat-{step_name}",
            daemon=True,
        )
        heartbeat_thread.start()

        try:
            yield
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=1.0)
            self.state_manager.clear_current_step(step_name)

    def _create_summary_observer(self) -> Optional[SummaryObserver]:
        """Create summary observer from runtime observability config."""
        if not isinstance(self.observability, dict):
            return None
        summaries_cfg = self.observability.get('step_summaries')
        if not isinstance(summaries_cfg, dict):
            return None
        if not summaries_cfg.get('enabled', False):
            return None

        provider_name = str(summaries_cfg.get('provider', 'claude_sonnet_summary'))
        mode = str(summaries_cfg.get('mode', 'async')).lower()
        if mode not in {'async', 'sync'}:
            mode = 'async'

        timeout_sec = summaries_cfg.get('timeout_sec', 120)
        max_input_chars = summaries_cfg.get('max_input_chars', 12000)
        try:
            timeout_sec = int(timeout_sec)
        except (TypeError, ValueError):
            timeout_sec = 120
        try:
            max_input_chars = int(max_input_chars)
        except (TypeError, ValueError):
            max_input_chars = 12000
        if timeout_sec <= 0:
            timeout_sec = 120
        if max_input_chars <= 0:
            max_input_chars = 12000

        best_effort = bool(summaries_cfg.get('best_effort', True))
        return SummaryObserver(
            run_root=self.state_manager.run_root,
            provider_executor=self.provider_executor,
            provider_name=provider_name,
            mode=mode,
            timeout_sec=timeout_sec,
            best_effort=best_effort,
            max_input_chars=max_input_chars,
        )

    def _emit_step_summary(self, step_name: str, step: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Emit observability summary for a completed step."""
        if self.summary_observer is None:
            return
        snapshot = self._build_step_summary_snapshot(step_name, step, result)
        try:
            self.summary_observer.emit(step_name, snapshot)
        except Exception as exc:
            logger.warning("Summary emission failed for %s: %s", step_name, exc)

    def _build_step_summary_snapshot(self, step_name: str, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Build a compact, deterministic snapshot for summary generation."""
        input_payload: Dict[str, Any] = {}
        if 'command' in step:
            input_payload['command'] = step.get('command')
        if 'provider' in step:
            input_payload['provider'] = step.get('provider')
            prompt_file = self.state_manager.logs_dir / f"{step_name}.prompt.txt"
            if prompt_file.exists():
                try:
                    input_payload['prompt'] = prompt_file.read_text(encoding='utf-8')
                except OSError:
                    pass

        output_payload: Dict[str, Any] = {}
        if isinstance(result, dict):
            output_payload = {
                'status': result.get('status'),
                'exit_code': result.get('exit_code'),
                'duration_ms': result.get('duration_ms'),
                'output': result.get('output') or result.get('text'),
                'lines': result.get('lines'),
                'json': result.get('json'),
                'error': result.get('error'),
                'artifacts': result.get('artifacts'),
            }

        return {
            'run_id': self.state_manager.run_id,
            'workflow': self.workflow.get('name'),
            'step': {
                'name': step_name,
                'type': 'provider' if 'provider' in step else 'command' if 'command' in step else 'other',
                'input': input_payload,
                'output': output_payload,
            },
        }

    def _contract_violation_result(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a standardized contract_violation failure result."""
        return {
            'status': 'failed',
            'exit_code': 2,
            'duration_ms': 0,
            'output': '',
            'error': {
                'type': 'contract_violation',
                'message': message,
                'context': context or {},
            },
        }

    def _persist_dataflow_state(self, state: Dict[str, Any]) -> None:
        """Persist artifact dataflow fields to state.json."""
        artifact_versions = state.get('artifact_versions', {})
        artifact_consumes = state.get('artifact_consumes', {})

        if not isinstance(artifact_versions, dict):
            artifact_versions = {}
            state['artifact_versions'] = artifact_versions
        if not isinstance(artifact_consumes, dict):
            artifact_consumes = {}
            state['artifact_consumes'] = artifact_consumes

        self.state_manager.update_dataflow_state(artifact_versions, artifact_consumes)

    def _persist_control_flow_state(self, state: Dict[str, Any]) -> None:
        """Persist cycle-guard counters to state.json."""
        transition_count = state.get('transition_count', 0)
        if not isinstance(transition_count, int):
            transition_count = 0
            state['transition_count'] = transition_count

        step_visits = state.get('step_visits', {})
        if not isinstance(step_visits, dict):
            step_visits = {}
            state['step_visits'] = step_visits

        self.state_manager.update_control_flow_counters(
            transition_count=transition_count,
            step_visits=step_visits,
        )

    def _increment_step_visit(self, state: Dict[str, Any], step_name: str) -> int:
        """Increment and persist the visit count for a top-level step entry."""
        step_visits = state.setdefault('step_visits', {})
        if not isinstance(step_visits, dict):
            step_visits = {}
            state['step_visits'] = step_visits

        current_value = step_visits.get(step_name, 0)
        if not isinstance(current_value, int):
            current_value = 0

        step_visits[step_name] = current_value + 1
        self._persist_control_flow_state(state)
        return step_visits[step_name]

    def _increment_transition_count(self, state: Dict[str, Any]) -> int:
        """Increment and persist the workflow transition counter."""
        transition_count = state.get('transition_count', 0)
        if not isinstance(transition_count, int):
            transition_count = 0
        transition_count += 1
        state['transition_count'] = transition_count
        self._persist_control_flow_state(state)
        return transition_count

    def _check_transition_guard(
        self,
        state: Dict[str, Any],
        step_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Fail the target step before execution when transition budget is exhausted."""
        max_transitions = self.workflow.get('max_transitions')
        if not isinstance(max_transitions, int):
            return None

        transition_count = state.get('transition_count', 0)
        if not isinstance(transition_count, int):
            transition_count = 0

        if transition_count <= max_transitions:
            return None

        return self._cycle_guard_result(
            step_name=step_name,
            limit_type='max_transitions',
            limit=max_transitions,
            observed=transition_count,
        )

    def _cycle_guard_result(
        self,
        step_name: str,
        limit_type: str,
        limit: int,
        observed: int,
    ) -> Dict[str, Any]:
        """Build a deterministic cycle-guard failure result."""
        return {
            'status': 'failed',
            'exit_code': 2,
            'duration_ms': 0,
            'error': {
                'type': 'cycle_guard_exceeded',
                'message': f"Cycle guard '{limit_type}' exceeded for step '{step_name}'",
                'context': {
                    'step': step_name,
                    'guard': limit_type,
                    'limit': limit,
                    'observed': observed,
                },
            },
        }

    def _resolve_next_step_index(self, current_index: int, next_step: Any) -> Optional[int]:
        """Resolve the concrete next step index for transition accounting."""
        if isinstance(next_step, int):
            return next_step

        implicit_index = current_index + 1
        if implicit_index < len(self.steps):
            return implicit_index
        return None

    def _collect_persisted_iteration_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        index: int,
    ) -> Dict[str, Any]:
        """Rebuild one loop iteration from persisted presentation keys."""
        steps_state = state.get('steps', {})
        if not isinstance(steps_state, dict):
            return {}

        iteration_state: Dict[str, Any] = {}
        loop_results = steps_state.get(loop_name)
        if (
            isinstance(loop_results, list)
            and 0 <= index < len(loop_results)
            and isinstance(loop_results[index], dict)
        ):
            iteration_state.update(loop_results[index])

        prefix = f"{loop_name}[{index}]."
        for persisted_key, persisted_value in steps_state.items():
            if not isinstance(persisted_key, str) or not persisted_key.startswith(prefix):
                continue
            nested_name = persisted_key[len(prefix):]
            if nested_name:
                iteration_state[nested_name] = persisted_value

        return iteration_state

    def _store_loop_iteration_result(
        self,
        loop_results: List[Dict[str, Any]],
        index: int,
        iteration_state: Dict[str, Any],
    ) -> None:
        """Store an iteration result at its stable list position."""
        while len(loop_results) <= index:
            loop_results.append({})
        loop_results[index] = iteration_state

    def _persist_for_each_progress(
        self,
        state: Dict[str, Any],
        loop_name: str,
        items: List[Any],
        completed_indices: List[int],
        current_index: Optional[int],
        loop_results: List[Dict[str, Any]],
    ) -> None:
        """Persist loop summary and bookkeeping for durable resume."""
        state.setdefault('steps', {})
        state.setdefault('for_each', {})

        progress = {
            'items': list(items),
            'completed_indices': sorted(set(completed_indices)),
            'current_index': current_index,
        }
        state['steps'][loop_name] = loop_results
        state['for_each'][loop_name] = progress

        self.state_manager.update_loop_results(loop_name, loop_results)
        self.state_manager.update_for_each(
            loop_name,
            ForEachState(
                items=list(items),
                completed_indices=progress['completed_indices'],
                current_index=current_index,
            ),
        )

    def _persist_repeat_until_progress(
        self,
        state: Dict[str, Any],
        loop_name: str,
        progress: Dict[str, Any],
        frame_result: Dict[str, Any],
    ) -> None:
        """Persist repeat_until bookkeeping plus the current loop-frame snapshot."""
        state.setdefault('steps', {})
        state.setdefault('repeat_until', {})
        state['steps'][loop_name] = frame_result
        state['repeat_until'][loop_name] = progress
        self.state_manager.update_repeat_until_state(loop_name, progress, frame_result)

    def _repeat_until_iteration_resume_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        iteration: int,
        body_steps: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], int, bool]:
        """Return persisted iteration state plus the first unfinished nested step index."""
        iteration_state = self._collect_persisted_iteration_state(state, loop_name, iteration)
        start_nested_index = 0
        for nested_index, nested_step in enumerate(body_steps):
            nested_name = nested_step.get('name', f'nested_{nested_index}')
            persisted = iteration_state.get(nested_name)
            if self._resume_entry_is_terminal(persisted):
                start_nested_index = nested_index + 1
                continue
            start_nested_index = nested_index
            break
        else:
            start_nested_index = len(body_steps)

        return iteration_state, start_nested_index, start_nested_index >= len(body_steps)

    def _resume_for_each_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        loop_steps: List[Dict[str, Any]],
        items: List[Any],
    ) -> tuple[List[Dict[str, Any]], List[int], int]:
        """Load persisted loop progress and determine the restart index."""
        steps_state = state.get('steps', {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        loop_results: List[Dict[str, Any]] = []
        existing_results = steps_state.get(loop_name)
        if isinstance(existing_results, list):
            loop_results = list(existing_results)

        progress = state.get('for_each', {}).get(loop_name)
        completed_indices: List[int] = []
        current_index: Optional[int] = None
        if isinstance(progress, dict):
            completed_indices = [
                index
                for index in progress.get('completed_indices', [])
                if isinstance(index, int) and 0 <= index < len(items)
            ]
            candidate_index = progress.get('current_index')
            if isinstance(candidate_index, int) and 0 <= candidate_index < len(items):
                current_index = candidate_index

        if not completed_indices and isinstance(existing_results, list):
            for i, iteration_result in enumerate(existing_results):
                if not isinstance(iteration_result, dict):
                    break
                all_steps_complete = True
                for nested_step in loop_steps:
                    nested_name = nested_step.get('name', f'step_{i}')
                    iteration_key = f"{loop_name}[{i}].{nested_name}"
                    nested_result = steps_state.get(iteration_key)
                    if not isinstance(nested_result, dict):
                        all_steps_complete = False
                        break
                    if nested_result.get('status') not in ['completed', 'failed', 'skipped']:
                        all_steps_complete = False
                        break
                if not all_steps_complete:
                    current_index = i
                    break
                completed_indices.append(i)

        for index in completed_indices:
            persisted_iteration = self._collect_persisted_iteration_state(state, loop_name, index)
            if persisted_iteration:
                self._store_loop_iteration_result(loop_results, index, persisted_iteration)

        start_index = current_index if current_index is not None else 0
        while start_index in completed_indices:
            logger.info(f"Skipping completed iteration {start_index} of {loop_name}")
            start_index += 1

        return loop_results, sorted(set(completed_indices)), start_index

    def _record_published_artifacts(
        self,
        step: Dict[str, Any],
        step_name: str,
        result: Dict[str, Any],
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Record artifact publications for successful steps."""
        publishes = step.get('publishes')
        if not publishes:
            return None
        if result.get('exit_code', 0) != 0:
            return None
        if not isinstance(publishes, list):
            return self._contract_violation_result(
                "Publish contract invalid",
                {"step": step_name, "reason": "publishes_not_list"},
            )

        artifacts = result.get('artifacts')
        if not isinstance(artifacts, dict):
            return self._contract_violation_result(
                "Publish contract failed",
                {
                    "step": step_name,
                    "reason": "missing_result_artifacts",
                    "hint": "publishes requires expected_outputs artifacts persisted in step result",
                },
            )

        artifacts_registry = self.workflow.get('artifacts', {})
        if not isinstance(artifacts_registry, dict):
            artifacts_registry = {}

        artifact_versions = state.setdefault('artifact_versions', {})
        if not isinstance(artifact_versions, dict):
            artifact_versions = {}
            state['artifact_versions'] = artifact_versions

        producer_identity = runtime_step_id or result.get('step_id') or self._step_id(step)
        if not self._uses_qualified_identities():
            producer_identity = step_name

        for publish in publishes:
            if not isinstance(publish, dict):
                continue

            artifact_name = publish.get('artifact')
            output_name = publish.get('from')
            if not isinstance(artifact_name, str) or not isinstance(output_name, str):
                continue

            if output_name not in artifacts:
                return self._contract_violation_result(
                    "Publish contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "missing_artifact_output",
                        "from": output_name,
                    },
                )

            value = artifacts[output_name]
            artifact_spec = artifacts_registry.get(artifact_name, {})
            if isinstance(artifact_spec, dict) and artifact_spec.get('type') == 'enum':
                allowed = artifact_spec.get('allowed')
                if (
                    not isinstance(value, str)
                    or not isinstance(allowed, list)
                    or value not in allowed
                ):
                    return self._contract_violation_result(
                        "Publish contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "invalid_enum_value",
                            "value": value,
                            "allowed": allowed if isinstance(allowed, list) else [],
                        },
                    )

            versions = artifact_versions.setdefault(artifact_name, [])
            if not isinstance(versions, list):
                versions = []
                artifact_versions[artifact_name] = versions

            max_version = 0
            for entry in versions:
                if isinstance(entry, dict):
                    entry_version = entry.get('version', 0)
                    if isinstance(entry_version, int) and entry_version > max_version:
                        max_version = entry_version

            entry = {
                'version': max_version + 1,
                'value': value,
                'producer': producer_identity,
                'producer_name': step_name,
                'step_index': self.current_step,
            }
            debug_payload = result.get('debug')
            if isinstance(debug_payload, dict):
                call_debug = debug_payload.get('call')
                if isinstance(call_debug, dict):
                    export_sources = call_debug.get('exports')
                    if isinstance(export_sources, dict):
                        source = export_sources.get(output_name)
                        if isinstance(source, dict):
                            entry['source_provenance'] = source

            versions.append(entry)

        self._persist_dataflow_state(state)
        return None

    def _enforce_consumes_contract(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve and enforce consumes contracts before step execution."""
        consumes = step.get('consumes')
        if not consumes:
            return None
        if not isinstance(consumes, list):
            return self._contract_violation_result(
                "Consume contract invalid",
                {"step": step_name, "reason": "consumes_not_list"},
            )

        artifacts_registry = self.workflow.get('artifacts', {})
        if not isinstance(artifacts_registry, dict):
            artifacts_registry = {}

        artifact_versions = state.setdefault('artifact_versions', {})
        if not isinstance(artifact_versions, dict):
            artifact_versions = {}
            state['artifact_versions'] = artifact_versions

        artifact_consumes = state.setdefault('artifact_consumes', {})
        if not isinstance(artifact_consumes, dict):
            artifact_consumes = {}
            state['artifact_consumes'] = artifact_consumes
        resolved_consumes = state.setdefault('_resolved_consumes', {})
        if not isinstance(resolved_consumes, dict):
            resolved_consumes = {}
            state['_resolved_consumes'] = resolved_consumes

        consumer_identity = runtime_step_id or self._step_id(step)
        if not self._uses_qualified_identities():
            consumer_identity = step_name

        step_consumes = artifact_consumes.setdefault(consumer_identity, {})
        if not isinstance(step_consumes, dict):
            step_consumes = {}
            artifact_consumes[consumer_identity] = step_consumes
        global_consumes = artifact_consumes.setdefault('__global__', {})
        if not isinstance(global_consumes, dict):
            global_consumes = {}
            artifact_consumes['__global__'] = global_consumes
        step_resolved_consumes: Dict[str, Any] = {}
        resolved_consumes[consumer_identity] = step_resolved_consumes
        workflow_version = self.workflow.get("version")
        materialize_relpath_consume_pointer = workflow_version in {"1.2", "1.3"}
        freshness_uses_step_scope = self._workflow_version_at_least("1.4")

        for consume in consumes:
            if not isinstance(consume, dict):
                continue

            artifact_name = consume.get('artifact')
            if not isinstance(artifact_name, str):
                continue

            candidates = artifact_versions.get(artifact_name, [])
            if not isinstance(candidates, list):
                candidates = []

            producers = consume.get('producers', [])
            if isinstance(producers, list) and producers:
                producer_set = {p for p in producers if isinstance(p, str)}
                candidates = [
                    c for c in candidates
                    if isinstance(c, dict) and (
                        c.get('producer') in producer_set or c.get('producer_name') in producer_set
                    )
                ]
            else:
                candidates = [c for c in candidates if isinstance(c, dict)]

            if not candidates:
                return self._contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "no_published_versions",
                    },
                )

            # v1.2 MVP supports latest_successful policy only.
            selected = max(
                candidates,
                key=lambda entry: entry.get('version', 0) if isinstance(entry.get('version'), int) else 0,
            )
            selected_version = selected.get('version', 0)
            if not isinstance(selected_version, int):
                return self._contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "invalid_selected_version",
                    },
                )

            freshness = consume.get('freshness', 'any')
            if freshness_uses_step_scope:
                last_consumed = step_consumes.get(artifact_name, 0)
            else:
                last_consumed = global_consumes.get(artifact_name, 0)
            if not isinstance(last_consumed, int):
                last_consumed = 0

            if freshness == 'since_last_consume' and selected_version <= last_consumed:
                return self._contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "stale_artifact",
                        "selected_version": selected_version,
                        "last_consumed_version": last_consumed,
                    },
                )

            artifact_spec = artifacts_registry.get(artifact_name, {})
            artifact_kind = 'relpath'
            artifact_type = None
            if isinstance(artifact_spec, dict):
                kind_value = artifact_spec.get('kind')
                if isinstance(kind_value, str) and kind_value:
                    artifact_kind = kind_value
                type_value = artifact_spec.get('type')
                if isinstance(type_value, str):
                    artifact_type = type_value
            selected_value = selected.get('value')
            if artifact_kind == 'relpath':
                pointer = artifact_spec.get('pointer') if isinstance(artifact_spec, dict) else None
                if not isinstance(pointer, str) or not pointer:
                    return self._contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "missing_registry_pointer",
                        },
                    )
                if not isinstance(selected_value, str):
                    return self._contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "invalid_selected_value",
                        },
                    )
                # v1.4+: consume preflight is read-only and must not mutate pointer files.
                if materialize_relpath_consume_pointer:
                    pointer_path = self.workspace / pointer
                    pointer_path.parent.mkdir(parents=True, exist_ok=True)
                    pointer_path.write_text(f"{selected_value}\n")
            elif artifact_kind == 'scalar':
                valid_scalar_value = False
                if artifact_type == 'integer':
                    valid_scalar_value = type(selected_value) is int
                elif artifact_type == 'float':
                    valid_scalar_value = (
                        isinstance(selected_value, float)
                        or type(selected_value) is int
                    )
                elif artifact_type == 'bool':
                    valid_scalar_value = isinstance(selected_value, bool)
                elif artifact_type == 'enum':
                    allowed = artifact_spec.get('allowed') if isinstance(artifact_spec, dict) else None
                    valid_scalar_value = (
                        isinstance(selected_value, str)
                        and isinstance(allowed, list)
                        and selected_value in allowed
                    )
                else:
                    valid_scalar_value = isinstance(selected_value, (int, float, bool, str))

                if not valid_scalar_value:
                    return self._contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "artifact": artifact_name,
                            "reason": "invalid_selected_value",
                            "artifact_kind": artifact_kind,
                            "artifact_type": artifact_type,
                        },
                    )
            else:
                return self._contract_violation_result(
                    "Consume contract failed",
                    {
                        "step": step_name,
                        "artifact": artifact_name,
                        "reason": "unsupported_artifact_kind",
                        "artifact_kind": artifact_kind,
                    },
                )

            step_consumes[artifact_name] = selected_version
            global_consumes[artifact_name] = selected_version
            step_resolved_consumes[artifact_name] = selected_value

        consume_bundle = step.get('consume_bundle')
        if consume_bundle:
            write_error = self._write_consume_bundle(
                consume_bundle=consume_bundle,
                step_name=step_name,
                resolved_values=step_resolved_consumes,
            )
            if write_error is not None:
                return write_error

        self._persist_dataflow_state(state)
        return None

    def _write_consume_bundle(
        self,
        consume_bundle: Any,
        step_name: str,
        resolved_values: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Materialize resolved consumes into a deterministic JSON bundle file."""
        if not isinstance(consume_bundle, dict):
            return self._contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "invalid_consume_bundle",
                },
            )

        bundle_path_raw = consume_bundle.get('path')
        if not isinstance(bundle_path_raw, str) or not bundle_path_raw:
            return self._contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "invalid_consume_bundle_path",
                },
            )

        bundle_path = self._resolve_workspace_path(bundle_path_raw)
        if bundle_path is None:
            return self._contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "consume_bundle_path_escape",
                    "path": bundle_path_raw,
                },
            )

        include = consume_bundle.get('include')
        selected_values: Dict[str, Any]
        if include is None:
            selected_values = dict(resolved_values)
        elif isinstance(include, list):
            selected_values = {}
            for artifact_name in include:
                if not isinstance(artifact_name, str):
                    return self._contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "reason": "invalid_consume_bundle_include",
                        },
                    )
                if artifact_name not in resolved_values:
                    return self._contract_violation_result(
                        "Consume contract failed",
                        {
                            "step": step_name,
                            "reason": "consume_bundle_include_missing_artifact",
                            "artifact": artifact_name,
                        },
                    )
                selected_values[artifact_name] = resolved_values[artifact_name]
        else:
            return self._contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "invalid_consume_bundle_include",
                },
            )

        try:
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
            bundle_path.write_text(
                json.dumps(selected_values, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            return self._contract_violation_result(
                "Consume contract failed",
                {
                    "step": step_name,
                    "reason": "consume_bundle_write_failed",
                    "path": bundle_path_raw,
                    "error": str(exc),
                },
            )

        return None

    def _resolve_workspace_path(self, relative_path: str) -> Optional[Path]:
        """Resolve workspace-relative path and reject escapes."""
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            return None

        candidate = (self.workspace / path).resolve()
        workspace_root = self.workspace.resolve()
        try:
            candidate.relative_to(workspace_root)
        except ValueError:
            return None
        return candidate

    def _prepare_output_file_path(self, output_file_value: str) -> Optional[Path]:
        """Resolve a workspace-relative output file path and ensure its parent exists."""
        output_file = self._resolve_workspace_path(output_file_value)
        if output_file is None:
            return None
        output_file.parent.mkdir(parents=True, exist_ok=True)
        return output_file

    def _read_prompt_source(self, step: Dict[str, Any]) -> tuple[str, Optional[Dict[str, Any]]]:
        """Read either a workspace-relative input_file or a source-relative asset_file."""
        if 'asset_file' in step:
            if self.asset_resolver is None:
                return "", self._contract_violation_result(
                    "Provider prompt asset resolution failed",
                    {
                        "step": step.get('name', f'step_{self.current_step}'),
                        "reason": "missing_workflow_source_root",
                    },
                )
            try:
                return self.asset_resolver.read_text(step['asset_file']), None
            except (AssetResolutionError, OSError) as exc:
                return "", self._contract_violation_result(
                    "Provider prompt asset resolution failed",
                    {
                        "step": step.get('name', f'step_{self.current_step}'),
                        "reason": "asset_file_read_failed",
                        "path": step.get('asset_file'),
                        "error": str(exc),
                    },
                )

        prompt = ""
        if 'input_file' in step:
            input_path = self.workspace / step['input_file']
            if input_path.exists():
                prompt = input_path.read_text()
        return prompt, None

    def _apply_asset_depends_on_prompt_injection(
        self,
        step: Dict[str, Any],
        prompt: str,
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """Inject source-relative asset files into the composed provider prompt."""
        asset_depends_on = step.get('asset_depends_on')
        if not asset_depends_on:
            return prompt, None
        if self.asset_resolver is None:
            return prompt, self._contract_violation_result(
                "Provider prompt asset resolution failed",
                {
                    "step": step.get('name', f'step_{self.current_step}'),
                    "reason": "missing_workflow_source_root",
                },
            )

        try:
            assets_block = self.asset_resolver.render_content_blocks(asset_depends_on)
        except (AssetResolutionError, OSError) as exc:
            return prompt, self._contract_violation_result(
                "Provider prompt asset resolution failed",
                {
                    "step": step.get('name', f'step_{self.current_step}'),
                    "reason": "asset_depends_on_read_failed",
                    "paths": list(asset_depends_on) if isinstance(asset_depends_on, list) else asset_depends_on,
                    "error": str(exc),
                },
            )

        if not assets_block:
            return prompt, None
        if not prompt:
            return assets_block, None
        return f"{assets_block}\n\n{prompt}", None

    def _write_prompt_audit(self, step_name: str, prompt_text: str, secrets: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None) -> None:
        """
        Write prompt to audit log with secrets masking.

        AT-70: With --debug, composed prompt text is written to logs/<Step>.prompt.txt
        with known secret values masked.

        Args:
            step_name: Name of the step
            prompt_text: The composed prompt text to audit
            secrets: List of secret names to resolve and mask
            env: Environment variables that may override secrets
        """
        if not self.state_manager.logs_dir:
            return

        # Get the secrets manager to mask known secrets
        secrets_manager = self.step_executor.secrets_manager

        # Resolve secrets to get their values tracked for masking
        if secrets or env:
            secrets_manager.resolve_secrets(
                declared_secrets=secrets,
                step_env=env
            )
            # Note: The resolve call adds the secret values to the manager's masked_values set

        # Mask known secrets in the prompt
        masked_prompt = secrets_manager.mask_text(prompt_text)

        # Write to logs/<Step>.prompt.txt
        prompt_file = self.state_manager.logs_dir / f"{step_name}.prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            prompt_file.write_text(masked_prompt)
        except Exception as e:
            # Log but don't fail if we can't write the audit file
            if self.debug:
                print(f"Warning: Could not write prompt audit for {step_name}: {e}")

    def _handle_control_flow(self, step: Dict[str, Any], state: Dict[str, Any],
                            step_name: str, current_index: int, on_error: str) -> Any:
        """
        Handle control flow after step execution.

        Implements:
        - AT-56: Strict flow stop - non-zero exit halts run when no goto and on_error=stop
        - AT-57: on_error continue - with --on-error continue, run proceeds after non-zero
        - AT-58: Goto precedence - on.success/failure execute before strict_flow applies
        - AT-59: Goto always ordering - on.always evaluated after success/failure handlers

        Returns:
            - '_end': terminate workflow successfully
            - '_stop': stop workflow due to error
            - int: jump to specific step index
            - None: continue to next step
        """
        # Get step result
        step_result = state.get('steps', {}).get(step_name, {})

        # Handle for-each loops (which return a list of results)
        if isinstance(step_result, list):
            # For for-each loops, control flow doesn't apply to individual iterations
            # The loop as a whole is considered successful if it completes
            return None  # Continue to next step

        # Handle regular steps (which return a dict)
        if not isinstance(step_result, dict):
            return None  # No result yet, continue

        exit_code = step_result.get('exit_code', 0)
        error = step_result.get('error')
        error_type = error.get('type') if isinstance(error, dict) else None

        # Check if step was skipped (conditional execution)
        if step_result.get('skipped'):
            return None  # Continue to next step

        # AT-58, AT-59: Check on.success/on.failure handlers first, then on.always (with precedence)
        if 'on' in step:
            handlers = step['on']
            goto_target = None

            # Determine which handler applies based on exit code
            if exit_code == 0 and 'success' in handlers:
                if 'goto' in handlers['success']:
                    goto_target = handlers['success']['goto']
            elif exit_code != 0 and 'failure' in handlers:
                if 'goto' in handlers['failure']:
                    goto_target = handlers['failure']['goto']

            # AT-59: on.always evaluated after success/failure and overrides them
            if 'always' in handlers:
                if 'goto' in handlers['always']:
                    goto_target = handlers['always']['goto']

            # If we found a goto target, use it
            if goto_target:
                return self._resolve_goto_target(goto_target)

        if error_type == 'cycle_guard_exceeded':
            logger.error(
                "Step '%s' exceeded a cycle guard and has no recovery edge. Stopping execution.",
                step_name,
            )
            return '_stop'

        # AT-56, AT-57: Apply strict_flow and on_error behavior
        # Only if no goto handler was found
        if exit_code != 0:
            strict_flow = self.workflow.get('strict_flow', True)

            if strict_flow and on_error == 'stop':
                # AT-56: Strict flow stop - halt on non-zero exit
                logger.error(f"Step '{step_name}' failed with exit code {exit_code}. "
                           f"Stopping execution (strict_flow=true, on_error=stop)")
                return '_stop'
            elif on_error == 'continue':
                # AT-57: Continue despite error
                logger.warning(f"Step '{step_name}' failed with exit code {exit_code}. "
                             f"Continuing execution (on_error=continue)")
                return None

        # Default: continue to next step
        return None

    def _resolve_goto_target(self, target: str) -> Any:
        """
        Resolve a goto target to a step index or special value.

        Args:
            target: Target step name or '_end'

        Returns:
            - '_end' for workflow termination
            - int for step index
            - None if target not found (should not happen if validation passed)
        """
        if target == '_end':
            return '_end'

        # Find step index by name
        for i, step in enumerate(self.steps):
            if step.get('name') == target:
                return i

        # This should not happen if validation passed
        logger.error(f"Goto target '{target}' not found")
        return None

    def _build_repeat_until_frame_result(
        self,
        step: Dict[str, Any],
        *,
        status: str,
        exit_code: int,
        artifacts: Optional[Dict[str, Any]],
        progress: Dict[str, Any],
        error: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build the persisted loop-frame result for one repeat_until step."""
        metadata = step.get('repeat_until', {})
        result: Dict[str, Any] = {
            'status': status,
            'exit_code': exit_code,
            'duration_ms': 0,
            'name': step.get('name', f'step_{self.current_step}'),
            'step_id': self._step_id(step),
            'debug': {
                'structured_repeat_until': {
                    'body_id': metadata.get('id'),
                    'max_iterations': metadata.get('max_iterations'),
                    'current_iteration': progress.get('current_iteration'),
                    'completed_iterations': list(progress.get('completed_iterations', [])),
                    'condition_evaluated_for_iteration': progress.get('condition_evaluated_for_iteration'),
                    'last_condition_result': progress.get('last_condition_result'),
                }
            },
        }
        if isinstance(artifacts, dict):
            result['artifacts'] = artifacts
        if isinstance(error, dict):
            result['error'] = error
        return result

    def _execute_repeat_until(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        resume: bool = False,
    ) -> Dict[str, Any]:
        """Execute a post-test repeat_until loop with durable resume bookkeeping."""
        step_name = step.get('name', f'step_{self.current_step}')
        block = step.get('repeat_until', {})
        body_steps = block.get('steps', []) if isinstance(block, dict) else []
        outputs = block.get('outputs', {}) if isinstance(block, dict) else {}
        condition = block.get('condition') if isinstance(block, dict) else None
        max_iterations = block.get('max_iterations') if isinstance(block, dict) else None

        if not isinstance(body_steps, list) or not isinstance(outputs, dict) or type(max_iterations) is not int:
            state['steps'][step_name] = self._attach_outcome(
                step,
                self._build_repeat_until_frame_result(
                    step,
                    status='failed',
                    exit_code=2,
                    artifacts=None,
                    progress={
                        'current_iteration': 0,
                        'completed_iterations': [],
                        'condition_evaluated_for_iteration': None,
                        'last_condition_result': None,
                    },
                    error={
                        'type': 'contract_violation',
                        'message': 'repeat_until configuration invalid at execution time',
                    },
                ),
                phase_hint='pre_execution',
                class_hint='contract_violation',
                retryable_hint=False,
            )
            self.state_manager.update_repeat_until_state(
                step_name,
                {
                    'current_iteration': 0,
                    'completed_iterations': [],
                    'condition_evaluated_for_iteration': None,
                    'last_condition_result': None,
                },
                state['steps'][step_name],
            )
            return state

        repeat_until_state = state.setdefault('repeat_until', {})
        if not isinstance(repeat_until_state, dict):
            repeat_until_state = {}
            state['repeat_until'] = repeat_until_state

        persisted_progress = repeat_until_state.get(step_name)
        if not isinstance(persisted_progress, dict):
            persisted_progress = {}

        completed_iterations = sorted(
            {
                index
                for index in persisted_progress.get('completed_iterations', [])
                if isinstance(index, int) and index >= 0
            }
        )
        current_iteration = persisted_progress.get('current_iteration')
        if not isinstance(current_iteration, int) or current_iteration < 0:
            current_iteration = 0
        condition_evaluated_for_iteration = persisted_progress.get('condition_evaluated_for_iteration')
        if not isinstance(condition_evaluated_for_iteration, int):
            condition_evaluated_for_iteration = None
        last_condition_result = persisted_progress.get('last_condition_result')
        if not isinstance(last_condition_result, bool):
            last_condition_result = None

        frame_artifacts: Dict[str, Any] = {}
        existing_frame = state.get('steps', {}).get(step_name)
        if isinstance(existing_frame, dict) and isinstance(existing_frame.get('artifacts'), dict):
            frame_artifacts = dict(existing_frame.get('artifacts', {}))

        loop_step_id = self._step_id(step)
        parent_scope_steps = self._build_loop_parent_scope_steps(step, state)

        if resume and current_iteration not in completed_iterations:
            _, _, body_complete = self._repeat_until_iteration_resume_state(
                state,
                step_name,
                current_iteration,
                body_steps,
            )
            if condition_evaluated_for_iteration == current_iteration:
                if last_condition_result is True:
                    completed_iterations = sorted(set(completed_iterations + [current_iteration]))
                    progress = {
                        'current_iteration': None,
                        'completed_iterations': completed_iterations,
                        'condition_evaluated_for_iteration': current_iteration,
                        'last_condition_result': True,
                    }
                    final_result = self._attach_outcome(
                        step,
                        self._build_repeat_until_frame_result(
                            step,
                            status='completed',
                            exit_code=0,
                            artifacts=frame_artifacts,
                            progress=progress,
                        ),
                    )
                    self._persist_repeat_until_progress(state, step_name, progress, final_result)
                    return state
                if body_complete:
                    completed_iterations = sorted(set(completed_iterations + [current_iteration]))
                    current_iteration += 1
                    condition_evaluated_for_iteration = None
                    last_condition_result = None

        while current_iteration < max_iterations:
            progress = {
                'current_iteration': current_iteration,
                'completed_iterations': completed_iterations,
                'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                'last_condition_result': last_condition_result,
            }
            running_frame = self._build_repeat_until_frame_result(
                step,
                status='running',
                exit_code=0,
                artifacts=frame_artifacts,
                progress=progress,
            )
            self._persist_repeat_until_progress(state, step_name, progress, running_frame)

            iteration_state, start_nested_index, body_complete = self._repeat_until_iteration_resume_state(
                state,
                step_name,
                current_iteration,
                body_steps,
            )
            loop_context = {
                'loop': {
                    'index': current_iteration,
                    'total': max_iterations,
                }
            }

            if not body_complete:
                for nested_index in range(start_nested_index, len(body_steps)):
                    nested_step = body_steps[nested_index]
                    nested_name = nested_step.get('name', f'nested_{nested_index}')
                    nested_runtime_step_id = iteration_step_id(
                        loop_step_id,
                        current_iteration,
                        nested_step,
                        nested_index,
                    )

                    if 'when' in nested_step:
                        variables = self.variable_substitutor.build_variables(
                            run_state=state,
                            context=self.workflow.get('context', {}),
                            loop_vars=loop_context.get('loop', {}),
                        )
                        try:
                            should_execute = self.condition_evaluator.evaluate(
                                nested_step['when'],
                                variables,
                                state,
                                scope={
                                    'self_steps': iteration_state,
                                    'parent_steps': parent_scope_steps,
                                    'root_steps': state.get('steps', {}),
                                },
                            )
                        except Exception as exc:
                            result = self._attach_outcome(
                                nested_step,
                                {
                                    'status': 'failed',
                                    'exit_code': 2,
                                    'name': nested_name,
                                    'step_id': nested_runtime_step_id,
                                    'error': {
                                        'type': 'predicate_evaluation_failed',
                                        'message': f"Condition evaluation failed: {exc}",
                                        'context': {'condition': nested_step['when']},
                                    },
                                },
                                phase_hint='pre_execution',
                                class_hint='pre_execution_failed',
                                retryable_hint=False,
                            )
                            iteration_state[nested_name] = result
                            self.state_manager.update_loop_step(
                                step_name,
                                current_iteration,
                                nested_name,
                                StepResult(
                                    status=result.get('status', 'failed'),
                                    name=result.get('name', nested_name),
                                    step_id=result.get('step_id'),
                                    exit_code=result.get('exit_code', 2),
                                    duration_ms=result.get('duration_ms', 0),
                                    error=result.get('error'),
                                    truncated=result.get('truncated', False),
                                    artifacts=result.get('artifacts'),
                                    skipped=result.get('skipped', False),
                                    outcome=result.get('outcome'),
                                ),
                            )
                            failure_progress = {
                                'current_iteration': current_iteration,
                                'completed_iterations': completed_iterations,
                                'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                                'last_condition_result': last_condition_result,
                            }
                            failure = self._attach_outcome(
                                step,
                                self._build_repeat_until_frame_result(
                                    step,
                                    status='failed',
                                    exit_code=2,
                                    artifacts=frame_artifacts,
                                    progress=failure_progress,
                                    error={
                                        'type': 'repeat_until_body_step_failed',
                                        'message': 'repeat_until body step failed',
                                        'context': {
                                            'iteration': current_iteration,
                                            'step': nested_name,
                                            'error': result.get('error'),
                                        },
                                    },
                                ),
                                phase_hint='pre_execution',
                                class_hint='pre_execution_failed',
                                retryable_hint=False,
                            )
                            self._persist_repeat_until_progress(state, step_name, failure_progress, failure)
                            return state

                        if not should_execute:
                            result = self._attach_outcome(
                                nested_step,
                                {
                                    'status': 'skipped',
                                    'exit_code': 0,
                                    'skipped': True,
                                    'name': nested_name,
                                    'step_id': nested_runtime_step_id,
                                },
                            )
                            iteration_state[nested_name] = result
                            self.state_manager.update_loop_step(
                                step_name,
                                current_iteration,
                                nested_name,
                                StepResult(
                                    status='skipped',
                                    name=result.get('name', nested_name),
                                    step_id=result.get('step_id'),
                                    exit_code=0,
                                    duration_ms=0,
                                    truncated=False,
                                    skipped=True,
                                    outcome=result.get('outcome'),
                                ),
                            )
                            continue

                    nested_context = self._create_loop_context(nested_step, loop_context, iteration_state)

                    if self.debug:
                        backup_name = f"{step_name}[{current_iteration}].{nested_name}"
                        self.state_manager.backup_state(backup_name)

                    consume_error = self._enforce_consumes_contract(
                        nested_step,
                        nested_name,
                        state,
                        runtime_step_id=nested_runtime_step_id,
                    )
                    if consume_error is not None:
                        result = consume_error
                    else:
                        result = self._execute_nested_loop_step(
                            nested_step,
                            nested_context,
                            state,
                            iteration_state,
                            parent_scope_steps,
                            runtime_step_id=nested_runtime_step_id,
                        )
                        publish_error = self._record_published_artifacts(
                            nested_step,
                            nested_name,
                            result,
                            state,
                            runtime_step_id=nested_runtime_step_id,
                        )
                        if publish_error is not None:
                            result = publish_error

                    result.setdefault('name', nested_name)
                    result.setdefault('step_id', nested_runtime_step_id)
                    result = self._attach_outcome(nested_step, result)
                    iteration_state[nested_name] = result
                    self.state_manager.update_loop_step(
                        step_name,
                        current_iteration,
                        nested_name,
                        StepResult(
                            status=result.get('status', 'completed' if result.get('exit_code', 0) == 0 else 'failed'),
                            name=result.get('name', nested_name),
                            step_id=result.get('step_id'),
                            exit_code=result.get('exit_code', 0),
                            duration_ms=result.get('duration_ms', 0),
                            output=result.get('output'),
                            lines=result.get('lines'),
                            json=result.get('json'),
                            error=result.get('error'),
                            truncated=result.get('truncated', False),
                            artifacts=result.get('artifacts'),
                            skipped=result.get('skipped', False),
                            files=result.get('files'),
                            wait_duration_ms=result.get('wait_duration_ms'),
                            poll_count=result.get('poll_count'),
                            timed_out=result.get('timed_out'),
                            outcome=result.get('outcome'),
                        ),
                    )

                    if result.get('exit_code', 0) != 0 and not result.get('skipped', False):
                        nested_outcome = result.get('outcome') if isinstance(result.get('outcome'), dict) else {}
                        failure_progress = {
                            'current_iteration': current_iteration,
                            'completed_iterations': completed_iterations,
                            'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                            'last_condition_result': last_condition_result,
                        }
                        failure = self._attach_outcome(
                            step,
                            self._build_repeat_until_frame_result(
                                step,
                                status='failed',
                                exit_code=result.get('exit_code', 1),
                                artifacts=frame_artifacts,
                                progress=failure_progress,
                                error={
                                    'type': 'repeat_until_body_step_failed',
                                    'message': 'repeat_until body step failed',
                                    'context': {
                                        'iteration': current_iteration,
                                        'step': nested_name,
                                        'error': result.get('error'),
                                    },
                                },
                            ),
                            phase_hint=nested_outcome.get('phase'),
                            class_hint=nested_outcome.get('class'),
                            retryable_hint=nested_outcome.get('retryable'),
                        )
                        self._persist_repeat_until_progress(state, step_name, failure_progress, failure)
                        return state

            artifacts = self._resolve_structured_output_artifacts(
                outputs,
                state,
                failure_message='repeat_until output resolution failed',
                selection_key='iteration',
                selection_value=str(current_iteration),
                scope={
                    'self_steps': iteration_state,
                    'parent_steps': parent_scope_steps,
                    'root_steps': state.get('steps', {}),
                },
            )
            if not isinstance(artifacts, dict):
                failure_progress = {
                    'current_iteration': current_iteration,
                    'completed_iterations': completed_iterations,
                    'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                    'last_condition_result': last_condition_result,
                }
                failure = self._attach_outcome(
                    step,
                    self._build_repeat_until_frame_result(
                        step,
                        status='failed',
                        exit_code=2,
                        artifacts=frame_artifacts,
                        progress=failure_progress,
                        error=artifacts.get('error') if isinstance(artifacts, dict) else None,
                    ),
                    phase_hint='post_execution',
                    class_hint='contract_violation',
                    retryable_hint=False,
                )
                self._persist_repeat_until_progress(state, step_name, failure_progress, failure)
                return state

            frame_artifacts = artifacts
            progress = {
                'current_iteration': current_iteration,
                'completed_iterations': completed_iterations,
                'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                'last_condition_result': last_condition_result,
            }
            self._persist_repeat_until_progress(
                state,
                step_name,
                progress,
                self._build_repeat_until_frame_result(
                    step,
                    status='running',
                    exit_code=0,
                    artifacts=frame_artifacts,
                    progress=progress,
                ),
            )

            if condition_evaluated_for_iteration != current_iteration:
                variables = self.variable_substitutor.build_variables(
                    run_state=state,
                    context=self.workflow.get('context', {}),
                )
                try:
                    should_stop = self.condition_evaluator.evaluate(condition, variables, state)
                except Exception as exc:
                    failure_progress = {
                        'current_iteration': current_iteration,
                        'completed_iterations': completed_iterations,
                        'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                        'last_condition_result': last_condition_result,
                    }
                    failure = self._attach_outcome(
                        step,
                        self._build_repeat_until_frame_result(
                            step,
                            status='failed',
                            exit_code=2,
                            artifacts=frame_artifacts,
                            progress=failure_progress,
                            error={
                                'type': 'predicate_evaluation_failed',
                                'message': f"repeat_until condition evaluation failed: {exc}",
                                'context': {'condition': condition, 'iteration': current_iteration},
                            },
                        ),
                        phase_hint='post_execution',
                        class_hint='contract_violation',
                        retryable_hint=False,
                    )
                    self._persist_repeat_until_progress(state, step_name, failure_progress, failure)
                    return state
                condition_evaluated_for_iteration = current_iteration
                last_condition_result = should_stop
                progress = {
                    'current_iteration': current_iteration,
                    'completed_iterations': completed_iterations,
                    'condition_evaluated_for_iteration': condition_evaluated_for_iteration,
                    'last_condition_result': last_condition_result,
                }
                self._persist_repeat_until_progress(
                    state,
                    step_name,
                    progress,
                    self._build_repeat_until_frame_result(
                        step,
                        status='running',
                        exit_code=0,
                        artifacts=frame_artifacts,
                        progress=progress,
                    ),
                )
            else:
                should_stop = bool(last_condition_result)

            completed_iterations = sorted(set(completed_iterations + [current_iteration]))
            if should_stop:
                progress = {
                    'current_iteration': None,
                    'completed_iterations': completed_iterations,
                    'condition_evaluated_for_iteration': current_iteration,
                    'last_condition_result': True,
                }
                completed = self._attach_outcome(
                    step,
                    self._build_repeat_until_frame_result(
                        step,
                        status='completed',
                        exit_code=0,
                        artifacts=frame_artifacts,
                        progress=progress,
                    ),
                )
                self._persist_repeat_until_progress(state, step_name, progress, completed)
                return state

            if current_iteration + 1 >= max_iterations:
                progress = {
                    'current_iteration': None,
                    'completed_iterations': completed_iterations,
                    'condition_evaluated_for_iteration': current_iteration,
                    'last_condition_result': False,
                }
                exhausted = self._attach_outcome(
                    step,
                    self._build_repeat_until_frame_result(
                        step,
                        status='failed',
                        exit_code=3,
                        artifacts=frame_artifacts,
                        progress=progress,
                        error={
                            'type': 'repeat_until_iterations_exhausted',
                            'message': 'repeat_until exhausted max_iterations before condition became true',
                            'context': {
                                'max_iterations': max_iterations,
                                'last_iteration': current_iteration,
                            },
                        },
                    ),
                    phase_hint='post_execution',
                    class_hint='assert_failed',
                    retryable_hint=False,
                )
                self._persist_repeat_until_progress(state, step_name, progress, exhausted)
                return state

            current_iteration += 1
            condition_evaluated_for_iteration = None
            last_condition_result = None

        return state

    def _execute_for_each(self, step: Dict[str, Any], state: Dict[str, Any], resume: bool = False) -> Dict[str, Any]:
        """
        Execute a for_each loop step.
        Implements AT-3: Dynamic for-each with items_from.
        Implements AT-13: Pointer grammar for nested JSON paths.

        Args:
            step: Step definition with for_each
            state: Current execution state
            resume: If True, skip already completed iterations

        Returns:
            Updated state after loop execution
        """
        step_name = step.get('name', f'step_{self.current_step}')
        for_each = step['for_each']
        persisted_progress = state.get('for_each', {}).get(step_name) if isinstance(state.get('for_each'), dict) else None

        # Resolve items to iterate over
        if (
            resume
            and isinstance(persisted_progress, dict)
            and isinstance(persisted_progress.get('items'), list)
        ):
            items = list(persisted_progress.get('items', []))
        elif 'items_from' in for_each:
            # AT-3: Dynamic items from pointer
            pointer_resolver = PointerResolver(state)
            try:
                items = pointer_resolver.resolve(for_each['items_from'])
            except ValueError as e:
                # Record error and fail
                state = self._record_step_error(
                    state, step_name,
                    exit_code=2,
                    error={
                        'message': f"Failed to resolve items_from pointer: {e}",
                        'context': {
                            'pointer': for_each['items_from'],
                            'error': str(e)
                        }
                    }
                )
                return state

            # Verify resolved value is an array
            if not isinstance(items, list):
                state = self._record_step_error(
                    state, step_name,
                    exit_code=2,
                    error={
                        'message': f"items_from must resolve to an array, got {type(items).__name__}",
                        'context': {
                            'pointer': for_each['items_from'],
                            'resolved_type': type(items).__name__
                        }
                    }
                )
                return state
        else:
            # Static items list
            items = list(for_each.get('items', []))

        # Get loop configuration
        item_var = for_each.get('as', 'item')
        loop_steps = for_each.get('steps', [])

        # Initialize loop state
        if 'steps' not in state:
            state['steps'] = {}
        state.setdefault('for_each', {})

        # Prepare loop state storage (indexed by iteration)
        # Format: steps.<LoopName>[i].<StepName>
        loop_results: List[Dict[str, Any]] = []
        completed_indices: List[int] = []

        # Check for existing partial results (for resume)
        start_index = 0
        if resume:
            loop_results, completed_indices, start_index = self._resume_for_each_state(
                state,
                step_name,
                loop_steps,
                items,
            )

        self._persist_for_each_progress(
            state,
            step_name,
            items,
            completed_indices,
            start_index if start_index < len(items) else None,
            loop_results,
        )

        # Execute loop iterations (starting from start_index for resume)
        loop_step_id = self._step_id(step)
        parent_scope_steps = self._build_loop_parent_scope_steps(step, state)
        for index in range(start_index, len(items)):
            item = items[index]
            self._persist_for_each_progress(
                state,
                step_name,
                items,
                completed_indices,
                index,
                loop_results,
            )

            # Setup loop scope variables
            loop_context = {
                'item': item,  # Current item
                item_var: item,  # Custom alias if specified
                'loop': {
                    'index': index,
                    'total': len(items)
                }
            }

            # Execute nested steps for this iteration
            iteration_state: Dict[str, Any] = {}
            for nested_index, nested_step in enumerate(loop_steps):
                nested_name = nested_step.get('name', f'nested_{index}')
                nested_runtime_step_id = iteration_step_id(loop_step_id, index, nested_step, nested_index)

                # Check conditional execution within loop (AT-37, AT-46, AT-47)
                if 'when' in nested_step:
                    # Build variables for condition evaluation (including loop scope)
                    variables = self.variable_substitutor.build_variables(
                        run_state=state,
                        context=self.workflow.get('context', {}),
                        loop_vars=loop_context.get('loop', {}),
                        item=item
                    )

                    # Evaluate condition
                    try:
                        should_execute = self.condition_evaluator.evaluate(
                            nested_step['when'],
                            variables,
                            state,
                            scope={
                                'self_steps': iteration_state,
                                'parent_steps': parent_scope_steps,
                                'root_steps': state.get('steps', {}),
                            },
                        )
                    except Exception as e:
                        # Condition evaluation error
                        result = {
                            'status': 'failed',
                            'exit_code': 2,
                            'error': {
                                'type': 'predicate_evaluation_failed',
                                'message': f"Condition evaluation failed: {e}",
                                'context': {'condition': nested_step['when']}
                            }
                        }
                        result.setdefault('name', nested_name)
                        result.setdefault('step_id', nested_runtime_step_id)
                        result = self._attach_outcome(nested_step, result)
                        iteration_state[nested_name] = result
                        self.state_manager.update_loop_step(
                            step_name,
                            index,
                            nested_name,
                            StepResult(
                                status=result.get('status', 'failed'),
                                name=result.get('name', nested_name),
                                step_id=result.get('step_id'),
                                exit_code=result.get('exit_code', 2),
                                duration_ms=result.get('duration_ms', 0),
                                error=result.get('error'),
                                truncated=result.get('truncated', False),
                                artifacts=result.get('artifacts'),
                                skipped=result.get('skipped', False),
                                outcome=result.get('outcome'),
                            ),
                        )
                        continue

                    if not should_execute:
                        # Condition false -> step skipped
                        result = {
                            'status': 'skipped',
                            'exit_code': 0,
                            'skipped': True
                        }
                        result.setdefault('name', nested_name)
                        result.setdefault('step_id', nested_runtime_step_id)
                        result = self._attach_outcome(nested_step, result)
                        iteration_state[nested_name] = result
                        self.state_manager.update_loop_step(
                            step_name,
                            index,
                            nested_name,
                            StepResult(
                                status=result.get('status', 'skipped'),
                                name=result.get('name', nested_name),
                                step_id=result.get('step_id'),
                                exit_code=result.get('exit_code', 0),
                                duration_ms=result.get('duration_ms', 0),
                                truncated=result.get('truncated', False),
                                artifacts=result.get('artifacts'),
                                skipped=result.get('skipped', True),
                                outcome=result.get('outcome'),
                            ),
                        )
                        continue

                # Create a modified context with loop variables
                # AT-65: Pass iteration_state to ensure loop scoping of steps.* variables
                nested_context = self._create_loop_context(nested_step, loop_context, iteration_state)

                # AT-69: Create backup for loop steps if debug enabled
                if self.debug:
                    backup_name = f"{step_name}[{index}].{nested_name}"
                    self.state_manager.backup_state(backup_name)

                consume_error = self._enforce_consumes_contract(
                    nested_step,
                    nested_name,
                    state,
                    runtime_step_id=nested_runtime_step_id,
                )
                if consume_error is not None:
                    result = consume_error
                else:
                    result = self._execute_nested_loop_step(
                        nested_step,
                        nested_context,
                        state,
                        iteration_state,
                        parent_scope_steps,
                        runtime_step_id=nested_runtime_step_id,
                    )
                    publish_error = self._record_published_artifacts(
                        nested_step,
                        nested_name,
                        result,
                        state,
                        runtime_step_id=nested_runtime_step_id,
                    )
                    if publish_error is not None:
                        result = publish_error

                # Store in iteration state
                result.setdefault('name', nested_name)
                result.setdefault('step_id', nested_runtime_step_id)
                result = self._attach_outcome(nested_step, result)
                iteration_state[nested_name] = result

                self.state_manager.update_loop_step(
                    step_name,
                    index,
                    nested_name,
                    StepResult(
                        status=result.get('status', 'completed' if result.get('exit_code', 0) == 0 else 'failed'),
                        name=result.get('name', nested_name),
                        step_id=result.get('step_id'),
                        exit_code=result.get('exit_code', 0),
                        duration_ms=result.get('duration_ms', 0),
                        output=result.get('output'),
                        lines=result.get('lines'),
                        json=result.get('json'),
                        error=result.get('error'),
                        truncated=result.get('truncated', False),
                        artifacts=result.get('artifacts'),
                        skipped=result.get('skipped', False),
                        files=result.get('files'),
                        wait_duration_ms=result.get('wait_duration_ms'),
                        poll_count=result.get('poll_count'),
                        timed_out=result.get('timed_out'),
                        outcome=result.get('outcome'),
                    ),
                )

            # Store iteration results in indexed format
            self._store_loop_iteration_result(loop_results, index, iteration_state)
            completed_indices.append(index)
            next_index = index + 1 if index + 1 < len(items) else None
            self._persist_for_each_progress(
                state,
                step_name,
                items,
                completed_indices,
                next_index,
                loop_results,
            )

        # Update state with loop results
        # Store as steps.<LoopName> = [{iteration_0}, {iteration_1}, ...]
        state['steps'][step_name] = loop_results

        # Also store flattened format for compatibility
        # steps.<LoopName>[i].<StepName> = result
        for i, iteration in enumerate(loop_results):
            for nested_name, result in iteration.items():
                indexed_key = f"{step_name}[{i}].{nested_name}"
                state['steps'][indexed_key] = result

        self._persist_for_each_progress(
            state,
            step_name,
            items,
            completed_indices,
            None,
            loop_results,
        )

        return state

    def _execute_nested_loop_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        scope = {
            'self_steps': iteration_state,
            'parent_steps': parent_scope_steps,
            'root_steps': state.get('steps', {}),
        }
        if 'command' in step:
            return self._execute_command_with_context(step, context, state)
        if 'provider' in step:
            return self._execute_provider_with_context(
                step,
                context,
                state,
                runtime_step_id=runtime_step_id,
            )
        if 'assert' in step:
            return self._execute_assert(step, state, context=context, scope=scope)
        if 'set_scalar' in step:
            return self._execute_set_scalar(step)
        if 'increment_scalar' in step:
            return self._execute_increment_scalar(step, state)
        if 'wait_for' in step:
            return self._execute_wait_for_result(step)
        return {'status': 'skipped', 'exit_code': 0, 'skipped': True}

    def _build_loop_parent_scope_steps(
        self,
        loop_step: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the lexical parent scope for structured refs inside one loop body."""
        steps_state = state.get('steps', {})
        if not isinstance(steps_state, dict):
            return {}

        loop_step_id = self._step_id(loop_step)
        if '.' in loop_step_id:
            parent_step_id = loop_step_id.rsplit('.', 1)[0]
        else:
            parent_step_id = 'root'

        loop_name = loop_step.get('name')
        name_prefix = None
        if isinstance(loop_name, str) and '.' in loop_name:
            name_prefix = loop_name.rsplit('.', 1)[0]

        parent_scope_steps: Dict[str, Any] = {}
        for candidate in self.steps:
            if not isinstance(candidate, dict):
                continue
            candidate_name = candidate.get('name')
            candidate_step_id = candidate.get('step_id')
            if not isinstance(candidate_name, str) or not isinstance(candidate_step_id, str):
                continue
            if '.' in candidate_step_id:
                candidate_parent_id = candidate_step_id.rsplit('.', 1)[0]
            else:
                candidate_parent_id = 'root'
            if candidate_parent_id != parent_step_id:
                continue

            candidate_result = steps_state.get(candidate_name)
            if not isinstance(candidate_result, dict):
                continue

            if name_prefix and candidate_name.startswith(f"{name_prefix}."):
                local_name = candidate_name[len(name_prefix) + 1:]
            else:
                local_name = candidate_name
            parent_scope_steps[local_name] = candidate_result

        return parent_scope_steps

    def _execute_command_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a command step with variable substitution context.
        Implements AT-21: Raw commands only retry when retries field is set.
        Implements AT-63: Undefined variable detection with error context.

        Args:
            step: Step definition
            context: Variable context for substitution
            state: Current state

        Returns:
            Execution result as dict
        """
        # Substitute variables in command
        command = step['command']

        # Build variables from all sources
        # AT-65: Use context's steps for loop scoping (contains only current iteration)
        scoped_state = state.copy()
        if 'steps' in context:
            # Inside loop: use scoped steps from context (current iteration only)
            scoped_state['steps'] = context['steps']

        variables = self.variable_substitutor.build_variables(
            run_state=scoped_state,
            context=context.get('context', {}),
            loop_vars=context.get('loop'),
            item=context.get('item')
        )

        # Add any custom loop variables (e.g., from for_each with "as: filename")
        # These come directly in the context, not under any namespace
        for key, value in context.items():
            if key not in ['run', 'context', 'steps', 'loop', 'item']:
                # This is likely a custom loop variable
                variables[key] = value

        # Apply variable substitution with error tracking (AT-63)
        try:
            if isinstance(command, list):
                # For list commands, substitute each element individually
                substituted_command = []
                for elem in command:
                    substituted_elem = self.variable_substitutor.substitute(elem, variables)
                    substituted_command.append(substituted_elem)
                command = substituted_command
            else:
                # For string commands, substitute the entire string
                command = self.variable_substitutor.substitute(command, variables)
        except ValueError:
            # AT-63: Undefined variable detected, return error without executing
            undefined_vars = list(self.variable_substitutor.undefined_vars)

            # Build substituted command for error context (best effort with undefined vars)
            try:
                # Try substituting without tracking undefined to show what we could substitute
                if isinstance(step['command'], list):
                    substituted_cmd = []
                    for elem in step['command']:
                        # Substitute without error tracking
                        subst = self.variable_substitutor.substitute(elem, variables, track_undefined=False)
                        substituted_cmd.append(subst)
                else:
                    substituted_cmd = self.variable_substitutor.substitute(
                        step['command'], variables, track_undefined=False
                    )
            except Exception:
                substituted_cmd = step['command']

            return {
                'exit_code': 2,
                'error': {
                    'type': 'undefined_variables',
                    'message': f'Undefined variables in command: {", ".join(undefined_vars)}',
                    'context': {
                        'undefined_vars': undefined_vars,
                        'substituted_command': substituted_cmd if isinstance(substituted_cmd, list) else [substituted_cmd]
                    }
                },
                'output': '',
                'duration_ms': 0
            }

        # Create retry policy for command steps (AT-21)
        retries_config = step.get('retries')
        retry_policy = RetryPolicy.for_command(retries_config)

        # Execute with retries
        attempt = 0
        result = None

        while True:
            # Apply variable substitution to output_file if present
            output_file = None
            if 'output_file' in step:
                output_file_str = self.variable_substitutor.substitute(step['output_file'], variables)
                output_file = self._prepare_output_file_path(output_file_str)
                if output_file is None:
                    return self._contract_violation_result(
                        "Provider execution failed",
                        {
                            "step": step.get('name', f'step_{self.current_step}'),
                            "reason": "output_file_path_escape",
                            "path": output_file_str,
                        },
                    )

            # Convert output_capture string to CaptureMode enum
            from ..exec.output_capture import CaptureMode
            capture_mode_str = step.get('output_capture', 'text')
            if capture_mode_str == 'text':
                capture_mode = CaptureMode.TEXT
            elif capture_mode_str == 'lines':
                capture_mode = CaptureMode.LINES
            else:
                capture_mode = CaptureMode.JSON

            # Execute command
            result = self.step_executor.execute_command(
                step_name=step.get('name', 'command'),
                command=command,
                env=step.get('env'),
                timeout_sec=step.get('timeout_sec'),
                output_capture=capture_mode,
                output_file=output_file,
                allow_parse_error=step.get('allow_parse_error', False)
            )

            # Check if should retry
            if retry_policy.should_retry(result.exit_code, attempt):
                if self.debug:
                    print(f"Command failed with exit code {result.exit_code}, retrying (attempt {attempt + 1}/{retry_policy.max_retries})")
                retry_policy.wait()
                attempt += 1
                continue

            # No retry needed or max retries reached
            break

        # Ensure result is not None before calling to_state_dict()
        if result is None:
            return {
                'status': 'failed',
                'exit_code': 1,
                'error': {'message': 'Command execution failed with no result'}
            }

        return self._apply_expected_outputs_contract(step, result.to_state_dict())

    def _execute_provider_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a provider step with variable substitution context.
        Implements AT-21: Provider steps retry on exit codes 1 and 124 by default.
        Implements AT-28-35,53: Dependency injection with debug record.

        Args:
            step: Step definition
            context: Variable context for substitution
            state: Current state

        Returns:
            Execution result as dict
        """
        # Initialize debug info dict for injection metadata
        debug_info = {}

        # Initialize prompt variable from either input_file or asset_file.
        prompt, prompt_error = self._read_prompt_source(step)
        if prompt_error is not None:
            return prompt_error

        # Handle dependencies if specified (AT-22-27)
        if 'depends_on' in step:
            depends_on = step['depends_on']

            # Build variables dict for substitution
            substitution_vars = self._build_substitution_variables(context, state)

            # Resolve dependencies using the correct API
            resolution = self.dependency_resolver.resolve(
                depends_on=depends_on,
                variables=substitution_vars
            )

            # Check for validation errors (missing required dependencies)
            if not resolution.is_valid:
                # Missing required dependencies - exit code 2
                return {
                    'status': 'failed',
                    'exit_code': 2,
                    'error': {
                        'type': 'dependency_validation',
                        'message': 'Missing required dependencies',
                        'context': {
                            'missing_dependencies': resolution.errors
                        }
                    }
                }

            # Get all resolved files in deterministic order
            all_files = resolution.files

            # Apply variable substitution to prompt
            # Build variables for substitution
            # AT-65: Use context's steps for loop scoping (contains only current iteration)
            scoped_state = state.copy()
            if 'steps' in context:
                # Inside loop: use scoped steps from context (current iteration only)
                scoped_state['steps'] = context['steps']

            variables = self.variable_substitutor.build_variables(
                run_state=scoped_state,
                context=context.get('context', {}),
                loop_vars=context.get('loop'),
                item=context.get('item')
            )

            # Add any custom loop variables
            for key, value in context.items():
                if key not in ['run', 'context', 'steps', 'loop', 'item']:
                    variables[key] = value

            # AT-73: Do NOT substitute variables in prompt text (input_file contents are literal)
            # The spec states: "input_file: read literal contents; no substitution inside file contents"
            # prompt = self.variable_substitutor.substitute(prompt, variables, track_undefined=False)

            # Apply dependency injection if configured (AT-28-35,53)
            inject_config = depends_on.get('inject', False)
            if inject_config:
                # Perform injection (use whether we had required deps)
                has_required = 'required' in depends_on and len(depends_on['required']) > 0
                injection_result = self.dependency_injector.inject(
                    prompt=prompt,
                    files=all_files,
                    inject_config=inject_config,
                    is_required=has_required
                )

                # Use the modified prompt
                prompt = injection_result.modified_prompt

                # Record truncation details if present (AT-35)
                if injection_result.was_truncated and injection_result.truncation_details:
                    debug_info['injection'] = injection_result.truncation_details

        else:
            # Apply variable substitution to prompt
            # Build variables for substitution
            # AT-65: Use context's steps for loop scoping (contains only current iteration)
            scoped_state = state.copy()
            if 'steps' in context:
                # Inside loop: use scoped steps from context (current iteration only)
                scoped_state['steps'] = context['steps']

            variables = self.variable_substitutor.build_variables(
                run_state=scoped_state,
                context=context.get('context', {}),
                loop_vars=context.get('loop'),
                item=context.get('item')
            )

            # Add any custom loop variables
            for key, value in context.items():
                if key not in ['run', 'context', 'steps', 'loop', 'item']:
                    variables[key] = value

            # AT-73: Do NOT substitute variables in prompt text (input_file contents are literal)
            # The spec states: "input_file: read literal contents; no substitution inside file contents"
            # prompt = self.variable_substitutor.substitute(prompt, variables, track_undefined=False)

        prompt, asset_error = self._apply_asset_depends_on_prompt_injection(step, prompt)
        if asset_error is not None:
            return asset_error

        # Inject resolved consumes into provider prompt when requested.
        prompt = self._apply_consumes_prompt_injection(
            step,
            step.get('name', f'step_{self.current_step}'),
            prompt,
            state,
            runtime_step_id=runtime_step_id,
        )

        # Deterministic output contract prompt suffix (provider steps only).
        prompt = self._apply_output_contract_prompt_suffix(step, prompt)

        # AT-70: Prompt audit with debug mode (when no dependencies)
        if self.debug and prompt:
            self._write_prompt_audit(step.get('name', 'provider'), prompt, step.get('secrets'), step.get('env'))

        # Create retry policy for provider steps (AT-21)
        # Providers use global max_retries or step-specific retries
        if 'retries' in step:
            retry_policy = RetryPolicy.for_command(step['retries'])
        else:
            retry_policy = RetryPolicy.for_provider(
                max_retries=self.max_retries,
                delay_ms=self.retry_delay_ms
            )

        # Execute with retries
        attempt = 0
        result: Optional[Dict[str, Any]] = None

        # Build context for provider parameter substitution (AT-44)
        # This should include all variable namespaces
        provider_context = self._create_provider_context(context, state)

        # Import types
        from ..providers.types import ProviderParams
        from ..exec.output_capture import OutputCapture

        while True:
            # Prepare provider invocation
            params = ProviderParams(
                params=step.get('provider_params', {}),
                input_file=step.get('input_file'),
                output_file=step.get('output_file')
            )

            invocation, error = self.provider_executor.prepare_invocation(
                provider_name=step['provider'],
                params=params,
                context=provider_context,
                prompt_content=prompt,
                env=step.get('env'),
                secrets=step.get('secrets'),
                timeout_sec=step.get('timeout_sec')
            )

            if error or invocation is None:
                # Invocation preparation failed
                return {
                    'status': 'failed',
                    'exit_code': 2,
                    'error': error or {
                        'type': 'provider_preparation_failed',
                        'message': 'Failed to create provider invocation',
                    }
                }

            # Execute the prepared invocation
            exec_result = self._execute_provider_invocation(invocation)

            # Capture output according to specified mode
            capture_mode = step.get('output_capture', 'text')
            allow_parse_error = step.get('allow_parse_error', False)

            # Apply variable substitution to output_file if present
            output_file = None
            if 'output_file' in step:
                output_file_str = self.variable_substitutor.substitute(step['output_file'], variables)
                output_file = self._prepare_output_file_path(output_file_str)
                if output_file is None:
                    return self._contract_violation_result(
                        "Command execution failed",
                        {
                            "step": step.get('name', f'step_{self.current_step}'),
                            "reason": "output_file_path_escape",
                            "path": output_file_str,
                        },
                    )

            capturer = OutputCapture(
                workspace=self.workspace,
                logs_dir=self.state_manager.logs_dir if hasattr(self.state_manager, 'logs_dir') else None
            )

            # Convert mode string to CaptureMode enum
            from ..exec.output_capture import CaptureMode
            if capture_mode == 'text':
                mode = CaptureMode.TEXT
            elif capture_mode == 'lines':
                mode = CaptureMode.LINES
            else:
                mode = CaptureMode.JSON

            capture_result = capturer.capture(
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                step_name=step.get('name', 'provider'),
                mode=mode,
                output_file=output_file,
                allow_parse_error=allow_parse_error,
                exit_code=exec_result.exit_code
            )

            # Build result dict
            result = {
                'status': 'completed' if exec_result.exit_code == 0 else 'failed',
                'exit_code': exec_result.exit_code,
                'duration_ms': exec_result.duration_ms
            }

            # Add captured output
            result.update(capture_result.to_state_dict())

            # Add error info if present
            if exec_result.error:
                result['error'] = exec_result.error
            elif exec_result.missing_placeholders:
                result['error'] = {
                    'type': 'missing_placeholders',
                    'message': 'Missing placeholders in provider template',
                    'context': {
                        'missing_placeholders': exec_result.missing_placeholders
                    }
                }
            elif exec_result.invalid_prompt_placeholder:
                result['error'] = {
                    'type': 'invalid_prompt_placeholder',
                    'message': 'Invalid ${PROMPT} placeholder in stdin mode',
                    'context': {
                        'invalid_prompt_placeholder': True
                    }
                }

            # Check if should retry
            if retry_policy.should_retry(exec_result.exit_code, attempt):
                if self.debug:
                    print(f"Provider failed with exit code {exec_result.exit_code}, retrying (attempt {attempt + 1}/{retry_policy.max_retries})")
                retry_policy.wait()
                attempt += 1
                continue

            # No retry needed or max retries reached
            break

        # Ensure result is not None before returning
        if result is None:
            return {
                'status': 'failed',
                'exit_code': 1,
                'error': {'message': 'Provider execution failed with no result'}
            }

        # Add debug info if present (AT-35: injection truncation metadata)
        if debug_info:
            result['debug'] = debug_info

        return self._apply_expected_outputs_contract(step, result)

    def _call_frame_id(self, step: Dict[str, Any], state: Dict[str, Any]) -> str:
        """Derive a durable call-frame id from the authored call step and visit count."""
        if getattr(self, "resume_mode", False):
            call_frames = state.get('call_frames', {})
            step_id = self._step_id(step)
            if isinstance(call_frames, dict):
                for frame_id, frame in call_frames.items():
                    if not isinstance(frame, dict):
                        continue
                    if frame.get('call_step_id') != step_id:
                        continue
                    if frame.get('status') == 'completed':
                        continue
                    return frame_id

        step_name = step.get('name', f'step_{self.current_step}')
        step_visits = state.get('step_visits', {})
        visit_count = step_visits.get(step_name, 1) if isinstance(step_visits, dict) else 1
        return f"{self._step_id(step)}::visit::{visit_count}"

    def _resolve_call_bound_inputs(
        self,
        step: Dict[str, Any],
        imported_workflow: Dict[str, Any],
        state: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Resolve call-site literal and structured-ref bindings into typed callee inputs."""
        bindings = step.get('with', {})
        if bindings is None:
            bindings = {}
        if not isinstance(bindings, dict):
            return None, self._contract_violation_result(
                "Call input binding failed",
                {
                    "step": step.get('name', f'step_{self.current_step}'),
                    "reason": "invalid_with_bindings",
                },
            )

        input_specs = imported_workflow.get('inputs', {})
        if not isinstance(input_specs, dict):
            input_specs = {}

        bound_inputs: Dict[str, Any] = {}
        for input_name, input_spec in input_specs.items():
            if not isinstance(input_spec, dict):
                continue

            if input_name in bindings:
                raw_value = bindings[input_name]
                if isinstance(raw_value, dict):
                    ref = raw_value.get('ref')
                    try:
                        raw_value = self.reference_resolver.resolve(ref, state).value
                    except ReferenceResolutionError as exc:
                        return None, self._contract_violation_result(
                            "Call input binding failed",
                            {
                                "step": step.get('name', f'step_{self.current_step}'),
                                "input": input_name,
                                "reason": "unresolved_ref",
                                "ref": ref,
                                "error": str(exc),
                            },
                        )
                try:
                    bound_inputs[input_name] = validate_contract_value(
                        raw_value,
                        input_spec,
                        workspace=self.workspace,
                    )
                except OutputContractError as exc:
                    return None, self._contract_violation_result(
                        "Call input binding failed",
                        {
                            "step": step.get('name', f'step_{self.current_step}'),
                            "input": input_name,
                            "reason": "invalid_value",
                            "violations": exc.violations,
                        },
                    )
                continue

            if 'default' in input_spec:
                bound_inputs[input_name] = input_spec['default']
                continue
            if input_spec.get('required', True):
                return None, self._contract_violation_result(
                    "Call input binding failed",
                    {
                        "step": step.get('name', f'step_{self.current_step}'),
                        "input": input_name,
                        "reason": "missing_required_input",
                    },
                )

        return bound_inputs, None

    def _build_call_debug_payload(
        self,
        *,
        frame_id: str,
        step: Dict[str, Any],
        imported_workflow: Dict[str, Any],
        child_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build observability metadata for one executed call frame."""
        workflow_path = imported_workflow.get('__workflow_path')
        workflow_file = (
            _display_workflow_path(self.workspace, workflow_path)
            if isinstance(workflow_path, str) and workflow_path
            else None
        )
        call_frames = child_state.get('call_frames', {})
        nested_frames = list(call_frames.keys()) if isinstance(call_frames, dict) else []
        finalization = child_state.get('finalization', {})
        exports: Dict[str, Any] = {}
        output_specs = imported_workflow.get('outputs', {})
        workflow_outputs = child_state.get('workflow_outputs', {})
        if isinstance(output_specs, dict) and isinstance(workflow_outputs, dict):
            child_steps = child_state.get('steps', {}) if isinstance(child_state.get('steps'), dict) else {}
            for output_name, output_spec in output_specs.items():
                if output_name not in workflow_outputs or not isinstance(output_spec, dict):
                    continue
                binding = output_spec.get('from')
                ref = binding.get('ref') if isinstance(binding, dict) else None
                export_entry: Dict[str, Any] = {"source_ref": ref}
                if isinstance(ref, str) and ref.startswith("root.steps."):
                    step_name = ref[len("root.steps."):].split(".", 1)[0]
                    child_step = child_steps.get(step_name)
                    if isinstance(child_step, dict):
                        export_entry["source_step_name"] = step_name
                        if isinstance(child_step.get("step_id"), str):
                            export_entry["source_step_id"] = child_step.get("step_id")
                exports[output_name] = export_entry

        return {
            'call_frame_id': frame_id,
            'import_alias': step.get('call'),
            'workflow_file': workflow_file,
            'status': child_state.get('status'),
            'finalization': finalization if isinstance(finalization, dict) else {},
            'bound_inputs': child_state.get('bound_inputs', {}),
            'workflow_outputs': workflow_outputs if isinstance(workflow_outputs, dict) else {},
            'exports': exports,
            'nested_call_frames': nested_frames,
        }

    def _execute_call(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an imported workflow inline and persist call-frame state."""
        call_alias = step.get('call')
        imported_workflow = self.workflow.get('__imports', {}).get(call_alias)
        if not isinstance(imported_workflow, dict):
            return self._contract_violation_result(
                "Call execution failed",
                {
                    "step": step.get('name', f'step_{self.current_step}'),
                    "reason": "unknown_import_alias",
                    "call": call_alias,
                },
            )

        bound_inputs, binding_error = self._resolve_call_bound_inputs(step, imported_workflow, state)
        if binding_error is not None:
            return binding_error
        assert bound_inputs is not None

        frame_id = self._call_frame_id(step, state)
        call_frames = state.setdefault('call_frames', {})
        existing_frame = call_frames.get(frame_id) if isinstance(call_frames, dict) else None
        if not isinstance(call_frames, dict):
            call_frames = {}
            state['call_frames'] = call_frames

        child_state_manager = _CallFrameStateManager(
            parent_manager=self.state_manager,
            workflow=imported_workflow,
            frame_id=frame_id,
            call_step_name=step.get('name', f'step_{self.current_step}'),
            call_step_id=self._step_id(step),
            import_alias=str(call_alias),
            bound_inputs=bound_inputs,
            existing_frame=existing_frame if isinstance(existing_frame, dict) else None,
            observability=self.observability,
        )
        child_executor = WorkflowExecutor(
            workflow=imported_workflow,
            workspace=self.workspace,
            state_manager=child_state_manager,
            debug=self.debug,
            stream_output=self.stream_output,
            max_retries=self.max_retries,
            retry_delay_ms=self.retry_delay_ms,
            observability=self.observability,
            step_heartbeat_interval_sec=self.step_heartbeat_interval_sec,
        )
        child_state = child_executor.execute(resume=self.resume_mode)
        call_frames[frame_id] = child_state_manager._snapshot()

        debug_payload = self._build_call_debug_payload(
            frame_id=frame_id,
            step=step,
            imported_workflow=imported_workflow,
            child_state=child_state,
        )
        if child_state.get('status') != 'completed':
            return {
                'status': 'failed',
                'exit_code': 2,
                'duration_ms': 0,
                'error': {
                    'type': 'call_failed',
                    'message': 'Called workflow failed',
                    'context': {
                        'call': call_alias,
                        'call_frame_id': frame_id,
                        'workflow_file': debug_payload.get('workflow_file'),
                        'error': child_state.get('error'),
                    },
                },
                'debug': {'call': debug_payload},
            }

        workflow_outputs = child_state.get('workflow_outputs', {})
        if not isinstance(workflow_outputs, dict):
            workflow_outputs = {}
        return {
            'status': 'completed',
            'exit_code': 0,
            'duration_ms': 0,
            'artifacts': workflow_outputs,
            'debug': {'call': debug_payload},
        }

    def _execute_provider_invocation(self, invocation: Any) -> Any:
        """Execute provider invocation with backward-compatible call shape."""
        execute_fn = self.provider_executor.execute
        try:
            return execute_fn(invocation, stream_output=(self.debug or self.stream_output))
        except TypeError as exc:
            if "unexpected keyword argument 'stream_output'" not in str(exc):
                raise
            return execute_fn(invocation)

    def _apply_expected_outputs_contract(self, step: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate deterministic output contracts and attach parsed values to step result."""
        expected_outputs = step.get('expected_outputs')
        output_bundle = step.get('output_bundle')
        if not expected_outputs and not output_bundle:
            return result

        if result.get('exit_code', 0) != 0:
            # Only enforce contract after a successful process/provider execution.
            return result

        try:
            if output_bundle:
                artifacts = validate_output_bundle(output_bundle, workspace=self.workspace)
            else:
                artifacts = validate_expected_outputs(expected_outputs, workspace=self.workspace)
        except OutputContractError as contract_error:
            failed_result = dict(result)
            failed_result['status'] = 'failed'
            failed_result['exit_code'] = 2
            failed_result['error'] = {
                'type': 'contract_violation',
                'message': 'Expected output contract validation failed',
                'context': {
                    'violations': contract_error.violations
                }
            }
            return failed_result

        # Some workflows intentionally keep on-disk pointer files as the single source of truth.
        # In that mode, we still validate expected_outputs but avoid duplicating artifact values
        # into state.json under steps.<Step>.artifacts.
        persist_artifacts = step.get('persist_artifacts_in_state', True)
        if not persist_artifacts:
            return dict(result)

        enriched_result = dict(result)
        enriched_result['artifacts'] = artifacts
        return enriched_result

    def _apply_output_contract_prompt_suffix(self, step: Dict[str, Any], prompt: str) -> str:
        """Append deterministic output contract instructions to provider prompts."""
        expected_outputs = step.get('expected_outputs')
        if not expected_outputs:
            return prompt

        if step.get('inject_output_contract', True) is False:
            return prompt

        contract_block = render_output_contract_block(expected_outputs)
        if not prompt:
            return contract_block
        if prompt.endswith("\n"):
            return f"{prompt}\n{contract_block}"
        return f"{prompt}\n\n{contract_block}"

    def _apply_consumes_prompt_injection(
        self,
        step: Dict[str, Any],
        step_name: str,
        prompt: str,
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> str:
        """Inject resolved consume values into provider prompts (v1.2)."""
        if step.get('inject_consumes', True) is False:
            return prompt

        consumes = step.get('consumes')
        if not isinstance(consumes, list) or not consumes:
            return prompt

        resolved_consumes = state.get('_resolved_consumes', {})
        if not isinstance(resolved_consumes, dict):
            return prompt

        step_consumed_values = resolved_consumes.get(step_name, {})
        if (
            self._uses_qualified_identities()
            and (not isinstance(step_consumed_values, dict) or not step_consumed_values)
        ):
            consume_identity = runtime_step_id or self._step_id(step)
            step_consumed_values = resolved_consumes.get(consume_identity, {})
        if not isinstance(step_consumed_values, dict) or not step_consumed_values:
            return prompt

        prompt_consumes = step.get('prompt_consumes')
        allowed_names: Optional[set[str]] = None
        if prompt_consumes is not None:
            if not isinstance(prompt_consumes, list):
                return prompt
            allowed_names = {
                name for name in prompt_consumes
                if isinstance(name, str) and name.strip()
            }
            if not allowed_names:
                return prompt

        consumed_values: Dict[str, Any] = {}
        for key, value in step_consumed_values.items():
            if not isinstance(key, str):
                continue
            if allowed_names is not None and key not in allowed_names:
                continue
            if isinstance(value, (str, int, float, bool)):
                consumed_values[key] = value

        if not consumed_values:
            return prompt

        consumes_guidance: Dict[str, Dict[str, str]] = {}
        for consume in consumes:
            if not isinstance(consume, dict):
                continue
            artifact_name = consume.get('artifact')
            if not isinstance(artifact_name, str):
                continue
            if artifact_name not in consumed_values:
                continue

            guidance: Dict[str, str] = {}
            for guidance_key in ('description', 'format_hint', 'example'):
                guidance_value = consume.get(guidance_key)
                if isinstance(guidance_value, str):
                    guidance[guidance_key] = guidance_value
            if guidance:
                consumes_guidance[artifact_name] = guidance

        consumes_block = render_consumed_artifacts_block(
            consumed_values,
            consumes_guidance,
        )
        position = step.get('consumes_injection_position', 'prepend')
        if position == 'append':
            if not prompt:
                return consumes_block
            if prompt.endswith("\n"):
                return f"{prompt}\n{consumes_block}"
            return f"{prompt}\n\n{consumes_block}"

        if not prompt:
            return consumes_block
        if prompt.startswith("\n"):
            return f"{consumes_block}{prompt}"
        return f"{consumes_block}\n{prompt}"

    def _create_loop_context(
        self,
        step: Dict[str, Any],
        loop_context: Dict[str, Any],
        iteration_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create variable substitution context for a loop iteration.
        Implements AT-65: Inside for_each, ${steps.<Name>.*} refers only to current iteration.

        Args:
            step: Step being executed
            loop_context: Loop-specific variables (item, loop.index, loop.total)
            iteration_state: Current iteration's step results only

        Returns:
            Combined context dictionary
        """
        # Combine contexts (loop vars override globals)
        # Get run metadata from current state
        run_state = self.state_manager.load()
        run_metadata = {
            'id': run_state.run_id,
            'root': run_state.run_root,  # Include run.root for AT-64
            'timestamp_utc': run_state.started_at
        }

        # AT-65: Use iteration_state for steps.* variables to ensure loop scoping
        context = {
            'run': run_metadata,
            'context': self.variables,
            'steps': iteration_state,  # Only current iteration's results
            **loop_context  # Loop vars override
        }
        return context

    def _create_provider_context(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create context for provider parameter substitution.

        Ensures all variable namespaces are available for AT-44.

        Args:
            context: Current execution context
            state: Current state

        Returns:
            Combined context for provider params
        """
        # Ensure we have all namespaces available
        run_state = self.state_manager.load()
        steps_namespace = context.get('steps', state.get('steps', {}))
        if not isinstance(steps_namespace, dict):
            steps_namespace = state.get('steps', {})
        provider_context = {
            'run': {
                'id': run_state.run_id,
                'timestamp_utc': run_state.started_at,
                'root': run_state.run_root or ''  # Use run_root from state
            },
            'context': context.get('context', self.variables),
            'inputs': run_state.bound_inputs,
            'steps': steps_namespace,
        }

        # Add loop variables if present
        if 'loop' in context:
            provider_context['loop'] = context['loop']
        if 'item' in context:
            provider_context['item'] = context['item']

        return provider_context

    def _build_substitution_variables(self, context: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, str]:
        """Build variables dict for dependency pattern substitution.

        Args:
            context: Context with run/context/loop namespaces
            state: Current state

        Returns:
            Flattened dict of variable name to value for substitution
        """
        # Flatten the context structure for substitution
        variables = {}

        # Add run namespace
        if 'run' in context:
            for key, value in context['run'].items():
                variables[f'run.{key}'] = str(value)

        # Add context namespace
        if 'context' in context:
            for key, value in context['context'].items():
                variables[f'context.{key}'] = str(value)

        # Add workflow inputs namespace
        if 'inputs' in context:
            for key, value in context['inputs'].items():
                variables[f'inputs.{key}'] = str(value)
        else:
            bound_inputs = state.get('bound_inputs', {})
            if isinstance(bound_inputs, dict):
                for key, value in bound_inputs.items():
                    variables[f'inputs.{key}'] = str(value)

        # Add loop namespace if present
        if 'loop' in context:
            for key, value in context['loop'].items():
                variables[f'loop.{key}'] = str(value)

        # Add item if present
        if 'item' in context:
            variables['item'] = str(context['item'])

        return variables


    def _record_step_error(
        self,
        state: Dict[str, Any],
        step_name: str,
        exit_code: int,
        error: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Record a step execution error in state.

        Args:
            state: Current state
            step_name: Name of failed step
            exit_code: Exit code
            error: Error details

        Returns:
            Updated state
        """
        if 'steps' not in state:
            state['steps'] = {}

        state['steps'][step_name] = {
            'exit_code': exit_code,
            'error': error,
            'failed': True
        }

        return state

    def _execute_assert(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if context is None:
            context = {}
        scoped_state = state.copy()
        steps_namespace = context.get('steps')
        if isinstance(steps_namespace, dict):
            scoped_state['steps'] = steps_namespace
        variables = self.variable_substitutor.build_variables(
            run_state=scoped_state,
            context=context.get('context', self.workflow.get('context', {})),
            loop_vars=context.get('loop'),
            item=context.get('item'),
        )
        for key, value in context.items():
            if key not in {'run', 'context', 'steps', 'loop', 'item'}:
                variables[key] = value
        try:
            passed = self.condition_evaluator.evaluate(step.get('assert'), variables, state, scope=scope)
        except Exception as exc:
            return {
                'status': 'failed',
                'exit_code': 2,
                'duration_ms': 0,
                'error': {
                    'type': 'predicate_evaluation_failed',
                    'message': str(exc),
                    'context': {'assert': step.get('assert')},
                },
            }

        if passed:
            return {
                'status': 'completed',
                'exit_code': 0,
                'duration_ms': 0,
            }

        return {
            'status': 'failed',
            'exit_code': 3,
            'duration_ms': 0,
            'error': {
                'type': 'assert_failed',
                'message': 'Assertion failed',
                'context': {'assert': step.get('assert')},
            },
        }

    def _execute_set_scalar(self, step: Dict[str, Any]) -> Dict[str, Any]:
        return self._execute_scalar_step(
            step=step,
            artifact_name=step['set_scalar'].get('artifact'),
            candidate_value=step['set_scalar'].get('value'),
        )

    def _execute_increment_scalar(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        node = step['increment_scalar']
        artifact_name = node.get('artifact')
        current_value, error = self._latest_published_scalar_value(artifact_name, state)
        if error is not None:
            return error

        registry = self.workflow.get('artifacts', {})
        artifact_spec = registry.get(artifact_name, {}) if isinstance(registry, dict) else {}
        artifact_type = artifact_spec.get('type')
        increment_by = node.get('by')
        if artifact_type == 'float':
            next_value = float(current_value) + float(increment_by)
        else:
            next_value = current_value + increment_by

        return self._execute_scalar_step(
            step=step,
            artifact_name=artifact_name,
            candidate_value=next_value,
        )

    def _execute_scalar_step(
        self,
        step: Dict[str, Any],
        artifact_name: Any,
        candidate_value: Any,
    ) -> Dict[str, Any]:
        registry = self.workflow.get('artifacts', {})
        artifact_spec = registry.get(artifact_name, {}) if isinstance(registry, dict) else {}
        validated_value = self._validate_scalar_value(artifact_name, artifact_spec, candidate_value)
        if isinstance(validated_value, dict) and validated_value.get('status') == 'failed':
            return validated_value

        return {
            'status': 'completed',
            'exit_code': 0,
            'duration_ms': 0,
            'artifacts': {
                artifact_name: validated_value,
            },
        }

    def _latest_published_scalar_value(
        self,
        artifact_name: Any,
        state: Dict[str, Any],
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        if not isinstance(artifact_name, str) or not artifact_name:
            return None, self._contract_violation_result(
                "Scalar bookkeeping failed",
                {"reason": "missing_artifact_name"},
            )

        artifact_versions = state.get('artifact_versions', {})
        candidates = artifact_versions.get(artifact_name, []) if isinstance(artifact_versions, dict) else []
        latest_entry: Optional[Dict[str, Any]] = None
        latest_version = -1

        if isinstance(candidates, list):
            for entry in candidates:
                if not isinstance(entry, dict):
                    continue
                version = entry.get('version')
                if isinstance(version, int) and version > latest_version:
                    latest_entry = entry
                    latest_version = version

        if latest_entry is None:
            return None, self._contract_violation_result(
                "Scalar bookkeeping failed",
                {
                    "artifact": artifact_name,
                    "reason": "no_published_versions",
                },
            )

        return latest_entry.get('value'), None

    def _validate_scalar_value(
        self,
        artifact_name: Any,
        artifact_spec: Any,
        candidate_value: Any,
    ) -> Any:
        if not isinstance(artifact_name, str) or not artifact_name:
            return self._contract_violation_result(
                "Scalar bookkeeping failed",
                {"reason": "missing_artifact_name"},
            )
        if not isinstance(artifact_spec, dict) or artifact_spec.get('kind') != 'scalar':
            return self._contract_violation_result(
                "Scalar bookkeeping failed",
                {
                    "artifact": artifact_name,
                    "reason": "invalid_scalar_artifact",
                },
            )

        artifact_type = artifact_spec.get('type')
        if artifact_type == 'integer':
            if type(candidate_value) is not int:
                return self._invalid_scalar_value_result(artifact_name, artifact_type, candidate_value)
            return candidate_value
        if artifact_type == 'float':
            if type(candidate_value) not in {int, float}:
                return self._invalid_scalar_value_result(artifact_name, artifact_type, candidate_value)
            return float(candidate_value)
        if artifact_type == 'bool':
            if not isinstance(candidate_value, bool):
                return self._invalid_scalar_value_result(artifact_name, artifact_type, candidate_value)
            return candidate_value
        if artifact_type == 'enum':
            allowed = artifact_spec.get('allowed')
            if (
                not isinstance(candidate_value, str)
                or not isinstance(allowed, list)
                or candidate_value not in allowed
            ):
                return self._invalid_scalar_value_result(artifact_name, artifact_type, candidate_value)
            return candidate_value

        return self._invalid_scalar_value_result(artifact_name, str(artifact_type), candidate_value)

    def _invalid_scalar_value_result(
        self,
        artifact_name: str,
        artifact_type: str,
        candidate_value: Any,
    ) -> Dict[str, Any]:
        return self._contract_violation_result(
            "Scalar bookkeeping failed",
            {
                "artifact": artifact_name,
                "reason": "invalid_scalar_value",
                "expected_type": artifact_type,
                "value": candidate_value,
            },
        )

    def _resolve_structured_output_artifacts(
        self,
        outputs: Dict[str, Any],
        state: Dict[str, Any],
        *,
        failure_message: str,
        selection_key: str,
        selection_value: str,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any] | None:
        """Resolve one structured statement's declared outputs into validated artifacts."""
        artifacts: Dict[str, Any] = {}
        for output_name, spec in outputs.items():
            if not isinstance(spec, dict):
                continue
            binding = spec.get('from')
            ref = binding.get('ref') if isinstance(binding, dict) else None
            if not isinstance(ref, str) or not ref:
                return self._contract_violation_result(
                    failure_message,
                    {
                        "reason": "missing_output_ref",
                        "output": output_name,
                        selection_key: selection_value,
                    },
                )
            try:
                raw_value = resolve_typed_operand({"ref": ref}, state, scope=scope)
            except PredicateEvaluationError as exc:
                return self._contract_violation_result(
                    failure_message,
                    {
                        "reason": "unresolved_output_ref",
                        "output": output_name,
                        selection_key: selection_value,
                        "ref": ref,
                        "error": str(exc),
                    },
                )
            try:
                artifacts[output_name] = validate_contract_value(raw_value, spec, workspace=self.workspace)
            except OutputContractError as exc:
                return self._contract_violation_result(
                    failure_message,
                    {
                        "reason": "invalid_output_value",
                        "output": output_name,
                        selection_key: selection_value,
                        "ref": ref,
                        "violations": exc.violations,
                    },
                )
        return artifacts

    def _execute_structured_if_branch(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Record one lowered branch marker for a structured if/else statement."""
        metadata = step.get('structured_if_branch', {})
        branch_name = metadata.get('branch_name') if isinstance(metadata, dict) else None
        statement_name = metadata.get('statement_name') if isinstance(metadata, dict) else None
        return {
            'status': 'completed',
            'exit_code': 0,
            'duration_ms': 0,
            'debug': {
                'structured_if': {
                    'statement_name': statement_name,
                    'selected_branch': branch_name,
                    'branch_marker': True,
                }
            },
        }

    def _execute_structured_if_join(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Materialize selected branch outputs onto the lowered join node."""
        metadata = step.get('structured_if_join', {})
        branches = metadata.get('branches', {}) if isinstance(metadata, dict) else {}
        if not isinstance(branches, dict) or not branches:
            return self._contract_violation_result(
                "Structured if/else join failed",
                {"reason": "missing_branch_metadata"},
            )

        steps_state = state.get('steps', {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        branch_statuses: Dict[str, Any] = {}
        selected_branch: Optional[str] = None
        for branch_name, branch in branches.items():
            if not isinstance(branch, dict):
                continue
            marker_name = branch.get('marker')
            marker_result = steps_state.get(marker_name) if isinstance(marker_name, str) else None
            marker_status = marker_result.get('status') if isinstance(marker_result, dict) else 'pending'
            branch_statuses[branch_name] = {
                'status': marker_status,
                'marker': marker_name,
                'steps': list(branch.get('steps', [])) if isinstance(branch.get('steps'), list) else [],
            }
            if marker_status != 'skipped':
                if selected_branch is not None:
                    return self._contract_violation_result(
                        "Structured if/else join failed",
                        {
                            "reason": "multiple_selected_branches",
                            "branches": branch_statuses,
                        },
                    )
                selected_branch = branch_name

        if selected_branch is None:
            return self._contract_violation_result(
                "Structured if/else join failed",
                {
                    "reason": "no_selected_branch",
                    "branches": branch_statuses,
                },
            )

        selected = branches.get(selected_branch, {})
        outputs = selected.get('outputs', {}) if isinstance(selected, dict) else {}
        if not isinstance(outputs, dict):
            outputs = {}

        artifacts = self._resolve_structured_output_artifacts(
            outputs,
            state,
            failure_message="Structured if/else join failed",
            selection_key="branch",
            selection_value=selected_branch,
        )
        if not isinstance(artifacts, dict):
            return artifacts

        return {
            'status': 'completed',
            'exit_code': 0,
            'duration_ms': 0,
            'artifacts': artifacts,
            'debug': {
                'structured_if': {
                    'selected_branch': selected_branch,
                    'branches': branch_statuses,
                }
            },
        }

    def _execute_structured_match_case(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Record one lowered case marker for a structured match statement."""
        metadata = step.get('structured_match_case', {})
        case_name = metadata.get('case_name') if isinstance(metadata, dict) else None
        statement_name = metadata.get('statement_name') if isinstance(metadata, dict) else None
        return {
            'status': 'completed',
            'exit_code': 0,
            'duration_ms': 0,
            'debug': {
                'structured_match': {
                    'statement_name': statement_name,
                    'selected_case': case_name,
                    'case_marker': True,
                }
            },
        }

    def _execute_structured_match_join(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Materialize selected case outputs onto the lowered join node."""
        metadata = step.get('structured_match_join', {})
        cases = metadata.get('cases', {}) if isinstance(metadata, dict) else {}
        if not isinstance(cases, dict) or not cases:
            return self._contract_violation_result(
                "Structured match join failed",
                {"reason": "missing_case_metadata"},
            )

        steps_state = state.get('steps', {})
        if not isinstance(steps_state, dict):
            steps_state = {}

        case_statuses: Dict[str, Any] = {}
        selected_case: Optional[str] = None
        for case_name, case in cases.items():
            if not isinstance(case, dict):
                continue
            marker_name = case.get('marker')
            marker_result = steps_state.get(marker_name) if isinstance(marker_name, str) else None
            marker_status = marker_result.get('status') if isinstance(marker_result, dict) else 'pending'
            case_statuses[case_name] = {
                'status': marker_status,
                'marker': marker_name,
                'steps': list(case.get('steps', [])) if isinstance(case.get('steps'), list) else [],
            }
            if marker_status != 'skipped':
                if selected_case is not None:
                    return self._contract_violation_result(
                        "Structured match join failed",
                        {
                            "reason": "multiple_selected_cases",
                            "cases": case_statuses,
                        },
                    )
                selected_case = case_name

        if selected_case is None:
            return self._contract_violation_result(
                "Structured match join failed",
                {
                    "reason": "no_selected_case",
                    "cases": case_statuses,
                },
            )

        selected = cases.get(selected_case, {})
        outputs = selected.get('outputs', {}) if isinstance(selected, dict) else {}
        if not isinstance(outputs, dict):
            outputs = {}

        artifacts = self._resolve_structured_output_artifacts(
            outputs,
            state,
            failure_message="Structured match join failed",
            selection_key="case",
            selection_value=selected_case,
        )
        if not isinstance(artifacts, dict):
            return artifacts

        return {
            'status': 'completed',
            'exit_code': 0,
            'duration_ms': 0,
            'artifacts': artifacts,
            'debug': {
                'structured_match': {
                    'selected_case': selected_case,
                    'cases': case_statuses,
                    'selector_ref': metadata.get('selector_ref'),
                }
            },
        }

    def _persist_step_result(
        self,
        state: Dict[str, Any],
        step_name: str,
        step: Dict[str, Any],
        result: Dict[str, Any],
        phase_hint: Optional[str] = None,
        class_hint: Optional[str] = None,
        retryable_hint: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if 'steps' not in state:
            state['steps'] = {}

        finalized = self._attach_outcome(step, result, phase_hint, class_hint, retryable_hint)
        finalized.setdefault('name', step_name)
        finalized.setdefault('step_id', self._step_id(step))
        step_visits = state.get('step_visits', {})
        visit_count = step_visits.get(step_name) if isinstance(step_visits, dict) else None
        if isinstance(visit_count, int):
            finalized.setdefault('visit_count', visit_count)
        state['steps'][step_name] = finalized

        from ..state import StepResult

        step_result = StepResult(
            status=finalized.get('status', 'completed' if finalized.get('exit_code', 0) == 0 else 'failed'),
            name=finalized.get('name'),
            step_id=finalized.get('step_id'),
            exit_code=finalized.get('exit_code'),
            duration_ms=finalized.get('duration_ms', 0),
            output=finalized.get('output'),
            truncated=finalized.get('truncated', False),
            lines=finalized.get('lines'),
            json=finalized.get('json'),
            error=finalized.get('error'),
            debug=finalized.get('debug'),
            artifacts=finalized.get('artifacts'),
            skipped=finalized.get('skipped', False),
            files=finalized.get('files'),
            wait_duration_ms=finalized.get('wait_duration_ms'),
            poll_count=finalized.get('poll_count'),
            timed_out=finalized.get('timed_out'),
            outcome=finalized.get('outcome'),
            visit_count=finalized.get('visit_count'),
        )
        self.state_manager.update_step(step_name, step_result)
        self._emit_step_summary(step_name, step, finalized)
        return finalized

    def _attach_outcome(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
        phase_hint: Optional[str] = None,
        class_hint: Optional[str] = None,
        retryable_hint: Optional[bool] = None,
    ) -> Dict[str, Any]:
        finalized = dict(result)
        status = finalized.get('status')
        if status is None:
            exit_code = finalized.get('exit_code', 0)
            status = 'completed' if exit_code == 0 else 'failed'
            finalized['status'] = status

        if status == 'skipped':
            finalized['outcome'] = {
                'status': 'skipped',
                'phase': 'pre_execution',
                'class': 'skipped',
                'retryable': False,
            }
            return finalized

        if status == 'completed':
            finalized['outcome'] = {
                'status': 'completed',
                'phase': 'execution',
                'class': 'completed',
                'retryable': False,
            }
            return finalized

        error = finalized.get('error')
        error_type = error.get('type') if isinstance(error, dict) else None
        step_type = self._resolve_step_type(step)
        normalized_class = class_hint
        normalized_phase = phase_hint
        retryable = retryable_hint

        if normalized_class is None:
            if error_type == 'assert_failed':
                normalized_class = 'assert_failed'
            elif error_type in {
                'undefined_variables',
                'missing_secrets',
                'provider_not_found',
                'provider_preparation_failed',
                'substitution_error',
                'validation_error',
            }:
                normalized_class = 'pre_execution_failed'
            elif error_type == 'contract_violation':
                normalized_class = 'contract_violation'
            elif error_type == 'timeout' or finalized.get('timed_out') or finalized.get('exit_code') == 124:
                normalized_class = 'timeout'
            elif step_type == 'provider' and finalized.get('exit_code', 0) != 0:
                normalized_class = 'provider_failed'
            elif step_type == 'command' and finalized.get('exit_code', 0) != 0:
                normalized_class = 'command_failed'
            else:
                normalized_class = 'pre_execution_failed'

        if normalized_phase is None:
            if normalized_class in {'assert_failed', 'command_failed', 'provider_failed', 'timeout'}:
                normalized_phase = 'execution'
            elif normalized_class == 'contract_violation':
                normalized_phase = 'post_execution'
            else:
                normalized_phase = 'pre_execution'

        if retryable is None:
            retryable = normalized_class == 'provider_failed'

        finalized['outcome'] = {
            'status': 'failed',
            'phase': normalized_phase,
            'class': normalized_class,
            'retryable': retryable,
        }
        return finalized

    # Stub implementations for other step types
    def _execute_wait_for(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute wait_for step and record results in state (AT-60)."""
        step_name = step['name']
        step_result = self._execute_wait_for_result(step)
        phase_hint = None
        class_hint = None
        if step_result.get('timed_out'):
            phase_hint = 'execution'
            class_hint = 'timeout'
        elif isinstance(step_result.get('error'), dict) and step_result['error'].get('type') == 'path_safety_error':
            phase_hint = 'pre_execution'
            class_hint = 'pre_execution_failed'
        self._persist_step_result(
            state,
            step_name,
            step,
            step_result,
            phase_hint=phase_hint,
            class_hint=class_hint,
            retryable_hint=False if class_hint == 'pre_execution_failed' else None,
        )

        return state

    def _execute_wait_for_result(self, step: Dict[str, Any]) -> Dict[str, Any]:
        step_name = step['name']
        wait_config = step.get('wait_for', {})
        result = self.step_executor.execute_wait_for(step_name, wait_config)
        step_result = result.to_state_dict()
        step_result['status'] = 'completed' if result.exit_code == 0 else 'failed'
        return step_result

    def _execute_provider(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute provider step without loop context."""
        context = {'context': state.get('context', {})}
        return self._execute_provider_with_context(step, context, state)

    def _execute_command(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command step without loop context."""
        context = {'context': state.get('context', {})}
        return self._execute_command_with_context(step, context, state)
