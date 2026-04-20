"""
Workflow executor with for-each loop support.
Implements AT-3, AT-13: Dynamic for-each execution with pointer resolution.
"""

import json
import logging
import os
import threading
import time
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import is_dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from ..state import ForEachState, RunState, StateManager, StepResult
from ..exec.step_executor import StepExecutor
from ..exec.retry import RetryPolicy
from ..providers.executor import ProviderExecutor
from ..providers.registry import ProviderRegistry
from ..providers.types import ProviderParams, ProviderSessionMode, ProviderSessionRequest
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
from .conditions import EqualsConditionNode, ExistsConditionNode, NotExistsConditionNode
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
    ExecutableNode,
    ExecutableTransfer,
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
from .loaded_bundle import (
    workflow_bundle,
    workflow_context,
    workflow_output_contracts,
    workflow_provenance,
)
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
)
from .prompting import PromptComposer
from .references import ReferenceResolutionError, ReferenceResolver
from .resume_planner import ResumePlanner, ResumeStateIntegrityError
from .runtime_context import RuntimeContext
from .runtime_step import RuntimeStep
from .runtime_types import RoutingDecision, StepExecutionIdentity
from .signatures import WorkflowSignatureError, resolve_workflow_outputs
from .adjudication import (
    BASELINE_COPY_POLICY,
    EVALUATION_PACKET_SCHEMA,
    EvaluatorOutputError,
    EvidencePacketError,
    LedgerConflictError,
    PathSurface,
    PromotionConflictError,
    SECRET_DETECTION_POLICY,
    adjudication_outcome,
    adjudication_visit_paths,
    build_evaluation_packet,
    candidate_paths,
    create_baseline_snapshot,
    generate_score_ledger_rows,
    materialize_run_score_ledger,
    materialize_score_ledger_mirror,
    parse_evaluator_output,
    persist_scorer_resolution_failure,
    persist_scorer_snapshot,
    prepare_candidate_workspace_from_baseline,
    promote_candidate_outputs,
    scorer_identity_hash,
    select_candidate,
)

logger = logging.getLogger(__name__)


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


