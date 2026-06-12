"""
Workflow executor with for-each loop support.
Implements AT-3, AT-13: Dynamic for-each execution with pointer resolution.
"""

import json
import logging
import os
import threading
import time
import traceback
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
from ..managed_jobs.recovery import recover_managed_jobs
from ..managed_jobs.runtime import ManagedProviderRuntime
from ..deps.resolver import DependencyResolver
from ..deps.injector import DependencyInjector
from ..contracts.output_contract import (
    OutputContractError,
    validate_contract_value,
    validate_expected_outputs,
    validate_output_bundle,
    validate_variant_output_bundle,
)
from .pure_expr import (
    PureExprEvaluationError,
    canonical_json_for_pure_value,
    evaluate_pure_expr,
)
from .pointers import PointerResolver
from .conditions import ConditionEvaluator
from .conditions import EqualsConditionNode, ExistsConditionNode, NotExistsConditionNode
from ..security.secrets import SecretsManager
from ..variables.substitution import VariableSubstitutor
from ..observability.summary import SummaryObserver
from ..observability.live_notes import LiveAgentNoteObserver
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
    PureProjectionStepConfig,
    RepeatUntilFrameNode,
    WorkflowInputAddress,
)
from .finalization import FinalizationController
from .identity import iteration_step_id, runtime_step_id
from .loaded_bundle import (
    workflow_boundary_projection,
    workflow_bundle,
    workflow_context,
    workflow_generated_path_allocations,
    workflow_managed_write_root_inputs,
    workflow_output_contracts,
    workflow_private_artifacts,
    workflow_provenance,
    workflow_runtime_context_inputs,
    workflow_runtime_input_contracts,
)
from .state_layout import GeneratedPathSemanticRole, render_generated_path_template
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
from .references import ReferenceResolutionError, ReferenceResolver, parse_structured_ref
from .resume_planner import ResumePlanner, ResumeStateIntegrityError
from .runtime_context import RuntimeContext
from .runtime_step import RuntimeStep
from .runtime_types import RoutingDecision, StepExecutionIdentity
from .signatures import WorkflowSignatureError, resolve_workflow_outputs
from .executable_ir import ManagedJobsConfig, ManagedJobsRoutes
from .adjudication import (
    AdjudicationDeadline,
    BASELINE_COPY_POLICY,
    EVALUATION_PACKET_SCHEMA,
    EvaluatorOutputError,
    EvidencePacketError,
    LedgerConflictError,
    PathSurface,
    PromotionConflictError,
    SECRET_DETECTION_POLICY,
    adjudication_sidecars_exist,
    adjudication_outcome,
    adjudication_visit_paths,
    build_evaluation_packet,
    candidate_metadata_path,
    candidate_paths,
    create_baseline_snapshot,
    generate_score_ledger_rows,
    load_baseline_manifest,
    load_candidate_metadata,
    load_score_ledger_rows,
    load_scorer_resolution_failure,
    load_scorer_snapshot,
    materialize_run_score_ledger,
    materialize_score_ledger_mirror,
    parse_evaluator_output,
    persist_candidate_metadata,
    persist_scorer_resolution_failure,
    persist_scorer_snapshot,
    prepare_candidate_workspace_from_baseline,
    promote_candidate_outputs,
    scorer_identity_hash,
    select_candidate,
)

