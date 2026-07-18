"""Leaf structural contract shared by adjudication runner phases."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, TypedDict

from ..exec.retry import RetryPolicy
from ..providers.executor import ProviderExecutionResult
from ..providers.registry import ProviderRegistry
from ..providers.types import ProviderInvocation, ProviderParams, ProviderSessionRequest
from .adjudication import AdjudicationDeadline, AdjudicationVisitPaths, PathSurface
from .adjudication_bindings import (
    AdjudicationBindings,
    AdjudicationExecution,
    AdjudicationSelection,
    AdjudicationStateManager,
)
from .executor_runtime import RuntimeStepInput
from .prompting import PromptComposer


Result = Dict[str, Any]


class AdjudicationFrameContext(TypedDict):
    run_root: Path
    frame_scope: str
    execution_frame_id: str
    call_frame_id: Optional[str]


class AdjudicationRuntime(Protocol):
    """Exact base and sibling surface used by adjudication phase mixins."""

    _bindings: AdjudicationBindings
    @property
    def workspace(self) -> Path: ...

    @property
    def state_manager(self) -> AdjudicationStateManager: ...

    @property
    def workflow_version(self) -> str: ...

    @property
    def provider_registry(self) -> ProviderRegistry: ...

    @property
    def prompt_composer(self) -> PromptComposer: ...

    @property
    def current_step(self) -> int: ...

    @property
    def resume_mode(self) -> bool: ...

    @property
    def max_retries(self) -> int: ...

    @property
    def retry_delay_ms(self) -> int: ...

    @property
    def global_secrets(self) -> Sequence[str]: ...

    @property
    def workflow_artifacts(self) -> Mapping[str, Any]: ...

    @property
    def private_workflow_artifacts(self) -> Mapping[str, Any]: ...

    def _step_id(
        self,
        step: RuntimeStepInput,
        fallback_index: Optional[int] = None,
    ) -> str: ...

    def _compose_provider_attempt_for_step(
        self,
        step: RuntimeStepInput,
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        workspace: Optional[Path] = None,
        output_contract_step: Optional[Dict[str, Any]] = None,
        runtime_step_id: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Result], Optional[Dict[str, Any]]]: ...

    def _contract_violation_result(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Result: ...

    def _create_provider_context(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        parent_steps: Optional[Dict[str, Any]] = None,
        self_steps: Optional[Dict[str, Any]] = None,
        root_steps: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    def _execute_provider_invocation(
        self,
        invocation: ProviderInvocation,
        *,
        cwd: Optional[Path] = None,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult: ...

    def _prepare_provider_invocation(
        self,
        provider_name: str,
        params: ProviderParams,
        context: Dict[str, Any],
        prompt_content: Optional[str] = None,
        session_request: Optional[ProviderSessionRequest] = None,
        env: Optional[Dict[str, str]] = None,
        secrets: Optional[List[str]] = None,
        timeout_sec: Optional[float] = None,
    ) -> tuple[Optional[ProviderInvocation], Optional[Dict[str, Any]]]: ...

    def _substitute_provider_params(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]: ...

    def _persist_control_flow_state(self, state: Dict[str, Any]) -> None: ...

    def _provider_env_with_runtime_output_bundle_path(
        self,
        step: RuntimeStepInput,
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, str]]: ...

    def _resolve_output_contract_paths(
        self,
        step: RuntimeStepInput,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[
        Optional[List[Dict[str, Any]]],
        Optional[Dict[str, Any]],
        Optional[Result],
    ]: ...

    def _substitute_path_template(
        self,
        path_value: str,
        state: Dict[str, Any],
        *,
        step_name: str,
        field_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[str], Optional[Result]]: ...

    def _uses_qualified_identities(self) -> bool: ...

    def _adjudication_frame_context(self) -> AdjudicationFrameContext: ...

    def _path_safe_frame_scope(self, frame_id: str) -> str: ...

    def _adjudication_timeout_value(self, raw_timeout: Any) -> Optional[float]: ...

    def _adjudication_retry_policy(self, step: Mapping[str, Any]) -> RetryPolicy: ...

    def _wait_for_adjudication_retry(
        self,
        retry_policy: RetryPolicy,
        deadline: AdjudicationDeadline,
    ) -> None: ...

    def _adjudication_deadline_expired(self, deadline: AdjudicationDeadline) -> bool: ...

    def _adjudication_required_path_surfaces(
        self,
        step: RuntimeStepInput,
    ) -> list[PathSurface]: ...

    def _adjudication_optional_path_surfaces(
        self,
        step: RuntimeStepInput,
    ) -> list[PathSurface]: ...

    def _resolve_adjudication_score_ledger_path(
        self,
        adjudicated: dict[str, Any],
        state: Dict[str, Any],
        context: Dict[str, Any],
        *,
        step_name: str,
        visit_paths: AdjudicationVisitPaths,
    ) -> Optional[Result]: ...

    def _candidate_step_from_adjudicated_step(
        self,
        step: RuntimeStepInput,
        candidate_config: Mapping[str, Any],
    ) -> Dict[str, Any]: ...

    def _candidate_state_map(
        self,
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    def _persist_adjudication_candidates(
        self,
        *,
        run_root: Path,
        frame_scope: str,
        step_id: str,
        visit_count: int,
        candidates: list[dict[str, Any]],
    ) -> None: ...

    def _output_paths_from_contract(self, step: RuntimeStepInput) -> dict[str, str]: ...

    def _promotion_destination_paths(
        self,
        step: RuntimeStepInput,
        artifacts: Mapping[str, Any],
    ) -> set[Path]: ...

    def _workflow_secret_values(self, step: RuntimeStepInput) -> list[str]: ...

    def _provider_model(self, params: Any) -> Optional[str]: ...

    def _prompt_source_metadata(
        self,
        step: Mapping[str, Any],
    ) -> tuple[Optional[str], Optional[str]]: ...

    def _stable_runtime_hash(self, payload: Any) -> str: ...

    def _text_hash(self, text: str) -> str: ...

    def _path_under(self, path: Path, root: Path) -> bool: ...

    def _reconcile_adjudication_resume(
        self,
        execution: AdjudicationExecution,
    ) -> Optional[Result]: ...

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
        visit_paths: AdjudicationVisitPaths,
    ) -> dict[str, Any]: ...

    def _resume_mismatch(
        self,
        message: str,
        *,
        visit_paths: AdjudicationVisitPaths,
        candidates: Optional[list[dict[str, Any]]] = None,
    ) -> Result: ...

    def _resolve_adjudication_scorer(
        self,
        evaluator_config: Mapping[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        visit_paths: AdjudicationVisitPaths,
        persist: bool = True,
    ) -> tuple[Optional[dict[str, Any]], str, Optional[dict[str, Any]]]: ...

    def _score_adjudicated_candidate(
        self,
        *,
        candidate: dict[str, Any],
        scorer: dict[str, Any],
        evaluator_prompt: str,
        evaluator_config: Mapping[str, Any],
        step: RuntimeStepInput,
        output_contract_step: Dict[str, Any],
        run_root: Path,
        frame_scope: str,
        step_id: str,
        visit_count: int,
        context: Dict[str, Any],
        state: Dict[str, Any],
        deadline: AdjudicationDeadline,
        retry_policy: RetryPolicy,
    ) -> None: ...

    def _resolve_provider_params_for_adjudication(
        self,
        provider_name: str,
        params: Any,
        context: Dict[str, Any],
        state: Dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]: ...

    def _adjudication_consumed_artifacts_for_prompt(
        self,
        step: RuntimeStepInput,
        state: Dict[str, Any],
        *,
        step_name: str,
        consume_identity: str,
    ) -> tuple[dict[str, Any], dict[str, str]]: ...

    def _score_adjudication_candidates(
        self,
        execution: AdjudicationExecution,
    ) -> Optional[Result]: ...

    def _write_adjudication_ledgers(
        self,
        *,
        adjudicated: Mapping[str, Any],
        visit_paths: AdjudicationVisitPaths,
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
    ) -> list[dict[str, Any]]: ...

    def _write_adjudication_ledgers_failure(
        self,
        *,
        adjudicated: Mapping[str, Any],
        visit_paths: AdjudicationVisitPaths,
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
    ) -> Optional[Result]: ...

    def _adjudication_failure_result(
        self,
        error_type: str,
        message: str,
        *,
        candidates: Optional[list[dict[str, Any]]] = None,
        visit_paths: Optional[AdjudicationVisitPaths] = None,
        selected_candidate_id: Optional[str] = None,
        selected_score: Optional[float] = None,
        selection_reason: Optional[str] = None,
        promotion_status: Optional[str] = None,
    ) -> Result: ...

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
    ) -> dict[str, Any]: ...

    def _adjudication_ledger_path_collision_message(
        self,
        *,
        adjudicated: Mapping[str, Any],
        output_contract_step: Dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> Optional[str]: ...

    def _execute_adjudication_candidates(
        self,
        execution: AdjudicationExecution,
    ) -> Optional[Result]: ...

    def _execute_single_adjudication_candidate(
        self,
        execution: AdjudicationExecution,
        *,
        index: int,
        candidate_config: Dict[str, Any],
    ) -> Optional[Result]: ...

    def _finalize_adjudication(self, execution: AdjudicationExecution) -> Result: ...

    def _select_adjudication_candidate(
        self,
        execution: AdjudicationExecution,
    ) -> AdjudicationSelection | Result: ...

    def _promote_and_validate_adjudication(
        self,
        execution: AdjudicationExecution,
        selected_state: AdjudicationSelection,
    ) -> Result: ...