class _CallFrameStateManager:
    """Persist a nested workflow state snapshot under the parent run state."""

    def __init__(
        self,
        *,
        parent_manager: StateManager,
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
            workflow: Loaded typed workflow bundle
            workspace: Base workspace directory
            state_manager: State persistence manager
            logs_dir: Directory for logs
            debug: Enable debug mode
            stream_output: Stream provider stdout/stderr live without enabling debug mode
        """
        self.loaded_bundle = workflow_bundle(workflow)
        if self.loaded_bundle is None:
            raise TypeError("WorkflowExecutor requires a LoadedWorkflowBundle")
        self.projection = self.loaded_bundle.projection
        self.executable_ir = self.loaded_bundle.ir
        self.workflow_name = self.loaded_bundle.surface.name
        self.workflow_version = self.loaded_bundle.surface.version
        workflow_context_defaults = _thaw_workflow_value(workflow_context(self.loaded_bundle))
        self.workflow_context_defaults = (
            workflow_context_defaults
            if isinstance(workflow_context_defaults, dict)
            else {}
        )
        global_secrets = _thaw_workflow_value(self.loaded_bundle.surface.secrets)
        self.global_secrets = (
            list(global_secrets)
            if isinstance(global_secrets, list)
            else list(global_secrets)
            if isinstance(global_secrets, tuple)
            else []
        )
        workflow_providers = _thaw_workflow_value(self.loaded_bundle.surface.providers)
        self.workflow_providers = workflow_providers if isinstance(workflow_providers, dict) else {}
        self.workflow_artifacts = {
            name: _thaw_workflow_value(contract.definition)
            for name, contract in self.loaded_bundle.surface.artifacts.items()
            if isinstance(name, str)
        }
        max_transitions = self.loaded_bundle.surface.max_transitions
        self.max_transitions = max_transitions if isinstance(max_transitions, int) else None
        strict_flow = self.loaded_bundle.surface.strict_flow
        self.strict_flow = strict_flow if isinstance(strict_flow, bool) else True
        self.workspace = workspace
        self.state_manager = state_manager
        self.debug = debug
        self.stream_output = stream_output
        self.observability = observability or {}

        # Initialize secrets manager
        self.secrets_manager = SecretsManager()

        # Initialize provider registry (load from workflow providers if present)
        self.provider_registry = ProviderRegistry()
        if self.workflow_providers:
            errors = self.provider_registry.register_from_workflow(self.workflow_providers)
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
            artifact_registry=self.workflow_artifacts,
            workflow_version=self.workflow_version,
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
        self.finalization = (
            {"token": self.loaded_bundle.surface.finalization.token}
            if self.loaded_bundle.surface.finalization is not None
            else None
        )
        self._step_node_ids: List[Optional[str]] = []
        self._step_node_ids = list(self.executable_ir.body_region) + list(
            self.executable_ir.finalization_region
        )
        self.finalization_start_index = len(self.executable_ir.body_region)
        self._execution_index_by_node_id = {
            node_id: index
            for index, node_id in enumerate(self._step_node_ids)
            if isinstance(node_id, str)
        }
        self._top_level_step_count = len(self._step_node_ids)
        self._projection_index_by_presentation_name = self._build_projection_index_by_presentation_name()
        self.variables = dict(self.workflow_context_defaults)
        self.resume_planner = ResumePlanner()
        self.finalization_controller = FinalizationController(
            finalization=self.finalization,
            finalization_start_index=self.finalization_start_index,
            finalization_step_count=(
                len(self.executable_ir.finalization_region)
            ),
            finalization_node_ids=list(self.executable_ir.finalization_region),
            finalization_entry_node_id=self.executable_ir.finalization_entry_node_id,
            projection=self.projection,
            has_workflow_outputs=bool(self.executable_ir.outputs),
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
        if isinstance(step, RuntimeStep) and fallback_index is None:
            return step.step_id
        projection_entry = self._projection_entry_for_step(
            step,
            self.current_step if fallback_index is None else fallback_index,
        )
        if projection_entry is not None:
            return projection_entry.step_id
        return runtime_step_id(step, self.current_step if fallback_index is None else fallback_index)

    def _adjudication_frame_context(self) -> Dict[str, Any]:
        """Return canonical run-root and current execution-frame identity."""
        manager: Any = self.state_manager
        call_frame_id = getattr(manager, "frame_id", None)
        root_manager = manager
        while hasattr(root_manager, "parent_manager"):
            root_manager = getattr(root_manager, "parent_manager")
        run_root = Path(getattr(root_manager, "run_root", self.state_manager.run_root))
        if isinstance(call_frame_id, str) and call_frame_id:
            return {
                "run_root": run_root,
                "frame_scope": self._path_safe_frame_scope(call_frame_id),
                "execution_frame_id": call_frame_id,
                "call_frame_id": call_frame_id,
            }
        return {
            "run_root": run_root,
            "frame_scope": "root",
            "execution_frame_id": "root",
            "call_frame_id": None,
        }

    def _path_safe_frame_scope(self, frame_id: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        normalized = "".join(char if char in allowed else "_" for char in frame_id).strip("._-")
        while ".." in normalized:
            normalized = normalized.replace("..", "._")
        if not normalized:
            normalized = "call_frame"
        digest = sha256(frame_id.encode("utf-8")).hexdigest()[:12]
        return f"{normalized}_{digest}"

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

    def _runtime_step_for_node(
        self,
        node: ExecutableNode,
        *,
        presentation_name: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> RuntimeStep:
        """Build one immutable runtime step view from an executable node."""
        resolved_name = (
            presentation_name
            if isinstance(presentation_name, str)
            else self.projection.presentation_key_by_node_id.get(node.node_id, node.presentation_name)
            if self.projection is not None
            else node.presentation_name
        )
        resolved_step_id = step_id if isinstance(step_id, str) else node.step_id
        return RuntimeStep(node=node, name=resolved_name, step_id=resolved_step_id)

    def _runtime_step_for_node_id(
        self,
        node_id: str,
        *,
        presentation_name: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> RuntimeStep:
        """Return the immutable runtime step view for one executable node id."""
        if self.executable_ir is None:
            raise ValueError("Typed workflow is missing executable IR")
        node = self.executable_ir.nodes.get(node_id)
        if node is None:
            raise ValueError(f"Typed workflow is missing executable node '{node_id}'")
        return self._runtime_step_for_node(
            node,
            presentation_name=presentation_name,
            step_id=step_id,
        )

    def _first_execution_node_id(self) -> Optional[str]:
        """Return the first top-level executable node id when bundle-backed IR is available."""
        if self.projection is None:
            return None
        ordered_node_ids = self.projection.ordered_execution_node_ids()
        return ordered_node_ids[0] if ordered_node_ids else None

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
                    return self.finalization_start_index + entry.finalization_index
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

    def _step_result_was_skipped(self, current_node_id: str, state: Dict[str, Any]) -> bool:
        """Return whether the persisted result for one typed node was recorded as skipped."""
        if self.projection is None:
            return False
        step_name = self.projection.presentation_key_by_node_id.get(current_node_id)
        if not isinstance(step_name, str) or not step_name:
            return False
        steps_state = state.get("steps")
        if not isinstance(steps_state, Mapping):
            return False
        step_result = steps_state.get(step_name)
        return isinstance(step_result, Mapping) and bool(step_result.get("skipped"))

    def _implicit_typed_transfer(
        self,
        current_node_id: str,
        state: Dict[str, Any],
    ) -> Optional[ExecutableTransfer]:
        """Return the implicit typed transfer selected by the current node result."""
        return self._implicit_typed_transfer_for_result(
            current_node_id,
            skipped=self._step_result_was_skipped(current_node_id, state),
        )

    def _implicit_typed_transfer_for_result(
        self,
        current_node_id: str,
        *,
        skipped: bool,
    ) -> Optional[ExecutableTransfer]:
        """Return the implicit typed transfer for one node/result pair."""
        if self.executable_ir is None:
            return None
        node = self.executable_ir.nodes.get(current_node_id)
        if node is None:
            return None
        if isinstance(node, IfBranchMarkerNode):
            reason = "branch_skipped" if skipped else "branch_taken"
            return node.routed_transfers.get(reason)
        if isinstance(node, MatchCaseMarkerNode):
            reason = "case_skipped" if skipped else "case_selected"
            return node.routed_transfers.get(reason)
        transfer = node.routed_transfers.get("call_return")
        if transfer is not None and transfer.target_node_id == node.fallthrough_node_id:
            return transfer
        return None

    def _typed_on_goto_transfer(
        self,
        current_node_id: str,
        *,
        exit_code: int,
    ) -> Optional[ExecutableTransfer]:
        """Return the explicit typed goto transfer selected by one step result."""
        if self.executable_ir is None:
            return None
        node = self.executable_ir.nodes.get(current_node_id)
        if node is None:
            return None

        selected = None
        if exit_code == 0:
            selected = node.routed_transfers.get("on_success_goto")
        else:
            selected = node.routed_transfers.get("on_failure_goto")
        always = node.routed_transfers.get("on_always_goto")
        return always if always is not None else selected

    def _counts_as_transition_for_typed_target(
        self,
        current_node_id: str,
        target_node_id: Optional[str],
        *,
        implicit: bool,
        state: Dict[str, Any],
    ) -> bool:
        """Return whether one typed top-level move should increment transition_count."""
        if not isinstance(target_node_id, str) or not target_node_id:
            return False
        if self.executable_ir is None:
            return True
        node = self.executable_ir.nodes.get(current_node_id)
        if node is None:
            return True

        if implicit:
            implicit_transfer = self._implicit_typed_transfer(current_node_id, state)
            if implicit_transfer is not None and implicit_transfer.target_node_id == target_node_id:
                return implicit_transfer.counts_as_transition
            return True

        for transfer in node.routed_transfers.values():
            if transfer.target_node_id == target_node_id:
                return transfer.counts_as_transition
        if node.fallthrough_node_id == target_node_id:
            return True
        return True

    def _persist_skipped_structured_descendants(
        self,
        state: Dict[str, Any],
        current_node_id: Optional[str],
    ) -> None:
        """Persist skipped result surfaces for descendants under one skipped branch/case marker."""
        if (
            not isinstance(current_node_id, str)
            or self.executable_ir is None
            or self.projection is None
        ):
            return
        node = self.executable_ir.nodes.get(current_node_id)
        if not isinstance(node, (IfBranchMarkerNode, MatchCaseMarkerNode)):
            return

        descendant_prefix = f"{current_node_id}."
        ordered_node_ids = [node_id for node_id in self._step_node_ids if isinstance(node_id, str)]
        for node_id in ordered_node_ids:
            if not node_id.startswith(descendant_prefix):
                continue
            step_name = self.projection.presentation_key_by_node_id.get(node_id)
            if not isinstance(step_name, str) or not step_name:
                continue
            steps_state = state.get("steps")
            if isinstance(steps_state, Mapping) and step_name in steps_state:
                continue
            skipped_step = self._runtime_step_for_node_id(node_id, presentation_name=step_name)
            self._persist_step_result(
                state,
                step_name,
                skipped_step,
                {"status": "skipped", "exit_code": 0, "skipped": True},
            )

    def _projection_entry_for_step(
        self,
        step: Dict[str, Any],
        step_index: Optional[int] = None,
    ) -> Optional[Any]:
        """Return projection metadata for one top-level step when a bundle is present."""
        if self.projection is None:
            return None

        node_id = None
        if isinstance(step, RuntimeStep):
            node_id = step.node_id
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
        if isinstance(step, RuntimeStep):
            return step.node
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

    def _typed_execution_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """Return an IR-backed runtime step view for one executable step mapping."""
        if isinstance(step, RuntimeStep):
            return step
        node = self._executable_node_for_step(step)
        if node is None:
            return step
        return self._runtime_step_for_node(
            node,
            presentation_name=step.get("name"),
            step_id=step.get("step_id"),
        )

    @staticmethod
    def _scoped_node_results(
        scope: Optional[Dict[str, Dict[str, Any]]],
        key: str,
    ) -> Optional[Mapping[str, Dict[str, Any]]]:
        if not isinstance(scope, dict):
            return None
        results = scope.get(key)
        return results if isinstance(results, Mapping) else None

    @staticmethod
    def _scoped_node_ids_contains(
        scope: Optional[Dict[str, Dict[str, Any]]],
        key: str,
        node_id: str,
    ) -> bool:
        if not isinstance(scope, dict):
            return False
        node_ids = scope.get(key)
        return isinstance(node_ids, (set, frozenset, tuple, list)) and node_id in node_ids

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

        if self._scoped_node_ids_contains(scope, "self_node_ids", node_id):
            raise ReferenceResolutionError(f"Bound address target step '{node_id}' is unavailable")

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
            raise ReferenceResolutionError(
                "Typed runtime does not accept legacy ref payloads; use lowered bound addresses"
            )
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

        raise PredicateEvaluationError(
            f"Unsupported lowered predicate node '{type(predicate).__name__}'"
        )

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
        if isinstance(condition, (EqualsConditionNode, ExistsConditionNode, NotExistsConditionNode)):
            return self.condition_evaluator.evaluate_parsed(condition, variables)
        if condition is None:
            return True
        raise PredicateEvaluationError(
            f"Typed runtime does not accept raw condition payloads; got '{type(condition).__name__}'"
        )

    def _structured_if_branches(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return structured-if branch metadata sourced from typed IR when available."""
        node = self._executable_node_for_step(step)
        if isinstance(node, IfJoinNode) and self.projection is not None:
            branches = self.projection.structured_if_branches.get(node.node_id)
            if branches is None:
                return {}
            return {
                branch_name: {
                    "marker": branch.marker_presentation_key,
                    "step_id": branch.marker_step_id,
                    "steps": list(branch.step_presentation_keys),
                    "outputs": node.branch_outputs.get(branch_name, {}),
                }
                for branch_name, branch in branches.items()
            }
        return {}

    def _structured_match_cases(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return structured-match case metadata sourced from typed IR when available."""
        node = self._executable_node_for_step(step)
        if isinstance(node, MatchJoinNode) and self.projection is not None:
            cases = self.projection.structured_match_cases.get(node.node_id)
            if cases is None:
                return {}
            return {
                case_name: {
                    "marker": case.marker_presentation_key,
                    "step_id": case.marker_step_id,
                    "steps": list(case.step_presentation_keys),
                    "outputs": node.case_outputs.get(case_name, {}),
                }
                for case_name, case in cases.items()
            }
        return {}

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
        return None, False

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
        return {}

    def _repeat_until_condition(self, step: Dict[str, Any]) -> Any:
        """Return one repeat_until stop condition, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, RepeatUntilFrameNode):
            return node.condition
        return None

    def _repeat_until_output_contracts(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return one repeat_until output contract map, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, RepeatUntilFrameNode):
            return node.output_contracts
        return {}

    def _call_input_bindings(self, step: Dict[str, Any]) -> Mapping[str, Any]:
        """Return one call step's bound input bindings, preferring the typed IR node."""
        node = self._executable_node_for_step(step)
        if isinstance(node, CallBoundaryNode):
            return node.bound_inputs
        return {}

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
            default_context=default_context or self.workflow_context_defaults,
            parent_steps=parent_steps,
            root_steps=state.get("steps", {}),
        )

    def _resume_entry_is_terminal(self, entry: Any) -> bool:
        """Return True when persisted step state is fully completed/skipped for resume purposes."""
        return self.resume_planner.entry_is_terminal(entry)

    def _determine_resume_restart_index(self, state: Dict[str, Any]) -> Optional[int]:
        """Determine the top-level step index where resumed execution should restart."""
        return self.resume_planner.determine_restart_index(state, projection=self.projection)

    def _determine_resume_restart_node_id(self, state: Dict[str, Any]) -> Optional[str]:
        """Determine the top-level executable node id where resumed execution should restart."""
        return self.resume_planner.determine_restart_node_id(state, projection=self.projection)

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
        version = self.workflow_version
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
                resume_restart_node_id = self._determine_resume_restart_node_id(state) if resume else None
            except ResumeStateIntegrityError as exc:
                return self._fail_resume_state_integrity(
                    "resume_state_integrity_error",
                    str(exc),
                    dict(exc.context),
                )
            step_index = 0
            current_node_id = resume_restart_node_id
            if current_node_id is None:
                current_node_id = self._first_execution_node_id()
            while True:
                if current_node_id is None:
                    break
                step_index = self._execution_index_for_node_id(current_node_id)
                step = self._runtime_step_for_node_id(current_node_id)
                self.current_step = step_index

                # Check if step should be executed
                identity = self._step_identity(step, step_index=step_index)
                step_name = identity.name
                step_id = identity.step_id
                step = self._typed_execution_step(step)
                resume_current_step = resume_restart_node_id is not None and current_node_id == resume_restart_node_id
                if resume_current_step:
                    resume_restart_node_id = None

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
                    current_node_id = next_node_id
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
                        current_node_id = next_node_id
                        continue

                    if not should_execute:
                        result = {
                            'status': 'skipped',
                            'exit_code': 0,
                            'skipped': True
                        }
                        self._persist_step_result(state, step_name, step, result)
                        self._persist_skipped_structured_descendants(state, current_node_id)
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
                        current_node_id = next_node_id
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
                        current_node_id = next_node_id
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
                        current_node_id = next_node_id
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
                    current_node_id = next_node_id
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
                    current_node_id = next_node_id
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
                current_node_id = next_node_id
        except Exception:
            terminal_status = 'failed'
            self.state_manager.update_status(terminal_status)
            raise

        finalization = self._ensure_finalization_state(state)

        if terminal_status == 'completed':
            try:
                output_specs = self.executable_ir.outputs
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
        if execution_kind is ExecutableNodeKind.ADJUDICATED_PROVIDER:
            return 'adjudicated_provider'
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
            'workflow': self.workflow_name,
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
        max_transitions = self.max_transitions
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

        if not isinstance(current_node_id, str):
            return None, None, terminal_status, True

        implicit_target = next_step is None
        implicit_transfer = (
            self._implicit_typed_transfer(current_node_id, state)
            if implicit_target
            else None
        )
        if isinstance(next_step, str) and next_step not in {"_end", "_stop"}:
            next_node_id = next_step
        elif isinstance(next_step, int):
            next_node_id = self._node_id_for_execution_index(next_step)
        elif implicit_transfer is not None and isinstance(implicit_transfer.target_node_id, str):
            next_node_id = implicit_transfer.target_node_id
        else:
            next_node_id = self._fallthrough_node_id(current_node_id)
        if self._counts_as_transition_for_typed_target(
            current_node_id,
            next_node_id,
            implicit=implicit_target,
            state=state,
        ):
            self._increment_transition_count(state)
        return None, next_node_id, terminal_status, False

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
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Resolve runtime path templates against workflow context and bound inputs."""
        if context is None:
            raw_context = state.get('context', {})
            context = {"context": raw_context if isinstance(raw_context, dict) else {}}
        runtime_context = self._runtime_context(context, state)
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

        if isinstance(current_node_id, str):
            goto_transfer = self._typed_on_goto_transfer(
                current_node_id,
                exit_code=exit_code,
            )
            if goto_transfer is not None:
                return goto_transfer.target_node_id or "_end"

        # AT-56, AT-57: Apply strict_flow and on_error behavior
        # Only if no goto handler was found
        if exit_code != 0:
            strict_flow = self.strict_flow

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

        projected_index = self._projection_index_by_presentation_name.get(target)
        if isinstance(projected_index, int):
            return projected_index

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

        if execution_kind is ExecutableNodeKind.FOR_EACH:
            self._execute_for_each(step, state, resume=resume_current_step)
            if step_name in state["steps"]:
                loop_results = state["steps"][step_name]
                if isinstance(loop_results, list):
                    self.state_manager.update_loop_results(step_name, loop_results)
            result = state.get("steps", {}).get(step_name, {"status": "completed"})
            self._emit_step_summary(step_name, step, result)
            return result

        if execution_kind is ExecutableNodeKind.REPEAT_UNTIL_FRAME:
            self._execute_repeat_until(step, state, resume=resume_current_step)
            result = state.get("steps", {}).get(step_name, {"status": "completed"})
            self._emit_step_summary(step_name, step, result)
            return result

        if execution_kind is ExecutableNodeKind.IF_BRANCH_MARKER:
            result = self._execute_structured_if_branch(step)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.IF_JOIN:
            result = self._execute_structured_if_join(step, state)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.MATCH_CASE_MARKER:
            result = self._execute_structured_match_case(step)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.MATCH_JOIN:
            result = self._execute_structured_match_join(step, state)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.WAIT_FOR:
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

        if execution_kind is ExecutableNodeKind.ASSERT:
            result = self._execute_assert(step, state)
            return self._persist_step_result(state, step_name, step, result)

        if execution_kind is ExecutableNodeKind.SET_SCALAR:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_set_scalar(step),
            )

        if execution_kind is ExecutableNodeKind.INCREMENT_SCALAR:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_increment_scalar(step, state),
            )

        if execution_kind is ExecutableNodeKind.CALL_BOUNDARY:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_call(step, state),
            )

        if execution_kind is ExecutableNodeKind.ADJUDICATED_PROVIDER:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_adjudicated_provider_with_context(step, {}, state),
            )

        if execution_kind is ExecutableNodeKind.PROVIDER:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_provider(step, state),
            )

        if execution_kind is ExecutableNodeKind.COMMAND:
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
        step = self._typed_execution_step(step)
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

        if execution_kind is ExecutableNodeKind.COMMAND:
            result = self._execute_command_with_context(step, context, state)
        elif execution_kind is ExecutableNodeKind.PROVIDER:
            result = self._execute_provider_with_context(
                step,
                context,
                state,
                runtime_step_id=runtime_step_id,
            )
        elif execution_kind is ExecutableNodeKind.ADJUDICATED_PROVIDER:
            result = self._execute_adjudicated_provider_with_context(
                step,
                context,
                state,
                runtime_step_id=runtime_step_id,
            )
        elif execution_kind is ExecutableNodeKind.ASSERT:
            result = self._execute_assert(step, state, context=context, scope=scope)
        elif execution_kind is ExecutableNodeKind.SET_SCALAR:
            result = self._execute_set_scalar(step)
        elif execution_kind is ExecutableNodeKind.INCREMENT_SCALAR:
            result = self._execute_increment_scalar(step, state)
        elif execution_kind is ExecutableNodeKind.WAIT_FOR:
            result = self._execute_wait_for_result(step)
        elif execution_kind is ExecutableNodeKind.IF_BRANCH_MARKER:
            result = self._execute_structured_if_branch(step)
        elif execution_kind is ExecutableNodeKind.IF_JOIN:
            result = self._execute_structured_if_join(step, state, scope=scope)
        elif execution_kind is ExecutableNodeKind.MATCH_CASE_MARKER:
            result = self._execute_structured_match_case(step)
        elif execution_kind is ExecutableNodeKind.MATCH_JOIN:
            result = self._execute_structured_match_join(step, state, scope=scope)
        elif execution_kind is ExecutableNodeKind.CALL_BOUNDARY:
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
        if isinstance(loop_name, str):
            state.setdefault("steps", {})[f"{resolved_loop_name}[{resolved_iteration_index}].{nested_name}"] = result
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

        return self._apply_expected_outputs_contract(step, result.to_state_dict(), state, context=context)

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
        resolved_expected_outputs, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
            step,
            state,
            context=context,
        )
        if path_error is not None:
            return path_error
        prompt_contract_step = step
        if resolved_expected_outputs is not None:
            prompt_contract_step = dict(step)
            prompt_contract_step['expected_outputs'] = resolved_expected_outputs
        elif resolved_output_bundle is not None:
            prompt_contract_step = dict(step)
            prompt_contract_step['output_bundle'] = resolved_output_bundle

        # Initialize prompt variable from either input_file or asset_file.
        prompt, prompt_error = self.prompt_composer.read_prompt_source(
            step,
            step_name=step.get('name', f'step_{self.current_step}'),
            contract_violation_result=self._contract_violation_result,
        )
        if prompt_error is not None:
            return prompt_error

        prompt, asset_error = self.prompt_composer.apply_asset_depends_on_prompt_injection(
            step,
            prompt,
            step_name=step.get('name', f'step_{self.current_step}'),
            contract_violation_result=self._contract_violation_result,
        )
        if asset_error is not None:
            return asset_error

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
        prompt = self.prompt_composer.apply_output_contract_prompt_suffix(prompt_contract_step, prompt)

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

        return self._apply_expected_outputs_contract(step, result, state, context=context)

    def _compose_provider_prompt_for_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        workspace: Optional[Path] = None,
        output_contract_step: Optional[Dict[str, Any]] = None,
        runtime_step_id: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Compose a provider prompt without invoking the provider."""
        step_name = step.get('name', f'step_{self.current_step}')
        workspace = self.workspace if workspace is None else workspace
        composer = self.prompt_composer if workspace == self.workspace else PromptComposer(
            workspace=workspace,
            asset_resolver=self.asset_resolver,
        )
        prompt, prompt_error = composer.read_prompt_source(
            step,
            step_name=step_name,
            contract_violation_result=self._contract_violation_result,
        )
        if prompt_error is not None:
            return None, prompt_error

        prompt, asset_error = composer.apply_asset_depends_on_prompt_injection(
            step,
            prompt,
            step_name=step_name,
            contract_violation_result=self._contract_violation_result,
        )
        if asset_error is not None:
            return None, asset_error

        if 'depends_on' in step:
            depends_on = step['depends_on']
            substitution_vars = self._build_substitution_variables(context, state)
            resolver = self.dependency_resolver if workspace == self.workspace else DependencyResolver(str(workspace))
            resolution = resolver.resolve(
                depends_on=depends_on,
                variables=substitution_vars,
            )
            if not resolution.is_valid:
                return None, {
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
            inject_config = depends_on.get('inject', False)
            if inject_config:
                injector = self.dependency_injector if workspace == self.workspace else DependencyInjector(str(workspace))
                injection_result = injector.inject(
                    prompt=prompt,
                    files=resolution.files,
                    inject_config=inject_config,
                    is_required='required' in depends_on and len(depends_on['required']) > 0,
                )
                prompt = injection_result.modified_prompt

        resolved_consumes = state.get('_resolved_consumes', {})
        prompt = composer.apply_consumes_prompt_injection(
            step,
            prompt,
            resolved_consumes=resolved_consumes if isinstance(resolved_consumes, dict) else {},
            step_name=step_name,
            consume_identity=runtime_step_id or self._step_id(step),
            uses_qualified_identities=self._uses_qualified_identities(),
        )
        prompt = composer.apply_output_contract_prompt_suffix(output_contract_step or step, prompt)
        return prompt, None

    def _execute_adjudicated_provider_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a DSL 2.11 adjudicated provider step sequentially."""
        started = time.monotonic()
        step_name = step.get('name', f'step_{self.current_step}')
        step_id = runtime_step_id or self._step_id(step)
        adjudicated = step.get('adjudicated_provider', {})
        if not isinstance(adjudicated, dict):
            return self._adjudication_failure_result("adjudication_resume_mismatch", "Missing adjudicated_provider config")

        resolved_expected_outputs, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
            step,
            state,
            context=context,
        )
        if path_error is not None:
            return path_error
        output_contract_step = dict(step)
        if resolved_expected_outputs is not None:
            output_contract_step['expected_outputs'] = resolved_expected_outputs
        if resolved_output_bundle is not None:
            output_contract_step['output_bundle'] = resolved_output_bundle

        frame_context = self._adjudication_frame_context()
        run_root = frame_context["run_root"]
        frame_scope = frame_context["frame_scope"]
        execution_frame_id = frame_context["execution_frame_id"]
        call_frame_id = frame_context["call_frame_id"]
        step_visits = state.get("step_visits", {})
        visit_count = step_visits.get(step_name, 1) if isinstance(step_visits, dict) else 1
        visit_paths = adjudication_visit_paths(run_root, frame_scope, step_id, int(visit_count or 1))

        required_surfaces = self._adjudication_required_path_surfaces(output_contract_step)
        try:
            baseline_manifest = create_baseline_snapshot(
                parent_workspace=self.workspace,
                run_root=run_root,
                visit_paths=visit_paths,
                workflow_checksum=state.get("workflow_checksum", ""),
                resolved_consumes=state.get("_resolved_consumes", {}),
                required_path_surfaces=required_surfaces,
                optional_path_surfaces=[],
            )
        except Exception as exc:
            return self._adjudication_failure_result(
                getattr(exc, "failure_type", "adjudication_resume_mismatch"),
                str(exc),
            )

        candidates_config = adjudicated.get("candidates", [])
        evaluator_config = adjudicated.get("evaluator", {})
        selection_config = adjudicated.get("selection", {})
        require_single_score = bool(
            isinstance(selection_config, dict)
            and selection_config.get("require_score_for_single_candidate") is True
        )
        candidates: list[dict[str, Any]] = []

        for index, candidate_config in enumerate(candidates_config if isinstance(candidates_config, list) else []):
            if not isinstance(candidate_config, dict):
                continue
            candidate_id = str(candidate_config.get("id"))
            candidate_provider = str(candidate_config.get("provider"))
            paths = candidate_paths(run_root, frame_scope, step_id, int(visit_count or 1), candidate_id)
            candidate_step = self._candidate_step_from_adjudicated_step(step, candidate_config)
            candidate_record = {
                "candidate_id": candidate_id,
                "candidate_index": index,
                "candidate_provider": candidate_provider,
                "candidate_model": self._provider_model(candidate_config.get("provider_params")),
                "candidate_params_hash": self._stable_runtime_hash(candidate_config.get("provider_params", {})),
                "candidate_config_hash": self._stable_runtime_hash(candidate_config),
                "prompt_variant_id": candidate_config.get("prompt_variant_id") or candidate_id,
                "candidate_root": paths.candidate_root.relative_to(self.workspace).as_posix()
                if self._path_under(paths.candidate_root, self.workspace)
                else paths.candidate_root.as_posix(),
                "candidate_workspace": paths.workspace.relative_to(self.workspace).as_posix()
                if self._path_under(paths.workspace, self.workspace)
                else paths.workspace.as_posix(),
                "attempt_count": 1,
                "output_paths": {},
            }
            try:
                prepare_candidate_workspace_from_baseline(
                    baseline_workspace=visit_paths.baseline_workspace,
                    candidate_workspace=paths.workspace,
                )
                prompt, prompt_error = self._compose_provider_prompt_for_step(
                    candidate_step,
                    context,
                    state,
                    workspace=paths.workspace,
                    output_contract_step=output_contract_step,
                    runtime_step_id=step_id,
                )
                if prompt_error is not None:
                    candidate_record.update(
                        {
                            "candidate_status": "prompt_failed",
                            "score_status": "not_evaluated",
                            "provider_exit_code": None,
                            "failure_type": prompt_error.get("error", {}).get("type", "prompt_failed"),
                            "failure_message": prompt_error.get("error", {}).get("message", "prompt failed"),
                        }
                    )
                    candidates.append(candidate_record)
                    continue
                paths.prompt_path.parent.mkdir(parents=True, exist_ok=True)
                paths.prompt_path.write_text(prompt or "", encoding="utf-8")
                candidate_record["composed_prompt_hash"] = self._text_hash(prompt or "")

                invocation, error = self.provider_executor.prepare_invocation(
                    provider_name=candidate_provider,
                    params=ProviderParams(
                        params=candidate_config.get("provider_params", {}),
                        input_file=candidate_step.get("input_file"),
                        output_file=None,
                    ),
                    context=self._create_provider_context(context, state),
                    prompt_content=prompt,
                    env=candidate_step.get("env"),
                    secrets=candidate_step.get("secrets"),
                    timeout_sec=step.get("timeout_sec"),
                )
                if error or invocation is None:
                    candidate_record.update(
                        {
                            "candidate_status": "prompt_failed",
                            "score_status": "not_evaluated",
                            "provider_exit_code": None,
                            "failure_type": (error or {}).get("type", "provider_preparation_failed"),
                            "failure_message": (error or {}).get("message", "provider preparation failed"),
                        }
                    )
                    candidates.append(candidate_record)
                    continue
                exec_result = self._execute_provider_invocation(invocation, cwd=paths.workspace)
                paths.stdout_log.write_bytes(exec_result.stdout)
                paths.stderr_log.write_bytes(exec_result.stderr)
                candidate_record["provider_exit_code"] = exec_result.exit_code
                if exec_result.exit_code != 0:
                    candidate_record.update(
                        {
                            "candidate_status": "timeout" if exec_result.exit_code == 124 else "provider_failed",
                            "score_status": "not_evaluated",
                            "failure_type": "timeout" if exec_result.exit_code == 124 else "provider_failed",
                            "failure_message": "candidate provider failed",
                        }
                    )
                    candidates.append(candidate_record)
                    continue
                try:
                    if resolved_output_bundle is not None:
                        artifacts = validate_output_bundle(resolved_output_bundle, workspace=paths.workspace)
                    else:
                        artifacts = validate_expected_outputs(resolved_expected_outputs or [], workspace=paths.workspace)
                except OutputContractError as exc:
                    candidate_record.update(
                        {
                            "candidate_status": "contract_failed",
                            "score_status": "not_evaluated",
                            "failure_type": "contract_failed",
                            "failure_message": str(exc),
                        }
                    )
                    candidates.append(candidate_record)
                    continue
                candidate_record.update(
                    {
                        "candidate_status": "output_valid",
                        "score_status": "not_evaluated",
                        "artifacts": artifacts,
                        "output_paths": self._output_paths_from_contract(output_contract_step),
                    }
                )
            except Exception as exc:
                candidate_record.update(
                    {
                        "candidate_status": "prompt_failed",
                        "score_status": "not_evaluated",
                        "provider_exit_code": None,
                        "failure_type": getattr(exc, "failure_type", "candidate_failed"),
                        "failure_message": str(exc),
                    }
                )
            candidates.append(candidate_record)

        output_valid = [candidate for candidate in candidates if candidate.get("candidate_status") == "output_valid"]
        scorer: dict[str, Any] | None = None
        evaluator_prompt = ""
        scorer_failure: dict[str, Any] | None = None
        if output_valid:
            scorer, evaluator_prompt, scorer_failure = self._resolve_adjudication_scorer(
                evaluator_config if isinstance(evaluator_config, dict) else {},
                context,
                state,
                visit_paths=visit_paths,
            )
        if scorer_failure is not None:
            for candidate in output_valid:
                candidate.update(
                    {
                        "score_status": "scorer_unavailable",
                        "scorer_resolution_failure_key": scorer_failure["scorer_resolution_failure_key"],
                        "failure_type": scorer_failure["failure_type"],
                        "failure_message": scorer_failure["failure_message"],
                    }
                )
        elif scorer is not None:
            for candidate in output_valid:
                self._score_adjudicated_candidate(
                    candidate=candidate,
                    scorer=scorer,
                    evaluator_prompt=evaluator_prompt,
                    evaluator_config=evaluator_config if isinstance(evaluator_config, dict) else {},
                    step=step,
                    output_contract_step=output_contract_step,
                    run_root=run_root,
                    frame_scope=frame_scope,
                    step_id=step_id,
                    visit_count=int(visit_count or 1),
                    context=context,
                    state=state,
                )

        selection = select_candidate(
            candidates,
            require_score_for_single_candidate=require_single_score,
        )
        if selection.error_type is not None:
            ledger_failure = self._write_adjudication_ledgers_failure(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=None,
                selection_reason="none",
                promotion_status="not_selected",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result(selection.error_type, selection.error_type, candidates=candidates, visit_paths=visit_paths)

        selected = next(candidate for candidate in candidates if candidate["candidate_id"] == selection.selected_candidate_id)
        for candidate in candidates:
            candidate["selected"] = candidate["candidate_id"] == selection.selected_candidate_id
            if candidate["selected"]:
                candidate["promotion_status"] = "pending"
            else:
                candidate["promotion_status"] = "not_selected"
        selected_paths = candidate_paths(run_root, frame_scope, step_id, int(visit_count or 1), str(selection.selected_candidate_id))
        ledger_path = adjudicated.get("score_ledger_path")
        if isinstance(ledger_path, str):
            ledger_abs = (self.workspace / ledger_path).resolve()
            dynamic_paths = set(self._promotion_destination_paths(output_contract_step, selected.get("artifacts", {})))
            if ledger_abs in dynamic_paths:
                return self._adjudication_failure_result("ledger_path_collision", "score ledger path collides with promoted outputs")
        try:
            promotion = promote_candidate_outputs(
                expected_outputs=resolved_expected_outputs,
                output_bundle=resolved_output_bundle,
                candidate_workspace=selected_paths.workspace,
                parent_workspace=self.workspace,
                baseline_manifest=baseline_manifest,
                promotion_manifest_path=visit_paths.promotion_manifest_path,
            )
        except PromotionConflictError as exc:
            ledger_failure = self._write_adjudication_ledgers_failure(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=str(selection.selected_candidate_id),
                selection_reason=selection.selection_reason,
                promotion_status="failed",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result(getattr(exc, "failure_type", "promotion_conflict"), str(exc), candidates=candidates, visit_paths=visit_paths)

        selected["promotion_status"] = "committed"
        selected["promoted_paths"] = promotion.promoted_paths
        ledger_failure = self._write_adjudication_ledgers_failure(
            adjudicated=adjudicated,
            visit_paths=visit_paths,
            state=state,
            step_id=step_id,
            step_name=step_name,
            visit_count=int(visit_count or 1),
            candidates=candidates,
            selected_candidate_id=str(selection.selected_candidate_id),
            selection_reason=selection.selection_reason,
            promotion_status="committed",
            promoted_paths=promotion.promoted_paths,
            execution_frame_id=execution_frame_id,
            call_frame_id=call_frame_id,
        )
        if ledger_failure is not None:
            return ledger_failure
        try:
            if resolved_output_bundle is not None:
                artifacts = validate_output_bundle(resolved_output_bundle, workspace=self.workspace)
            else:
                artifacts = validate_expected_outputs(resolved_expected_outputs or [], workspace=self.workspace)
        except OutputContractError as exc:
            return self._adjudication_failure_result("promotion_validation_failed", str(exc), candidates=candidates, visit_paths=visit_paths)

        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": duration_ms,
            "artifacts": artifacts,
            "adjudication": self._adjudication_state_block(
                selected_candidate_id=str(selection.selected_candidate_id),
                selected_score=selection.selected_score,
                selection_reason=selection.selection_reason,
                promotion_status="committed",
                scorer=scorer,
                score_ledger_path=ledger_path if isinstance(ledger_path, str) else None,
                run_score_ledger_path=visit_paths.run_score_ledger_path,
                scorer_snapshot_path=visit_paths.scorer_root / "metadata.json",
                promotion_manifest_path=visit_paths.promotion_manifest_path,
                candidates=candidates,
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
            ),
        }

    def _adjudication_required_path_surfaces(self, step: Dict[str, Any]) -> list[PathSurface]:
        surfaces: list[PathSurface] = []
        input_file = step.get("input_file")
        if isinstance(input_file, str):
            surfaces.append(PathSurface("input_file", Path(input_file)))
        depends_on = step.get("depends_on")
        if isinstance(depends_on, dict):
            for key in ("required",):
                values = depends_on.get(key)
                if isinstance(values, list):
                    for index, value in enumerate(values):
                        if isinstance(value, str):
                            surfaces.append(PathSurface(f"depends_on.{key}[{index}]", Path(value)))
        consume_bundle = step.get("consume_bundle")
        if isinstance(consume_bundle, dict) and isinstance(consume_bundle.get("path"), str):
            surfaces.append(PathSurface("consume_bundle.path", Path(consume_bundle["path"])))
        for index, spec in enumerate(step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []):
            if isinstance(spec, dict) and isinstance(spec.get("path"), str):
                surfaces.append(PathSurface(f"expected_outputs[{index}].path", Path(spec["path"])))
        output_bundle = step.get("output_bundle")
        if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
            surfaces.append(PathSurface("output_bundle.path", Path(output_bundle["path"])))
        return surfaces

    def _candidate_step_from_adjudicated_step(
        self,
        step: Dict[str, Any],
        candidate_config: Mapping[str, Any],
    ) -> Dict[str, Any]:
        candidate_step = dict(step)
        candidate_step.pop("adjudicated_provider", None)
        candidate_step["provider"] = candidate_config.get("provider")
        if "provider_params" in candidate_config:
            candidate_step["provider_params"] = candidate_config.get("provider_params")
        else:
            candidate_step.pop("provider_params", None)
        if "asset_file" in candidate_config:
            candidate_step["asset_file"] = candidate_config["asset_file"]
            candidate_step.pop("input_file", None)
        elif "input_file" in candidate_config:
            candidate_step["input_file"] = candidate_config["input_file"]
            candidate_step.pop("asset_file", None)
        return candidate_step

    def _resolve_adjudication_scorer(
        self,
        evaluator_config: Mapping[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        visit_paths: Any,
    ) -> tuple[Optional[dict[str, Any]], str, Optional[dict[str, Any]]]:
        limits = dict(evaluator_config.get("evidence_limits") or {})
        limits.setdefault("max_item_bytes", 262144)
        limits.setdefault("max_packet_bytes", 1048576)
        evaluator_prompt_source_kind = "asset_file" if "asset_file" in evaluator_config else "input_file"
        evaluator_prompt_source = evaluator_config.get("asset_file") or evaluator_config.get("input_file")
        rubric_source_kind = None
        rubric_source = None
        if "rubric_asset_file" in evaluator_config:
            rubric_source_kind = "asset_file"
            rubric_source = evaluator_config.get("rubric_asset_file")
        elif "rubric_input_file" in evaluator_config:
            rubric_source_kind = "input_file"
            rubric_source = evaluator_config.get("rubric_input_file")

        def scorer_failure(failure_type: str, failure_message: str) -> dict[str, Any]:
            payload = {
                "failure_type": failure_type,
                "failure_message": failure_message,
                "evaluator_provider": evaluator_config.get("provider"),
                "evaluator_params": evaluator_config.get("provider_params", {}),
                "evaluator_prompt_source_kind": evaluator_prompt_source_kind,
                "evaluator_prompt_source": evaluator_prompt_source,
                "rubric_source_kind": rubric_source_kind,
                "rubric_source": rubric_source,
                "evaluator_json_contract": "adjudication.evaluator_json.v1",
                "evaluation_packet_schema": EVALUATION_PACKET_SCHEMA,
                "evidence_limits": limits,
                "evidence_confidentiality": evaluator_config.get("evidence_confidentiality"),
                "secret_detection_policy": SECRET_DETECTION_POLICY,
            }
            payload["scorer_resolution_failure_key"] = self._stable_runtime_hash(
                {
                    key: value
                    for key, value in payload.items()
                    if key not in {"failure_message", "scorer_resolution_failure_key"}
                }
            )
            persist_scorer_resolution_failure(payload, visit_paths.scorer_root)
            return payload

        evaluator_prompt, prompt_error = self.prompt_composer.read_prompt_source(
            dict(evaluator_config),
            step_name="adjudication_evaluator",
            contract_violation_result=self._contract_violation_result,
        )
        if prompt_error is not None:
            return None, "", scorer_failure(
                prompt_error.get("error", {}).get("type", "scorer_unavailable"),
                prompt_error.get("error", {}).get("message", "scorer prompt unavailable"),
            )
        rubric_content = None
        rubric_hash = None
        if rubric_source_kind is not None and isinstance(rubric_source, str):
            if rubric_source_kind == "input_file" and not (self.workspace / rubric_source).exists():
                return None, "", scorer_failure("rubric_read_failed", f"rubric input file '{rubric_source}' does not exist")
            rubric_step = {rubric_source_kind: rubric_source}
            rubric_content, rubric_error = self.prompt_composer.read_prompt_source(
                rubric_step,
                step_name="adjudication_evaluator_rubric",
                contract_violation_result=self._contract_violation_result,
            )
            if rubric_error is not None:
                return None, "", scorer_failure(
                    rubric_error.get("error", {}).get("type", "rubric_read_failed"),
                    rubric_error.get("error", {}).get("message", "rubric unavailable"),
                )
            rubric_hash = self._text_hash(rubric_content)
        provider_name = evaluator_config.get("provider")
        if not isinstance(provider_name, str):
            return None, "", scorer_failure("missing_evaluator_provider", "evaluator provider is missing")
        provider_context = self._create_provider_context(context, state)
        merged_params = self.provider_registry.merge_params(provider_name, evaluator_config.get("provider_params", {}))
        try:
            substituted_params, param_errors = self.provider_executor._substitute_params(merged_params, provider_context)
        except Exception as exc:
            param_errors = [str(exc)]
            substituted_params = {}
        if param_errors:
            return None, "", scorer_failure(
                "evaluator_params_substitution_failed",
                "; ".join(str(error) for error in param_errors),
            )
        scorer = {
            "evaluator_provider": provider_name,
            "evaluator_model": self._provider_model(substituted_params),
            "evaluator_params": substituted_params,
            "evaluator_params_hash": self._stable_runtime_hash(substituted_params),
            "evaluator_config_hash": self._stable_runtime_hash(evaluator_config),
            "evaluator_prompt_source_kind": evaluator_prompt_source_kind,
            "evaluator_prompt_source": evaluator_prompt_source,
            "evaluator_prompt_content": evaluator_prompt,
            "evaluator_prompt_hash": self._text_hash(evaluator_prompt),
            "rubric_source_kind": rubric_source_kind,
            "rubric_source": rubric_source,
            "rubric_content": rubric_content,
            "rubric_hash": rubric_hash,
            "evidence_confidentiality": evaluator_config.get("evidence_confidentiality"),
            "secret_detection_policy": SECRET_DETECTION_POLICY,
            "evaluation_packet_schema": EVALUATION_PACKET_SCHEMA,
            "evidence_limits": limits,
        }
        scorer["scorer_identity_hash"] = scorer_identity_hash(scorer)
        persist_scorer_snapshot(scorer, visit_paths.scorer_root)
        return scorer, evaluator_prompt, None

    def _score_adjudicated_candidate(
        self,
        *,
        candidate: dict[str, Any],
        scorer: dict[str, Any],
        evaluator_prompt: str,
        evaluator_config: Mapping[str, Any],
        step: Dict[str, Any],
        output_contract_step: Dict[str, Any],
        run_root: Path,
        frame_scope: str,
        step_id: str,
        visit_count: int,
        context: Dict[str, Any],
        state: Dict[str, Any],
    ) -> None:
        paths = candidate_paths(run_root, frame_scope, step_id, visit_count, str(candidate["candidate_id"]))
        candidate.update(
            {
                "scorer_identity_hash": scorer.get("scorer_identity_hash"),
                "evaluator_provider": scorer.get("evaluator_provider"),
                "evaluator_model": scorer.get("evaluator_model"),
                "evaluator_params_hash": scorer.get("evaluator_params_hash"),
                "evaluator_config_hash": scorer.get("evaluator_config_hash"),
                "evaluator_prompt_source_kind": scorer.get("evaluator_prompt_source_kind"),
                "evaluator_prompt_source": scorer.get("evaluator_prompt_source"),
                "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash"),
                "evidence_confidentiality": scorer.get("evidence_confidentiality"),
                "secret_detection_policy": scorer.get("secret_detection_policy"),
                "rubric_source_kind": scorer.get("rubric_source_kind"),
                "rubric_source": scorer.get("rubric_source"),
                "rubric_hash": scorer.get("rubric_hash"),
            }
        )
        try:
            packet = build_evaluation_packet(
                candidate_id=str(candidate["candidate_id"]),
                candidate_workspace=paths.workspace,
                rendered_prompt=paths.prompt_path.read_text(encoding="utf-8"),
                expected_outputs=output_contract_step.get("expected_outputs"),
                output_bundle=output_contract_step.get("output_bundle"),
                artifacts=candidate.get("artifacts", {}),
                scorer=scorer,
                evidence_limits=scorer.get("evidence_limits"),
                workflow_secret_values=self._workflow_secret_values(step),
                rubric_content=scorer.get("rubric_content") if isinstance(scorer.get("rubric_content"), str) else None,
            )
            paths.evaluation_packet_path.parent.mkdir(parents=True, exist_ok=True)
            paths.evaluation_packet_path.write_text(json.dumps(packet, sort_keys=True, ensure_ascii=False), encoding="utf-8")
            candidate["evaluation_packet_hash"] = packet["evaluation_packet_hash"]
        except (EvidencePacketError, OSError, ValueError) as exc:
            candidate.update(
                {
                    "score_status": "evaluation_failed",
                    "failure_type": getattr(exc, "failure_type", "evidence_packet_failed"),
                    "failure_message": str(exc),
                }
            )
            return

        evaluator_prompt_text = f"{evaluator_prompt}\n\nEvaluator Packet:{json.dumps(packet, sort_keys=True, ensure_ascii=False)}"
        invocation, error = self.provider_executor.prepare_invocation(
            provider_name=str(evaluator_config.get("provider")),
            params=ProviderParams(
                params=evaluator_config.get("provider_params", {}),
                input_file=evaluator_config.get("input_file"),
                output_file=None,
            ),
            context=self._create_provider_context(context, state),
            prompt_content=evaluator_prompt_text,
            env=step.get("env"),
            secrets=step.get("secrets"),
            timeout_sec=step.get("timeout_sec"),
        )
        if error or invocation is None:
            candidate.update(
                {
                    "score_status": "evaluation_failed",
                    "failure_type": (error or {}).get("type", "evaluator_preparation_failed"),
                    "failure_message": (error or {}).get("message", "evaluator preparation failed"),
                }
            )
            return
        paths.evaluator_workspace.mkdir(parents=True, exist_ok=True)
        exec_result = self._execute_provider_invocation(invocation, cwd=paths.evaluator_workspace)
        paths.evaluation_output_path.write_bytes(exec_result.stdout)
        if exec_result.exit_code != 0:
            candidate.update(
                {
                    "score_status": "evaluation_failed",
                    "failure_type": "evaluator_failed",
                    "failure_message": "evaluator provider failed",
                }
            )
            return
        try:
            parsed = parse_evaluator_output(exec_result.stdout, expected_candidate_id=str(candidate["candidate_id"]))
        except EvaluatorOutputError as exc:
            candidate.update(
                {
                    "score_status": "evaluation_failed",
                    "failure_type": "invalid_evaluator_json",
                    "failure_message": str(exc),
                }
            )
            return
        candidate.update(
            {
                "score_status": "scored",
                "score": parsed["score"],
                "summary": parsed["summary"],
            }
        )

    def _write_adjudication_ledgers(
        self,
        *,
        adjudicated: Mapping[str, Any],
        visit_paths: Any,
        state: Dict[str, Any],
        step_id: str,
        step_name: str,
        visit_count: int,
        candidates: list[dict[str, Any]],
        selected_candidate_id: Optional[str],
        selection_reason: str,
        promotion_status: str,
        promoted_paths: Mapping[str, str],
        execution_frame_id: str,
        call_frame_id: Optional[str],
    ) -> list[dict[str, Any]]:
        rows = generate_score_ledger_rows(
            run_id=str(state.get("run_id", self.state_manager.run_id)),
            workflow_file=str(state.get("workflow_file", "")),
            workflow_checksum=str(state.get("workflow_checksum", "")),
            dsl_version=self.workflow_version,
            execution_frame_id=execution_frame_id,
            call_frame_id=call_frame_id,
            step_id=step_id,
            step_name=step_name,
            visit_count=visit_count,
            candidates=candidates,
            selected_candidate_id=selected_candidate_id,
            selection_reason=selection_reason,
            promotion_status=promotion_status,
            promoted_paths=promoted_paths,
        )
        materialize_run_score_ledger(rows, visit_paths.run_score_ledger_path)
        mirror = adjudicated.get("score_ledger_path")
        if isinstance(mirror, str):
            materialize_score_ledger_mirror(rows, self.workspace / mirror)
        return rows

    def _write_adjudication_ledgers_failure(
        self,
        *,
        adjudicated: Mapping[str, Any],
        visit_paths: Any,
        state: Dict[str, Any],
        step_id: str,
        step_name: str,
        visit_count: int,
        candidates: list[dict[str, Any]],
        selected_candidate_id: Optional[str],
        selection_reason: str,
        promotion_status: str,
        promoted_paths: Mapping[str, str],
        execution_frame_id: str,
        call_frame_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        try:
            self._write_adjudication_ledgers(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=visit_count,
                candidates=candidates,
                selected_candidate_id=selected_candidate_id,
                selection_reason=selection_reason,
                promotion_status=promotion_status,
                promoted_paths=promoted_paths,
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
            )
        except LedgerConflictError as exc:
            return self._adjudication_failure_result("ledger_conflict", str(exc), candidates=candidates, visit_paths=visit_paths)
        except OSError as exc:
            return self._adjudication_failure_result("ledger_mirror_failed", str(exc), candidates=candidates, visit_paths=visit_paths)
        return None

    def _adjudication_failure_result(
        self,
        error_type: str,
        message: str,
        *,
        candidates: Optional[list[dict[str, Any]]] = None,
        visit_paths: Any = None,
    ) -> Dict[str, Any]:
        mapped = adjudication_outcome(error_type)
        result = {
            "status": "failed",
            "exit_code": mapped["exit_code"],
            "duration_ms": 0,
            "error": {
                "type": error_type,
                "message": message,
            },
            "outcome": mapped["outcome"],
        }
        if candidates is not None or visit_paths is not None:
            result["adjudication"] = {
                "schema": "adjudicated_provider.state.v1",
                "selected_candidate_id": None,
                "selected_score": None,
                "selection_reason": "none",
                "promotion_status": "failed",
                "run_score_ledger_path": (
                    visit_paths.run_score_ledger_path.as_posix()
                    if visit_paths is not None
                    else None
                ),
                "candidates": self._candidate_state_map(candidates or []),
            }
        return result

    def _adjudication_state_block(
        self,
        *,
        selected_candidate_id: str,
        selected_score: Optional[float],
        selection_reason: str,
        promotion_status: str,
        scorer: Optional[Mapping[str, Any]],
        score_ledger_path: Optional[str],
        run_score_ledger_path: Path,
        scorer_snapshot_path: Path,
        promotion_manifest_path: Path,
        candidates: list[dict[str, Any]],
        execution_frame_id: str,
        call_frame_id: Optional[str],
    ) -> dict[str, Any]:
        return {
            "schema": "adjudicated_provider.state.v1",
            "execution_frame_id": execution_frame_id,
            "call_frame_id": call_frame_id,
            "selected_candidate_id": selected_candidate_id,
            "selected_score": selected_score,
            "selection_reason": selection_reason,
            "promotion_status": promotion_status,
            "scorer_identity_hash": scorer.get("scorer_identity_hash") if scorer else None,
            "evaluator_prompt_hash": scorer.get("evaluator_prompt_hash") if scorer else None,
            "evidence_confidentiality": scorer.get("evidence_confidentiality") if scorer else None,
            "secret_detection_policy": SECRET_DETECTION_POLICY,
            "score_ledger_path": score_ledger_path,
            "run_score_ledger_path": run_score_ledger_path.as_posix(),
            "scorer_snapshot_path": scorer_snapshot_path.as_posix(),
            "promotion_manifest_path": promotion_manifest_path.as_posix(),
            "candidates": self._candidate_state_map(candidates),
        }

    def _candidate_state_map(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for candidate in candidates:
            candidate_id = str(candidate.get("candidate_id"))
            result[candidate_id] = {
                "candidate_status": candidate.get("candidate_status"),
                "score_status": candidate.get("score_status"),
                "score": candidate.get("score"),
                "selected": bool(candidate.get("selected", False)),
                "promotion_status": candidate.get("promotion_status", "not_selected"),
                "candidate_root": candidate.get("candidate_root"),
                "failure_type": candidate.get("failure_type"),
                "failure_message": candidate.get("failure_message"),
            }
        return result

    def _output_paths_from_contract(self, step: Dict[str, Any]) -> dict[str, str]:
        paths: dict[str, str] = {}
        for spec in step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []:
            if isinstance(spec, dict) and isinstance(spec.get("name"), str) and isinstance(spec.get("path"), str):
                paths[spec["name"]] = spec["path"]
        output_bundle = step.get("output_bundle")
        if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
            paths["output_bundle"] = output_bundle["path"]
        return paths

    def _promotion_destination_paths(self, step: Dict[str, Any], artifacts: Mapping[str, Any]) -> set[Path]:
        paths: set[Path] = set()
        for spec in step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []:
            if not isinstance(spec, dict):
                continue
            if isinstance(spec.get("path"), str):
                paths.add((self.workspace / spec["path"]).resolve())
            if spec.get("type") == "relpath" and spec.get("must_exist_target") and isinstance(spec.get("name"), str):
                value = artifacts.get(spec["name"])
                if isinstance(value, str):
                    paths.add((self.workspace / value).resolve())
        output_bundle = step.get("output_bundle")
        if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
            paths.add((self.workspace / output_bundle["path"]).resolve())
        return paths

    def _workflow_secret_values(self, step: Dict[str, Any]) -> list[str]:
        secret_names = []
        secret_names.extend(self.global_secrets)
        step_secrets = step.get("secrets")
        if isinstance(step_secrets, list):
            secret_names.extend(name for name in step_secrets if isinstance(name, str))
        values: list[str] = []
        for name in secret_names:
            value = os.environ.get(name)
            if value:
                values.append(value)
        return values

    def _provider_model(self, params: Any) -> Optional[str]:
        if isinstance(params, Mapping):
            model = params.get("model") or params.get("reasoning_model")
            return model if isinstance(model, str) else None
        return None

    def _stable_runtime_hash(self, payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
        from hashlib import sha256

        return f"sha256:{sha256(encoded).hexdigest()}"

    def _text_hash(self, text: str) -> str:
        from hashlib import sha256

        return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"

    def _path_under(self, path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

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
        cwd: Optional[Path] = None,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute provider invocation with backward-compatible call shape."""
        execute_fn = self.provider_executor.execute
        try:
            return execute_fn(
                invocation,
                cwd=cwd,
                stream_output=(self.debug or self.stream_output),
                session_runtime=session_runtime,
            )
        except TypeError as exc:
            message = str(exc)
            if "unexpected keyword argument 'cwd'" in message:
                try:
                    return execute_fn(
                        invocation,
                        stream_output=(self.debug or self.stream_output),
                        session_runtime=session_runtime,
                    )
                except TypeError as nested_exc:
                    nested_message = str(nested_exc)
                    if "unexpected keyword argument 'session_runtime'" in nested_message:
                        try:
                            return execute_fn(invocation, stream_output=(self.debug or self.stream_output))
                        except TypeError as final_exc:
                            if "unexpected keyword argument 'stream_output'" not in str(final_exc):
                                raise
                            return execute_fn(invocation)
                    if "unexpected keyword argument 'stream_output'" not in nested_message:
                        raise
                    return execute_fn(invocation)
            if "unexpected keyword argument 'session_runtime'" in message:
                try:
                    return execute_fn(invocation, cwd=cwd, stream_output=(self.debug or self.stream_output))
                except TypeError as nested_exc:
                    if "unexpected keyword argument 'cwd'" in str(nested_exc):
                        try:
                            return execute_fn(invocation, stream_output=(self.debug or self.stream_output))
                        except TypeError as final_exc:
                            if "unexpected keyword argument 'stream_output'" not in str(final_exc):
                                raise
                            return execute_fn(invocation)
                    if "unexpected keyword argument 'stream_output'" not in str(nested_exc):
                        raise
                    return execute_fn(invocation)
            if "unexpected keyword argument 'stream_output'" not in message:
                raise
            try:
                return execute_fn(invocation, cwd=cwd)
            except TypeError as nested_exc:
                if "unexpected keyword argument 'cwd'" not in str(nested_exc):
                    raise
                return execute_fn(invocation)

    def _resolve_output_contract_paths(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
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
                        context=context,
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
                    context=context,
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
        context: Optional[Dict[str, Any]] = None,
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
            context=context,
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
                run_state.context
                if isinstance(run_state.context, dict) and run_state.context
                else self.workflow_context_defaults,
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

        registry = self.workflow_artifacts
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
        registry = self.workflow_artifacts
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
                validation_spec = spec.definition
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
        branch_name = node.branch_name if isinstance(node, IfBranchMarkerNode) else None
        statement_name = node.statement_name if isinstance(node, IfBranchMarkerNode) else None
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
        case_name = node.case_name if isinstance(node, MatchCaseMarkerNode) else None
        statement_name = node.statement_name if isinstance(node, MatchCaseMarkerNode) else None
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
        state_context = state.get('context')
        context = {'context': state_context} if isinstance(state_context, dict) and state_context else {}
        return self._execute_provider_with_context(step, context, state)

    def _execute_command(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command step without loop context."""
        state_context = state.get('context')
        context = {'context': state_context} if isinstance(state_context, dict) and state_context else {}
        return self._execute_command_with_context(step, context, state)