logger = logging.getLogger(__name__)


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
        frame_root_name = _path_safe_frame_scope_token(frame_id)
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
        self.runtime_plan = getattr(self.loaded_bundle, "runtime_plan", None)
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
        private_artifacts = workflow_private_artifacts(self.loaded_bundle)
        self.private_workflow_artifacts = {
            name: _thaw_workflow_value(entry.contract.definition)
            for name, entry in private_artifacts.items()
            if isinstance(name, str)
        }
        for private_artifact_name in self.private_workflow_artifacts:
            self.workflow_artifacts.pop(private_artifact_name, None)
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
        self.live_agent_note_observer = self._create_live_agent_note_observer()
        provenance = workflow_provenance(workflow)
        workflow_path = provenance.workflow_path if provenance is not None else None
        self._compiled_frontend_kind = provenance.frontend_kind if provenance is not None else None
        self._compiled_frontend_node_origins = self._load_compiled_frontend_node_origins(provenance)
        self._compiled_frontend_step_origins = self._load_compiled_frontend_step_origins(provenance)
        self._compiled_frontend_command_boundaries = self._load_compiled_frontend_command_boundaries(provenance)
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
            private_artifact_registry=self.private_workflow_artifacts,
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
        if self.runtime_plan is not None:
            self._step_node_ids = list(self.runtime_plan.ordered_node_ids)
        else:
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

    def _load_compiled_frontend_source_trace_payload(
        self,
        provenance: Any,
    ) -> Mapping[str, Any]:
        """Load the persisted compiled-frontend source-trace payload once."""
        source_trace_path = (
            provenance.frontend_source_trace_path
            if provenance is not None
            else None
        )
        if not isinstance(source_trace_path, Path) or not source_trace_path.exists():
            return {}
        cache_key = str(source_trace_path.resolve())
        payload_cache = getattr(self, "_compiled_frontend_source_trace_payload_cache", None)
        if isinstance(payload_cache, dict) and cache_key in payload_cache:
            return payload_cache[cache_key]
        try:
            payload = json.loads(source_trace_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("Failed to read compiled frontend source trace %s: %s", source_trace_path, exc)
            return {}
        normalized = payload if isinstance(payload, Mapping) else {}
        if not isinstance(payload_cache, dict):
            payload_cache = {}
            self._compiled_frontend_source_trace_payload_cache = payload_cache
        payload_cache[cache_key] = normalized
        return normalized

    def _load_compiled_frontend_step_origins(
        self,
        provenance: Any,
    ) -> Dict[str, Mapping[str, Any]]:
        """Load persisted frontend source-trace entries keyed by step identity."""
        payload = self._load_compiled_frontend_source_trace_payload(provenance)

        indexed: Dict[str, Mapping[str, Any]] = {}
        workflows = payload.get("workflows")
        if not isinstance(workflows, Mapping):
            return indexed
        for workflow_payload in workflows.values():
            if not isinstance(workflow_payload, Mapping):
                continue
            step_ids = workflow_payload.get("step_ids")
            if not isinstance(step_ids, Mapping):
                continue
            for key, origin in step_ids.items():
                if isinstance(key, str) and isinstance(origin, Mapping):
                    indexed.setdefault(key, origin)
        return indexed

    def _load_compiled_frontend_node_origins(
        self,
        provenance: Any,
    ) -> Dict[str, Mapping[str, Any]]:
        """Load persisted frontend source-trace entries keyed by executable node id."""
        payload = self._load_compiled_frontend_source_trace_payload(provenance)

        indexed: Dict[str, Mapping[str, Any]] = {}
        workflows = payload.get("workflows")
        if not isinstance(workflows, Mapping):
            return indexed
        for workflow_payload in workflows.values():
            if not isinstance(workflow_payload, Mapping):
                continue
            origins_by_key: Dict[str, Mapping[str, Any]] = {}
            for section in (
                "step_ids",
                "generated_inputs",
                "generated_outputs",
                "generated_paths",
                "generated_internal_inputs",
            ):
                entries = workflow_payload.get(section)
                if not isinstance(entries, Mapping):
                    continue
                for origin in entries.values():
                    if not isinstance(origin, Mapping):
                        continue
                    origin_key = origin.get("origin_key")
                    if isinstance(origin_key, str) and origin_key:
                        origins_by_key.setdefault(origin_key, origin)
            workflow_origin = workflow_payload.get("workflow_origin")
            if isinstance(workflow_origin, Mapping):
                origin_key = workflow_origin.get("origin_key")
                if isinstance(origin_key, str) and origin_key:
                    origins_by_key.setdefault(origin_key, workflow_origin)
            for node in workflow_payload.get("executable_nodes", ()):
                if not isinstance(node, Mapping):
                    continue
                node_id = node.get("node_id")
                origin_key = node.get("origin_key")
                if not isinstance(node_id, str) or not isinstance(origin_key, str):
                    continue
                origin = origins_by_key.get(origin_key)
                if origin is not None:
                    indexed.setdefault(node_id, origin)
        return indexed

    def _load_compiled_frontend_command_boundaries(
        self,
        provenance: Any,
    ) -> Dict[str, Mapping[str, Any]]:
        """Load persisted command-boundary lineage keyed by step id."""
        payload = self._load_compiled_frontend_source_trace_payload(provenance)

        indexed: Dict[str, Mapping[str, Any]] = {}
        workflows = payload.get("workflows")
        if not isinstance(workflows, Mapping):
            return indexed
        for workflow_payload in workflows.values():
            if not isinstance(workflow_payload, Mapping):
                continue
            for boundary in workflow_payload.get("command_boundaries", ()):
                if not isinstance(boundary, Mapping):
                    continue
                step_id = boundary.get("step_id")
                if isinstance(step_id, str) and step_id:
                    indexed.setdefault(step_id, boundary)
        return indexed

    def _compiled_frontend_origin_for_step(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Resolve one runtime step back to compiled frontend source metadata."""
        if isinstance(node_id, str) and node_id:
            origin = self._compiled_frontend_node_origins.get(node_id)
            if origin is not None:
                return origin
        candidate_keys = [step_name, step_id]
        if step_id.startswith("root."):
            candidate_keys.append(step_id[len("root."):])
        for candidate in candidate_keys:
            if not isinstance(candidate, str) or not candidate:
                continue
            origin = self._compiled_frontend_step_origins.get(candidate)
            if origin is not None:
                return origin
        return None

    def _compiled_frontend_command_boundary_for_step(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None = None,
    ) -> Mapping[str, Any] | None:
        for candidate in (step_id, step_name):
            if not isinstance(candidate, str) or not candidate:
                continue
            boundary = self._compiled_frontend_command_boundaries.get(candidate)
            if boundary is not None:
                return boundary
        runtime_plan_node = self._runtime_plan_node_for_step(
            step_name,
            step_id,
            node_id=node_id,
        )
        if (
            runtime_plan_node is not None
            and isinstance(runtime_plan_node.command_boundary_kind, str)
            and runtime_plan_node.command_boundary_kind
            and isinstance(runtime_plan_node.command_boundary_name, str)
            and runtime_plan_node.command_boundary_name
        ):
            return {
                "boundary_kind": runtime_plan_node.command_boundary_kind,
                "command_name": runtime_plan_node.command_boundary_name,
                "adapter_name": runtime_plan_node.command_boundary_name,
            }
        return None

    def _emit_compiled_frontend_step_display(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None = None,
    ) -> None:
        """Emit source-aware observability lines for compiled frontend steps."""
        if self._compiled_frontend_kind != "workflow_lisp":
            return
        logger.info("Running step %s", step_name)
        origin = self._compiled_frontend_origin_for_step(step_name, step_id, node_id=node_id)
        if not isinstance(origin, Mapping):
            return
        path = origin.get("path")
        line = origin.get("line")
        column = origin.get("column")
        if isinstance(path, str) and isinstance(line, int):
            if isinstance(column, int):
                logger.info("  source: %s:%s:%s", path, line, column)
            else:
                logger.info("  source: %s:%s", path, line)
        form_path = origin.get("form_path")
        if isinstance(form_path, list) and form_path:
            logger.info("  form: %s", " > ".join(str(part) for part in form_path))
        boundary = self._compiled_frontend_command_boundary_for_step(
            step_name,
            step_id,
            node_id=node_id,
        )
        if not isinstance(boundary, Mapping):
            return
        if boundary.get("boundary_kind") == "certified_adapter":
            adapter_name = boundary.get("adapter_name")
            if isinstance(adapter_name, str) and adapter_name:
                logger.info("  certified adapter: %s", adapter_name)
            source_map_behavior = boundary.get("source_map_behavior")
            if isinstance(source_map_behavior, str) and source_map_behavior:
                logger.info("  source-map behavior: %s", source_map_behavior)

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
        return _path_safe_frame_scope_token(frame_id)

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
            else (
                self._runtime_plan_node_for_node_id(node.node_id).presentation_key
                if self._runtime_plan_node_for_node_id(node.node_id) is not None
                else self.projection.presentation_key_by_node_id.get(node.node_id, node.presentation_name)
            )
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
        if self.runtime_plan is not None:
            ordered_node_ids = self.runtime_plan.ordered_node_ids
            return ordered_node_ids[0] if ordered_node_ids else None
        if self.projection is None:
            return None
        ordered_node_ids = self.projection.ordered_execution_node_ids()
        return ordered_node_ids[0] if ordered_node_ids else None

    def _execution_index_for_node_id(self, node_id: str) -> int:
        """Return the combined execution index for one top-level executable node id."""
        runtime_plan_node = self._runtime_plan_node_for_node_id(node_id)
        if runtime_plan_node is not None and isinstance(runtime_plan_node.execution_index, int):
            return runtime_plan_node.execution_index
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
        if self.runtime_plan is not None and 0 <= step_index < len(self.runtime_plan.ordered_node_ids):
            return self.runtime_plan.ordered_node_ids[step_index]
        if self.projection is not None:
            return self.projection.node_id_for_execution_index(step_index)
        if 0 <= step_index < len(self._step_node_ids):
            node_id = self._step_node_ids[step_index]
            return node_id if isinstance(node_id, str) else None
        return None

    def _runtime_plan_node_for_node_id(self, node_id: str):
        """Return one runtime-plan node summary when the bundle exposes it."""
        if self.runtime_plan is None:
            return None
        return self.runtime_plan.nodes.get(node_id)

    def _runtime_plan_node_for_step(
        self,
        step_name: str,
        step_id: str,
        *,
        node_id: str | None = None,
    ):
        """Resolve one runtime step to a runtime-plan node summary when available."""
        if isinstance(node_id, str) and node_id:
            node = self._runtime_plan_node_for_node_id(node_id)
            if node is not None:
                return node
        if self.runtime_plan is None:
            return None
        for node in self.runtime_plan.nodes.values():
            if step_id == node.step_id or step_name == node.presentation_key or step_name == node.display_name:
                return node
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
        managed_job_outcome: Optional[str] = None,
    ) -> Optional[ExecutableTransfer]:
        """Return the explicit typed goto transfer selected by one step result."""
        if self.executable_ir is None:
            return None
        node = self.executable_ir.nodes.get(current_node_id)
        if node is None:
            return None

        if isinstance(managed_job_outcome, str):
            managed_key = {
                "COMPLETE": "managed_jobs_complete_goto",
                "FAILED": "managed_jobs_failed_goto",
                "INVALID": "managed_jobs_invalid_goto",
            }.get(managed_job_outcome)
            if managed_key is not None:
                return node.routed_transfers.get(managed_key)

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
        if not isinstance(current_node_id, str) or self.executable_ir is None or self.projection is None:
            return
        node = self.executable_ir.nodes.get(current_node_id)
        if not isinstance(node, (IfBranchMarkerNode, IfJoinNode, MatchCaseMarkerNode, MatchJoinNode)):
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
            if node.bound_when_predicate is None:
                return node.guard_condition, node.invert_guard
            if node.guard_condition is None:
                return node.bound_when_predicate, False
            branch_guard = (
                NotPredicateNode(item=node.guard_condition)
                if node.invert_guard
                else node.guard_condition
            )
            return (
                AllOfPredicateNode(items=(node.bound_when_predicate, branch_guard)),
                False,
            )
        if isinstance(node, MatchCaseMarkerNode):
            case_predicate = ComparePredicateNode(
                left=node.selector_address,
                op="eq",
                right=node.case_name,
            )
            if node.bound_when_predicate is None:
                return case_predicate, False
            return AllOfPredicateNode(items=(node.bound_when_predicate, case_predicate)), False
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

    def _executor_exception_error(
        self,
        exc: BaseException,
        *,
        step_name: Optional[str] = None,
        step_id: Optional[str] = None,
        step_index: Optional[int] = None,
        node_id: Optional[str] = None,
        visit_count: Optional[int] = None,
    ) -> Dict[str, Any]:
        context = {
            "step_name": step_name,
            "step_id": step_id,
            "step_index": step_index,
            "node_id": node_id,
            "visit_count": visit_count,
        }
        return {
            "type": "executor_unhandled_exception",
            "message": str(exc),
            "exception_type": type(exc).__name__,
            "traceback": "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            "context": {
                key: value for key, value in context.items() if value is not None
            },
        }

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
        if self.state_manager.state is not None:
            self.state_manager.state.bound_inputs = dict(bound_inputs)

        workflow_outputs = state.get('workflow_outputs', {})
        if not isinstance(workflow_outputs, dict):
            workflow_outputs = {}
            state['workflow_outputs'] = workflow_outputs

        self._persist_finalization_state(state)
        self.state_manager.update_workflow_outputs(workflow_outputs)
        self.state_manager.update_run_error(state.get('error') if isinstance(state.get('error'), dict) else None)

    def _persist_bound_inputs(self, state: Dict[str, Any]) -> None:
        """Persist the current workflow-boundary input bag."""
        bound_inputs = state.get('bound_inputs', {})
        if not isinstance(bound_inputs, dict):
            bound_inputs = {}
            state['bound_inputs'] = bound_inputs
        if self.state_manager.state is None:
            return
        self.state_manager.state.bound_inputs = dict(bound_inputs)
        self.state_manager._write_state()

    def _entry_managed_write_root_bindings(self) -> Dict[str, str]:
        """Return deterministic runtime-owned managed write-root bindings for entry workflows."""
        if not isinstance(self.state_manager, StateManager):
            return {}
        allocations = [
            allocation
            for allocation in workflow_generated_path_allocations(self.loaded_bundle)
            if allocation.semantic_role == GeneratedPathSemanticRole.ENTRYPOINT_MANAGED_WRITE_ROOT
            and isinstance(allocation.generated_input_name, str)
        ]
        if allocations:
            return {
                allocation.generated_input_name: render_generated_path_template(
                    allocation,
                    run_id=self.state_manager.run_id,
                )
                for allocation in allocations
            }
        workflow_root = Path(self.workflow_name) if isinstance(self.workflow_name, str) and self.workflow_name else Path("workflow")
        base = (
            Path(".orchestrate")
            / "workflow_lisp"
            / "entry"
            / self.state_manager.run_id
            / workflow_root
        )
        return {
            input_name: (base / f"{input_name}.json").as_posix()
            for input_name in workflow_managed_write_root_inputs(self.loaded_bundle)
            if isinstance(input_name, str)
        }

    def _entry_runtime_context_bindings(self) -> Dict[str, Any]:
        """Return deterministic runtime-owned hidden context bindings for entry workflows."""

        if not isinstance(self.state_manager, StateManager):
            return {}
        contracts = self._workflow_input_contracts()
        bindings: Dict[str, Any] = {}
        for binding in workflow_boundary_projection(self.loaded_bundle).private_runtime_context_bindings:
            if binding.context_family not in {"RunCtx", "PhaseCtx"}:
                continue
            for input_name in binding.generated_input_names:
                if not isinstance(input_name, str):
                    continue
                contract = contracts.get(input_name, {})
                derived_value = self._private_exec_context_binding_value(
                    binding=binding,
                    input_name=input_name,
                )
                if derived_value is not None:
                    bindings[input_name] = derived_value
                    continue
                default_value = contract.get("default") if isinstance(contract, dict) else None
                if default_value is not None:
                    bindings[input_name] = default_value
        return bindings

    def _private_exec_context_binding_value(
        self,
        *,
        binding: Any,
        input_name: str,
    ) -> Any:
        """Derive one runtime-owned hidden context value from structured binding metadata."""

        if not isinstance(self.state_manager, StateManager):
            return None
        prefix = f"{binding.source_param_name}__"
        relative_name = input_name[len(prefix):] if input_name.startswith(prefix) else input_name
        run_state_root = "state/run"
        run_artifact_root = "artifacts/run"
        phase_name = (
            binding.derived_phase_identity
            if binding.context_family == "PhaseCtx" and isinstance(binding.derived_phase_identity, str)
            else None
        )
        value_by_path = {
            "run-id": self.state_manager.run_id,
            "run__run-id": self.state_manager.run_id,
            "state-root": run_state_root,
            "run__state-root": run_state_root,
            "artifact-root": run_artifact_root,
            "run__artifact-root": run_artifact_root,
        }
        if phase_name is not None:
            value_by_path["phase-name"] = phase_name
            value_by_path["state-root"] = f"state/{phase_name}"
            value_by_path["artifact-root"] = f"artifacts/{phase_name}"
        return value_by_path.get(relative_name)

    def _runtime_context_inputs_missing_provenance(self) -> tuple[str, ...]:
        """Return hidden runtime-context inputs present in contracts but absent from provenance."""

        if not isinstance(self.state_manager, StateManager):
            return ()

        contracts = self._workflow_input_contracts()
        if not contracts:
            return ()
        if workflow_boundary_projection(self.loaded_bundle).private_runtime_context_bindings:
            return ()
        return tuple(
            sorted(
                {
                    input_name
                    for input_name in self.loaded_bundle.surface.provenance.runtime_context_inputs
                    if isinstance(input_name, str) and input_name in contracts
                }
            )
        )

    def _unsupported_private_exec_context_families(self) -> tuple[str, ...]:
        """Return private context families that this runtime cannot bootstrap."""

        return tuple(
            sorted(
                {
                    binding.context_family
                    for binding in workflow_boundary_projection(self.loaded_bundle).private_runtime_context_bindings
                    if binding.context_family not in {"RunCtx", "PhaseCtx"}
                }
            )
        )

    def _recorded_runtime_context_inputs(self) -> tuple[str, ...]:
        """Return hidden runtime-context inputs declared by the bundle."""

        return tuple(
            sorted(
                {
                    input_name
                    for input_name in workflow_runtime_context_inputs(self.loaded_bundle)
                    if isinstance(input_name, str)
                }
            )
        )

    def _ensure_entry_managed_write_root_bindings(
        self,
        state: Dict[str, Any],
        *,
        resume: bool,
    ) -> Optional[Dict[str, Any]]:
        """Allocate or validate runtime-owned managed write roots for entry workflows."""
        managed_bindings = self._entry_managed_write_root_bindings()
        if not managed_bindings:
            return None

        bound_inputs = state.get('bound_inputs', {})
        if not isinstance(bound_inputs, dict):
            bound_inputs = {}
            state['bound_inputs'] = bound_inputs

        changed = False
        for input_name, expected_value in managed_bindings.items():
            if input_name not in bound_inputs:
                bound_inputs[input_name] = expected_value
                changed = True
                continue

            current_value = bound_inputs[input_name]
            if resume and current_value == expected_value:
                continue

            return self._contract_violation_result(
                "Workflow input binding failed",
                {
                    "scope": "workflow_inputs",
                    "reason": "managed_write_root_override",
                    "input": input_name,
                    "value": self._json_safe_runtime_value(current_value),
                    "expected": expected_value,
                },
            )

        if changed:
            self._persist_bound_inputs(state)
        return None

    def _ensure_entry_runtime_context_bindings(
        self,
        state: Dict[str, Any],
        *,
        resume: bool,
    ) -> Optional[Dict[str, Any]]:
        """Allocate or validate runtime-owned hidden context inputs for entry workflows."""

        unsupported_families = self._unsupported_private_exec_context_families()
        if unsupported_families:
            return self._contract_violation_result(
                "Workflow input binding failed",
                {
                    "scope": "workflow_inputs",
                    "reason": "private_exec_context_bootstrap_unsupported",
                    "context_families": list(unsupported_families),
                },
            )

        missing_metadata_inputs = self._runtime_context_inputs_missing_provenance()
        if missing_metadata_inputs:
            return self._contract_violation_result(
                "Workflow input binding failed",
                {
                    "scope": "workflow_inputs",
                    "reason": "promoted_entry_hidden_context_metadata_missing",
                    "inputs": list(missing_metadata_inputs or self._recorded_runtime_context_inputs()),
                },
            )

        runtime_bindings = self._entry_runtime_context_bindings()
        if not runtime_bindings:
            return None

        bound_inputs = state.get('bound_inputs', {})
        if not isinstance(bound_inputs, dict):
            bound_inputs = {}
            state['bound_inputs'] = bound_inputs

        changed = False
        for input_name, expected_value in runtime_bindings.items():
            if input_name not in bound_inputs:
                bound_inputs[input_name] = expected_value
                changed = True
                continue

            current_value = bound_inputs[input_name]
            if current_value == expected_value:
                continue
            if resume and current_value == expected_value:
                continue

            return self._contract_violation_result(
                "Workflow input binding failed",
                {
                    "scope": "workflow_inputs",
                    "reason": "promoted_entry_hidden_context_override",
                    "input": input_name,
                    "value": self._json_safe_runtime_value(current_value),
                    "expected": expected_value,
                },
            )

        if changed:
            self._persist_bound_inputs(state)
        return None

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
        state.setdefault('private_artifact_versions', {})
        state.setdefault('private_artifact_consumes', {})
        state.setdefault('transition_count', 0)
        state.setdefault('step_visits', {})
        state.setdefault('bound_inputs', {})
        state.setdefault('workflow_outputs', {})
        state.setdefault('call_frames', {})
        initial_finalization = self._initial_finalization_state()
        if initial_finalization is not None:
            state.setdefault('finalization', initial_finalization)
        state['_resolved_consumes'] = {}
        managed_input_error = self._ensure_entry_managed_write_root_bindings(state, resume=resume)
        if managed_input_error is not None:
            state['status'] = 'failed'
            state['error'] = managed_input_error.get('error')
            self._persist_bound_inputs(state)
            self.state_manager.update_run_error(state['error'] if isinstance(state.get('error'), dict) else None)
            self.state_manager.update_status('failed')
            return self.state_manager.load().to_dict()
        runtime_context_error = self._ensure_entry_runtime_context_bindings(state, resume=resume)
        if runtime_context_error is not None:
            state['status'] = 'failed'
            state['error'] = runtime_context_error.get('error')
            self._persist_bound_inputs(state)
            self.state_manager.update_run_error(state['error'] if isinstance(state.get('error'), dict) else None)
            self.state_manager.update_status('failed')
            return self.state_manager.load().to_dict()
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
            active_step_context: Dict[str, Any] = {}
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
                active_step_context = {
                    "step_name": step_name,
                    "step_id": step_id,
                    "step_index": step_index,
                    "node_id": current_node_id,
                }
                step = self._typed_execution_step(step)
                self._emit_compiled_frontend_step_display(step_name, step_id, node_id=current_node_id)
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

                # AT-69: Create backup before step execution if debug enabled
                if self.debug:
                    self.state_manager.backup_state(step_name)

                consume_error = self._enforce_consumes_contract(step, step_name, state)
                visit_count = self._increment_step_visit(state, step_name)
                if isinstance(visit_count, int):
                    active_step_context["visit_count"] = visit_count
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
                    self._finalize_consumes(
                        step,
                        step_name,
                        state,
                        succeeded=False,
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
                    self._finalize_consumes(
                        step,
                        step_name,
                        state,
                        succeeded=False,
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
        except Exception as exc:
            terminal_status = 'failed'
            self.state_manager.fail_run(
                self._executor_exception_error(exc, **active_step_context)
            )
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
        if execution_kind is ExecutableNodeKind.PURE_PROJECTION:
            return 'pure_projection'
        if execution_kind is ExecutableNodeKind.INCREMENT_SCALAR:
            return 'increment_scalar'
        if execution_kind is ExecutableNodeKind.MATERIALIZE_ARTIFACTS:
            return 'materialize_artifacts'
        if execution_kind is ExecutableNodeKind.SELECT_VARIANT_OUTPUT:
            return 'select_variant_output'
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
            except Exception:
                raise
            else:
                self.state_manager.clear_current_step(
                    step_name,
                    preserve_managed_recovery=True,
                )
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
        except Exception:
            raise
        else:
            self.state_manager.clear_current_step(
                step_name,
                preserve_managed_recovery=True,
            )
        finally:
            if interval_sec > 0:
                stop_event.set()
                heartbeat_thread.join(timeout=1.0)

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
        profile = str(summaries_cfg.get('profile', 'basic'))
        root_manager = self.state_manager
        while hasattr(root_manager, "parent_manager"):
            root_manager = getattr(root_manager, "parent_manager")
        aggregate_run_root = Path(getattr(root_manager, "run_root", self.state_manager.run_root))
        return SummaryObserver(
            run_root=self.state_manager.run_root,
            provider_executor=self.provider_executor,
            provider_name=provider_name,
            mode=mode,
            timeout_sec=timeout_sec,
            best_effort=best_effort,
            max_input_chars=max_input_chars,
            profile=profile,
            invocation_context={"context": dict(self.workflow_context_defaults)},
            aggregate_run_root=aggregate_run_root,
        )

    def _create_live_agent_note_observer(self) -> Optional[LiveAgentNoteObserver]:
        """Create optional live-note observer from summary observability config."""
        if not isinstance(self.observability, dict):
            return None
        summaries_cfg = self.observability.get('step_summaries')
        if not isinstance(summaries_cfg, dict) or not summaries_cfg.get('enabled', False):
            return None
        live_cfg = summaries_cfg.get('live_agent_notes')
        if not isinstance(live_cfg, dict) or not live_cfg.get('enabled', False):
            return None
        provider_name = str(live_cfg.get('provider') or summaries_cfg.get('provider') or 'claude_sonnet_summary')
        try:
            interval_sec = float(live_cfg.get('interval_sec', 15.0))
        except (TypeError, ValueError):
            interval_sec = 15.0
        try:
            timeout_sec = int(live_cfg.get('timeout_sec', 30))
        except (TypeError, ValueError):
            timeout_sec = 30
        try:
            max_tail_chars = int(live_cfg.get('max_tail_chars', 6000))
        except (TypeError, ValueError):
            max_tail_chars = 6000
        root_manager = self.state_manager
        while hasattr(root_manager, "parent_manager"):
            root_manager = getattr(root_manager, "parent_manager")
        aggregate_run_root = Path(getattr(root_manager, "run_root", self.state_manager.run_root))
        return LiveAgentNoteObserver(
            aggregate_run_root=aggregate_run_root,
            provider_executor=self.provider_executor,
            provider_name=provider_name,
            interval_sec=interval_sec,
            timeout_sec=timeout_sec,
            max_tail_chars=max_tail_chars,
            invocation_context={"context": dict(self.workflow_context_defaults)},
        )

    @contextmanager
    def _live_agent_note_watch(
        self,
        step_name: str,
        step: Dict[str, Any],
        session_runtime: Optional[Dict[str, Any]],
    ):
        """Best-effort live-note watch for one active provider session."""
        if self.live_agent_note_observer is None:
            yield
            return
        transport_spool_path = None
        step_id = None
        visit_count = None
        if isinstance(session_runtime, dict):
            transport_spool_path = session_runtime.get("transport_spool_path")
            step_id = session_runtime.get("step_id")
            visit_count = session_runtime.get("visit_count")
        current_step = self.state_manager.state.current_step if self.state_manager.state is not None else None
        if (not isinstance(step_id, str) or not isinstance(visit_count, int)) and isinstance(current_step, dict):
            if current_step.get("name") == step_name:
                current_step_id = current_step.get("step_id")
                current_visit_count = current_step.get("visit_count")
                if isinstance(current_step_id, str):
                    step_id = current_step_id
                if isinstance(current_visit_count, int):
                    visit_count = current_visit_count
        if not isinstance(step_id, str):
            step_id = self._step_id(step)
        if not isinstance(visit_count, int):
            visit_count = 1
        if not isinstance(step_id, str) or not isinstance(visit_count, int):
            yield
            return
        with self.live_agent_note_observer.watch(
            step_name=step_name,
            step_id=step_id,
            visit_count=visit_count,
            transport_spool_path=Path(transport_spool_path) if isinstance(transport_spool_path, str) else None,
        ):
            yield

    def _emit_step_summary(self, step_name: str, step: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Emit observability summary for a completed step."""
        if self.summary_observer is None:
            return
        summary_kind = self._summary_kind_for_step(step)
        if summary_kind is None:
            return
        snapshot = self._build_step_summary_snapshot(step_name, step, result, summary_kind=summary_kind)
        try:
            self.summary_observer.emit(step_name, snapshot, summary_kind=summary_kind)
        except Exception as exc:
            logger.warning("Summary emission failed for %s: %s", step_name, exc)

    def _summary_profile(self) -> str:
        if not isinstance(self.observability, dict):
            return "basic"
        summaries_cfg = self.observability.get('step_summaries')
        if not isinstance(summaries_cfg, dict):
            return "basic"
        profile = str(summaries_cfg.get('profile', 'basic'))
        return profile if profile in {'basic', 'phase-performance'} else 'basic'

    def _summary_kind_for_step(self, step: Dict[str, Any]) -> Optional[str]:
        profile = self._summary_profile()
        if profile == 'basic':
            return 'step'
        if 'provider' in step or 'adjudicated_provider' in step:
            return 'provider'
        if 'call' in step or 'repeat_until' in step:
            return 'phase'
        return None

    def _build_step_summary_snapshot(
        self,
        step_name: str,
        step: Dict[str, Any],
        result: Dict[str, Any],
        *,
        summary_kind: str = "step",
    ) -> Dict[str, Any]:
        """Build a compact, deterministic snapshot for summary generation."""
        input_payload: Dict[str, Any] = {}
        if 'command' in step:
            input_payload['command'] = step.get('command')
        if 'provider' in step or 'adjudicated_provider' in step:
            input_payload['provider'] = step.get('provider') or step.get('adjudicated_provider')
            input_payload['timeout_sec'] = step.get('timeout_sec')
            input_payload['has_variant_output'] = 'variant_output' in step
            input_payload['has_output_bundle'] = 'output_bundle' in step
            input_payload['has_expected_outputs'] = 'expected_outputs' in step
            input_payload['prompt_sources'] = {
                'input_file': step.get('input_file'),
                'asset_file': step.get('asset_file'),
                'prompt_consumes': step.get('prompt_consumes'),
            }
            prompt_file = self.state_manager.logs_dir / f"{step_name}.prompt.txt"
            if prompt_file.exists():
                try:
                    input_payload['prompt'] = prompt_file.read_text(encoding='utf-8')
                except OSError:
                    pass
        if summary_kind == 'phase':
            input_payload['phase_boundary'] = {
                'call': step.get('call'),
                'repeat_until': 'repeat_until' in step,
                'step_id': step.get('id'),
            }

        output_payload: Dict[str, Any] = {}
        if isinstance(result, dict):
            output_payload = {
                'status': result.get('status'),
                'exit_code': result.get('exit_code'),
                'duration_ms': result.get('duration_ms'),
                'outcome': result.get('outcome'),
                'output': result.get('output') or result.get('text'),
                'lines': result.get('lines'),
                'json': result.get('json'),
                'error': result.get('error'),
                'artifacts': result.get('artifacts'),
                'debug': result.get('debug'),
                'step_id': result.get('step_id'),
                'visit_count': result.get('visit_count'),
            }

        return {
            'run_id': self.state_manager.run_id,
            'workflow': self.workflow_name,
            'summary': {
                'schema': 'orchestrator_step_summary_snapshot/v2',
                'kind': summary_kind,
                'profile': self._summary_profile(),
                'advisory_only': True,
            },
            'step': {
                'name': step_name,
                'type': 'provider'
                if ('provider' in step or 'adjudicated_provider' in step)
                else 'command'
                if 'command' in step
                else 'other',
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
        private_artifact_versions = state.get('private_artifact_versions', {})
        private_artifact_consumes = state.get('private_artifact_consumes', {})

        if not isinstance(artifact_versions, dict):
            artifact_versions = {}
            state['artifact_versions'] = artifact_versions
        if not isinstance(artifact_consumes, dict):
            artifact_consumes = {}
            state['artifact_consumes'] = artifact_consumes
        if not isinstance(private_artifact_versions, dict):
            private_artifact_versions = {}
            state['private_artifact_versions'] = private_artifact_versions
        if not isinstance(private_artifact_consumes, dict):
            private_artifact_consumes = {}
            state['private_artifact_consumes'] = private_artifact_consumes

        self.state_manager.update_dataflow_state(
            artifact_versions,
            artifact_consumes,
            private_artifact_versions=private_artifact_versions,
            private_artifact_consumes=private_artifact_consumes,
        )

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

    def _finalize_consumes(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        *,
        succeeded: bool,
        runtime_step_id: Optional[str] = None,
    ) -> None:
        """Commit or discard pending consumes once a step has settled."""
        self.dataflow_manager.finalize_consumes(
            step,
            step_name,
            state,
            runtime_step_id=runtime_step_id,
            succeeded=succeeded,
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

    def _resolve_run_root_path(self, relative_path: str) -> Optional[Path]:
        """Resolve a run-root-relative path and reject escapes outside the run root."""
        path = Path(relative_path)
        if path.is_absolute() or ".." in path.parts:
            return None

        candidate = (self.state_manager.run_root / path).resolve()
        run_root = self.state_manager.run_root.resolve()
        try:
            candidate.relative_to(run_root)
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

    def _prepare_runtime_output_bundle_parent(
        self,
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Resolve and prepare the parent for one explicit structured-output bundle."""
        bundle_path_value = (
            resolved_output_bundle.get('path')
            if isinstance(resolved_output_bundle, dict)
            else None
        )
        if not isinstance(bundle_path_value, str):
            return None

        bundle_path = self._resolve_workspace_path(bundle_path_value)
        if bundle_path is None:
            return self._contract_violation_result(
                "Structured output bundle path escapes the workspace",
                {"path": bundle_path_value},
            )

        try:
            bundle_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return self._contract_violation_result(
                "Failed to prepare structured output bundle parent",
                {
                    "path": bundle_path_value,
                    "error": str(exc),
                },
            )

        return None

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
            managed_jobs = step_result.get('managed_jobs')
            managed_job_outcome = (
                managed_jobs.get('managed_job_outcome')
                if isinstance(managed_jobs, dict)
                else None
            )
            goto_transfer = self._typed_on_goto_transfer(
                current_node_id,
                exit_code=exit_code,
                managed_job_outcome=managed_job_outcome,
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

        requires_variant = step.get("requires_variant")
        if isinstance(requires_variant, dict):
            guard_error = self._resolve_selected_variant_guard(requires_variant, state)
            if guard_error is not None:
                return self._persist_step_result(
                    state,
                    step_name,
                    step,
                    guard_error,
                    phase_hint="pre_execution",
                    class_hint="pre_execution_failed",
                    retryable_hint=False,
                )

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

        if execution_kind is ExecutableNodeKind.PURE_PROJECTION:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_pure_projection(step, state),
            )

        if execution_kind is ExecutableNodeKind.INCREMENT_SCALAR:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_increment_scalar(step, state),
            )

        if execution_kind is ExecutableNodeKind.MATERIALIZE_ARTIFACTS:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_materialize_artifacts(step, state),
            )

        if execution_kind is ExecutableNodeKind.SELECT_VARIANT_OUTPUT:
            return self._execute_top_level_publish_and_persist(
                step,
                step_name,
                state,
                self._execute_select_variant_output(step, state),
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

        requires_variant = step.get("requires_variant")
        if isinstance(requires_variant, dict):
            guard_error = self._resolve_selected_variant_guard(requires_variant, state)
            if guard_error is not None:
                result = guard_error
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
                result = self._attach_outcome(
                    step,
                    result,
                    phase_hint="pre_execution",
                    class_hint="pre_execution_failed",
                    retryable_hint=False,
                )
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

        if execution_kind is ExecutableNodeKind.COMMAND:
            result = self._execute_command_with_context(
                step,
                context,
                state,
                parent_steps=scope.get("parent_steps"),
                self_steps=scope.get("self_steps"),
                root_steps=scope.get("root_steps"),
            )
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
        elif execution_kind is ExecutableNodeKind.PURE_PROJECTION:
            result = self._execute_pure_projection(step, state, scope=scope)
        elif execution_kind is ExecutableNodeKind.INCREMENT_SCALAR:
            result = self._execute_increment_scalar(step, state)
        elif execution_kind is ExecutableNodeKind.MATERIALIZE_ARTIFACTS:
            result = self._execute_materialize_artifacts(step, state, scope=scope)
        elif execution_kind is ExecutableNodeKind.SELECT_VARIANT_OUTPUT:
            result = self._execute_select_variant_output(step, state)
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
        self._finalize_consumes(
            step,
            nested_name,
            state,
            succeeded=result.get("status") == "completed",
            runtime_step_id=runtime_step_id,
        )
        self._emit_step_summary(nested_name, step, result)
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
            finalized = self._persist_step_result(state, step_name, step, result)
            self._finalize_consumes(
                step,
                step_name,
                state,
                succeeded=finalized.get("status") == "completed",
            )
            self._mark_managed_jobs_recovery_if_outstanding(
                step,
                step_name,
                state,
                finalized,
            )
            return finalized

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
        self._finalize_consumes(
            step,
            step_name,
            state,
            succeeded=finalized.get("status") == "completed",
        )

        artifact_versions = state.get("artifact_versions", {})
        artifact_consumes = state.get("artifact_consumes", {})
        private_artifact_versions = state.get("private_artifact_versions", {})
        private_artifact_consumes = state.get("private_artifact_consumes", {})
        self.state_manager.finalize_step_with_dataflow(
            step_name,
            self._to_step_result(finalized, step_name),
            artifact_versions=artifact_versions if isinstance(artifact_versions, dict) else {},
            artifact_consumes=artifact_consumes if isinstance(artifact_consumes, dict) else {},
            private_artifact_versions=(
                private_artifact_versions if isinstance(private_artifact_versions, dict) else {}
            ),
            private_artifact_consumes=(
                private_artifact_consumes if isinstance(private_artifact_consumes, dict) else {}
            ),
            expected_step_id=finalized.get("step_id"),
            expected_visit_count=visit_count if isinstance(visit_count, int) else None,
        )
        self._mark_managed_jobs_recovery_if_outstanding(
            step,
            step_name,
            state,
            finalized,
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

    def _mark_managed_jobs_recovery_if_outstanding(
        self,
        step: Dict[str, Any],
        step_name: str,
        state: Dict[str, Any],
        finalized: Dict[str, Any],
    ) -> None:
        """Persist the recovery phase for managed jobs that outlive the provider."""
        managed_jobs = finalized.get("managed_jobs")
        if not (
            isinstance(managed_jobs, dict)
            and managed_jobs.get("managed_job_outcome") == "OUTSTANDING"
        ):
            return

        step_visits = state.get("step_visits", {})
        visit_count = step_visits.get(step_name) if isinstance(step_visits, dict) else None
        recovery_state = {
            "phase": "recovery",
            "audit_path": managed_jobs.get("audit_path"),
            "outcome": "OUTSTANDING",
            "poll_budget_sec": step.get("managed_jobs", {}).get("poll_budget_sec")
            if isinstance(step.get("managed_jobs"), dict)
            else None,
        }
        self.state_manager.mark_current_step_recovery(
            step_name=step_name,
            step_index=self.current_step,
            step_type=self._resolve_step_type(step),
            step_id=finalized.get("step_id"),
            visit_count=visit_count if isinstance(visit_count, int) else None,
            managed_jobs=recovery_state,
        )
        state["current_step"] = {
            "name": step_name,
            "index": self.current_step,
            "type": self._resolve_step_type(step),
            "status": "running",
            "managed_jobs": recovery_state,
        }
        if finalized.get("step_id") is not None:
            state["current_step"]["step_id"] = finalized.get("step_id")
        if isinstance(visit_count, int):
            state["current_step"]["visit_count"] = visit_count

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
        state: Dict[str, Any],
        *,
        parent_steps: Optional[Dict[str, Any]] = None,
        self_steps: Optional[Dict[str, Any]] = None,
        root_steps: Optional[Dict[str, Any]] = None,
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
        runtime_context = RuntimeContext.from_mapping(
            context,
            default_context=self.workflow_context_defaults,
            parent_steps=parent_steps,
            root_steps=root_steps or state.get("steps", {}),
        )
        if isinstance(self_steps, dict):
            runtime_context = RuntimeContext(
                values=runtime_context.values,
                workflow_context=runtime_context.workflow_context,
                self_steps=self_steps,
                explicit_steps=True,
                parent_steps=runtime_context.parent_steps,
                root_steps=runtime_context.root_steps,
            )
        variables = runtime_context.build_variables(self.variable_substitutor, state)
        snapshots, snapshot_error = self._capture_pre_snapshot(step, state)
        if snapshot_error is not None:
            return snapshot_error

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

            # For structured command contracts, expose the resolved bundle path
            # to the command adapter via a reserved env var and ensure the
            # runtime-owned bundle parent exists before launch.
            command_env = step.get('env')
            _, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
                step,
                state,
                context=context,
            )
            if path_error is not None:
                return path_error
            bundle_path_error = self._prepare_runtime_output_bundle_parent(resolved_output_bundle)
            if bundle_path_error is not None:
                return bundle_path_error
            command_env = self._env_with_runtime_output_bundle_path(
                command_env,
                resolved_output_bundle,
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
                env=command_env,
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

        final_result = self._apply_expected_outputs_contract(step, result.to_state_dict(), state, context=context)
        if snapshots:
            final_result['snapshots'] = snapshots
        return final_result

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
        managed_jobs_config = _managed_jobs_config_from_step(step)
        current_step_state = state.get('current_step')
        current_managed_state = (
            current_step_state.get('managed_jobs')
            if isinstance(current_step_state, dict) and current_step_state.get('name') == step_name
            else None
        )
        if managed_jobs_config is not None and isinstance(current_managed_state, dict) and current_managed_state.get('phase') == 'recovery':
            audit_path = current_managed_state.get('audit_path')
            recovery_summary = recover_managed_jobs(Path(audit_path)) if isinstance(audit_path, str) else {
                "managed_job_outcome": "INVALID",
                "recovery_status": "INVALID",
                "audit_path": audit_path,
                "jobs": [{"status": "INVALID", "error": "missing managed audit path"}],
            }
            result = {
                'status': 'completed' if recovery_summary.get('managed_job_outcome') == 'COMPLETE' else 'failed',
                'exit_code': 0 if recovery_summary.get('managed_job_outcome') == 'COMPLETE' else 1,
                'duration_ms': 0,
                'managed_jobs': recovery_summary,
            }
            if result['exit_code'] != 0:
                result['error'] = {
                    "type": "managed_jobs_recovery",
                    "message": f"Managed jobs recovery outcome: {recovery_summary.get('managed_job_outcome')}",
                    "context": recovery_summary,
                }
            return result
        snapshots, snapshot_error = self._capture_pre_snapshot(step, state)
        if snapshot_error is not None:
            return snapshot_error
        runtime_context = self._runtime_context(context, state)
        variables = runtime_context.build_variables(self.variable_substitutor, state)
        resolved_expected_outputs, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
            step,
            state,
            context=context,
        )
        if path_error is not None:
            return path_error
        bundle_path_error = self._prepare_runtime_output_bundle_parent(resolved_output_bundle)
        if bundle_path_error is not None:
            return bundle_path_error
        prompt_contract_step = step
        if resolved_expected_outputs is not None:
            prompt_contract_step = dict(step)
            prompt_contract_step['expected_outputs'] = resolved_expected_outputs
        elif resolved_output_bundle is not None:
            prompt_contract_step = dict(step)
            if 'variant_output' in step:
                prompt_contract_step['variant_output'] = resolved_output_bundle
            else:
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
        if managed_jobs_config is not None:
            retry_policy = RetryPolicy.for_command(0)
        elif session_request is not None:
            retry_policy = RetryPolicy.for_command(0)
        elif 'retries' in step:
            retry_policy = RetryPolicy.for_command(step['retries'])
        else:
            retry_policy = RetryPolicy.for_provider(
                max_retries=self.max_retries,
                delay_ms=self.retry_delay_ms
            )

        # Build context for provider parameter substitution (AT-44)
        # This should include all variable namespaces
        provider_context = self._create_provider_context(context, state)
        resolved_provider_name, provider_name_error = self._resolve_provider_name_for_step(
            step,
            provider_context,
        )
        if provider_name_error is not None:
            return {
                'status': 'failed',
                'exit_code': 2,
                'error': provider_name_error,
            }

        # Execute with retries
        attempt = 0
        result: Optional[Dict[str, Any]] = None

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
                provider_name=resolved_provider_name,
                params=params,
                context=provider_context,
                prompt_content=prompt,
                session_request=session_request,
                env=self._provider_env_with_runtime_output_bundle_path(step, resolved_output_bundle),
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

            if managed_jobs_config is not None:
                visit_count = 1
                step_visits = state.get('step_visits')
                if isinstance(step_visits, dict) and isinstance(step_visits.get(step_name), int):
                    visit_count = step_visits[step_name]
                invocation = ManagedProviderRuntime(
                    run_root=self.state_manager.run_root,
                    workspace=self.workspace,
                ).wrap_invocation(
                    invocation,
                    step_name=step_name,
                    visit_count=visit_count,
                    config=managed_jobs_config,
                )

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
            with self._live_agent_note_watch(step_name, step, session_runtime):
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
        if managed_jobs_config is not None:
            managed_metadata = getattr(invocation, "metadata", {}).get("managed_jobs", {})
            audit_path = managed_metadata.get("audit_path") if isinstance(managed_metadata, dict) else None
            recovery_summary = recover_managed_jobs(Path(audit_path)) if isinstance(audit_path, str) else {
                "managed_job_outcome": "INVALID",
                "recovery_status": "INVALID",
                "audit_path": audit_path,
                "jobs": [{"status": "INVALID", "error": "missing managed audit path"}],
            }
            result["managed_jobs"] = recovery_summary
            outcome = recovery_summary.get("managed_job_outcome")
            if outcome == "COMPLETE":
                result["status"] = "completed"
                result["exit_code"] = 0
            else:
                result["status"] = "failed"
                result["exit_code"] = 1
                result.setdefault("error", {
                    "type": "managed_jobs_recovery",
                    "message": f"Managed jobs recovery outcome: {outcome}",
                    "context": recovery_summary,
                })

        if debug_info:
            result['debug'] = debug_info

        final_result = self._apply_expected_outputs_contract(step, result, state, context=context)
        if snapshots:
            final_result['snapshots'] = snapshots
        return final_result

    def _resolve_provider_name_for_step(
        self,
        step: Dict[str, Any],
        provider_context: Dict[str, Any],
    ) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Resolve one provider step's provider alias before template lookup."""
        raw_provider = step.get("provider")
        step_name = step.get("name", f"step_{self.current_step}")
        if not isinstance(raw_provider, str) or not raw_provider.strip():
            return None, {
                "type": "validation_error",
                "message": "Provider step requires a non-empty provider name",
                "context": {"step": step_name, "provider": raw_provider},
            }

        try:
            resolved = self.variable_substitutor.substitute(raw_provider, provider_context)
        except ValueError as exc:
            return None, {
                "type": "substitution_error",
                "message": "Failed to substitute provider name",
                "context": {
                    "step": step_name,
                    "provider": raw_provider,
                    "error": str(exc),
                },
            }

        if not isinstance(resolved, str) or not resolved.strip():
            return None, {
                "type": "validation_error",
                "message": "Provider name resolved to an empty value",
                "context": {
                    "step": step_name,
                    "provider": raw_provider,
                    "resolved_provider": resolved,
                },
            }

        return resolved.strip(), None

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

    def _adjudication_timeout_value(self, raw_timeout: Any) -> float | None:
        if isinstance(raw_timeout, (int, float)):
            return float(raw_timeout)
        return None

    def _adjudication_retry_policy(self, step: Mapping[str, Any]) -> RetryPolicy:
        if "retries" in step:
            return RetryPolicy.for_command(step.get("retries"))
        return RetryPolicy.for_provider(max_retries=self.max_retries, delay_ms=self.retry_delay_ms)

    def _wait_for_adjudication_retry(
        self,
        retry_policy: RetryPolicy,
        deadline: AdjudicationDeadline,
    ) -> None:
        delay_sec = max(0.0, float(retry_policy.delay_ms or 0) / 1000.0)
        if delay_sec <= 0:
            deadline.require_time_remaining("retry")
            return
        remaining = deadline.remaining_timeout_sec()
        if remaining is not None and remaining <= delay_sec:
            raise TimeoutError("adjudicated provider deadline expired before retry delay")
        time.sleep(delay_sec)
        deadline.require_time_remaining("retry")

    def _execute_adjudicated_provider_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a DSL 2.11 adjudicated provider step sequentially."""
        started = time.monotonic()
        deadline = AdjudicationDeadline(
            started_monotonic=started,
            timeout_sec=self._adjudication_timeout_value(step.get("timeout_sec")),
        )
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
            if 'variant_output' in step:
                output_contract_step['variant_output'] = resolved_output_bundle
            else:
                output_contract_step['output_bundle'] = resolved_output_bundle

        frame_context = self._adjudication_frame_context()
        run_root = frame_context["run_root"]
        frame_scope = frame_context["frame_scope"]
        execution_frame_id = frame_context["execution_frame_id"]
        call_frame_id = frame_context["call_frame_id"]
        step_visits = state.get("step_visits", {})
        visit_count = step_visits.get(step_name, 1) if isinstance(step_visits, dict) else 1
        visit_paths = adjudication_visit_paths(run_root, frame_scope, step_id, int(visit_count or 1))

        adjudicated = dict(adjudicated)
        ledger_path_error = self._resolve_adjudication_score_ledger_path(
            adjudicated,
            state,
            context,
            step_name=step_name,
            visit_paths=visit_paths,
        )
        if ledger_path_error is not None:
            return ledger_path_error

        candidates_config = adjudicated.get("candidates", [])
        evaluator_config = adjudicated.get("evaluator", {})
        selection_config = adjudicated.get("selection", {})
        candidate_roots = [
            candidate_paths(run_root, frame_scope, step_id, int(visit_count or 1), str(candidate_config.get("id"))).candidate_root
            for candidate_config in candidates_config
            if isinstance(candidate_config, dict)
        ] if isinstance(candidates_config, list) else []
        sidecars_exist = adjudication_sidecars_exist(visit_paths=visit_paths, candidate_roots=candidate_roots)
        if (
            not sidecars_exist
            and getattr(self, "resume_mode", False)
            and isinstance(visit_count, int)
            and visit_count > 1
        ):
            previous_visit_count = visit_count - 1
            previous_visit_paths = adjudication_visit_paths(run_root, frame_scope, step_id, previous_visit_count)
            previous_candidate_roots = [
                candidate_paths(run_root, frame_scope, step_id, previous_visit_count, str(candidate_config.get("id"))).candidate_root
                for candidate_config in candidates_config
                if isinstance(candidate_config, dict)
            ] if isinstance(candidates_config, list) else []
            if adjudication_sidecars_exist(
                visit_paths=previous_visit_paths,
                candidate_roots=previous_candidate_roots,
            ):
                visit_count = previous_visit_count
                if isinstance(step_visits, dict):
                    step_visits[step_name] = previous_visit_count
                    self._persist_control_flow_state(state)
                visit_paths = previous_visit_paths
                candidate_roots = previous_candidate_roots
                sidecars_exist = True

        baseline_manifest = None
        candidates: list[dict[str, Any]] = []
        scorer: dict[str, Any] | None = None
        evaluator_prompt = ""
        scorer_failure: dict[str, Any] | None = None
        resume_loaded = False
        resume_baseline_only = False
        if sidecars_exist:
            if not getattr(self, "resume_mode", False):
                return self._adjudication_failure_result(
                    "adjudication_resume_mismatch",
                    "existing adjudication sidecars require resume reconciliation before rerun",
                    visit_paths=visit_paths,
                )
            resume_state = self._load_adjudication_resume_state(
                candidates_config=candidates_config if isinstance(candidates_config, list) else [],
                evaluator_config=evaluator_config if isinstance(evaluator_config, dict) else {},
                context=context,
                state=state,
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                visit_paths=visit_paths,
            )
            if isinstance(resume_state.get("error"), dict):
                return resume_state["error"]
            baseline_manifest = resume_state["baseline_manifest"]
            candidates = resume_state["candidates"]
            scorer = resume_state.get("scorer")
            evaluator_prompt = str(resume_state.get("evaluator_prompt") or "")
            scorer_failure = resume_state.get("scorer_failure")
            resume_baseline_only = bool(resume_state.get("baseline_only"))
            resume_loaded = not resume_baseline_only

        if sidecars_exist and not resume_loaded and not resume_baseline_only:
            return self._adjudication_failure_result(
                "adjudication_resume_mismatch",
                "existing adjudication sidecars require resume reconciliation before rerun",
                visit_paths=visit_paths,
            )

        required_surfaces = self._adjudication_required_path_surfaces(output_contract_step)
        optional_surfaces = self._adjudication_optional_path_surfaces(output_contract_step)
        if baseline_manifest is None:
            try:
                deadline.require_time_remaining("baseline snapshot")
                baseline_manifest = create_baseline_snapshot(
                    parent_workspace=self.workspace,
                    run_root=run_root,
                    visit_paths=visit_paths,
                    workflow_checksum=state.get("workflow_checksum", ""),
                    resolved_consumes=state.get("_resolved_consumes", {}),
                    required_path_surfaces=required_surfaces,
                    optional_path_surfaces=optional_surfaces,
                )
            except TimeoutError as exc:
                return self._adjudication_failure_result("timeout", str(exc), visit_paths=visit_paths)
            except Exception as exc:
                return self._adjudication_failure_result(
                    getattr(exc, "failure_type", "adjudication_resume_mismatch"),
                    str(exc),
                )

        require_single_score = bool(
            isinstance(selection_config, dict)
            and selection_config.get("require_score_for_single_candidate") is True
        )
        retry_policy = self._adjudication_retry_policy(step)

        if resume_loaded:
            candidate_configs_to_run = resume_state.get("pending_candidate_configs", [])
        else:
            candidate_configs_to_run = list(enumerate(candidates_config if isinstance(candidates_config, list) else []))
        for index, candidate_config in candidate_configs_to_run:
            if not isinstance(candidate_config, dict):
                continue
            candidate_id = str(candidate_config.get("id"))
            candidate_provider = str(candidate_config.get("provider"))
            paths = candidate_paths(run_root, frame_scope, step_id, int(visit_count or 1), candidate_id)
            candidate_step = self._candidate_step_from_adjudicated_step(step, candidate_config)
            candidate_params, _candidate_param_errors = self._resolve_provider_params_for_adjudication(
                candidate_provider,
                candidate_config.get("provider_params", {}),
                context,
                state,
            )
            prompt_source_kind, prompt_source = self._prompt_source_metadata(candidate_step)
            candidate_record = {
                "candidate_id": candidate_id,
                "candidate_index": index,
                "candidate_provider": candidate_provider,
                "candidate_model": self._provider_model(candidate_params),
                "candidate_params_hash": self._stable_runtime_hash(candidate_params),
                "candidate_config_hash": self._stable_runtime_hash(candidate_config),
                "prompt_variant_id": candidate_config.get("prompt_variant_id"),
                "prompt_source_kind": prompt_source_kind,
                "prompt_source": prompt_source,
                "candidate_root": paths.candidate_root.relative_to(self.workspace).as_posix()
                if self._path_under(paths.candidate_root, self.workspace)
                else paths.candidate_root.as_posix(),
                "candidate_workspace": paths.workspace.relative_to(self.workspace).as_posix()
                if self._path_under(paths.workspace, self.workspace)
                else paths.workspace.as_posix(),
                "attempt_count": 0,
                "provider_attempts": [],
                "output_paths": {},
            }
            attempt = 0
            try:
                while True:
                    deadline.require_time_remaining(f"candidate {candidate_id} provider attempt")
                    prepare_candidate_workspace_from_baseline(
                        baseline_workspace=visit_paths.baseline_workspace,
                        candidate_workspace=paths.workspace,
                    )
                    deadline.require_time_remaining(f"candidate {candidate_id} workspace copy")
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
                        break
                    paths.prompt_path.parent.mkdir(parents=True, exist_ok=True)
                    paths.prompt_path.write_text(prompt or "", encoding="utf-8")
                    candidate_record["composed_prompt_hash"] = self._text_hash(prompt or "")
                    if not candidate_record.get("prompt_variant_id"):
                        candidate_record["prompt_variant_id"] = self._stable_runtime_hash(
                            {
                                "prompt_source_kind": prompt_source_kind,
                                "prompt_source": prompt_source,
                                "composed_prompt_hash": candidate_record["composed_prompt_hash"],
                            }
                        )

                    invocation, error = self.provider_executor.prepare_invocation(
                        provider_name=candidate_provider,
                        params=ProviderParams(
                            params=candidate_config.get("provider_params", {}),
                            input_file=candidate_step.get("input_file"),
                            output_file=None,
                        ),
                        context=self._create_provider_context(context, state),
                        prompt_content=prompt,
                        env=self._provider_env_with_runtime_output_bundle_path(candidate_step, resolved_output_bundle),
                        secrets=candidate_step.get("secrets"),
                        timeout_sec=deadline.remaining_timeout_sec(),
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
                        break
                    exec_result = self._execute_provider_invocation(invocation, cwd=paths.workspace)
                    paths.stdout_log.write_bytes(exec_result.stdout)
                    paths.stderr_log.write_bytes(exec_result.stderr)
                    candidate_record["provider_exit_code"] = exec_result.exit_code
                    candidate_record["attempt_count"] = attempt + 1
                    candidate_record["provider_attempts"].append(
                        {
                            "attempt": attempt + 1,
                            "exit_code": exec_result.exit_code,
                            "duration_ms": exec_result.duration_ms,
                        }
                    )
                    if exec_result.exit_code != 0:
                        if retry_policy.should_retry(exec_result.exit_code, attempt):
                            self._wait_for_adjudication_retry(retry_policy, deadline)
                            attempt += 1
                            continue
                        candidate_record.update(
                            {
                                "candidate_status": "timeout" if exec_result.exit_code == 124 else "provider_failed",
                                "score_status": "not_evaluated",
                                "failure_type": "timeout" if exec_result.exit_code == 124 else "provider_failed",
                                "failure_message": "candidate provider failed",
                            }
                        )
                        if exec_result.exit_code == 124 and self._adjudication_deadline_expired(deadline):
                            candidates.append(candidate_record)
                            self._persist_adjudication_candidates(
                                run_root=run_root,
                                frame_scope=frame_scope,
                                step_id=step_id,
                                visit_count=int(visit_count or 1),
                                candidates=candidates,
                            )
                            return self._adjudication_failure_result(
                                "timeout",
                                "adjudicated provider deadline expired during candidate provider execution",
                                candidates=candidates,
                                visit_paths=visit_paths,
                            )
                        break
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
                        break
                    candidate_record.update(
                        {
                            "candidate_status": "output_valid",
                            "score_status": "not_evaluated",
                            "artifacts": artifacts,
                            "output_paths": self._output_paths_from_contract(output_contract_step),
                        }
                    )
                    break
            except TimeoutError as exc:
                candidate_record.update(
                    {
                        "candidate_status": "timeout",
                        "score_status": "not_evaluated",
                        "provider_exit_code": 124,
                        "failure_type": "timeout",
                        "failure_message": str(exc),
                    }
                )
                candidates.append(candidate_record)
                self._persist_adjudication_candidates(
                    run_root=run_root,
                    frame_scope=frame_scope,
                    step_id=step_id,
                    visit_count=int(visit_count or 1),
                    candidates=candidates,
                )
                return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
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
            self._persist_adjudication_candidates(
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                candidates=[candidate_record],
            )

        output_valid = [candidate for candidate in candidates if candidate.get("candidate_status") == "output_valid"]
        score_pending = [
            candidate
            for candidate in output_valid
            if candidate.get("score_status") not in {"scored", "evaluation_failed", "scorer_unavailable"}
        ]
        if score_pending and scorer is None and scorer_failure is None:
            scorer, evaluator_prompt, scorer_failure = self._resolve_adjudication_scorer(
                evaluator_config if isinstance(evaluator_config, dict) else {},
                context,
                state,
                visit_paths=visit_paths,
            )
        if scorer_failure is not None:
            for candidate in score_pending:
                candidate.update(
                    {
                        "score_status": "scorer_unavailable",
                        "scorer_resolution_failure_key": scorer_failure["scorer_resolution_failure_key"],
                        "failure_type": scorer_failure["failure_type"],
                        "failure_message": scorer_failure["failure_message"],
                    }
                )
        elif scorer is not None:
            for candidate in score_pending:
                try:
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
                        deadline=deadline,
                        retry_policy=retry_policy,
                    )
                except TimeoutError as exc:
                    return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        if score_pending:
            self._persist_adjudication_candidates(
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                candidates=candidates,
            )

        try:
            deadline.require_time_remaining("selection")
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
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
                preserve_primary_failure=True,
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
        self._persist_adjudication_candidates(
            run_root=run_root,
            frame_scope=frame_scope,
            step_id=step_id,
            visit_count=int(visit_count or 1),
            candidates=candidates,
        )
        selected_paths = candidate_paths(run_root, frame_scope, step_id, int(visit_count or 1), str(selection.selected_candidate_id))
        ledger_path = adjudicated.get("score_ledger_path")
        try:
            deadline.require_time_remaining("ledger collision check")
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        collision_message = self._adjudication_ledger_path_collision_message(
            adjudicated=adjudicated,
            output_contract_step=output_contract_step,
            candidates=candidates,
        )
        if collision_message is not None:
            selected["promotion_status"] = "failed"
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
                materialize_mirror=False,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result("ledger_path_collision", collision_message, candidates=candidates, visit_paths=visit_paths)
        try:
            deadline.require_time_remaining("pending ledger materialization")
            self._write_adjudication_ledgers(
                adjudicated=adjudicated,
                visit_paths=visit_paths,
                state=state,
                step_id=step_id,
                step_name=step_name,
                visit_count=int(visit_count or 1),
                candidates=candidates,
                selected_candidate_id=str(selection.selected_candidate_id),
                selection_reason=selection.selection_reason,
                promotion_status="pending",
                promoted_paths={},
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                materialize_mirror=False,
            )
            self._persist_adjudication_candidates(
                run_root=run_root,
                frame_scope=frame_scope,
                step_id=step_id,
                visit_count=int(visit_count or 1),
                candidates=candidates,
            )
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        except OSError as exc:
            return self._adjudication_failure_result("ledger_mirror_failed", str(exc), candidates=candidates, visit_paths=visit_paths)
        try:
            deadline.require_time_remaining("promotion")
            promotion = promote_candidate_outputs(
                expected_outputs=resolved_expected_outputs,
                output_bundle=resolved_output_bundle,
                candidate_workspace=selected_paths.workspace,
                parent_workspace=self.workspace,
                baseline_manifest=baseline_manifest,
                promotion_manifest_path=visit_paths.promotion_manifest_path,
                selected_candidate_id=str(selection.selected_candidate_id),
            )
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
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
                preserve_primary_failure=True,
            )
            if ledger_failure is not None:
                return ledger_failure
            return self._adjudication_failure_result(getattr(exc, "failure_type", "promotion_conflict"), str(exc), candidates=candidates, visit_paths=visit_paths)

        selected["promotion_status"] = "committed"
        selected["promoted_paths"] = promotion.promoted_paths
        self._persist_adjudication_candidates(
            run_root=run_root,
            frame_scope=frame_scope,
            step_id=step_id,
            visit_count=int(visit_count or 1),
            candidates=candidates,
        )
        try:
            deadline.require_time_remaining("terminal ledger materialization")
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
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
            deadline.require_time_remaining("parent output validation")
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)
        try:
            if resolved_output_bundle is not None:
                artifacts = validate_output_bundle(resolved_output_bundle, workspace=self.workspace)
            else:
                artifacts = validate_expected_outputs(resolved_expected_outputs or [], workspace=self.workspace)
            deadline.require_time_remaining("parent output validation completion")
        except OutputContractError as exc:
            return self._adjudication_failure_result("promotion_validation_failed", str(exc), candidates=candidates, visit_paths=visit_paths)
        except TimeoutError as exc:
            return self._adjudication_failure_result("timeout", str(exc), candidates=candidates, visit_paths=visit_paths)

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

    def _adjudication_deadline_expired(self, deadline: AdjudicationDeadline) -> bool:
        remaining = deadline.remaining_timeout_sec()
        return remaining is not None and remaining <= 0

    def _load_adjudication_resume_state(
        self,
        *,
        candidates_config: list[Any],
        evaluator_config: Mapping[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        run_root: Path,
        frame_scope: str,
        step_id: str,
        visit_count: int,
        visit_paths: Any,
    ) -> dict[str, Any]:
        if not visit_paths.baseline_manifest_path.exists() or not visit_paths.baseline_workspace.exists():
            return {
                "error": self._resume_mismatch(
                    "baseline manifest or workspace is missing for adjudication resume",
                    visit_paths=visit_paths,
                )
            }
        try:
            baseline_manifest = load_baseline_manifest(visit_paths.baseline_manifest_path)
        except Exception as exc:
            return {
                "error": self._resume_mismatch(
                    f"baseline manifest cannot be loaded for adjudication resume: {exc}",
                    visit_paths=visit_paths,
                )
            }
        if baseline_manifest.workflow_checksum != state.get("workflow_checksum", ""):
            return {
                "error": self._resume_mismatch(
                    "baseline workflow checksum does not match current resume state",
                    visit_paths=visit_paths,
                )
            }
        if baseline_manifest.copy_policy != BASELINE_COPY_POLICY:
            return {
                "error": self._resume_mismatch(
                    "baseline copy policy does not match the adjudication runtime",
                    visit_paths=visit_paths,
                )
            }

        try:
            ledger_rows = load_score_ledger_rows(visit_paths.run_score_ledger_path)
        except Exception as exc:
            return {
                "error": self._resume_mismatch(
                    f"score ledger cannot be loaded for adjudication resume: {exc}",
                    visit_paths=visit_paths,
                )
            }
        ledger_by_candidate = {
            str(row.get("candidate_id")): row
            for row in ledger_rows
            if isinstance(row.get("candidate_id"), str)
        }

        candidate_sidecars_exist = False
        for candidate_config in candidates_config:
            if not isinstance(candidate_config, dict):
                continue
            paths = candidate_paths(run_root, frame_scope, step_id, visit_count, str(candidate_config.get("id")))
            if paths.candidate_root.exists():
                candidate_sidecars_exist = True
                break
        if (
            not ledger_rows
            and not candidate_sidecars_exist
            and not visit_paths.scorer_root.exists()
            and not visit_paths.promotion_manifest_path.exists()
        ):
            return {
                "baseline_manifest": baseline_manifest,
                "candidates": [],
                "scorer": None,
                "evaluator_prompt": "",
                "scorer_failure": None,
                "baseline_only": True,
            }

        candidates: list[dict[str, Any]] = []
        pending_candidate_configs: list[tuple[int, dict[str, Any]]] = []
        for index, candidate_config in enumerate(candidates_config):
            if not isinstance(candidate_config, dict):
                continue
            candidate_id = str(candidate_config.get("id"))
            paths = candidate_paths(run_root, frame_scope, step_id, visit_count, candidate_id)
            metadata_file = candidate_metadata_path(paths)
            if not metadata_file.exists():
                if paths.candidate_root.exists() or candidate_id in ledger_by_candidate:
                    return {
                        "error": self._resume_mismatch(
                            f"candidate metadata missing for adjudication resume candidate '{candidate_id}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                pending_candidate_configs.append((index, candidate_config))
                continue
            try:
                candidate = load_candidate_metadata(paths)
            except Exception as exc:
                return {
                    "error": self._resume_mismatch(
                        f"candidate metadata cannot be loaded for adjudication resume candidate '{candidate_id}': {exc}",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if candidate.get("candidate_id") != candidate_id:
                return {
                    "error": self._resume_mismatch(
                        f"candidate metadata id mismatch for adjudication resume candidate '{candidate_id}'",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if candidate.get("candidate_index") != index:
                return {
                    "error": self._resume_mismatch(
                        f"candidate order mismatch for adjudication resume candidate '{candidate_id}'",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            expected_config_hash = self._stable_runtime_hash(candidate_config)
            if candidate.get("candidate_config_hash") != expected_config_hash:
                return {
                    "error": self._resume_mismatch(
                        f"candidate config hash mismatch for adjudication resume candidate '{candidate_id}'",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if paths.prompt_path.exists() and isinstance(candidate.get("composed_prompt_hash"), str):
                prompt_hash = self._text_hash(paths.prompt_path.read_text(encoding="utf-8"))
                if candidate.get("composed_prompt_hash") != prompt_hash:
                    return {
                        "error": self._resume_mismatch(
                            f"composed prompt hash mismatch for adjudication resume candidate '{candidate_id}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
            row = ledger_by_candidate.get(candidate_id)
            if row is not None:
                for key in ("candidate_run_key", "score_run_key"):
                    if isinstance(row.get(key), str):
                        candidate[key] = row[key]
            candidates.append(candidate)

        packet_candidates = []
        for candidate in candidates:
            paths = candidate_paths(run_root, frame_scope, step_id, visit_count, str(candidate.get("candidate_id")))
            if paths.evaluation_packet_path.exists():
                packet_candidates.append((candidate, paths.evaluation_packet_path))

        scored_or_evaluation_failed = [
            candidate
            for candidate in candidates
            if candidate.get("score_status") in {"scored", "evaluation_failed"}
        ]
        scorer_unavailable = [
            candidate
            for candidate in candidates
            if candidate.get("score_status") == "scorer_unavailable"
        ]

        scorer: dict[str, Any] | None = None
        evaluator_prompt = ""
        scorer_failure: dict[str, Any] | None = None
        if scored_or_evaluation_failed or packet_candidates:
            try:
                scorer = load_scorer_snapshot(visit_paths.scorer_root)
            except Exception as exc:
                return {
                    "error": self._resume_mismatch(
                        f"scorer snapshot cannot be loaded for adjudication resume: {exc}",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if scorer is None:
                return {
                    "error": self._resume_mismatch(
                        "scorer snapshot missing for terminal score metadata during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            current_scorer, current_prompt, current_failure = self._resolve_adjudication_scorer(
                evaluator_config,
                context,
                state,
                visit_paths=visit_paths,
                persist=False,
            )
            if current_failure is not None or current_scorer is None:
                return {
                    "error": self._resume_mismatch(
                        "scorer identity no longer resolves during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if current_scorer.get("scorer_identity_hash") != scorer.get("scorer_identity_hash"):
                return {
                    "error": self._resume_mismatch(
                        "scorer identity hash mismatch during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            evaluator_prompt = (
                scorer.get("evaluator_prompt_content")
                if isinstance(scorer.get("evaluator_prompt_content"), str)
                else current_prompt
            )
            for candidate in scored_or_evaluation_failed:
                if candidate.get("scorer_identity_hash") != scorer.get("scorer_identity_hash"):
                    return {
                        "error": self._resume_mismatch(
                            f"candidate scorer identity mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
            for candidate, packet_path in packet_candidates:
                try:
                    packet = json.loads(packet_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    return {
                        "error": self._resume_mismatch(
                            f"evaluation packet cannot be loaded for adjudication resume candidate '{candidate.get('candidate_id')}': {exc}",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if packet.get("scorer_identity_hash") != scorer.get("scorer_identity_hash"):
                    return {
                        "error": self._resume_mismatch(
                            f"evaluation packet scorer identity mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if (
                    isinstance(candidate.get("evaluation_packet_hash"), str)
                    and packet.get("evaluation_packet_hash") != candidate.get("evaluation_packet_hash")
                ):
                    return {
                        "error": self._resume_mismatch(
                            f"evaluation packet hash mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }

        if scorer_unavailable:
            try:
                scorer_failure = load_scorer_resolution_failure(visit_paths.scorer_root)
            except Exception as exc:
                return {
                    "error": self._resume_mismatch(
                        f"scorer resolution failure cannot be loaded for adjudication resume: {exc}",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if scorer_failure is None:
                return {
                    "error": self._resume_mismatch(
                        "scorer resolution failure metadata missing for scorer_unavailable ledger rows during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            current_scorer, _current_prompt, current_failure = self._resolve_adjudication_scorer(
                evaluator_config,
                context,
                state,
                visit_paths=visit_paths,
                persist=False,
            )
            if current_scorer is not None or current_failure is None:
                return {
                    "error": self._resume_mismatch(
                        "scorer resolution no longer fails during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if current_failure.get("scorer_resolution_failure_key") != scorer_failure.get("scorer_resolution_failure_key"):
                return {
                    "error": self._resume_mismatch(
                        "scorer resolution failure key mismatch during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            for candidate in scorer_unavailable:
                if candidate.get("scorer_resolution_failure_key") != scorer_failure.get("scorer_resolution_failure_key"):
                    return {
                        "error": self._resume_mismatch(
                            f"candidate scorer resolution key mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }

        for row in ledger_rows:
            score_status = row.get("score_status")
            if score_status in {"scored", "evaluation_failed"} and scorer is None:
                return {
                    "error": self._resume_mismatch(
                        "scorer snapshot missing for terminal score ledger rows during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }
            if score_status == "scorer_unavailable" and scorer_failure is None:
                return {
                    "error": self._resume_mismatch(
                        "scorer resolution failure metadata missing for scorer_unavailable ledger rows during adjudication resume",
                        visit_paths=visit_paths,
                        candidates=candidates,
                    )
                }

        return {
            "baseline_manifest": baseline_manifest,
            "candidates": candidates,
            "scorer": scorer,
            "evaluator_prompt": evaluator_prompt,
            "scorer_failure": scorer_failure,
            "pending_candidate_configs": pending_candidate_configs,
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

    def _adjudication_optional_path_surfaces(self, step: Dict[str, Any]) -> list[PathSurface]:
        surfaces: list[PathSurface] = []
        depends_on = step.get("depends_on")
        if isinstance(depends_on, dict):
            values = depends_on.get("optional")
            if isinstance(values, list):
                for index, value in enumerate(values):
                    if isinstance(value, str):
                        surfaces.append(PathSurface(f"depends_on.optional[{index}]", Path(value)))
        return surfaces

    def _resolve_adjudication_score_ledger_path(
        self,
        adjudicated: dict[str, Any],
        state: Dict[str, Any],
        context: Dict[str, Any],
        *,
        step_name: str,
        visit_paths: Any,
    ) -> Optional[Dict[str, Any]]:
        ledger_path = adjudicated.get("score_ledger_path")
        if not isinstance(ledger_path, str):
            return None
        resolved_path, path_error = self._substitute_path_template(
            ledger_path,
            state,
            step_name=step_name,
            field_name="adjudicated_provider.score_ledger_path",
            context=context,
        )
        if path_error is not None:
            return path_error
        if not isinstance(resolved_path, str):
            return self._adjudication_failure_result(
                "ledger_path_collision",
                "score_ledger_path must resolve to a workspace-relative artifacts path",
                visit_paths=visit_paths,
            )

        path = Path(resolved_path)
        normalized = path.as_posix()
        if path.is_absolute() or ".." in path.parts or not normalized.startswith("artifacts/"):
            return self._adjudication_failure_result(
                "ledger_path_collision",
                "score_ledger_path must resolve under artifacts/",
                visit_paths=visit_paths,
            )
        ledger_abs = (self.workspace / path).resolve()
        workspace_root = self.workspace.resolve()
        if not self._path_under(ledger_abs, workspace_root):
            return self._adjudication_failure_result(
                "ledger_path_collision",
                "score_ledger_path must not escape the parent workspace",
                visit_paths=visit_paths,
            )
        artifacts_root = (self.workspace / "artifacts").resolve()
        if not self._path_under(ledger_abs, artifacts_root):
            return self._adjudication_failure_result(
                "ledger_path_collision",
                "score_ledger_path must not escape artifacts/",
                visit_paths=visit_paths,
            )
        adjudicated["score_ledger_path"] = normalized
        return None

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
        persist: bool = True,
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
            if persist:
                persist_scorer_resolution_failure(payload, visit_paths.scorer_root)
            return payload

        provider_name = evaluator_config.get("provider")
        if not isinstance(provider_name, str) or not provider_name:
            return None, "", scorer_failure("missing_evaluator_provider", "evaluator provider is missing")
        if not self.provider_registry.exists(provider_name):
            return None, "", scorer_failure(
                "evaluator_provider_not_found",
                f"evaluator provider '{provider_name}' is not registered",
            )

        if (
            evaluator_prompt_source_kind == "input_file"
            and isinstance(evaluator_prompt_source, str)
            and not (self.workspace / evaluator_prompt_source).exists()
        ):
            return None, "", scorer_failure(
                "evaluator_prompt_read_failed",
                f"evaluator input file '{evaluator_prompt_source}' does not exist",
            )

        try:
            evaluator_prompt, prompt_error = self.prompt_composer.read_prompt_source(
                dict(evaluator_config),
                step_name="adjudication_evaluator",
                contract_violation_result=self._contract_violation_result,
            )
        except OSError as exc:
            return None, "", scorer_failure("evaluator_prompt_read_failed", str(exc))
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
            try:
                rubric_content, rubric_error = self.prompt_composer.read_prompt_source(
                    rubric_step,
                    step_name="adjudication_evaluator_rubric",
                    contract_violation_result=self._contract_violation_result,
                )
            except OSError as exc:
                return None, "", scorer_failure("rubric_read_failed", str(exc))
            if rubric_error is not None:
                return None, "", scorer_failure(
                    rubric_error.get("error", {}).get("type", "rubric_read_failed"),
                    rubric_error.get("error", {}).get("message", "rubric unavailable"),
                )
            rubric_hash = self._text_hash(rubric_content)
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
        if persist:
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
        deadline: AdjudicationDeadline,
        retry_policy: RetryPolicy,
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
            consumed_artifacts, consumed_relpath_targets = self._adjudication_consumed_artifacts_for_prompt(
                step,
                state,
                step_name=str(step.get("name", "")),
                consume_identity=step_id,
            )
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
                consumed_artifacts=consumed_artifacts,
                consumed_relpath_targets=consumed_relpath_targets,
                candidate_metadata={
                    "candidate_provider": candidate.get("candidate_provider"),
                    "candidate_model": candidate.get("candidate_model"),
                    "candidate_params_hash": candidate.get("candidate_params_hash"),
                    "candidate_index": candidate.get("candidate_index"),
                    "prompt_variant_id": candidate.get("prompt_variant_id"),
                },
                prompt_metadata={
                    "prompt_source_kind": candidate.get("prompt_source_kind"),
                    "prompt_source": candidate.get("prompt_source"),
                    "composed_prompt_hash": candidate.get("composed_prompt_hash"),
                },
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
        paths.evaluator_workspace.mkdir(parents=True, exist_ok=True)
        candidate["evaluator_attempts"] = []
        attempt = 0
        while True:
            deadline.require_time_remaining(f"candidate {candidate['candidate_id']} evaluator attempt")
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
                timeout_sec=deadline.remaining_timeout_sec(),
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
            exec_result = self._execute_provider_invocation(invocation, cwd=paths.evaluator_workspace)
            paths.evaluation_output_path.write_bytes(exec_result.stdout)
            paths.evaluation_stderr_log.write_bytes(exec_result.stderr)
            candidate["evaluator_attempt_count"] = attempt + 1
            candidate["evaluator_attempts"].append(
                {
                    "attempt": attempt + 1,
                    "exit_code": exec_result.exit_code,
                    "duration_ms": exec_result.duration_ms,
                }
            )
            if exec_result.exit_code == 0:
                break
            if retry_policy.should_retry(exec_result.exit_code, attempt):
                self._wait_for_adjudication_retry(retry_policy, deadline)
                attempt += 1
                continue
            candidate.update(
                {
                    "score_status": "evaluation_failed",
                    "failure_type": "timeout" if exec_result.exit_code == 124 else "evaluator_failed",
                    "failure_message": "evaluator provider failed",
                }
            )
            if exec_result.exit_code == 124 and self._adjudication_deadline_expired(deadline):
                raise TimeoutError("adjudicated provider deadline expired during evaluator execution")
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
        materialize_mirror: bool = True,
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
        rows_by_candidate = {str(row.get("candidate_id")): row for row in rows}
        for candidate in candidates:
            row = rows_by_candidate.get(str(candidate.get("candidate_id")))
            if row is not None:
                candidate["candidate_run_key"] = row["candidate_run_key"]
                candidate["score_run_key"] = row["score_run_key"]
        materialize_run_score_ledger(rows, visit_paths.run_score_ledger_path)
        mirror = adjudicated.get("score_ledger_path")
        if materialize_mirror and isinstance(mirror, str):
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
        preserve_primary_failure: bool = False,
        materialize_mirror: bool = True,
    ) -> Optional[Dict[str, Any]]:
        try:
            rows = self._write_adjudication_ledgers(
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
                materialize_mirror=False,
            )
        except OSError as exc:
            return self._adjudication_failure_result(
                "ledger_mirror_failed",
                str(exc),
                candidates=candidates,
                visit_paths=visit_paths,
                selected_candidate_id=selected_candidate_id,
                selection_reason=selection_reason,
                promotion_status=promotion_status,
            )
        if materialize_mirror:
            mirror = adjudicated.get("score_ledger_path")
            if isinstance(mirror, str):
                try:
                    materialize_score_ledger_mirror(rows, self.workspace / mirror)
                except LedgerConflictError as exc:
                    return self._adjudication_failure_result(
                        "ledger_conflict",
                        str(exc),
                        candidates=candidates,
                        visit_paths=visit_paths,
                        selected_candidate_id=selected_candidate_id,
                        selection_reason=selection_reason,
                        promotion_status=promotion_status,
                    )
                except OSError as exc:
                    if preserve_primary_failure:
                        return None
                    return self._adjudication_failure_result(
                        "ledger_mirror_failed",
                        str(exc),
                        candidates=candidates,
                        visit_paths=visit_paths,
                        selected_candidate_id=selected_candidate_id,
                        selection_reason=selection_reason,
                        promotion_status=promotion_status,
                    )
        return None

    def _adjudication_failure_result(
        self,
        error_type: str,
        message: str,
        *,
        candidates: Optional[list[dict[str, Any]]] = None,
        visit_paths: Any = None,
        selected_candidate_id: Optional[str] = None,
        selected_score: Optional[float] = None,
        selection_reason: Optional[str] = None,
        promotion_status: Optional[str] = None,
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
            if candidates:
                selected_candidate = next(
                    (
                        candidate
                        for candidate in candidates
                        if candidate.get("selected")
                        or (
                            selected_candidate_id is not None
                            and str(candidate.get("candidate_id")) == selected_candidate_id
                        )
                    ),
                    None,
                )
                if selected_candidate is not None:
                    if selected_candidate_id is None:
                        selected_candidate_id = str(selected_candidate.get("candidate_id"))
                    if selected_score is None:
                        score = selected_candidate.get("score")
                        selected_score = float(score) if isinstance(score, (int, float)) else None
                    promotion_status = str(selected_candidate.get("promotion_status") or promotion_status or "failed")
            result["adjudication"] = {
                "schema": "adjudicated_provider.state.v1",
                "selected_candidate_id": selected_candidate_id,
                "selected_score": selected_score,
                "selection_reason": selection_reason or ("none" if selected_candidate_id is None else "highest_score"),
                "promotion_status": promotion_status or ("not_selected" if selected_candidate_id is None else "failed"),
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
                "candidate_run_key": candidate.get("candidate_run_key"),
                "score_run_key": candidate.get("score_run_key"),
                "provider_exit_code": candidate.get("provider_exit_code"),
                "attempt_count": candidate.get("attempt_count"),
                "evaluator_attempt_count": candidate.get("evaluator_attempt_count"),
                "failure_type": candidate.get("failure_type"),
                "failure_message": candidate.get("failure_message"),
                "scorer_resolution_failure_key": candidate.get("scorer_resolution_failure_key"),
                "evaluation_packet_hash": candidate.get("evaluation_packet_hash"),
            }
        return result

    def _persist_adjudication_candidates(
        self,
        *,
        run_root: Path,
        frame_scope: str,
        step_id: str,
        visit_count: int,
        candidates: list[dict[str, Any]],
    ) -> None:
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            if not isinstance(candidate_id, str) or not candidate_id:
                continue
            paths = candidate_paths(run_root, frame_scope, step_id, visit_count, candidate_id)
            persist_candidate_metadata(candidate, paths)

    def _resume_mismatch(
        self,
        message: str,
        *,
        visit_paths: Any,
        candidates: Optional[list[dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        return self._adjudication_failure_result(
            "adjudication_resume_mismatch",
            message,
            candidates=candidates,
            visit_paths=visit_paths,
        )

    def _output_paths_from_contract(self, step: Dict[str, Any]) -> dict[str, str]:
        paths: dict[str, str] = {}
        for spec in step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []:
            if isinstance(spec, dict) and isinstance(spec.get("name"), str) and isinstance(spec.get("path"), str):
                paths[spec["name"]] = spec["path"]
        output_bundle = step.get("output_bundle")
        if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
            paths["output_bundle"] = output_bundle["path"]
        return paths

    def _adjudication_ledger_path_collision_message(
        self,
        *,
        adjudicated: Mapping[str, Any],
        output_contract_step: Dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> Optional[str]:
        ledger_path = adjudicated.get("score_ledger_path")
        if not isinstance(ledger_path, str):
            return None
        ledger_abs = (self.workspace / ledger_path).resolve()
        dynamic_paths: set[Path] = set()
        for candidate in candidates:
            if candidate.get("candidate_status") != "output_valid":
                continue
            artifacts = candidate.get("artifacts")
            if isinstance(artifacts, Mapping):
                dynamic_paths.update(self._promotion_destination_paths(output_contract_step, artifacts))
        if ledger_abs in dynamic_paths:
            return "score ledger path collides with step-managed output path"
        return None

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
            fields = output_bundle.get("fields")
            if isinstance(fields, list):
                for field_spec in fields:
                    if not isinstance(field_spec, dict):
                        continue
                    if field_spec.get("type") == "relpath" and field_spec.get("must_exist_target") and isinstance(field_spec.get("name"), str):
                        value = artifacts.get(field_spec["name"])
                        if isinstance(value, str):
                            paths.add((self.workspace / value).resolve())
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

    def _adjudication_consumed_artifacts_for_prompt(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        step_name: str,
        consume_identity: str,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        if step.get("inject_consumes", True) is False:
            return {}, {}
        consumes = step.get("consumes")
        if not isinstance(consumes, list) or not consumes:
            return {}, {}
        resolved_consumes = state.get("_resolved_consumes", {})
        if not isinstance(resolved_consumes, dict):
            return {}, {}

        step_consumed_values = resolved_consumes.get(step_name, {})
        if self._uses_qualified_identities() and (
            not isinstance(step_consumed_values, dict) or not step_consumed_values
        ):
            step_consumed_values = resolved_consumes.get(consume_identity, {})
        if not isinstance(step_consumed_values, dict) or not step_consumed_values:
            return {}, {}

        prompt_consumes = step.get("prompt_consumes")
        allowed_names: Optional[set[str]] = None
        if prompt_consumes is not None:
            if not isinstance(prompt_consumes, list):
                return {}, {}
            allowed_names = {
                name for name in prompt_consumes
                if isinstance(name, str) and name.strip()
            }
            if not allowed_names:
                return {}, {}

        injected_values: dict[str, Any] = {}
        for key, value in step_consumed_values.items():
            if not isinstance(key, str):
                continue
            if allowed_names is not None and key not in allowed_names:
                continue
            if isinstance(value, (str, int, float, bool, list, dict)):
                injected_values[key] = value

        relpath_targets: dict[str, str] = {}
        for consume in consumes:
            if not isinstance(consume, dict):
                continue
            artifact_name = consume.get("artifact")
            if not isinstance(artifact_name, str) or artifact_name not in injected_values:
                continue
            artifact_spec = self.workflow_artifacts.get(artifact_name)
            if not isinstance(artifact_spec, dict):
                artifact_spec = self.private_workflow_artifacts.get(artifact_name, {})
            artifact_kind = "relpath"
            if isinstance(artifact_spec, dict) and isinstance(artifact_spec.get("kind"), str):
                artifact_kind = artifact_spec["kind"]
            value = injected_values[artifact_name]
            if (
                artifact_kind == "relpath"
                and isinstance(artifact_spec, dict)
                and isinstance(value, str)
            ):
                relpath_targets[artifact_name] = value
        return injected_values, relpath_targets

    def _provider_model(self, params: Any) -> Optional[str]:
        if isinstance(params, Mapping):
            model = params.get("model") or params.get("reasoning_model")
            return model if isinstance(model, str) else None
        return None

    def _resolve_provider_params_for_adjudication(
        self,
        provider_name: str,
        params: Any,
        context: Dict[str, Any],
        state: Dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        raw_params = params if isinstance(params, dict) else {}
        merged = self.provider_registry.merge_params(provider_name, raw_params)
        provider_context = self._create_provider_context(context, state)
        try:
            substituted, errors = self.provider_executor._substitute_params(merged, provider_context)
        except Exception as exc:
            return merged, [str(exc)]
        return substituted, [str(error) for error in errors]

    def _prompt_source_metadata(self, step: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
        if isinstance(step.get("asset_file"), str):
            return "asset_file", step.get("asset_file")
        if isinstance(step.get("input_file"), str):
            return "input_file", step.get("input_file")
        return None, None

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
        variant_output = step.get('variant_output')
        contract_bundle = variant_output if isinstance(variant_output, dict) else output_bundle
        resolved_output_bundle: Optional[Dict[str, Any]] = None
        if isinstance(contract_bundle, dict):
            resolved_output_bundle = deepcopy(contract_bundle)
            path_value = resolved_output_bundle.get('path')
            if isinstance(path_value, str):
                resolved_path, path_error = self._substitute_path_template(
                    path_value,
                    state,
                    step_name=step_name,
                    field_name='variant_output.path' if isinstance(variant_output, dict) else 'output_bundle.path',
                    context=context,
                )
                if path_error is not None:
                    return None, None, path_error
                resolved_output_bundle['path'] = resolved_path

        return resolved_expected_outputs, resolved_output_bundle, None

    def _env_with_runtime_output_bundle_path(
        self,
        authored_env: Any,
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, str]]:
        """Return env with runtime-owned structured bundle path binding."""
        bundle_path = (
            resolved_output_bundle.get('path')
            if isinstance(resolved_output_bundle, dict)
            else None
        )
        if not isinstance(bundle_path, str):
            return authored_env if isinstance(authored_env, dict) else None

        env_map: Dict[str, str] = {}
        if isinstance(authored_env, dict):
            env_map.update(authored_env)
        env_map['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'] = bundle_path
        return env_map

    def _provider_env_with_runtime_output_bundle_path(
        self,
        step: Dict[str, Any],
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, str]]:
        """Return provider env with runtime-owned structured bundle path binding."""
        return self._env_with_runtime_output_bundle_path(step.get('env'), resolved_output_bundle)

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
        variant_output = step.get('variant_output')
        if not expected_outputs and not output_bundle and not variant_output:
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
            if isinstance(variant_output, dict):
                artifacts = validate_variant_output_bundle(
                    resolved_output_bundle or {},
                    workspace=self.workspace,
                )
            elif resolved_output_bundle:
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

    def _v214_failure_result(
        self,
        error_type: str,
        message: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": "failed",
            "exit_code": 2,
            "duration_ms": 0,
            "error": {
                "type": error_type,
                "message": message,
                "context": context or {},
            },
        }

    def _atomic_write_text(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.parent / f".{target.name}.tmp-{os.getpid()}-{time.time_ns()}"
        temp_path.write_text(content, encoding="utf-8")
        os.replace(temp_path, target)

    def _workflow_input_contracts(self) -> Dict[str, Dict[str, Any]]:
        return dict(workflow_runtime_input_contracts(self.loaded_bundle))

    def _runtime_step_by_name(self, step_name: str) -> Optional[RuntimeStep]:
        if not isinstance(step_name, str) or not step_name:
            return None
        index = self._projection_index_by_presentation_name.get(step_name)
        if not isinstance(index, int) or index >= len(self._step_node_ids):
            return None
        node_id = self._step_node_ids[index]
        if not isinstance(node_id, str):
            return None
        return self._runtime_step_for_node_id(node_id, presentation_name=step_name)

    def _variant_contract_for_step(self, step_name: str) -> Optional[Dict[str, Any]]:
        runtime_step = self._runtime_step_by_name(step_name)
        if runtime_step is None:
            return None
        variant_output = runtime_step.get("variant_output")
        if isinstance(variant_output, dict) and variant_output:
            return variant_output
        select_variant_output = runtime_step.get("select_variant_output")
        if isinstance(select_variant_output, dict) and select_variant_output:
            return select_variant_output
        return None

    def _artifact_contract_for_step(self, step_name: str, artifact_name: str) -> Optional[Dict[str, Any]]:
        runtime_step = self._runtime_step_by_name(step_name)
        if runtime_step is None:
            return None

        expected_outputs = runtime_step.get("expected_outputs")
        if isinstance(expected_outputs, list):
            for spec in expected_outputs:
                if isinstance(spec, dict) and spec.get("name") == artifact_name:
                    return spec

        output_bundle = runtime_step.get("output_bundle")
        if isinstance(output_bundle, dict):
            fields = output_bundle.get("fields", [])
            if isinstance(fields, list):
                for spec in fields:
                    if isinstance(spec, dict) and spec.get("name") == artifact_name:
                        return spec

        materialize_artifacts = runtime_step.get("materialize_artifacts")
        if isinstance(materialize_artifacts, dict):
            values = materialize_artifacts.get("values", [])
            if isinstance(values, list):
                for spec in values:
                    if isinstance(spec, dict) and spec.get("name") == artifact_name:
                        contract = spec.get("contract")
                        if isinstance(contract, dict):
                            return contract

        variant_contract = self._variant_contract_for_step(step_name)
        if not isinstance(variant_contract, dict):
            return None

        discriminant = variant_contract.get("discriminant")
        if isinstance(discriminant, dict) and discriminant.get("name") == artifact_name:
            return discriminant

        shared_fields = variant_contract.get("shared_fields", [])
        if isinstance(shared_fields, list):
            for spec in shared_fields:
                if isinstance(spec, dict) and spec.get("name") == artifact_name:
                    return spec

        variants = variant_contract.get("variants", {})
        if isinstance(variants, dict):
            for variant_spec in variants.values():
                if not isinstance(variant_spec, dict):
                    continue
                fields = variant_spec.get("fields", [])
                if not isinstance(fields, list):
                    continue
                for spec in fields:
                    if isinstance(spec, dict) and spec.get("name") == artifact_name:
                        return spec
        return None

    def _variant_requirement_for_artifact(
        self,
        step_name: str,
        artifact_name: str,
    ) -> tuple[Optional[str], Optional[str]]:
        variant_contract = self._variant_contract_for_step(step_name)
        if not isinstance(variant_contract, dict):
            return None, None
        discriminant = variant_contract.get("discriminant")
        discriminant_name = (
            discriminant.get("name")
            if isinstance(discriminant, dict) and isinstance(discriminant.get("name"), str)
            else None
        )
        if artifact_name == discriminant_name:
            return discriminant_name, None
        shared_fields = variant_contract.get("shared_fields", [])
        if isinstance(shared_fields, list):
            for spec in shared_fields:
                if isinstance(spec, dict) and spec.get("name") == artifact_name:
                    return discriminant_name, None
        variants = variant_contract.get("variants", {})
        if isinstance(variants, dict):
            for variant_name, variant_spec in variants.items():
                if not isinstance(variant_spec, dict):
                    continue
                fields = variant_spec.get("fields", [])
                if not isinstance(fields, list):
                    continue
                for spec in fields:
                    if isinstance(spec, dict) and spec.get("name") == artifact_name:
                        return discriminant_name, str(variant_name)
        return discriminant_name, None

    def _resolve_variant_ref_guard(
        self,
        ref: str,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        if ".artifacts." not in ref:
            return None
        if ref.startswith("self.steps."):
            steps = scope.get("self_steps") if isinstance(scope, dict) else None
        elif ref.startswith("parent.steps."):
            steps = scope.get("parent_steps") if isinstance(scope, dict) else None
        else:
            steps = state.get("steps", {})
        if not isinstance(steps, dict):
            return None
        try:
            target = parse_structured_ref(ref, steps.keys())
        except ReferenceResolutionError:
            return None
        if target.field != "artifacts" or not isinstance(target.member, str):
            return None
        discriminant_name, required_variant = self._variant_requirement_for_artifact(
            target.step_name,
            target.member,
        )
        if required_variant is None:
            return None
        step_result = steps.get(target.step_name)
        artifacts = step_result.get("artifacts") if isinstance(step_result, dict) else None
        selected_variant = (
            artifacts.get(discriminant_name)
            if isinstance(artifacts, dict) and isinstance(discriminant_name, str)
            else None
        )
        if selected_variant == required_variant:
            return None
        return self._v214_failure_result(
            "variant_unavailable",
            f"Variant-specific artifact '{target.member}' is unavailable",
            context={
                "producer_step": target.step_name,
                "requested_field": target.member,
                "required_variant": required_variant,
                "selected_variant": selected_variant,
            },
        )

    @staticmethod
    def _rewrite_scoped_ref_for_nested_projection(
        ref: str,
        *,
        scope_name: str,
        step_results: Dict[str, Any],
    ) -> str | None:
        prefix = f"{scope_name}.steps."
        if not ref.startswith(prefix) or not isinstance(step_results, dict):
            return None

        remainder = ref[len(prefix):]
        step_name: str | None = None
        suffix = ""
        for marker in (".artifacts.", ".snapshots.", ".outcome.", ".exit_code"):
            if marker in remainder:
                step_name, trailing = remainder.split(marker, 1)
                suffix = marker + trailing
                break
        if step_name is None:
            return None

        candidates = [
            key
            for key in step_results
            if key == step_name or key.endswith(f".{step_name}")
        ]
        if len(candidates) != 1:
            return None
        return f"{prefix}{candidates[0]}{suffix}"

    def _resolve_ref_value(
        self,
        ref: str,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        variant_guard_error = self._resolve_variant_ref_guard(ref, state, scope=scope)
        if variant_guard_error is not None:
            return None, variant_guard_error
        try:
            return self.reference_resolver.resolve(ref, state, scope=scope).value, None
        except ReferenceResolutionError as exc:
            if (
                ref.startswith("parent.steps.")
                and isinstance(scope, dict)
                and isinstance(scope.get("self_steps"), dict)
            ):
                retry_scope = dict(scope)
                retry_scope["parent_steps"] = scope["self_steps"]
                try:
                    return self.reference_resolver.resolve(ref, state, scope=retry_scope).value, None
                except ReferenceResolutionError:
                    pass
            scope_name = "self" if ref.startswith("self.steps.") else "parent" if ref.startswith("parent.steps.") else None
            if scope_name is not None:
                candidate_step_maps: list[dict[str, Any]] = []
                if isinstance(scope, dict) and isinstance(scope.get(f"{scope_name}_steps"), dict):
                    candidate_step_maps.append(scope[f"{scope_name}_steps"])
                if isinstance(state.get("steps"), dict):
                    candidate_step_maps.append(state["steps"])
                for step_results in candidate_step_maps:
                    rewritten_ref = self._rewrite_scoped_ref_for_nested_projection(
                        ref,
                        scope_name=scope_name,
                        step_results=step_results,
                    )
                    if not isinstance(rewritten_ref, str):
                        continue
                    retry_scope = dict(scope) if isinstance(scope, dict) else {}
                    retry_scope.setdefault(f"{scope_name}_steps", step_results)
                    try:
                        return self.reference_resolver.resolve(rewritten_ref, state, scope=retry_scope).value, None
                    except ReferenceResolutionError:
                        continue
            return None, self._v214_failure_result(
                "materialize_ref_unresolved",
                "Structured ref could not be resolved",
                context={"ref": ref, "error": str(exc)},
            )

    def _copy_contract_definition(self, contract: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(contract, dict):
            return None
        return deepcopy(contract)

    def _infer_contract_kind(self, contract: Dict[str, Any]) -> str:
        kind = contract.get("kind")
        if isinstance(kind, str) and kind:
            return kind
        return "relpath" if contract.get("type") == "relpath" else "scalar"

    def _normalize_under_parts(self, raw_under: Any) -> Optional[tuple[str, ...]]:
        if not isinstance(raw_under, str) or not raw_under:
            return None
        parts = Path(raw_under).parts
        if any(part in {"..", ""} for part in parts):
            return None
        return tuple(parts)

    def _refine_contract(
        self,
        base_contract: Dict[str, Any],
        refine_contract: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        contract = deepcopy(base_contract)
        source_type = contract.get("type")
        source_kind = self._infer_contract_kind(contract)
        refined = dict(refine_contract)
        refined.pop("inherit", None)
        if "refine" in refined and isinstance(refined["refine"], dict):
            nested_refine = dict(refined.pop("refine"))
            refined.update(nested_refine)

        if "type" in refined and refined["type"] != source_type:
            return None, self._v214_failure_result(
                "contract_refinement_type_conflict",
                "Materialized contract type conflicts with source contract",
                context={"source_type": source_type, "refined_type": refined["type"]},
            )
        if "kind" in refined and refined["kind"] != source_kind:
            return None, self._v214_failure_result(
                "contract_refinement_kind_conflict",
                "Materialized contract kind conflicts with source contract",
                context={"source_kind": source_kind, "refined_kind": refined["kind"]},
            )

        if "must_exist_target" in refined:
            source_required = bool(contract.get("must_exist_target"))
            refined_required = bool(refined["must_exist_target"])
            if source_required and not refined_required:
                return None, self._v214_failure_result(
                    "contract_refinement_weakened",
                    "must_exist_target cannot be weakened",
                    context={"source": source_required, "refined": refined_required},
                )

        if "under" in refined:
            source_under = self._normalize_under_parts(contract.get("under"))
            refined_under = self._normalize_under_parts(refined.get("under"))
            if refined_under is None:
                return None, self._v214_failure_result(
                    "unsafe_path",
                    "Refined under root is unsafe",
                    context={"under": refined.get("under")},
                )
            if source_under is not None and refined_under[: len(source_under)] != source_under:
                return None, self._v214_failure_result(
                    "contract_refinement_incompatible_under",
                    "Refined under root is incompatible with source contract",
                    context={"source_under": contract.get("under"), "refined_under": refined.get("under")},
                )

        if "allowed" in refined:
            source_allowed = contract.get("allowed")
            refined_allowed = refined.get("allowed")
            if contract.get("type") != "enum":
                return None, self._v214_failure_result(
                    "contract_field_invalid_for_type",
                    "allowed is only valid for enum contracts",
                    context={"type": contract.get("type")},
                )
            if (
                isinstance(source_allowed, list)
                and isinstance(refined_allowed, list)
                and not set(refined_allowed).issubset(set(source_allowed))
            ):
                return None, self._v214_failure_result(
                    "contract_refinement_weakened",
                    "Enum refinements must be a subset of the source contract",
                    context={"source_allowed": source_allowed, "refined_allowed": refined_allowed},
                )

        contract.update(refined)
        contract.setdefault("kind", source_kind)
        return contract, None

    def _resolve_materialized_contract(
        self,
        source_node: Dict[str, Any],
        contract_node: Any,
        state: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        source_contract: Optional[Dict[str, Any]] = None
        if "input" in source_node:
            source_contract = self._workflow_input_contracts().get(str(source_node["input"]))
        elif "ref" in source_node and isinstance(source_node.get("ref"), str):
            ref = source_node["ref"]
            if ".artifacts." in ref:
                try:
                    target = parse_structured_ref(ref, state.get("steps", {}).keys())
                except ReferenceResolutionError:
                    target = None
                if target is not None and target.field == "artifacts" and isinstance(target.member, str):
                    source_contract = self._artifact_contract_for_step(target.step_name, target.member)
        elif source_node.get("runtime") == "now_ns":
            source_contract = {"kind": "scalar", "type": "integer"}

        if not isinstance(contract_node, dict):
            if "literal" in source_node:
                return None, self._v214_failure_result(
                    "contract_required_for_literal",
                    "Literal materialization requires an explicit contract",
                )
            if source_contract is None:
                return None, self._v214_failure_result(
                    "contract_source_unknown",
                    "Source contract is unavailable for materialization",
                )
            return deepcopy(source_contract), None

        if contract_node.get("inherit") == "source" or source_contract is not None:
            if source_contract is None:
                return None, self._v214_failure_result(
                    "contract_source_unknown",
                    "Source contract is unavailable for materialization",
                )
            return self._refine_contract(source_contract, contract_node)

        return deepcopy(contract_node), None

    def _validate_materialized_value(
        self,
        raw_value: Any,
        contract: Dict[str, Any],
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        try:
            return validate_contract_value(raw_value, contract, workspace=self.workspace), None
        except OutputContractError as exc:
            violation = exc.violations[0] if exc.violations else {}
            violation_type = violation.get("type")
            error_type = {
                "missing_target": "target_missing",
                "path_escape": "unsafe_path",
                "outside_under_root": "unsafe_path",
                "invalid_under_root": "unsafe_path",
            }.get(violation_type, "contract_violation")
            return None, self._v214_failure_result(
                error_type,
                "Materialized value failed contract validation",
                context={"violations": exc.violations},
            )

    def _capture_file_snapshot(
        self,
        relpath: str,
        *,
        max_bytes_per_candidate: int,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        candidate = self._resolve_workspace_path(relpath)
        if candidate is None:
            return None, self._v214_failure_result(
                "snapshot_candidate_unsafe_path",
                "Snapshot candidate path is unsafe",
                context={"path": relpath},
            )
        if candidate.exists() and candidate.is_dir():
            return None, self._v214_failure_result(
                "snapshot_candidate_is_directory",
                "Snapshot candidate must be a file",
                context={"path": relpath},
            )
        if not candidate.exists():
            return {
                "path": relpath,
                "exists": False,
                "size": None,
                "sha256": None,
                "mtime_ns": None,
            }, None

        stat_result = candidate.stat()
        if stat_result.st_size > max_bytes_per_candidate:
            return None, self._v214_failure_result(
                "snapshot_candidate_oversize",
                "Snapshot candidate exceeds the allowed size limit",
                context={
                    "path": relpath,
                    "size": stat_result.st_size,
                    "max_bytes_per_candidate": max_bytes_per_candidate,
                },
            )

        digest = sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "path": relpath,
            "exists": True,
            "size": stat_result.st_size,
            "sha256": digest.hexdigest(),
            "mtime_ns": stat_result.st_mtime_ns,
        }, None

    def _step_snapshot_dir(self, step: Dict[str, Any]) -> Path:
        safe_step_id = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in self._step_id(step)
        ).strip("._-") or "step"
        return self.state_manager.run_root / "snapshots" / safe_step_id

    def _project_snapshot_record(
        self,
        step: Dict[str, Any],
        snapshot_name: str,
        snapshot_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = json.dumps(snapshot_record, sort_keys=True, ensure_ascii=True) + "\n"
        if len(payload.encode("utf-8")) <= 4096:
            return snapshot_record

        snapshot_dir = self._step_snapshot_dir(step)
        sidecar_path = snapshot_dir / f"{snapshot_name}.json"
        self._atomic_write_text(sidecar_path, payload)
        sidecar_rel = sidecar_path.relative_to(self.state_manager.run_root).as_posix()
        return {
            "schema": snapshot_record["schema"],
            "digest": snapshot_record["digest"],
            "captured_at": snapshot_record["captured_at"],
            "candidate_keys": snapshot_record["candidate_keys"],
            "sidecar": sidecar_rel,
            "sha256": sha256(payload.encode("utf-8")).hexdigest(),
        }

    def _inflate_snapshot_record(self, snapshot_state: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if "sidecar" not in snapshot_state:
            return snapshot_state, None
        sidecar = snapshot_state.get("sidecar")
        if not isinstance(sidecar, str):
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot state is missing sidecar metadata",
            )
        sidecar_path = self._resolve_run_root_path(sidecar)
        if sidecar_path is None:
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot sidecar path is unsafe",
                context={"sidecar": sidecar},
            )
        if not sidecar_path.exists():
            return None, self._v214_failure_result(
                "snapshot_sidecar_missing",
                "Snapshot sidecar is missing",
                context={"sidecar": sidecar},
            )
        expected_hash = snapshot_state.get("sha256")
        if not isinstance(expected_hash, str) or not expected_hash:
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot sidecar state is missing the recorded sha256 hash",
                context={"sidecar": sidecar},
            )
        if not sidecar_path.is_file():
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot sidecar must be a file",
                context={"sidecar": sidecar},
            )
        payload = sidecar_path.read_text(encoding="utf-8")
        actual_hash = sha256(payload.encode("utf-8")).hexdigest()
        if expected_hash != actual_hash:
            return None, self._v214_failure_result(
                "snapshot_sidecar_hash_mismatch",
                "Snapshot sidecar hash does not match recorded state",
                context={"sidecar": sidecar},
            )
        try:
            snapshot_record = json.loads(payload)
        except json.JSONDecodeError:
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot sidecar payload is not valid JSON",
                context={"sidecar": sidecar},
            )
        if not isinstance(snapshot_record, Mapping):
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot sidecar payload must decode to an object",
                context={"sidecar": sidecar},
            )
        return dict(snapshot_record), None

    def _capture_pre_snapshot(self, step: Dict[str, Any], state: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        snapshot_config = step.get("pre_snapshot")
        if not isinstance(snapshot_config, dict) or not snapshot_config:
            return None, None

        snapshot_name = snapshot_config.get("name")
        if not isinstance(snapshot_name, str) or not snapshot_name:
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "pre_snapshot requires a snapshot name",
            )
        digest = snapshot_config.get("digest")
        if digest != "sha256":
            return None, self._v214_failure_result(
                "snapshot_ref_not_snapshot_diff",
                "pre_snapshot requires digest 'sha256'",
                context={"snapshot": snapshot_name, "digest": digest},
            )
        max_bytes = snapshot_config.get("max_bytes_per_candidate", 16 * 1024 * 1024)
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            max_bytes = 16 * 1024 * 1024
        max_bytes = min(max_bytes, 64 * 1024 * 1024)

        candidates_config = snapshot_config.get("candidates")
        if not isinstance(candidates_config, dict) or not candidates_config:
            return None, self._v214_failure_result(
                "snapshot_state_missing",
                "pre_snapshot requires candidates",
            )

        snapshot_record = {
            "schema": "snapshot_diff/v1",
            "digest": "sha256",
            "captured_at": "pre_step",
            "max_bytes_per_candidate": max_bytes,
            "candidate_keys": sorted(str(key) for key in candidates_config.keys()),
            "candidates": {},
        }
        for candidate_key in snapshot_record["candidate_keys"]:
            candidate_spec = candidates_config.get(candidate_key)
            ref = candidate_spec.get("ref") if isinstance(candidate_spec, dict) else None
            if not isinstance(ref, str):
                return None, self._v214_failure_result(
                    "snapshot_state_missing",
                    "Snapshot candidates require a structured ref",
                    context={"candidate": candidate_key},
                )
            relpath, resolve_error = self._resolve_ref_value(ref, state)
            if resolve_error is not None:
                return None, resolve_error
            if not isinstance(relpath, str):
                return None, self._v214_failure_result(
                    "snapshot_candidate_unsafe_path",
                    "Snapshot candidate ref must resolve to a relpath string",
                    context={"candidate": candidate_key, "ref": ref},
                )
            snapshot_entry, snapshot_error = self._capture_file_snapshot(
                relpath,
                max_bytes_per_candidate=max_bytes,
            )
            if snapshot_error is not None:
                return None, snapshot_error
            snapshot_record["candidates"][candidate_key] = snapshot_entry

        return {snapshot_name: self._project_snapshot_record(step, snapshot_name, snapshot_record)}, None

    def _resolve_selected_variant_guard(
        self,
        requires_variant: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        producer_step = requires_variant.get("step")
        required_variant = requires_variant.get("value")
        if not isinstance(producer_step, str) or not isinstance(required_variant, str):
            return self._v214_failure_result(
                "unsupported_variant_proof",
                "requires_variant must declare step and value",
            )
        step_result = state.get("steps", {}).get(producer_step)
        discriminant_name, _ = self._variant_requirement_for_artifact(producer_step, "__unused__")
        if discriminant_name is None:
            variant_contract = self._variant_contract_for_step(producer_step)
            discriminant = variant_contract.get("discriminant") if isinstance(variant_contract, dict) else None
            discriminant_name = discriminant.get("name") if isinstance(discriminant, dict) else None
        artifacts = step_result.get("artifacts") if isinstance(step_result, dict) else None
        selected_variant = (
            artifacts.get(discriminant_name)
            if isinstance(artifacts, dict) and isinstance(discriminant_name, str)
            else None
        )
        if selected_variant == required_variant:
            return None
        return self._v214_failure_result(
            "variant_unavailable",
            "Required variant is unavailable for this step",
            context={
                "producer_step": producer_step,
                "required_variant": required_variant,
                "selected_variant": selected_variant,
            },
        )

    def _execute_materialize_artifacts(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        config = step.get("materialize_artifacts")
        if not isinstance(config, dict):
            return self._v214_failure_result(
                "materialize_source_unknown",
                "materialize_artifacts config must be a dictionary",
            )
        values = config.get("values")
        if not isinstance(values, list):
            return self._v214_failure_result(
                "materialize_source_unknown",
                "materialize_artifacts requires a values list",
            )

        artifacts: Dict[str, Any] = {}
        pointer_map: Dict[str, str] = {}
        for entry in values:
            if not isinstance(entry, dict):
                return self._v214_failure_result(
                    "materialize_source_unknown",
                    "materialize_artifacts values must be dictionaries",
                )
            name = entry.get("name")
            source = entry.get("source")
            if not isinstance(name, str) or not isinstance(source, dict):
                return self._v214_failure_result(
                    "materialize_source_unknown",
                    "materialize_artifacts values require name and source",
                )

            if "input" in source:
                input_name = source.get("input")
                bound_inputs = state.get("bound_inputs", {})
                if not isinstance(input_name, str) or not isinstance(bound_inputs, dict) or input_name not in bound_inputs:
                    return self._v214_failure_result(
                        "materialize_source_unknown",
                        "Materialization input source is unavailable",
                        context={"name": name, "input": input_name},
                    )
                raw_value = bound_inputs[input_name]
            elif "ref" in source:
                ref = source.get("ref")
                if not isinstance(ref, str):
                    return self._v214_failure_result(
                        "materialize_ref_unresolved",
                        "Materialization ref source must be a structured ref",
                        context={"name": name},
                    )
                raw_value, resolve_error = self._resolve_ref_value(ref, state, scope=scope)
                if resolve_error is not None:
                    return resolve_error
            elif "literal" in source:
                raw_value = source.get("literal")
            elif source.get("runtime") == "now_ns":
                raw_value = time.time_ns()
            else:
                return self._v214_failure_result(
                    "materialize_source_unknown",
                    "Unsupported materialization source",
                    context={"name": name, "source": source},
                )

            contract, contract_error = self._resolve_materialized_contract(source, entry.get("contract"), state)
            if contract_error is not None or contract is None:
                return contract_error or self._v214_failure_result(
                    "contract_source_unknown",
                    "Failed to resolve materialized contract",
                    context={"name": name},
                )

            contract.setdefault("kind", self._infer_contract_kind(contract))
            value, validation_error = self._validate_materialized_value(raw_value, contract)
            if validation_error is not None:
                return validation_error

            if entry.get("ensure_parent") and contract.get("type") == "relpath" and isinstance(value, str):
                target = self._resolve_workspace_path(value)
                if target is not None:
                    target.parent.mkdir(parents=True, exist_ok=True)

            pointer = entry.get("pointer")
            if pointer:
                pointer_path = pointer.get("path") if isinstance(pointer, dict) else None
                if not isinstance(pointer_path, str):
                    return self._v214_failure_result(
                        "unsafe_path",
                        "Pointer path must be a string",
                        context={"name": name},
                    )
                substituted_pointer_path, pointer_error = self._substitute_path_template(
                    pointer_path,
                    state,
                    step_name=step.get("name", "<unnamed>"),
                    field_name=f"materialize_artifacts.values[{name}].pointer.path",
                )
                if pointer_error is not None or substituted_pointer_path is None:
                    return pointer_error or self._v214_failure_result(
                        "unsafe_path",
                        "Pointer path substitution failed",
                        context={"name": name, "path": pointer_path},
                    )
                resolved_pointer = self._resolve_workspace_path(substituted_pointer_path)
                if resolved_pointer is None:
                    return self._v214_failure_result(
                        "unsafe_path",
                        "Pointer path escapes the workspace",
                        context={"name": name, "path": substituted_pointer_path},
                    )
                try:
                    pointer_value = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
                    self._atomic_write_text(resolved_pointer, f"{pointer_value}\n")
                except OSError as exc:
                    return self._v214_failure_result(
                        "atomic_commit_failed",
                        "Failed to write materialized pointer",
                        context={"name": name, "path": substituted_pointer_path, "error": str(exc)},
                    )
                pointer_map[name] = resolved_pointer.relative_to(self.workspace).as_posix()

            artifacts[name] = value

        result: Dict[str, Any] = {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": artifacts,
        }
        if pointer_map:
            result["debug"] = {"materialize_artifacts": {"pointers": pointer_map}}
        return result

    def _execute_select_variant_output(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Dict[str, Any]:
        config = step.get("select_variant_output")
        if not isinstance(config, dict):
            return self._v214_failure_result(
                "invalid_variant_bundle",
                "select_variant_output config must be a dictionary",
            )
        evidence = config.get("evidence")
        mode = evidence.get("mode") if isinstance(evidence, dict) else None
        if mode != "snapshot_diff":
            return self._v214_failure_result(
                "snapshot_ref_not_snapshot_diff",
                "select_variant_output requires evidence.mode 'snapshot_diff'",
                context={"mode": mode},
            )
        snapshot_ref = (
            evidence.get("snapshot", {}).get("ref")
            if isinstance(evidence, dict) and isinstance(evidence.get("snapshot"), dict)
            else None
        )
        if not isinstance(snapshot_ref, str):
            return self._v214_failure_result(
                "snapshot_state_missing",
                "select_variant_output requires evidence.snapshot.ref",
            )
        snapshot_state, resolve_error = self._resolve_ref_value(snapshot_ref, state)
        if resolve_error is not None:
            return resolve_error
        if not isinstance(snapshot_state, dict):
            return self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot ref did not resolve to snapshot state",
                context={"ref": snapshot_ref},
            )
        snapshot_record, snapshot_error = self._inflate_snapshot_record(snapshot_state)
        if snapshot_error is not None or snapshot_record is None:
            return snapshot_error or self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot record is unavailable",
            )
        if snapshot_record.get("schema") != "snapshot_diff/v1" or snapshot_record.get("digest") != "sha256":
            return self._v214_failure_result(
                "snapshot_ref_not_snapshot_diff",
                "Snapshot ref must resolve to snapshot_diff/v1 evidence with sha256 digests",
                context={
                    "ref": snapshot_ref,
                    "schema": snapshot_record.get("schema"),
                    "digest": snapshot_record.get("digest"),
                },
            )

        max_bytes = snapshot_record.get("max_bytes_per_candidate", 16 * 1024 * 1024)
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            max_bytes = 16 * 1024 * 1024

        candidates = snapshot_record.get("candidates")
        if not isinstance(candidates, dict) or not candidates:
            return self._v214_failure_result(
                "snapshot_state_missing",
                "Snapshot record has no candidates",
            )
        variants = config.get("variants", {})
        variant_keys = sorted(str(key) for key in variants.keys()) if isinstance(variants, dict) else []
        candidate_keys = sorted(str(key) for key in candidates.keys())
        if variant_keys != candidate_keys:
            return self._v214_failure_result(
                "snapshot_ref_candidate_mismatch",
                "Snapshot candidate keys do not match select_variant_output variants",
                context={
                    "ref": snapshot_ref,
                    "candidate_keys": candidate_keys,
                    "variant_keys": variant_keys,
                },
            )

        current_candidates: Dict[str, Dict[str, Any]] = {}
        changed: List[str] = []
        for candidate_key in sorted(candidates.keys()):
            candidate_state = candidates.get(candidate_key)
            if not isinstance(candidate_state, dict):
                continue
            current_entry, current_error = self._capture_file_snapshot(
                str(candidate_state.get("path", "")),
                max_bytes_per_candidate=max_bytes,
            )
            if current_error is not None or current_entry is None:
                return current_error or self._v214_failure_result(
                    "snapshot_candidate_invalid",
                    "Current snapshot candidate could not be captured",
                    context={"candidate": candidate_key},
                )
            current_candidates[candidate_key] = current_entry
            before_exists = bool(candidate_state.get("exists"))
            after_exists = bool(current_entry.get("exists"))
            before_sha = candidate_state.get("sha256")
            after_sha = current_entry.get("sha256")
            if (not before_exists and after_exists) or (before_exists and after_exists and before_sha != after_sha):
                changed.append(candidate_key)

        if not changed:
            return self._v214_failure_result(
                "snapshot_candidate_unchanged",
                "No snapshot candidates changed",
                context={"candidate_keys": sorted(candidates.keys())},
            )
        if len(changed) > 1:
            return self._v214_failure_result(
                "snapshot_candidate_ambiguous",
                "Multiple snapshot candidates changed",
                context={
                    "candidate_keys": sorted(candidates.keys()),
                    "changed_candidate_keys": changed,
                },
            )

        selected_variant = changed[0]
        discriminant = config.get("discriminant")
        discriminant_name = (
            discriminant.get("name")
            if isinstance(discriminant, dict) and isinstance(discriminant.get("name"), str)
            else None
        )
        if discriminant_name is None:
            return self._v214_failure_result(
                "variant_discriminant_missing",
                "select_variant_output requires a discriminant definition",
            )

        bundle_payload: Dict[str, Any] = {discriminant_name: selected_variant}
        selected_config = variants.get(selected_variant) if isinstance(variants, dict) else None
        if not isinstance(selected_config, dict):
            return self._v214_failure_result(
                "variant_discriminant_invalid",
                "Selected variant does not exist in select_variant_output",
                context={"selected_variant": selected_variant},
            )
        fields = selected_config.get("fields", [])
        candidate_path = current_candidates[selected_variant]["path"]
        extract_config = config.get("extract")
        for field_spec in fields if isinstance(fields, list) else []:
            if not isinstance(field_spec, dict):
                continue
            field_name = field_spec.get("name")
            if not isinstance(field_name, str):
                continue
            if field_spec.get("type") == "relpath":
                bundle_payload[field_name] = candidate_path
                continue
            if isinstance(extract_config, dict) and extract_config.get("from") == "candidate_path":
                prefix = extract_config.get("line_prefix")
                strip_chars = extract_config.get("strip", [])
                try:
                    text = (self.workspace / candidate_path).read_text(encoding="utf-8")
                except OSError as exc:
                    return self._v214_failure_result(
                        "variant_extractor_failed",
                        "Failed to read candidate file for extraction",
                        context={"path": candidate_path, "error": str(exc)},
                    )
                matched_value = None
                for line in text.splitlines():
                    if isinstance(prefix, str) and line.startswith(prefix):
                        matched_value = line[len(prefix):].strip()
                        break
                if matched_value is None:
                    return self._v214_failure_result(
                        "variant_extractor_failed",
                        "Variant extractor did not find the requested line prefix",
                        context={"path": candidate_path, "line_prefix": prefix},
                    )
                if isinstance(strip_chars, list):
                    for raw_strip in strip_chars:
                        if isinstance(raw_strip, str):
                            matched_value = matched_value.replace(raw_strip, "")
                bundle_payload[field_name] = matched_value.strip()

        bundle_path_raw = config.get("path")
        if not isinstance(bundle_path_raw, str):
            return self._v214_failure_result(
                "invalid_variant_bundle",
                "select_variant_output requires a bundle path",
            )
        substituted_bundle_path, bundle_path_error = self._substitute_path_template(
            bundle_path_raw,
            state,
            step_name=step.get("name", "<unnamed>"),
            field_name="select_variant_output.path",
        )
        if bundle_path_error is not None or substituted_bundle_path is None:
            return bundle_path_error or self._v214_failure_result(
                "unsafe_path",
                "select_variant_output bundle path substitution failed",
                context={"path": bundle_path_raw},
            )
        bundle_path = self._resolve_workspace_path(substituted_bundle_path)
        if bundle_path is None:
            return self._v214_failure_result(
                "unsafe_path",
                "select_variant_output bundle path escapes the workspace",
                context={"path": substituted_bundle_path},
            )
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = bundle_path.parent / f".{bundle_path.name}.tmp-{os.getpid()}-{time.time_ns()}"
        payload = json.dumps(bundle_payload, sort_keys=True, ensure_ascii=True) + "\n"
        temp_path.write_text(payload, encoding="utf-8")

        validation_contract = deepcopy(config)
        validation_contract["path"] = temp_path.relative_to(self.workspace).as_posix()
        try:
            artifacts = validate_variant_output_bundle(validation_contract, workspace=self.workspace)
        except OutputContractError as exc:
            temp_path.unlink(missing_ok=True)
            return self._v214_failure_result(
                "bundle_commit_aborted_invalid_candidate",
                "Selected variant bundle failed validation",
                context={"violations": exc.violations, "selected_variant": selected_variant},
            )

        try:
            os.replace(temp_path, bundle_path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            return self._v214_failure_result(
                "atomic_commit_failed",
                "Failed to atomically commit the selected variant bundle",
                context={"path": bundle_path_raw, "error": str(exc)},
            )

        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": artifacts,
            "debug": {
                "select_variant_output": {
                    "selected_variant": selected_variant,
                    "changed_candidate_keys": changed,
                }
            },
        }

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

    def _execute_pure_projection(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        config = step.get("pure_projection")
        if not isinstance(config, dict):
            return self._contract_violation_result(
                "Pure projection execution failed",
                {"reason": "missing_pure_projection_config"},
            )
        payload = config.get("payload")
        binding_refs = config.get("binding_refs")
        payload_digest = config.get("payload_digest")
        output_contracts = config.get("output_contracts")
        if not isinstance(payload, dict) or not isinstance(binding_refs, dict) or not isinstance(payload_digest, str):
            return self._contract_violation_result(
                "Pure projection execution failed",
                {"reason": "invalid_pure_projection_config"},
            )
        resolved_expected_outputs, resolved_output_bundle, path_error = self._resolve_output_contract_paths(
            step,
            state,
            context=scope,
        )
        if path_error is not None:
            return path_error
        bundle_path = None
        if isinstance(resolved_output_bundle, dict):
            raw_path = resolved_output_bundle.get("path")
            if isinstance(raw_path, str) and raw_path:
                bundle_path = (self.workspace / raw_path).resolve()
        if bundle_path is not None:
            bundle_parent_error = self._prepare_runtime_output_bundle_parent(resolved_output_bundle)
            if bundle_parent_error is not None:
                return bundle_parent_error
            reused_result, reuse_error = self._reuse_pure_projection_bundle(
                bundle_path=bundle_path,
                payload=payload,
                payload_digest=payload_digest,
            )
            if reuse_error is not None:
                return reuse_error
            if reused_result is not None:
                try:
                    artifacts = self._pure_projection_artifacts(
                        reused_result,
                        output_contracts=output_contracts,
                    )
                except OutputContractError as exc:
                    return self._contract_violation_result(
                        "Pure projection execution failed",
                        {"reason": "invalid_reused_pure_projection_result", "violations": exc.violations},
                    )
                return {
                    "status": "completed",
                    "exit_code": 0,
                    "duration_ms": 0,
                    "artifacts": artifacts,
                    "debug": {"pure_projection": {"reused_bundle": True}},
                }
        resolved_bindings, binding_error = self._resolve_pure_projection_bindings(
            binding_refs,
            state,
            scope=scope,
        )
        if binding_error is not None:
            return binding_error
        try:
            result_value = evaluate_pure_expr(payload, resolved_bindings=resolved_bindings)
            artifacts = self._pure_projection_artifacts(
                result_value,
                output_contracts=output_contracts,
            )
        except OutputContractError as exc:
            return self._contract_violation_result(
                "Pure projection execution failed",
                {"reason": "pure_projection_contract_invalid", "violations": exc.violations},
            )
        except PureExprEvaluationError as exc:
            context: Dict[str, Any] = {"error": str(exc)}
            if exc.metadata:
                context["metadata"] = exc.metadata
            if exc.source is not None:
                context["source"] = exc.source
            return self._v214_failure_result(
                exc.code,
                str(exc),
                context=context,
            )
        except Exception as exc:
            return self._v214_failure_result(
                "pure_projection_failed",
                "Pure projection evaluation failed",
                context={"error": str(exc)},
            )
        if bundle_path is not None:
            bundle_record = {
                "pure_expr_schema_version": payload.get("pure_expr_schema_version"),
                "payload_digest": payload_digest,
                "result": result_value,
            }
            self._atomic_write_text(bundle_path, canonical_json_for_pure_value(bundle_record))
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": artifacts,
            "debug": {"pure_projection": {"reused_bundle": False}},
        }

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

    def _resolve_pure_projection_bindings(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> tuple[Any, Optional[Dict[str, Any]]]:
        if isinstance(value, dict):
            if set(value) == {"ref"} and isinstance(value.get("ref"), str):
                return self._resolve_ref_value(value["ref"], state, scope=scope)
            resolved: dict[str, Any] = {}
            for key, item in value.items():
                resolved_item, error = self._resolve_pure_projection_bindings(item, state, scope=scope)
                if error is not None:
                    return None, error
                resolved[str(key)] = resolved_item
            return resolved, None
        if isinstance(value, list):
            resolved_list: list[Any] = []
            for item in value:
                resolved_item, error = self._resolve_pure_projection_bindings(item, state, scope=scope)
                if error is not None:
                    return None, error
                resolved_list.append(resolved_item)
            return resolved_list, None
        return value, None

    def _reuse_pure_projection_bundle(
        self,
        *,
        bundle_path: Path,
        payload: Mapping[str, Any],
        payload_digest: str,
    ) -> tuple[Any | None, Optional[Dict[str, Any]]]:
        if not bundle_path.exists():
            return None, None
        try:
            bundle_record = json.loads(bundle_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return None, self._v214_failure_result(
                "pure_projection_resume_invalid",
                "Pure projection bundle could not be loaded during resume",
                context={"path": str(bundle_path), "error": str(exc)},
            )
        if not isinstance(bundle_record, dict):
            return None, self._v214_failure_result(
                "pure_projection_resume_invalid",
                "Pure projection bundle must decode to an object",
                context={"path": str(bundle_path)},
            )
        if bundle_record.get("pure_expr_schema_version") != payload.get("pure_expr_schema_version"):
            return None, self._v214_failure_result(
                "pure_projection_resume_schema_mismatch",
                "Pure projection resume bundle schema version does not match the current payload",
                context={"path": str(bundle_path)},
            )
        if bundle_record.get("payload_digest") != payload_digest:
            return None, self._v214_failure_result(
                "pure_projection_resume_digest_mismatch",
                "Pure projection resume bundle payload digest does not match the current payload",
                context={"path": str(bundle_path)},
            )
        return bundle_record.get("result"), None

    def _pure_projection_artifacts(
        self,
        result_value: Any,
        *,
        output_contracts: Any,
    ) -> Dict[str, Any]:
        if not isinstance(output_contracts, dict):
            raise OutputContractError([{"message": "pure projection output contracts must be an object"}])
        artifacts: dict[str, Any] = {}
        for output_name, contract in output_contracts.items():
            if not isinstance(output_name, str) or not isinstance(contract, dict):
                continue
            if output_name == "return":
                candidate = result_value
            elif output_name == "return__variant":
                candidate = result_value.get("variant") if isinstance(result_value, dict) else None
            else:
                candidate = result_value
                for field_name in output_name.removeprefix("return__").split("__"):
                    if not isinstance(candidate, dict):
                        candidate = None
                        break
                    candidate = candidate.get(field_name)
            artifacts[output_name] = validate_contract_value(candidate, contract, workspace=self.workspace)
        return artifacts

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
