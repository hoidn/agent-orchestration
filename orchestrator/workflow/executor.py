"""
Workflow executor with for-each loop support.
Implements AT-3, AT-13: Dynamic for-each execution with pointer resolution.
"""

import json
import logging
import threading
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..state import ForEachState, RunState, StateManager, StepResult
from ..exec.step_executor import StepExecutor
from ..exec.retry import RetryPolicy
from ..providers.executor import ProviderExecutor
from ..providers.registry import ProviderRegistry
from ..providers.types import ProviderSessionMode, ProviderSessionRequest
from ..deps.resolver import DependencyResolver
from ..deps.injector import DependencyInjector
from ..contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
    validate_expected_outputs,
    validate_output_bundle,
)
from .pointers import PointerResolver
from .conditions import ConditionEvaluator
from ..security.secrets import SecretsManager
from ..variables.substitution import VariableSubstitutor
from ..observability.summary import SummaryObserver
from .assets import WorkflowAssetResolver
from .calls import CallExecutor
from .dataflow import DataflowManager
from .executable_ir import (
    BlockOutputAddress,
    CallBoundaryNode,
    CallOutputAddress,
    ExecutableNodeKind,
    FinalizationStepNode,
    ExecutableContract,
    IfBranchMarkerNode,
    IfJoinNode,
    LoopOutputAddress,
    MatchCaseMarkerNode,
    MatchJoinNode,
    NodeResultAddress,
    RepeatUntilFrameNode,
    WorkflowInputAddress,
)
from .finalization import FinalizationController
from .identity import iteration_step_id, runtime_step_id
from .loaded_bundle import workflow_bundle, workflow_legacy_dict, workflow_provenance
from .loops import LoopExecutor
from .outcomes import OutcomeRecorder
from .predicates import (
    AllOfPredicateNode,
    AnyOfPredicateNode,
    ArtifactBoolPredicateNode,
    ComparePredicateNode,
    NotPredicateNode,
    PredicateEvaluationError,
    ScorePredicateNode,
    is_numeric_predicate_value,
    resolve_typed_operand,
)
from .prompting import PromptComposer
from .references import ReferenceResolutionError, ReferenceResolver
from .resume_planner import ResumePlanner, ResumeStateIntegrityError
from .runtime_context import RuntimeContext
from .runtime_types import RoutingDecision, StepExecutionIdentity
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

    def calculate_checksum(self, workflow_path: Path) -> str:
        """Delegate checksum calculation so nested call frames can nest again."""
        return self.parent_manager.calculate_checksum(workflow_path)

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
        workflow: Any,
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
        self.loaded_bundle = workflow_bundle(workflow)
        legacy_workflow = workflow_legacy_dict(workflow)
        if legacy_workflow is None:
            raise TypeError(f"Unsupported workflow type for execution: {type(workflow).__name__}")
        self.workflow = legacy_workflow
        self.projection = self.loaded_bundle.projection if self.loaded_bundle is not None else None
        self.executable_ir = self.loaded_bundle.ir if self.loaded_bundle is not None else None
        self.workspace = workspace
        self.state_manager = state_manager
        self.debug = debug
        self.stream_output = stream_output
        self.observability = observability or {}

        # Initialize secrets manager
        self.secrets_manager = SecretsManager()

        # Initialize provider registry (load from workflow providers if present)
        self.provider_registry = ProviderRegistry()
        if 'providers' in self.workflow:
            errors = self.provider_registry.register_from_workflow(self.workflow['providers'])
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
        provenance = workflow_provenance(workflow)
        workflow_path = provenance.workflow_path if provenance is not None else None
        self.asset_resolver = (
            WorkflowAssetResolver(Path(workflow_path))
            if workflow_path is not None
            else None
        )
        self.prompt_composer = PromptComposer(
            workspace=workspace,
            asset_resolver=self.asset_resolver,
        )
        self.dataflow_manager = DataflowManager(
            workspace=workspace,
            workflow=self.workflow,
            uses_qualified_identities=self._uses_qualified_identities,
            workflow_version_at_least=self._workflow_version_at_least,
            step_id_resolver=lambda step: self._step_id(step),
            contract_violation_result=self._contract_violation_result,
            persist_state=self._persist_dataflow_state,
            substitute_path_template=self._substitute_path_template,
            resolve_workspace_path=self._resolve_workspace_path,
            current_step_index=lambda: self.current_step,
        )

        # Execution state
        self.current_step = 0
        self.body_steps = self.workflow.get('steps', [])
        self.finalization = self.workflow.get('finally') if isinstance(self.workflow.get('finally'), dict) else None
        self.finalization_steps = (
            self.finalization.get('steps', [])
            if isinstance(self.finalization, dict) and isinstance(self.finalization.get('steps'), list)
            else []
        )
        self._step_node_ids: List[Optional[str]] = []
        self.body_steps, self.finalization_steps, self._step_node_ids = self._ordered_top_level_steps()
        self.finalization_start_index = len(self.body_steps)
        self.steps = list(self.body_steps) + list(self.finalization_steps)
        self._use_ir_topology = (
            self.loaded_bundle is not None and self.executable_ir is not None and self.projection is not None
        )
        self._step_by_node_id = {
            node_id: step
            for node_id, step in zip(self._step_node_ids, self.steps)
            if isinstance(node_id, str) and isinstance(step, dict)
        }
        self._execution_index_by_node_id = {
            node_id: index
            for index, node_id in enumerate(self._step_node_ids)
            if isinstance(node_id, str)
        }
        self._projection_index_by_presentation_name = self._build_projection_index_by_presentation_name()
        self.variables = self.workflow.get('variables', {})
        self.global_secrets = self.workflow.get('secrets', [])
        self.resume_planner = ResumePlanner()
        self.finalization_controller = FinalizationController(
            finalization=self.finalization,
            finalization_steps=self.finalization_steps,
            finalization_start_index=self.finalization_start_index,
            finalization_node_ids=list(self.executable_ir.finalization_region) if self.executable_ir is not None else [],
            finalization_entry_node_id=(
                self.executable_ir.finalization_entry_node_id if self.executable_ir is not None else None
            ),
            projection=self.projection,
            has_workflow_outputs=bool(
                self.executable_ir.outputs if self.executable_ir is not None else self.workflow.get("outputs")
            ),
            persist_state=self._persist_finalization_state,
            finalization_failure_error=self._finalization_failure_error,
        )
        self.loop_executor = LoopExecutor(self)
        self.call_executor = CallExecutor(self)
        self.outcome_recorder = OutcomeRecorder(
            state_manager=self.state_manager,
            step_id_resolver=lambda step: self._step_id(step),
            step_type_resolver=self._resolve_step_type,
            summary_emitter=self._emit_step_summary,
        )

        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.step_heartbeat_interval_sec = step_heartbeat_interval_sec
        self._active_provider_sessions: Dict[str, Dict[str, Any]] = {}

    def _step_id(self, step: Dict[str, Any], fallback_index: Optional[int] = None) -> str:
        """Return the durable identity for a top-level step."""
        projection_entry = self._projection_entry_for_step(
            step,
            self.current_step if fallback_index is None else fallback_index,
        )
        if projection_entry is not None:
            return projection_entry.step_id
        return runtime_step_id(step, self.current_step if fallback_index is None else fallback_index)

    def _step_identity(
        self,
        step: Dict[str, Any],
        *,
        step_index: Optional[int] = None,
        step_name: Optional[str] = None,
        step_id: Optional[str] = None,
        visit_count: Optional[int] = None,
    ) -> StepExecutionIdentity:
        """Build typed identity metadata for one step execution."""
        resolved_index = self.current_step if step_index is None else step_index
        projection_entry = self._projection_entry_for_step(step, resolved_index)
        if projection_entry is not None:
            resolved_name = step_name or projection_entry.presentation_key
            resolved_step_id = step_id or projection_entry.step_id
            if isinstance(projection_entry.compatibility_index, int):
                resolved_index = projection_entry.compatibility_index
        else:
            resolved_name = step_name or step.get("name", f"step_{resolved_index}")
            resolved_step_id = step_id or self._step_id(step, resolved_index)
        return StepExecutionIdentity(
            name=resolved_name,
            step_id=resolved_step_id,
            step_index=resolved_index,
            visit_count=visit_count,
        )

    def _ordered_top_level_steps(self) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Optional[str]]]:
        """Return top-level body/finalization adapter steps ordered by projection when available."""
        body_steps = self.workflow.get("steps", [])
        if not isinstance(body_steps, list):
            body_steps = []
        finalization_steps = (
            self.finalization.get("steps", [])
            if isinstance(self.finalization, dict) and isinstance(self.finalization.get("steps"), list)
            else []
        )
        if self.loaded_bundle is None or self.executable_ir is None:
            step_node_ids = [
                step.get("step_id") if isinstance(step, dict) and isinstance(step.get("step_id"), str) else None
                for step in list(body_steps) + list(finalization_steps)
            ]
            return list(body_steps), list(finalization_steps), step_node_ids

        steps_by_node_id: Dict[str, Dict[str, Any]] = {}
        for step in list(body_steps) + list(finalization_steps):
            if isinstance(step, dict) and isinstance(step.get("step_id"), str):
                steps_by_node_id[step["step_id"]] = step

        ordered_body_steps = self._ordered_projection_steps(
            steps_by_node_id,
            self.executable_ir.body_region,
            region_name="body",
        )
        ordered_finalization_steps = self._ordered_projection_steps(
            steps_by_node_id,
            self.executable_ir.finalization_region,
            region_name="finalization",
        )
        ordered_node_ids = list(self.executable_ir.body_region) + list(self.executable_ir.finalization_region)
        return ordered_body_steps, ordered_finalization_steps, ordered_node_ids

    @staticmethod
    def _ordered_projection_steps(
        steps_by_node_id: Dict[str, Dict[str, Any]],
        node_ids: tuple[str, ...],
        *,
        region_name: str,
    ) -> List[Dict[str, Any]]:
        """Materialize legacy adapter steps in executable-node order."""
        ordered_steps: List[Dict[str, Any]] = []
        for node_id in node_ids:
            step = steps_by_node_id.get(node_id)
            if step is None:
                raise ValueError(
                    f"Legacy workflow adapter is missing {region_name} step for typed node '{node_id}'"
                )
            ordered_steps.append(step)
        return ordered_steps

    def _first_execution_node_id(self) -> Optional[str]:
        """Return the first top-level executable node id when bundle-backed IR is available."""
        if not self._use_ir_topology or self.projection is None:
            return None
        ordered_node_ids = self.projection.ordered_execution_node_ids()
        return ordered_node_ids[0] if ordered_node_ids else None

    def _step_for_node_id(self, node_id: str) -> Dict[str, Any]:
        """Return the legacy adapter step for one executable node id."""
        step = self._step_by_node_id.get(node_id)
        if step is None:
            raise ValueError(f"Legacy workflow adapter is missing top-level step for typed node '{node_id}'")
        return step

    def _execution_index_for_node_id(self, node_id: str) -> int:
        """Return the combined execution index for one top-level executable node id."""
        index = self._execution_index_by_node_id.get(node_id)
        if isinstance(index, int):
            return index
        if self.projection is not None:
            entry = self.projection.entries_by_node_id.get(node_id)
            if entry is not None:
                if isinstance(entry.compatibility_index, int):
                    return entry.compatibility_index
                if isinstance(entry.finalization_index, int):
                    return len(self.body_steps) + entry.finalization_index
        raise ValueError(f"Typed node '{node_id}' does not map to a top-level execution index")

    def _node_id_for_execution_index(self, step_index: int) -> Optional[str]:
        """Return the executable node id for one top-level execution index."""
        if self.projection is not None:
            return self.projection.node_id_for_execution_index(step_index)
        if 0 <= step_index < len(self._step_node_ids):
            node_id = self._step_node_ids[step_index]
            return node_id if isinstance(node_id, str) else None
        return None

    def _fallthrough_node_id(self, current_node_id: str) -> Optional[str]:
        """Return the next IR fallthrough target for one executable node id."""
        if self.executable_ir is None:
            return None
        node = self.executable_ir.nodes.get(current_node_id)
        return node.fallthrough_node_id if node is not None else None

    def _projection_entry_for_step(
        self,
        step: Dict[str, Any],
        step_index: Optional[int] = None,
    ) -> Optional[Any]:
        """Return projection metadata for one top-level step when a bundle is present."""
        if self.projection is None:
            return None

        node_id = None
        if isinstance(step_index, int) and 0 <= step_index < len(self._step_node_ids):
            node_id = self._step_node_ids[step_index]
        if not isinstance(node_id, str):
            candidate_step_id = step.get("step_id")
            if isinstance(candidate_step_id, str):
                node_id = candidate_step_id
        if not isinstance(node_id, str):
            return None
        return self.projection.entries_by_node_id.get(node_id)

    def _build_projection_index_by_presentation_name(self) -> Dict[str, int]:
        """Index projection presentation keys to top-level compatibility indices."""
        if self.projection is None:
            return {}
        return {
            entry.presentation_key: entry.compatibility_index
            for entry in self.projection.entries_by_node_id.values()
            if isinstance(entry.compatibility_index, int)
        }

    def _executable_node_for_step(self, step: Dict[str, Any]) -> Any:
        """Return the typed executable node backing one legacy compatibility step."""
        if self.executable_ir is None or not isinstance(step, dict):
            return None
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id:
            return None
        return self.executable_ir.nodes.get(step_id)

    def _execution_kind_for_step(self, step: Dict[str, Any]) -> Optional[ExecutableNodeKind]:
        """Return the typed execution kind for one step when bundle-backed IR is available."""
        node = self._executable_node_for_step(step)
        if isinstance(node, FinalizationStepNode):
            return node.execution_kind
        if node is None:
            return None
        return node.kind

    @staticmethod
    def _scoped_node_results(
        scope: Optional[Dict[str, Dict[str, Any]]],
        key: str,
    ) -> Optional[Mapping[str, Dict[str, Any]]]:
        if not isinstance(scope, dict):
            return None
        results = scope.get(key)
        return results if isinstance(results, Mapping) else None

    def _result_for_node_id(
        self,
        node_id: str,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Resolve one node id to the visible runtime result payload."""
        for scope_key in ("self_node_results", "parent_node_results", "root_node_results"):
            indexed_results = self._scoped_node_results(scope, scope_key)
            if indexed_results is None:
                continue
            candidate = indexed_results.get(node_id)
            if isinstance(candidate, dict):
                return candidate

        presentation_key = (
            self.projection.presentation_key_by_node_id.get(node_id)
            if self.projection is not None
            else None
        )
        candidate_maps: list[Mapping[str, Any]] = []
        if isinstance(scope, dict):
            for key in ("self_steps", "parent_steps", "root_steps"):
                mapping = scope.get(key)
                if isinstance(mapping, Mapping):
                    candidate_maps.append(mapping)
        steps_state = state.get("steps")
        if isinstance(steps_state, Mapping):
            candidate_maps.append(steps_state)

        for mapping in candidate_maps:
            if isinstance(presentation_key, str):
                candidate = mapping.get(presentation_key)
                if isinstance(candidate, dict):
                    return candidate

        raise ReferenceResolutionError(f"Bound address target step '{node_id}' is unavailable")

    def _resolve_bound_address(
        self,
        address: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Any:
        """Resolve one lowered bound address against persisted runtime state."""
        if isinstance(address, WorkflowInputAddress):
            bound_inputs = (
                scope.get("inputs")
                if isinstance(scope, dict) and isinstance(scope.get("inputs"), dict)
                else state.get("bound_inputs", {})
            )
            if not isinstance(bound_inputs, dict) or address.input_name not in bound_inputs:
                raise ReferenceResolutionError(
                    f"Bound workflow input '{address.input_name}' is unavailable"
                )
            return bound_inputs[address.input_name]

        result = self._result_for_node_id(address.node_id, state, scope=scope)
        if isinstance(address, NodeResultAddress):
            if address.field == "exit_code":
                if "exit_code" not in result:
                    raise ReferenceResolutionError(
                        f"Bound step field '{address.node_id}.{address.field}' is unavailable"
                    )
                return result["exit_code"]
            container = result.get(address.field)
            if not isinstance(container, dict) or address.member not in container:
                raise ReferenceResolutionError(
                    f"Bound step field '{address.node_id}.{address.field}' is unavailable"
                )
            return container[address.member]

        if isinstance(address, (BlockOutputAddress, LoopOutputAddress, CallOutputAddress)):
            artifacts = result.get("artifacts")
            output_name = address.output_name
            if not isinstance(artifacts, dict) or output_name not in artifacts:
                raise ReferenceResolutionError(
                    f"Bound step output '{address.node_id}.artifacts.{output_name}' is unavailable"
                )
            return artifacts[output_name]

        raise ReferenceResolutionError(f"Unsupported bound address type '{type(address).__name__}'")

    def _resolve_runtime_value(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Any:
        """Resolve one runtime value that may be a bound address or legacy ref binding."""
        if isinstance(
            value,
            (
                WorkflowInputAddress,
                NodeResultAddress,
                BlockOutputAddress,
                LoopOutputAddress,
                CallOutputAddress,
            ),
        ):
            return self._resolve_bound_address(value, state, scope=scope)
        if isinstance(value, dict) and set(value.keys()) == {"ref"}:
            return resolve_typed_operand(value, state, scope=scope)
        return value

    def _evaluate_bound_predicate(
        self,
        predicate: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        """Evaluate one lowered typed predicate node against runtime state."""
        try:
            if isinstance(predicate, ArtifactBoolPredicateNode):
                value = self._resolve_runtime_value(predicate.ref, state, scope=scope)
                if not isinstance(value, bool):
                    raise PredicateEvaluationError("artifact_bool ref must resolve to a bool")
                return value

            if isinstance(predicate, ComparePredicateNode):
                left = self._resolve_runtime_value(predicate.left, state, scope=scope)
                right = self._resolve_runtime_value(predicate.right, state, scope=scope)
                if predicate.op == "eq":
                    return left == right
                if predicate.op == "ne":
                    return left != right
                if predicate.op in {"lt", "lte", "gt", "gte"}:
                    if not is_numeric_predicate_value(left) or not is_numeric_predicate_value(right):
                        raise PredicateEvaluationError(
                            "ordered compare operators require numeric operands"
                        )
                if predicate.op == "lt":
                    return left < right
                if predicate.op == "lte":
                    return left <= right
                if predicate.op == "gt":
                    return left > right
                if predicate.op == "gte":
                    return left >= right
                raise PredicateEvaluationError(f"Unsupported compare operator '{predicate.op}'")

            if isinstance(predicate, ScorePredicateNode):
                score_value = self._resolve_runtime_value(predicate.ref, state, scope=scope)
                if not is_numeric_predicate_value(score_value):
                    raise PredicateEvaluationError("score requires a numeric ref")
                if predicate.gt is not None and not score_value > predicate.gt:
                    return False
                if predicate.gte is not None and not score_value >= predicate.gte:
                    return False
                if predicate.lt is not None and not score_value < predicate.lt:
                    return False
                if predicate.lte is not None and not score_value <= predicate.lte:
                    return False
                return True

            if isinstance(predicate, AllOfPredicateNode):
                return all(
                    self._evaluate_bound_predicate(item, state, scope=scope)
                    for item in predicate.items
                )

            if isinstance(predicate, AnyOfPredicateNode):
                return any(
                    self._evaluate_bound_predicate(item, state, scope=scope)
                    for item in predicate.items
                )

            if isinstance(predicate, NotPredicateNode):
                return not self._evaluate_bound_predicate(predicate.item, state, scope=scope)
        except ReferenceResolutionError as exc:
            raise PredicateEvaluationError(str(exc)) from exc

        return self.condition_evaluator.evaluate(predicate, {}, state, scope=scope)

    def _evaluate_condition_expression(
        self,
        condition: Any,
        variables: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        """Evaluate either a legacy condition dict or one lowered predicate node."""
        if isinstance(
            condition,
            (
                ArtifactBoolPredicateNode,
                ComparePredicateNode,
                ScorePredicateNode,
                AllOfPredicateNode,
                AnyOfPredicateNode,
                NotPredicateNode,
            ),
        ):
            return self._evaluate_bound_predicate(condition, state, scope=scope)
        return self.condition_evaluator.evaluate(condition, variables, state, scope=scope)

    def _structured_if_branches(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return typed structured-if branch metadata with legacy fallback."""
        node = self._executable_node_for_step(step)
        if isinstance(node, IfJoinNode) and self.executable_ir is not None and self.projection is not None:
            branches: Dict[str, Any] = {}
            markers = [
                candidate
                for candidate in self.executable_ir.nodes.values()
                if isinstance(candidate, IfBranchMarkerNode)
                and candidate.statement_name == node.statement_name
                and candidate.region == node.region
            ]
            for marker in markers:
                branch_steps = [
                    candidate.presentation_name
                    for candidate in self.executable_ir.nodes.values()
                    if candidate.region == marker.region
                    and candidate.node_id.startswith(f"{marker.node_id}.")
                ]
                branch_steps.sort(
                    key=lambda name: self._projection_index_by_presentation_name.get(name, len(self.steps))
                )
                branches[marker.branch_name] = {
                    "marker": marker.presentation_name,
                    "step_id": marker.step_id,
                    "steps": branch_steps,
                    "outputs": node.branch_outputs.get(marker.branch_name, {}),
                }
            return branches
        metadata = step.get("structured_if_join", {})
        branches = metadata.get("branches") if isinstance(metadata, dict) else {}
        return branches if isinstance(branches, Mapping) else {}

    def _structured_match_cases(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return typed structured-match case metadata with legacy fallback."""
        node = self._executable_node_for_step(step)
        if isinstance(node, MatchJoinNode) and self.executable_ir is not None and self.projection is not None:
            cases: Dict[str, Any] = {}
            markers = [
                candidate
                for candidate in self.executable_ir.nodes.values()
                if isinstance(candidate, MatchCaseMarkerNode)
                and candidate.statement_name == node.statement_name
                and candidate.region == node.region
            ]
            for marker in markers:
                case_steps = [
                    candidate.presentation_name
                    for candidate in self.executable_ir.nodes.values()
                    if candidate.region == marker.region
                    and candidate.node_id.startswith(f"{marker.node_id}.")
                ]
                case_steps.sort(
                    key=lambda name: self._projection_index_by_presentation_name.get(name, len(self.steps))
                )
                cases[marker.case_name] = {
                    "marker": marker.presentation_name,
                    "step_id": marker.step_id,
                    "steps": case_steps,
                    "outputs": node.case_outputs.get(marker.case_name, {}),
                }
            return cases
        metadata = step.get("structured_match_join", {})
        cases = metadata.get("cases") if isinstance(metadata, dict) else {}
        return cases if isinstance(cases, Mapping) else {}

    def _structured_guard_condition(self, step: Dict[str, Any]) -> tuple[Any, bool]:
        """Return one structured guard condition, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, IfBranchMarkerNode):
            return node.guard_condition, node.invert_guard
        if isinstance(node, MatchCaseMarkerNode):
            return ComparePredicateNode(
                left=node.selector_address,
                op="eq",
                right=node.case_name,
            ), False
        guard = step.get("structured_if_guard", {})
        condition = guard.get("condition") if isinstance(guard, dict) else None
        invert = bool(guard.get("invert")) if isinstance(guard, dict) else False
        return condition, invert

    def _when_condition(self, step: Dict[str, Any]) -> Any:
        """Return one step-level when condition, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        bound = getattr(node, "bound_when_predicate", None) if node is not None else None
        return bound if bound is not None else step.get("when")

    def _assert_condition(self, step: Dict[str, Any]) -> Any:
        """Return one step-level assert condition, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        bound = getattr(node, "bound_assert_predicate", None) if node is not None else None
        return bound if bound is not None else step.get("assert")

    def _structured_output_contracts(
        self,
        step: Dict[str, Any],
        selection_value: str,
    ) -> Mapping[str, Any]:
        """Return one structured statement's output contracts for the selected path."""
        node = self._executable_node_for_step(step)
        if isinstance(node, IfJoinNode):
            return node.branch_outputs.get(selection_value, {})
        if isinstance(node, MatchJoinNode):
            return node.case_outputs.get(selection_value, {})
        metadata = step.get("structured_if_join") or step.get("structured_match_join") or {}
        selections = metadata.get("branches") or metadata.get("cases") or {}
        if not isinstance(selections, Mapping):
            return {}
        selected = selections.get(selection_value, {})
        outputs = selected.get("outputs") if isinstance(selected, Mapping) else {}
        return outputs if isinstance(outputs, Mapping) else {}

    def _repeat_until_condition(self, step: Dict[str, Any]) -> Any:
        """Return one repeat_until stop condition, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, RepeatUntilFrameNode):
            return node.condition
        block = step.get("repeat_until", {})
        return block.get("condition") if isinstance(block, dict) else None

    def _repeat_until_output_contracts(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return one repeat_until output contract map, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, RepeatUntilFrameNode):
            return node.output_contracts
        block = step.get("repeat_until", {})
        outputs = block.get("outputs") if isinstance(block, dict) else {}
        return outputs if isinstance(outputs, Mapping) else {}

    def _call_input_bindings(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return one call step's bound input bindings, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, CallBoundaryNode):
            return node.bound_inputs
        bindings = step.get("with", {})
        return bindings if isinstance(bindings, Mapping) else {}

    def _json_safe_runtime_value(self, value: Any) -> Any:
        """Convert bound runtime metadata into a JSON-safe error/debug payload."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {
                str(key): self._json_safe_runtime_value(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._json_safe_runtime_value(item) for item in value]
        if is_dataclass(value):
            return {
                key: self._json_safe_runtime_value(item)
                for key, item in vars(value).items()
            }
        return str(value)

    def _runtime_context(
        self,
        context: Optional[Dict[str, Any]],
        state: Dict[str, Any],
        *,
        default_context: Optional[Dict[str, Any]] = None,
        parent_steps: Optional[Dict[str, Any]] = None,
    ) -> RuntimeContext:
        """Normalize the loose execution context bundle used by step helpers."""
        return RuntimeContext.from_mapping(
            context,
            default_context=default_context or self.workflow.get("context", {}),
            parent_steps=parent_steps,
            root_steps=state.get("steps", {}),
        )

    def _resume_entry_is_terminal(self, entry: Any) -> bool:
        """Return True when persisted step state is fully completed/skipped for resume purposes."""
        return self.resume_planner.entry_is_terminal(entry)

    def _determine_resume_restart_index(self, state: Dict[str, Any]) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart."""
        return self.resume_planner.determine_restart_index(
            state,
            self.steps,
            projection=self.projection,
        )

    def _determine_resume_restart_node_id(self, state: Dict[str, Any]) -> Optional[str]:
        """Determine the top-level executable node id where resumed execution should restart."""
        return self.resume_planner.determine_restart_node_id(
            state,
            self.steps,
            projection=self.projection,
        )

    def _fail_resume_state_integrity(
        self,
        error_type: str,
        message: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        error = {
            "type": error_type,
            "message": message,
            "context": context,
        }
        self.state_manager.fail_run(error)
        persisted = self.state_manager.load().to_dict()
        persisted["status"] = "failed"
        return persisted

    def _resume_for_each_has_pending_work(self, state: Dict[str, Any], step_name: str) -> bool:
        """Return True when persisted loop bookkeeping shows unfinished iterations."""
        return self.resume_planner.for_each_has_pending_work(state, step_name)

    def _resume_repeat_until_has_pending_work(self, state: Dict[str, Any], step_name: str) -> bool:
        """Return True when persisted repeat_until bookkeeping shows unfinished iterations."""
        return self.resume_planner.repeat_until_has_pending_work(state, step_name)

    @staticmethod
    def _provider_session_config(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return the authored provider_session block when present."""
        provider_session = step.get("provider_session")
        return provider_session if isinstance(provider_session, dict) else None

    def _prepare_provider_session_visit(
        self,
        step: Dict[str, Any],
        *,
        step_name: str,
        step_id: str,
        visit_count: int,
    ) -> None:
        """Create the canonical session metadata and spool before current_step is persisted."""
        provider_session = self._provider_session_config(step)
        if provider_session is None:
            return

        visit_info = self.state_manager.initialize_provider_session_visit(
            provider_name=str(step.get("provider", "")),
            step_name=step_name,
            step_id=step_id,
            visit_count=visit_count,
            mode=str(provider_session.get("mode", "")),
        )
        visit_info.update(
            {
                "mode": provider_session.get("mode"),
                "step_id": step_id,
                "visit_count": visit_count,
            }
        )
        self._active_provider_sessions[step_name] = visit_info

    def _active_provider_session(self, step_name: str) -> Optional[Dict[str, Any]]:
        """Return the current provider-session visit metadata for one top-level step."""
        session_info = self._active_provider_sessions.get(step_name)
        return session_info if isinstance(session_info, dict) else None

    def _update_active_provider_session_metadata(
        self,
        step_name: str,
        **updates: Any,
    ) -> Optional[Dict[str, Any]]:
        """Merge updates into the active provider-session metadata record."""
        session_info = self._active_provider_session(step_name)
        if session_info is None:
            return None
        metadata_path = session_info.get("metadata_path")
        if not isinstance(metadata_path, str) or not metadata_path:
            return None
        metadata = self.state_manager.update_provider_session_metadata(metadata_path, updates)
        session_info.update(updates)
        return metadata

    def _finalize_active_provider_session(
        self,
        step_name: str,
        *,
        step_status: str,
        publication_state: str,
        session_id: Optional[str],
        metadata_mode: Optional[str],
        command_variant: Optional[str],
        parser_summary: Optional[Dict[str, Any]] = None,
        retain_transport_spool: bool,
    ) -> None:
        """Finalize visit-scoped provider-session metadata after state publication."""
        session_info = self._active_provider_session(step_name)
        if session_info is None:
            return

        transport_spool_path = session_info.get("transport_spool_path")
        spool_path = Path(transport_spool_path) if isinstance(transport_spool_path, str) else None
        captured_transport_bytes = 0
        if spool_path is not None and spool_path.exists():
            try:
                captured_transport_bytes = spool_path.stat().st_size
            except OSError:
                captured_transport_bytes = 0

        retained_spool_path: Optional[str] = None
        if retain_transport_spool and spool_path is not None and spool_path.exists():
            retained_spool_path = str(spool_path)

        self._update_active_provider_session_metadata(
            step_name,
            step_status=step_status,
            publication_state=publication_state,
            session_id=session_id,
            metadata_mode=metadata_mode,
            command_variant=command_variant,
            parser_summary=parser_summary or {},
            captured_transport_bytes=captured_transport_bytes,
            transport_spool_path=retained_spool_path,
        )
        if not retain_transport_spool and spool_path is not None and spool_path.exists():
            spool_path.unlink()
        self._active_provider_sessions.pop(step_name, None)

    def _quarantine_provider_session_resume_guard(
        self,
        state: Dict[str, Any],
        guard: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Project an interrupted provider-session visit into durable run-level failure state."""
        step_name = guard["step_name"]
        step_id = guard["step_id"]
        visit_count = guard["visit_count"]
        metadata_path, transport_spool_path = self.state_manager.provider_session_paths(step_id, visit_count)
        metadata_synthesized = not metadata_path.exists()
        if not transport_spool_path.exists():
            transport_spool_path.write_text("", encoding="utf-8")

        metadata_updates = {
            "provider": guard.get("provider"),
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": visit_count,
            "mode": guard.get("mode"),
            "step_status": "interrupted",
            "publication_state": "quarantined_interrupted_visit",
            "metadata_synthesized": metadata_synthesized,
            "captured_transport_bytes": transport_spool_path.stat().st_size if transport_spool_path.exists() else 0,
            "transport_spool_path": str(transport_spool_path),
        }
        self.state_manager.update_provider_session_metadata(metadata_path, metadata_updates)

        error = {
            "type": "provider_session_interrupted_visit_quarantined",
            "message": "An interrupted provider-session visit was quarantined.",
            "context": {
                "step_name": step_name,
                "step_id": step_id,
                "visit_count": visit_count,
                "metadata_path": str(metadata_path),
                "transport_spool_path": str(transport_spool_path),
                "metadata_synthesized": metadata_synthesized,
            },
        }
        self.state_manager.fail_run(
            error,
            clear_current_step=True,
            expected_step_id=step_id,
            expected_visit_count=visit_count,
        )
        persisted = self.state_manager.load().to_dict()
        persisted["status"] = "failed"
        return persisted

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
        return self.finalization_controller.initial_state()

    def _persist_finalization_state(self, state: Dict[str, Any]) -> None:
        """Persist finalization bookkeeping when present."""
        finalization = state.get('finalization')
        if isinstance(finalization, dict):
            self.state_manager.update_finalization_state(finalization)

    def _ensure_finalization_state(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Ensure run state contains the finalization bookkeeping structure."""
        return self.finalization_controller.ensure_state(state)

    def _activate_finalization(self, state: Dict[str, Any], body_status: str) -> None:
        """Mark finalization as pending/running after the workflow body settles."""
        self.finalization_controller.activate(state, body_status)

    def _record_finalization_step_start(self, state: Dict[str, Any], final_index: int, body_status: str) -> None:
        """Persist which cleanup step is currently running."""
        self.finalization_controller.record_step_start(state, final_index, body_status)

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
        self.finalization_controller.record_step_result(
            state,
            final_index,
            step_name,
            failed,
            result,
            body_status,
        )

    def _record_finalization_settled_result(
        self,
        state: Dict[str, Any],
        step_index: Optional[int],
        step_name: str,
        body_status: str,
        *,
        step_node_id: Optional[str] = None,
    ) -> None:
        """Project one settled cleanup result into finalization bookkeeping."""
        self.finalization_controller.record_settled_result(
            state,
            step_index,
            step_name,
            body_status,
            step_node_id=step_node_id,
        )

    def _maybe_continue_into_finalization(
        self,
        next_step: Optional[str],
        step_index: Optional[int],
        terminal_status: str,
        state: Dict[str, Any],
        *,
        step_node_id: Optional[str] = None,
    ) -> RoutingDecision:
        """Redirect body termination into finalization when configured."""
        return self.finalization_controller.continue_into_finalization(
            next_step,
            step_index,
            terminal_status,
            state,
            step_node_id=step_node_id,
        )

    def _is_finalization_step(
        self,
        step_index: Optional[int] = None,
        *,
        step_node_id: Optional[str] = None,
    ) -> bool:
        """Return True when the current step belongs to the appended finalization slice."""
        return self.finalization_controller.is_finalization_step(
            step_index=step_index,
            step_node_id=step_node_id,
        )

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
        state['_resolved_consumes'] = {}
        if resume:
            session_guard = self.resume_planner.detect_interrupted_provider_session_visit(
                state,
                self.steps,
                projection=self.projection,
            )
            if session_guard is not None:
                if session_guard.get("kind") == "existing_quarantine":
                    state['status'] = 'failed'
                    return state
                if session_guard.get("kind") == "quarantine":
                    return self._quarantine_provider_session_resume_guard(state, session_guard)
                if session_guard.get("kind") == "integrity_error":
                    context = session_guard.get("context")
                    if not isinstance(context, dict):
                        context = {
                            "step_name": session_guard.get("step_name"),
                            "step_id": session_guard.get("step_id"),
                            "visit_count": session_guard.get("visit_count"),
                        }
                    return self._fail_resume_state_integrity(
                        "provider_session_resume_state_integrity_error",
                        str(session_guard.get("message", "Provider-session resume state is invalid.")),
                        context,
                    )
        state.pop('error', None)
        if state.get('status') != 'running':
            self.state_manager.update_status('running')
            state['status'] = 'running'
        terminal_status = 'completed'

        try:
            # Execute steps with control flow support
            try:
                if self._use_ir_topology:
                    resume_restart_node_id = self._determine_resume_restart_node_id(state) if resume else None
                    resume_restart_index = None
                else:
                    resume_restart_index = self._determine_resume_restart_index(state) if resume else None
                    resume_restart_node_id = None
            except ResumeStateIntegrityError as exc:
                return self._fail_resume_state_integrity(
                    "resume_state_integrity_error",
                    str(exc),
                    dict(exc.context),
                )
            step_index = 0
            current_node_id = resume_restart_node_id
            if self._use_ir_topology and current_node_id is None:
                current_node_id = self._first_execution_node_id()
            while True:
                if self._use_ir_topology:
                    if current_node_id is None:
                        break
                    step_index = self._execution_index_for_node_id(current_node_id)
                    step = self._step_for_node_id(current_node_id)
                else:
                    if step_index >= len(self.steps):
                        break
                    step = self.steps[step_index]
                    current_node_id = self._node_id_for_execution_index(step_index)
                self.current_step = step_index

                # Check if step should be executed
                identity = self._step_identity(step, step_index=step_index)
                step_name = identity.name
                step_id = identity.step_id
                resume_current_step = False
                if resume_restart_index is not None:
                    if step_index < resume_restart_index:
                        logger.info(f"Skipping step before resume restart point: {step_name}")
                        step_index += 1
                        continue
                    if step_index == resume_restart_index:
                        resume_current_step = True
                        resume_restart_index = None

                is_finalization_step = self._is_finalization_step(
                    step_index,
                    step_node_id=current_node_id,
                )
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
                        step_node_id=current_node_id,
                    )
                    next_step = self._handle_control_flow(
                        step,
                        state,
                        step_name,
                        step_index,
                        on_error,
                        current_node_id=current_node_id,
                    )
                    next_step_index, next_node_id, terminal_status, should_break = (
                        self._advance_after_top_level_route(
                            current_index=step_index,
                            current_node_id=current_node_id,
                            next_step=next_step,
                            terminal_status=terminal_status,
                            state=state,
                        )
                    )
                    if should_break:
                        break
                    if self._use_ir_topology:
                        current_node_id = next_node_id
                    else:
                        assert next_step_index is not None
                        step_index = next_step_index
                    continue

                # Check structured branch guards before the step's own when clause.
                guard_condition, invert = self._structured_guard_condition(step)
                if guard_condition is not None:
                    runtime_context = self._runtime_context({}, state)
                    variables = runtime_context.build_variables(self.variable_substitutor, state)
                    try:
                        should_execute = self._evaluate_condition_expression(
                            guard_condition,
                            variables,
                            state,
                        )
                        if invert:
                            should_execute = not should_execute
                    except Exception as e:
                        error_info = {
                            'type': 'predicate_evaluation_failed',
                            'message': f"Condition evaluation failed: {e}",
                            'context': {'condition': self._json_safe_runtime_value(guard_condition)}
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
                            step_node_id=current_node_id,
                        )
                        next_step = self._handle_control_flow(
                            step,
                            state,
                            step_name,
                            step_index,
                            on_error,
                            current_node_id=current_node_id,
                        )
                        next_step_index, next_node_id, terminal_status, should_break = (
                            self._advance_after_top_level_route(
                                current_index=step_index,
                                current_node_id=current_node_id,
                                next_step=next_step,
                                terminal_status=terminal_status,
                                state=state,
                            )
                        )
                        if should_break:
                            break
                        if self._use_ir_topology:
                            current_node_id = next_node_id
                        else:
                            assert next_step_index is not None
                            step_index = next_step_index
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
                            step_node_id=current_node_id,
                        )
                        next_step = self._handle_control_flow(
                            step,
                            state,
                            step_name,
                            step_index,
                            on_error,
                            current_node_id=current_node_id,
                        )
                        next_step_index, next_node_id, terminal_status, should_break = (
                            self._advance_after_top_level_route(
                                current_index=step_index,
                                current_node_id=current_node_id,
                                next_step=next_step,
                                terminal_status=terminal_status,
                                state=state,
                            )
                        )
                        if should_break:
                            break
                        if self._use_ir_topology:
                            current_node_id = next_node_id
                        else:
                            assert next_step_index is not None
                            step_index = next_step_index
                        continue

                # Check conditional execution (AT-37, AT-46, AT-47)
                when_condition = self._when_condition(step)
                if when_condition is not None:
                    # Build variables for condition evaluation
                    runtime_context = self._runtime_context({}, state)
                    variables = runtime_context.build_variables(self.variable_substitutor, state)

                    # Evaluate condition
                    try:
                        should_execute = self._evaluate_condition_expression(
                            when_condition,
                            variables,
                            state,
                        )
                    except Exception as e:
                        # Condition evaluation error - record and skip
                        error_info = {
                            'type': 'predicate_evaluation_failed',
                            'message': f"Condition evaluation failed: {e}",
                            'context': {'condition': self._json_safe_runtime_value(when_condition)}
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
                            step_node_id=current_node_id,
                        )
                        next_step = self._handle_control_flow(
                            step,
                            state,
                            step_name,
                            step_index,
                            on_error,
                            current_node_id=current_node_id,
                        )
                        next_step_index, next_node_id, terminal_status, should_break = (
                            self._advance_after_top_level_route(
                                current_index=step_index,
                                current_node_id=current_node_id,
                                next_step=next_step,
                                terminal_status=terminal_status,
                                state=state,
                            )
                        )
                        if should_break:
                            break
                        if self._use_ir_topology:
                            current_node_id = next_node_id
                        else:
                            assert next_step_index is not None
                            step_index = next_step_index
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
                            step_node_id=current_node_id,
                        )
                        next_step = self._handle_control_flow(
                            step,
                            state,
                            step_name,
                            step_index,
                            on_error,
                            current_node_id=current_node_id,
                        )
                        next_step_index, next_node_id, terminal_status, should_break = (
                            self._advance_after_top_level_route(
                                current_index=step_index,
                                current_node_id=current_node_id,
                                next_step=next_step,
                                terminal_status=terminal_status,
                                state=state,
                            )
                        )
                        if should_break:
                            break
                        if self._use_ir_topology:
                            current_node_id = next_node_id
                        else:
                            assert next_step_index is not None
                            step_index = next_step_index
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
                        step_node_id=current_node_id,
                    )
                    next_step = self._handle_control_flow(
                        step,
                        state,
                        step_name,
                        step_index,
                        on_error,
                        current_node_id=current_node_id,
                    )
                    next_step_index, next_node_id, terminal_status, should_break = (
                        self._advance_after_top_level_route(
                            current_index=step_index,
                            current_node_id=current_node_id,
                            next_step=next_step,
                            terminal_status=terminal_status,
                            state=state,
                        )
                    )
                    if should_break:
                        break
                    if self._use_ir_topology:
                        current_node_id = next_node_id
                    else:
                        assert next_step_index is not None
                        step_index = next_step_index
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
                        step_node_id=current_node_id,
                    )

                    next_step = self._handle_control_flow(
                        step,
                        state,
                        step_name,
                        step_index,
                        on_error,
                        current_node_id=current_node_id,
                    )
                    next_step_index, next_node_id, terminal_status, should_break = (
                        self._advance_after_top_level_route(
                            current_index=step_index,
                            current_node_id=current_node_id,
                            next_step=next_step,
                            terminal_status=terminal_status,
                            state=state,
                        )
                    )
                    if should_break:
                        break
                    if self._use_ir_topology:
                        current_node_id = next_node_id
                    else:
                        assert next_step_index is not None
                        step_index = next_step_index
                    continue

                if isinstance(visit_count, int):
                    self._prepare_provider_session_visit(
                        step,
                        step_name=identity.name,
                        step_id=identity.step_id,
                        visit_count=visit_count,
                    )

                self.state_manager.start_step(
                    identity.name,
                    identity.step_index if identity.step_index is not None else step_index,
                    self._resolve_step_type(step),
                    step_id=identity.step_id,
                    visit_count=visit_count,
                )

                # Execute based on step type
                with self._step_heartbeat(step_name):
                    self._run_top_level_step(
                        step,
                        state,
                        step_name=step_name,
                        resume_current_step=resume_current_step,
                    )

                # Handle control flow after step execution (AT-56, AT-57, AT-58)
                next_step = self._handle_control_flow(
                    step,
                    state,
                    step_name,
                    step_index,
                    on_error,
                    current_node_id=current_node_id,
                )
                if is_finalization_step:
                    self._record_finalization_settled_result(
                        state,
                        step_index,
                        step_name,
                        finalization_body_status,
                        step_node_id=current_node_id,
                    )
                    finalization_result = state.get('steps', {}).get(step_name)
                    if isinstance(finalization_result, dict) and finalization_result.get('status') == 'failed':
                        if next_step is None:
                            next_step = '_stop'

                next_step_index, next_node_id, terminal_status, should_break = (
                    self._advance_after_top_level_route(
                        current_index=step_index,
                        current_node_id=current_node_id,
                        next_step=next_step,
                        terminal_status=terminal_status,
                        state=state,
                    )
                )
                if should_break:
                    break
                if self._use_ir_topology:
                    current_node_id = next_node_id
                else:
                    assert next_step_index is not None
                    step_index = next_step_index
        except Exception:
            terminal_status = 'failed'
            self.state_manager.update_status(terminal_status)
            raise

        finalization = self._ensure_finalization_state(state)

        if terminal_status == 'completed':
            try:
                output_specs = (
                    self.executable_ir.outputs
                    if self.executable_ir is not None
                    else self.workflow.get('outputs')
                )
                workflow_outputs = resolve_workflow_outputs(
                    output_specs,
                    state,
                    workspace=self.workspace,
                    resolve_source=self._resolve_runtime_value,
                )
            except WorkflowSignatureError as exc:
                terminal_status = 'failed'
                state['error'] = exc.error
                if isinstance(finalization, dict) and output_specs:
                    finalization['workflow_outputs_status'] = 'failed'
                    self._persist_finalization_state(state)
            else:
                state['workflow_outputs'] = workflow_outputs
                state.pop('error', None)
                if isinstance(finalization, dict) and output_specs:
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
        execution_kind = self._execution_kind_for_step(step)
        if execution_kind is ExecutableNodeKind.IF_BRANCH_MARKER:
            return 'structured_if_branch'
        if execution_kind is ExecutableNodeKind.IF_JOIN:
            return 'structured_if_join'
        if execution_kind is ExecutableNodeKind.MATCH_CASE_MARKER:
            return 'structured_match_case'
        if execution_kind is ExecutableNodeKind.MATCH_JOIN:
            return 'structured_match_join'
        if execution_kind is ExecutableNodeKind.PROVIDER:
            return 'provider'
        if execution_kind is ExecutableNodeKind.COMMAND:
            return 'command'
        if execution_kind is ExecutableNodeKind.WAIT_FOR:
            return 'wait_for'
        if execution_kind is ExecutableNodeKind.ASSERT:
            return 'assert'
        if execution_kind is ExecutableNodeKind.SET_SCALAR:
            return 'set_scalar'
        if execution_kind is ExecutableNodeKind.INCREMENT_SCALAR:
            return 'increment_scalar'
        if execution_kind is ExecutableNodeKind.CALL_BOUNDARY:
            return 'call'
        if execution_kind is ExecutableNodeKind.FOR_EACH:
            return 'for_each'
        if execution_kind is ExecutableNodeKind.REPEAT_UNTIL_FRAME:
            return 'repeat_until'
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

    def _advance_after_top_level_route(
        self,
        *,
        current_index: int,
        current_node_id: Optional[str],
        next_step: Any,
        terminal_status: str,
        state: Dict[str, Any],
    ) -> tuple[Optional[int], Optional[str], str, bool]:
        """Advance top-level execution through legacy indices or typed node ids."""
        finalization_decision = self._maybe_continue_into_finalization(
            next_step,
            current_index,
            terminal_status,
            state,
            step_node_id=current_node_id,
        )
        terminal_status = finalization_decision.terminal_status
        if finalization_decision.next_node_id is not None:
            return None, finalization_decision.next_node_id, terminal_status, False
        if finalization_decision.next_step_index is not None:
            return finalization_decision.next_step_index, None, terminal_status, False
        if finalization_decision.should_break:
            return None, None, terminal_status, True

        if self._use_ir_topology and isinstance(current_node_id, str):
            if isinstance(next_step, str) and next_step not in {"_end", "_stop"}:
                next_node_id = next_step
            elif isinstance(next_step, int):
                next_node_id = self._node_id_for_execution_index(next_step)
            else:
                next_node_id = self._fallthrough_node_id(current_node_id)
            if next_node_id is not None:
                self._increment_transition_count(state)
            return None, next_node_id, terminal_status, False

        target_index = self._resolve_next_step_index(current_index, next_step)
        if target_index is None:
            return current_index + 1, None, terminal_status, False
        self._increment_transition_count(state)
        return target_index, None, terminal_status, False

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
        return self.loop_executor.collect_persisted_iteration_state(state, loop_name, index)

    def _store_loop_iteration_result(
        self,
        loop_results: List[Dict[str, Any]],
        index: int,
        iteration_state: Dict[str, Any],
    ) -> None:
        """Store an iteration result at its stable list position."""
        self.loop_executor.store_loop_iteration_result(loop_results, index, iteration_state)

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
        self.loop_executor.persist_for_each_progress(
            state,
            loop_name,
            items,
            completed_indices,
            current_index,
            loop_results,
        )

    def _persist_repeat_until_progress(
        self,
        state: Dict[str, Any],
        loop_name: str,
        progress: Dict[str, Any],
        frame_result: Dict[str, Any],
    ) -> None:
        """Persist repeat_until bookkeeping plus the current loop-frame snapshot."""
        self.loop_executor.persist_repeat_until_progress(state, loop_name, progress, frame_result)

    def _repeat_until_iteration_resume_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        iteration: int,
        body_steps: List[Dict[str, Any]],
    ) -> tuple[Dict[str, Any], int, bool]:
        """Return persisted iteration state plus the first unfinished nested step index."""
        return self.loop_executor.repeat_until_iteration_resume_state(
            state,
            loop_name,
            iteration,
            body_steps,
        )

    def _resume_for_each_state(
        self,
        state: Dict[str, Any],
        loop_name: str,
        loop_steps: List[Dict[str, Any]],
        items: List[Any],
    ) -> tuple[List[Dict[str, Any]], List[int], int]:
        """Load persisted loop progress and determine the restart index."""
        return self.loop_executor.resume_for_each_state(
            state,
            loop_name,
            loop_steps,
            items,
        )

    def _record_published_artifacts(
        self,
        step: Dict[str, Any],
        step_name: str,
        result: Dict[str, Any],
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
        additional_publishes: Optional[List[Dict[str, str]]] = None,
        persist: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Record artifact publications for successful steps."""
        return self.dataflow_manager.record_published_artifacts(
            step,
            step_name,
            result,
            state,
            runtime_step_id=runtime_step_id,
            additional_publishes=additional_publishes,
            persist=persist,
        )

    def _enforce_consumes_contract(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Resolve and enforce consumes contracts before step execution."""
        return self.dataflow_manager.enforce_consumes_contract(
            step,
            step_name,
            state,
            runtime_step_id=runtime_step_id,
        )

    def _substitute_path_template(
        self,
        path_value: str,
        state: Dict[str, Any],
        *,
        step_name: str,
        field_name: str,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Resolve runtime path templates against workflow context and bound inputs."""
        raw_context = state.get('context', {})
        runtime_context = RuntimeContext.from_mapping(
            {"context": raw_context if isinstance(raw_context, dict) else {}},
            default_context=self.workflow.get("context", {}),
            root_steps=state.get("steps", {}),
        )
        variables = runtime_context.build_variables(self.variable_substitutor, state)
        try:
            substituted = self.variable_substitutor.substitute(path_value, variables)
        except ValueError:
            undefined_vars = list(self.variable_substitutor.undefined_vars)
            return None, self._contract_violation_result(
                "Path substitution failed",
                {
                    "step": step_name,
                    "field": field_name,
                    "reason": "undefined_path_variables",
                    "path": path_value,
                    "undefined_vars": undefined_vars,
                },
            )

        return substituted, None

    def _resolve_workspace_path(self, relative_path: str) -> Optional[Path]:
        """Resolve a workspace path and reject escapes outside the workspace root."""
        path = Path(relative_path)
        if ".." in path.parts:
            return None

        candidate = path.resolve() if path.is_absolute() else (self.workspace / path).resolve()
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

    def _handle_control_flow(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        step_name: str,
        current_index: int,
        on_error: str,
        *,
        current_node_id: Optional[str] = None,
    ) -> Any:
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

        if error_type == 'cycle_guard_exceeded':
            logger.error(
                "Step '%s' exceeded a cycle guard. Stopping execution.",
                step_name,
            )
            return '_stop'

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
                return self._resolve_goto_target(goto_target, current_node_id=current_node_id)

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

    def _resolve_goto_target(self, target: str, *, current_node_id: Optional[str] = None) -> Any:
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

        if self._use_ir_topology and isinstance(current_node_id, str) and self.executable_ir is not None:
            node = self.executable_ir.nodes.get(current_node_id)
            transfer = node.routed_transfers.get("goto") if node is not None else None
            if transfer is not None:
                return transfer.target_node_id

        projected_index = self._projection_index_by_presentation_name.get(target)
        if isinstance(projected_index, int):
            return projected_index

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
        return self.loop_executor.build_repeat_until_frame_result(
            step,
            status=status,
            exit_code=exit_code,
            artifacts=artifacts,
            progress=progress,
            error=error,
        )

    def _execute_repeat_until(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        resume: bool = False,
    ) -> Dict[str, Any]:
        """Execute a post-test repeat_until loop with durable resume bookkeeping."""
        return self.loop_executor.execute_repeat_until(step, state, resume=resume)

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
        return self.loop_executor.execute_for_each(step, state, resume=resume)

    def _run_top_level_step(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        step_name: str,
        resume_current_step: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Execute one top-level step and persist its result when applicable."""
        execution_kind = self._execution_kind_for_step(step)

        if execution_kind is ExecutableNodeKind.FOR_EACH or "for_each" in step:
            self._execute_for_each(step, state, resume=resume_current_step)
            if step_name in state["steps"]:
                loop_results = state["steps"][step_name]
                if isinstance(loop_results, list):
                    self.state_manager.update_loop_results(step_name, loop_results)
            result = state.get("steps", {}).get(step_name, {"status": "completed"})
            self._emit_step_summary(step_name, step, result)
            return result

        if execution_kind is ExecutableNodeKind.REPEAT_UNTIL_FRAME or "repeat_until" in step:
            self._execute_repeat_until(step, state, resume=resume_current_step)
            result = state.get("steps", {}).get(step_name, {"status": "completed"})
            self._emit_step_summary(step_name, step, result)
            return result

        if execution_kind is ExecutableNodeKind.IF_BRANCH_MARKER or "structured_if_branch" in step:
            result = self._execute_structured_if_branch(step)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.IF_JOIN or "structured_if_join" in step:
            result = self._execute_structured_if_join(step, state)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.MATCH_CASE_MARKER or "structured_match_case" in step:
            result = self._execute_structured_match_case(step)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.MATCH_JOIN or "structured_match_join" in step:
            result = self._execute_structured_match_join(step, state)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.WAIT_FOR or "wait_for" in step:
            result = self._execute_wait_for_result(step)
            phase_hint = None
            class_hint = None
            if result.get("timed_out"):
                phase_hint = "execution"
                class_hint = "timeout"
            elif isinstance(result.get("error"), dict) and result["error"].get("type") == "path_safety_error":
                phase_hint = "pre_execution"
                class_hint = "pre_execution_failed"
            return self._persist_step_result(
                state,
                step_name,
                step,
                result,
                phase_hint=phase_hint,
                class_hint=class_hint,
                retryable_hint=False if class_hint == "pre_execution_failed" else None,
            )

        if execution_kind is ExecutableNodeKind.ASSERT or "assert" in step:
            result = self._execute_assert(step, state)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.SET_SCALAR or "set_scalar" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_set_scalar(step),
            )

        if execution_kind is ExecutableNodeKind.INCREMENT_SCALAR or "increment_scalar" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_increment_scalar(step, state),
            )

        if execution_kind is ExecutableNodeKind.CALL_BOUNDARY or "call" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_call(step, state),
            )

        if execution_kind is ExecutableNodeKind.PROVIDER or "provider" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_provider(step, state),
            )

        if execution_kind is ExecutableNodeKind.COMMAND or "command" in step:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_command(step, state),
            )

        return None

    def _execute_nested_loop_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        *,
        loop_step: Optional[Dict[str, Any]] = None,
        parent_scope_node_results: Optional[Dict[str, Any]] = None,
        runtime_step_id: Optional[str] = None,
        loop_name: Optional[str] = None,
        iteration_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        resolved_loop_name = loop_name or step.get('name', f'step_{self.current_step}')
        resolved_iteration_index = 0 if iteration_index is None else iteration_index
        nested_name = step.get('name', f'nested_{resolved_iteration_index}')
        scope = self._build_loop_scope(
            state,
            iteration_state,
            parent_scope_steps,
            loop_step=loop_step,
            parent_scope_node_results=parent_scope_node_results,
        )
        step_name_override = step.get("name")
        execution_kind = self._execution_kind_for_step(step)

        if execution_kind is ExecutableNodeKind.COMMAND or "command" in step:
            result = self._execute_command_with_context(step, context, state)
        elif execution_kind is ExecutableNodeKind.PROVIDER or "provider" in step:
            result = self._execute_provider_with_context(
                step,
                context,
                state,
                runtime_step_id=runtime_step_id,
            )
        elif execution_kind is ExecutableNodeKind.ASSERT or "assert" in step:
            result = self._execute_assert(step, state, context=context, scope=scope)
        elif execution_kind is ExecutableNodeKind.SET_SCALAR or "set_scalar" in step:
            result = self._execute_set_scalar(step)
        elif execution_kind is ExecutableNodeKind.INCREMENT_SCALAR or "increment_scalar" in step:
            result = self._execute_increment_scalar(step, state)
        elif execution_kind is ExecutableNodeKind.WAIT_FOR or "wait_for" in step:
            result = self._execute_wait_for_result(step)
        elif execution_kind is ExecutableNodeKind.IF_BRANCH_MARKER or "structured_if_branch" in step:
            result = self._execute_structured_if_branch(step)
        elif execution_kind is ExecutableNodeKind.IF_JOIN or "structured_if_join" in step:
            result = self._execute_structured_if_join(step, state, scope=scope)
        elif execution_kind is ExecutableNodeKind.MATCH_CASE_MARKER or "structured_match_case" in step:
            result = self._execute_structured_match_case(step)
        elif execution_kind is ExecutableNodeKind.MATCH_JOIN or "structured_match_join" in step:
            result = self._execute_structured_match_join(step, state, scope=scope)
        elif execution_kind is ExecutableNodeKind.CALL_BOUNDARY or "call" in step:
            result = self._execute_call(
                step,
                state,
                scope=scope,
                runtime_step_id=runtime_step_id,
                step_name_override=step_name_override,
            )
        else:
            result = {"status": "skipped", "exit_code": 0, "skipped": True}

        publish_error = self._record_published_artifacts(
            step,
            nested_name,
            result,
            state,
            runtime_step_id=runtime_step_id,
        )
        if publish_error is not None:
            result = publish_error

        result.setdefault("name", nested_name)
        result.setdefault("step_id", runtime_step_id)
        result = self._attach_outcome(step, result)
        iteration_state[nested_name] = result
        self.state_manager.update_loop_step(
            resolved_loop_name,
            resolved_iteration_index,
            nested_name,
            self._to_step_result(result, nested_name),
        )
        return result

    def _execute_top_level_publish_and_persist(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        provider_session = step.get("provider_session")
        if not isinstance(provider_session, dict):
            publish_error = self._record_published_artifacts(step, step_name, result, state)
            if publish_error is not None:
                result = publish_error
            return self._persist_step_result(state, step_name, step, result)

        session_info = self._active_provider_session(step_name)
        additional_publishes: List[Dict[str, str]] = []
        if provider_session.get("mode") == "fresh" and result.get("exit_code", 0) == 0:
            session_id = (
                result.get("debug", {})
                .get("provider_session", {})
                .get("session_id")
                if isinstance(result.get("debug"), dict)
                else None
            )
            publish_artifact = provider_session.get("publish_artifact")
            if not isinstance(session_id, str) or not session_id:
                result = self._contract_violation_result(
                    "Provider execution failed",
                    {
                        "step": step_name,
                        "reason": "missing_provider_session_id",
                        "artifact": publish_artifact,
                    },
                )
            elif isinstance(publish_artifact, str):
                artifacts = result.setdefault("artifacts", {})
                if isinstance(artifacts, dict):
                    artifacts[publish_artifact] = session_id
                else:
                    result["artifacts"] = {publish_artifact: session_id}
                additional_publishes.append({"artifact": publish_artifact, "from": publish_artifact})

        publish_error = self._record_published_artifacts(
            step,
            step_name,
            result,
            state,
            additional_publishes=additional_publishes or None,
            persist=False,
        )
        if publish_error is not None:
            result = publish_error

        finalized = self._attach_outcome(step, result)
        finalized.setdefault("name", step_name)
        finalized.setdefault("step_id", self._step_id(step))
        step_visits = state.get("step_visits", {})
        visit_count = step_visits.get(step_name) if isinstance(step_visits, dict) else None
        if isinstance(visit_count, int):
            finalized.setdefault("visit_count", visit_count)
        provider_debug = None
        if session_info is not None:
            debug_payload = finalized.setdefault("debug", {})
            if isinstance(debug_payload, dict):
                provider_debug = debug_payload.setdefault("provider_session", {})
            if isinstance(provider_debug, dict):
                provider_debug.setdefault("mode", provider_session.get("mode"))
                provider_debug.setdefault("metadata_path", session_info.get("metadata_path"))
                provider_debug.setdefault("session_id", None)
                publication_state = (
                    "published"
                    if provider_session.get("mode") == "fresh"
                    and finalized.get("exit_code", 0) == 0
                    and isinstance(finalized.get("artifacts"), dict)
                    and provider_session.get("publish_artifact") in finalized.get("artifacts", {})
                    else "suppressed_failure"
                )
                provider_debug["publication_state"] = publication_state
                provider_debug["transport_spool_path"] = (
                    session_info.get("transport_spool_path")
                    if self.debug or finalized.get("exit_code", 0) != 0
                    else None
                )
        state.setdefault("steps", {})[step_name] = finalized

        artifact_versions = state.get("artifact_versions", {})
        artifact_consumes = state.get("artifact_consumes", {})
        self.state_manager.finalize_step_with_dataflow(
            step_name,
            self._to_step_result(finalized, step_name),
            artifact_versions=artifact_versions if isinstance(artifact_versions, dict) else {},
            artifact_consumes=artifact_consumes if isinstance(artifact_consumes, dict) else {},
            expected_step_id=finalized.get("step_id"),
            expected_visit_count=visit_count if isinstance(visit_count, int) else None,
        )
        if session_info is not None:
            retain_transport_spool = self.debug or finalized.get("exit_code", 0) != 0
            parser_summary = {}
            if isinstance(provider_debug, dict):
                event_count = provider_debug.get("event_count")
                if isinstance(event_count, int):
                    parser_summary["event_count"] = event_count
            self._finalize_active_provider_session(
                step_name,
                step_status=str(finalized.get("status", "failed")),
                publication_state=(
                    provider_debug.get("publication_state")
                    if isinstance(provider_debug, dict)
                    else "suppressed_failure"
                ),
                session_id=(
                    provider_debug.get("session_id")
                    if isinstance(provider_debug, dict) and isinstance(provider_debug.get("session_id"), str)
                    else None
                ),
                metadata_mode=(
                    provider_debug.get("metadata_mode")
                    if isinstance(provider_debug, dict) and isinstance(provider_debug.get("metadata_mode"), str)
                    else None
                ),
                command_variant=(
                    provider_debug.get("command_variant")
                    if isinstance(provider_debug, dict) and isinstance(provider_debug.get("command_variant"), str)
                    else None
                ),
                parser_summary=parser_summary,
                retain_transport_spool=retain_transport_spool,
            )
        self._emit_step_summary(step_name, step, finalized)
        return finalized

    @staticmethod
    def _to_step_result(result: Dict[str, Any], fallback_name: str) -> StepResult:
        """Convert a persisted result payload into the runtime StepResult model."""
        return OutcomeRecorder.to_step_result(result, fallback_name)

    def _build_loop_parent_scope_steps(
        self,
        loop_step: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the lexical parent scope for structured refs inside one loop body."""
        return self.loop_executor.build_loop_parent_scope_steps(loop_step, state)

    def _build_loop_scope(
        self,
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        *,
        loop_step: Optional[Dict[str, Any]] = None,
        parent_scope_node_results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Build structured-ref scope maps for one nested loop step."""
        return self.loop_executor.build_loop_scope(
            state,
            iteration_state,
            parent_scope_steps,
            loop_step=loop_step,
            parent_scope_node_results=parent_scope_node_results,
        )

    def _evaluate_loop_body_condition(
        self,
        step: Dict[str, Any],
        condition: Dict[str, Any],
        state: Dict[str, Any],
        *,
        loop_context: Dict[str, Any],
        scope: Dict[str, Dict[str, Any]],
        runtime_step_id: str,
        invert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Evaluate one loop-body guard/when condition and return failure or skip results."""
        return self.loop_executor.evaluate_loop_body_condition(
            step,
            condition,
            state,
            loop_context=loop_context,
            scope=scope,
            runtime_step_id=runtime_step_id,
            invert=invert,
        )

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
        runtime_context = self._runtime_context(context, state)
        variables = runtime_context.build_variables(self.variable_substitutor, state)

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

        return self._apply_expected_outputs_contract(step, result.to_state_dict(), state)

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
        step_name = step.get('name', f'step_{self.current_step}')
        runtime_context = self._runtime_context(context, state)
        variables = runtime_context.build_variables(self.variable_substitutor, state)

        # Initialize prompt variable from either input_file or asset_file.
        prompt, prompt_error = self.prompt_composer.read_prompt_source(
            step,
            step_name=step.get('name', f'step_{self.current_step}'),
            contract_violation_result=self._contract_violation_result,
        )
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

        prompt, asset_error = self.prompt_composer.apply_asset_depends_on_prompt_injection(
            step,
            prompt,
            step_name=step.get('name', f'step_{self.current_step}'),
            contract_violation_result=self._contract_violation_result,
        )
        if asset_error is not None:
            return asset_error

        # Inject resolved consumes into provider prompt when requested.
        resolved_consumes = state.get('_resolved_consumes', {})
        prompt = self.prompt_composer.apply_consumes_prompt_injection(
            step,
            prompt,
            resolved_consumes=resolved_consumes if isinstance(resolved_consumes, dict) else {},
            step_name=step.get('name', f'step_{self.current_step}'),
            consume_identity=runtime_step_id or self._step_id(step),
            uses_qualified_identities=self._uses_qualified_identities(),
        )

        # Deterministic output contract prompt suffix (provider steps only).
        prompt = self.prompt_composer.apply_output_contract_prompt_suffix(step, prompt)

        # AT-70: Prompt audit with debug mode (when no dependencies)
        if self.debug and prompt:
            self._write_prompt_audit(step.get('name', 'provider'), prompt, step.get('secrets'), step.get('env'))

        session_request, session_error = self._build_provider_session_request(
            step,
            state,
            step_name=step_name,
            consume_identity=runtime_step_id or self._step_id(step),
        )
        if session_error is not None:
            return session_error

        # Create retry policy for provider steps (AT-21)
        # Providers use global max_retries or step-specific retries
        if session_request is not None:
            retry_policy = RetryPolicy.for_command(0)
        elif 'retries' in step:
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
                session_request=session_request,
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

            session_runtime = self._active_provider_session(step_name)
            if session_runtime is not None:
                invocation_command = getattr(invocation, "command", None)
                if isinstance(invocation_command, list):
                    resolved_command = self.secrets_manager.mask_text(
                        " ".join(str(token) for token in invocation_command)
                    )
                else:
                    resolved_command = None
                self._update_active_provider_session_metadata(
                    step_name,
                    metadata_mode=getattr(invocation, "metadata_mode", None),
                    command_variant=getattr(invocation, "command_variant", None),
                    resolved_command=resolved_command,
                )

            # Execute the prepared invocation
            exec_result = self._execute_provider_invocation(
                invocation,
                session_runtime=session_runtime,
            )

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

            provider_session_payload = getattr(exec_result, "provider_session", None)
            if not isinstance(provider_session_payload, dict):
                provider_session_payload = None

            if provider_session_payload:
                debug_info.setdefault('provider_session', {}).update({
                    'mode': session_request.mode.value if session_request is not None else None,
                    'session_id': provider_session_payload.get('session_id'),
                    'event_count': provider_session_payload.get('event_count'),
                    'command_variant': getattr(invocation, 'command_variant', None),
                    'metadata_mode': getattr(invocation, 'metadata_mode', None),
                    'metadata_path': session_runtime.get('metadata_path') if isinstance(session_runtime, dict) else None,
                    'transport_spool_path': (
                        session_runtime.get('transport_spool_path')
                        if isinstance(session_runtime, dict)
                        else None
                    ),
                })
            elif isinstance(session_runtime, dict):
                debug_info.setdefault('provider_session', {}).update({
                    'mode': session_request.mode.value if session_request is not None else None,
                    'command_variant': getattr(invocation, 'command_variant', None),
                    'metadata_mode': getattr(invocation, 'metadata_mode', None),
                    'metadata_path': session_runtime.get('metadata_path'),
                    'transport_spool_path': session_runtime.get('transport_spool_path'),
                })

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

        return self._apply_expected_outputs_contract(step, result, state)

    def _build_provider_session_request(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        step_name: str,
        consume_identity: str,
    ) -> tuple[Optional[ProviderSessionRequest], Optional[Dict[str, Any]]]:
        """Resolve the optional provider_session request for one provider step."""
        provider_session = step.get("provider_session")
        if not isinstance(provider_session, dict):
            return None, None

        mode = provider_session.get("mode")
        if mode == "fresh":
            publish_artifact = provider_session.get("publish_artifact")
            return ProviderSessionRequest(
                mode=ProviderSessionMode.FRESH,
                publish_artifact=publish_artifact if isinstance(publish_artifact, str) else None,
            ), None

        if mode != "resume":
            return None, self._contract_violation_result(
                "Provider execution failed",
                {
                    "step": step_name,
                    "reason": "invalid_provider_session_mode",
                },
            )

        session_artifact = provider_session.get("session_id_from")
        resolved_consumes = state.get("_resolved_consumes", {})
        if not isinstance(resolved_consumes, dict):
            resolved_consumes = {}
        step_consumes = resolved_consumes.get(step_name, {})
        if not isinstance(step_consumes, dict) or not step_consumes:
            step_consumes = resolved_consumes.get(consume_identity, {})
        if not isinstance(step_consumes, dict):
            step_consumes = {}

        session_id = step_consumes.get(session_artifact) if isinstance(session_artifact, str) else None
        if not isinstance(session_id, str) or not session_id:
            return None, self._contract_violation_result(
                "Provider execution failed",
                {
                    "step": step_name,
                    "reason": "missing_provider_session_id",
                    "artifact": session_artifact,
                },
            )

        return ProviderSessionRequest(
            mode=ProviderSessionMode.RESUME,
            session_id=session_id,
            session_id_from=session_artifact if isinstance(session_artifact, str) else None,
        ), None

    def _execute_call(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
        runtime_step_id: Optional[str] = None,
        step_name_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute an imported workflow inline and persist call-frame state."""
        return self.call_executor.execute_call(
            step,
            state,
            scope=scope,
            runtime_step_id=runtime_step_id,
            step_name_override=step_name_override,
        )

    def _execute_provider_invocation(
        self,
        invocation: Any,
        *,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute provider invocation with backward-compatible call shape."""
        execute_fn = self.provider_executor.execute
        try:
            return execute_fn(
                invocation,
                stream_output=(self.debug or self.stream_output),
                session_runtime=session_runtime,
            )
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument 'session_runtime'" in message:
                try:
                    return execute_fn(invocation, stream_output=(self.debug or self.stream_output))
                except TypeError as nested_exc:
                    if "unexpected keyword argument 'stream_output'" not in str(nested_exc):
                        raise
                    return execute_fn(invocation)
            if "unexpected keyword argument 'stream_output'" not in message:
                raise
            return execute_fn(invocation)

    def _resolve_output_contract_paths(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
    ) -> tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Resolve runtime path templates for output contract surfaces."""
        step_name = step.get('name', f'step_{self.current_step}')

        expected_outputs = step.get('expected_outputs')
        resolved_expected_outputs: Optional[List[Dict[str, Any]]] = None
        if isinstance(expected_outputs, list):
            resolved_expected_outputs = []
            for index, spec in enumerate(expected_outputs):
                if not isinstance(spec, dict):
                    resolved_expected_outputs.append(spec)
                    continue

                spec_copy = deepcopy(spec)
                path_value = spec_copy.get('path')
                if isinstance(path_value, str):
                    resolved_path, path_error = self._substitute_path_template(
                        path_value,
                        state,
                        step_name=step_name,
                        field_name=f"expected_outputs[{index}].path",
                    )
                    if path_error is not None:
                        return None, None, path_error
                    spec_copy['path'] = resolved_path
                resolved_expected_outputs.append(spec_copy)

        output_bundle = step.get('output_bundle')
        resolved_output_bundle: Optional[Dict[str, Any]] = None
        if isinstance(output_bundle, dict):
            resolved_output_bundle = deepcopy(output_bundle)
            path_value = resolved_output_bundle.get('path')
            if isinstance(path_value, str):
                resolved_path, path_error = self._substitute_path_template(
                    path_value,
                    state,
                    step_name=step_name,
                    field_name='output_bundle.path',
                )
                if path_error is not None:
                    return None, None, path_error
                resolved_output_bundle['path'] = resolved_path

        return resolved_expected_outputs, resolved_output_bundle, None

    def _apply_expected_outputs_contract(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate deterministic output contracts and attach parsed values to step result."""
        expected_outputs = step.get('expected_outputs')
        output_bundle = step.get('output_bundle')
        if not expected_outputs and not output_bundle:
            return result

        if result.get('exit_code', 0) != 0:
            # Only enforce contract after a successful process/provider execution.
            return result

        resolved_expected_outputs, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
            step,
            state,
        )
        if path_error is not None:
            return path_error

        try:
            if resolved_output_bundle:
                artifacts = validate_output_bundle(resolved_output_bundle, workspace=self.workspace)
            else:
                artifacts = validate_expected_outputs(resolved_expected_outputs or [], workspace=self.workspace)
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
        return self.loop_executor.create_loop_context(step, loop_context, iteration_state)

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
            'context': context.get(
                'context',
                run_state.context if isinstance(run_state.context, dict) else self.variables,
            ),
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
        runtime_context = self._runtime_context(context, state)
        return runtime_context.build_dependency_variables(state)


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
        runtime_context = self._runtime_context(context, state)
        variables = runtime_context.build_variables(self.variable_substitutor, state)
        if scope is None:
            scope = runtime_context.scope()
        assert_condition = self._assert_condition(step)
        try:
            passed = self._evaluate_condition_expression(
                assert_condition,
                variables,
                state,
                scope=scope,
            )
        except Exception as exc:
            return {
                'status': 'failed',
                'exit_code': 2,
                'duration_ms': 0,
                'error': {
                    'type': 'predicate_evaluation_failed',
                    'message': str(exc),
                    'context': {'assert': self._json_safe_runtime_value(assert_condition)},
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
                'context': {'assert': self._json_safe_runtime_value(assert_condition)},
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
        if artifact_type == 'string':
            if not isinstance(candidate_value, str):
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
        outputs: Mapping[str, Any],
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
            validation_spec: Any = spec
            source: Any = None
            if isinstance(spec, ExecutableContract):
                validation_spec = spec.raw
                source = spec.source_address
            elif isinstance(spec, dict):
                binding = spec.get('from')
                ref = binding.get('ref') if isinstance(binding, dict) else None
                source = {"ref": ref} if isinstance(ref, str) and ref else None
            else:
                continue

            if source is None:
                return self._contract_violation_result(
                    failure_message,
                    {
                        "reason": "missing_output_ref",
                        "output": output_name,
                        selection_key: selection_value,
                    },
                )
            try:
                raw_value = self._resolve_runtime_value(source, state, scope=scope)
            except (PredicateEvaluationError, ReferenceResolutionError) as exc:
                return self._contract_violation_result(
                    failure_message,
                    {
                        "reason": "unresolved_output_ref",
                        "output": output_name,
                        selection_key: selection_value,
                        "ref": self._json_safe_runtime_value(source),
                        "error": str(exc),
                    },
                )
            try:
                artifacts[output_name] = validate_contract_value(
                    raw_value,
                    validation_spec,
                    workspace=self.workspace,
                )
            except OutputContractError as exc:
                return self._contract_violation_result(
                    failure_message,
                    {
                        "reason": "invalid_output_value",
                        "output": output_name,
                        selection_key: selection_value,
                        "ref": self._json_safe_runtime_value(source),
                        "violations": exc.violations,
                    },
                )
        return artifacts

    def _execute_structured_if_branch(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Record one lowered branch marker for a structured if/else statement."""
        node = self._executable_node_for_step(step)
        if isinstance(node, IfBranchMarkerNode):
            branch_name = node.branch_name
            statement_name = node.statement_name
        else:
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

    def _execute_structured_if_join(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Materialize selected branch outputs onto the lowered join node."""
        branches = self._structured_if_branches(step)
        if not isinstance(branches, dict) or not branches:
            return self._contract_violation_result(
                "Structured if/else join failed",
                {"reason": "missing_branch_metadata"},
            )

        steps_state = (
            scope.get('self_steps')
            if isinstance(scope, dict) and isinstance(scope.get('self_steps'), dict)
            else state.get('steps', {})
        )
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

        outputs = self._structured_output_contracts(step, selected_branch)

        artifacts = self._resolve_structured_output_artifacts(
            outputs,
            state,
            failure_message="Structured if/else join failed",
            selection_key="branch",
            selection_value=selected_branch,
            scope=scope,
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
        node = self._executable_node_for_step(step)
        if isinstance(node, MatchCaseMarkerNode):
            case_name = node.case_name
            statement_name = node.statement_name
        else:
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

    def _execute_structured_match_join(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Materialize selected case outputs onto the lowered join node."""
        node = self._executable_node_for_step(step)
        cases = self._structured_match_cases(step)
        if not isinstance(cases, dict) or not cases:
            return self._contract_violation_result(
                "Structured match join failed",
                {"reason": "missing_case_metadata"},
            )

        steps_state = (
            scope.get('self_steps')
            if isinstance(scope, dict) and isinstance(scope.get('self_steps'), dict)
            else state.get('steps', {})
        )
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

        outputs = self._structured_output_contracts(step, selected_case)

        artifacts = self._resolve_structured_output_artifacts(
            outputs,
            state,
            failure_message="Structured match join failed",
            selection_key="case",
            selection_value=selected_case,
            scope=scope,
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
                    'selector_ref': self._json_safe_runtime_value(
                        node.selector_address if isinstance(node, MatchJoinNode) else None
                    ),
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
        return self.outcome_recorder.persist_step_result(
            state,
            step_name,
            step,
            result,
            phase_hint=phase_hint,
            class_hint=class_hint,
            retryable_hint=retryable_hint,
        )

    def _attach_outcome(
        self,
        step: Dict[str, Any],
        result: Dict[str, Any],
        phase_hint: Optional[str] = None,
        class_hint: Optional[str] = None,
        retryable_hint: Optional[bool] = None,
    ) -> Dict[str, Any]:
        return self.outcome_recorder.attach_outcome(
            step,
            result,
            phase_hint=phase_hint,
            class_hint=class_hint,
            retryable_hint=retryable_hint,
        )

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
