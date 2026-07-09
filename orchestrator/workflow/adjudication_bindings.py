"""Typed executor bindings used by the adjudication runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence

from ..exec.retry import RetryPolicy
from ..providers.executor import ProviderExecutionResult
from ..providers.registry import ProviderRegistry
from ..providers.types import ProviderInvocation, ProviderParams, ProviderSessionRequest
from .adjudication import (
    AdjudicationDeadline,
    AdjudicationVisitPaths,
    BaselineManifest,
    CandidateRuntimePaths,
    PathSurface,
    PromotionResult,
    SelectionResult,
)
from .prompting import PromptComposer


class AdjudicationStateManager(Protocol):
    """State-manager surface read directly by adjudication."""

    run_id: str
    run_root: Path


class PrepareProviderInvocationCallback(Protocol):
    """Prepare a provider invocation with a fractional remaining deadline."""

    def __call__(
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


class SubstituteProviderParamsCallback(Protocol):
    def __call__(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]: ...


Result = Dict[str, Any]


class StepIdCallback(Protocol):
    def __call__(
        self,
        step: Dict[str, Any],
        fallback_index: Optional[int] = None,
    ) -> str: ...


class ComposeProviderPromptCallback(Protocol):
    def __call__(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        workspace: Optional[Path] = None,
        output_contract_step: Optional[Dict[str, Any]] = None,
        runtime_step_id: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Result]]: ...


class ContractViolationCallback(Protocol):
    def __call__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Result: ...


class CreateProviderContextCallback(Protocol):
    def __call__(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        parent_steps: Optional[Dict[str, Any]] = None,
        self_steps: Optional[Dict[str, Any]] = None,
        root_steps: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...


class ExecuteProviderInvocationCallback(Protocol):
    def __call__(
        self,
        invocation: ProviderInvocation,
        *,
        cwd: Optional[Path] = None,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult: ...


class ProviderEnvCallback(Protocol):
    def __call__(
        self,
        step: Dict[str, Any],
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, str]]: ...


class ResolveOutputPathsCallback(Protocol):
    def __call__(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[
        Optional[List[Dict[str, Any]]],
        Optional[Dict[str, Any]],
        Optional[Result],
    ]: ...


class SubstitutePathCallback(Protocol):
    def __call__(
        self,
        path_value: str,
        state: Dict[str, Any],
        *,
        step_name: str,
        field_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[str], Optional[Result]]: ...


class CreateBaselineCallback(Protocol):
    def __call__(
        self,
        *,
        parent_workspace: Path,
        run_root: Path,
        visit_paths: AdjudicationVisitPaths,
        workflow_checksum: str,
        resolved_consumes: Mapping[str, Any],
        required_path_surfaces: Sequence[PathSurface],
        optional_path_surfaces: Sequence[PathSurface],
    ) -> BaselineManifest: ...


class PrepareCandidateWorkspaceCallback(Protocol):
    def __call__(
        self,
        *,
        baseline_workspace: Path,
        candidate_workspace: Path,
    ) -> None: ...


class SelectCandidateCallback(Protocol):
    def __call__(
        self,
        candidates: Sequence[Mapping[str, Any]],
        *,
        require_score_for_single_candidate: bool,
    ) -> SelectionResult: ...


class MaterializeLedgerCallback(Protocol):
    def __call__(
        self,
        rows: Sequence[Mapping[str, Any]],
        path: Path,
    ) -> None: ...


class PromoteCandidateOutputsCallback(Protocol):
    def __call__(
        self,
        *,
        expected_outputs: Optional[List[Dict[str, Any]]],
        output_bundle: Optional[Dict[str, Any]],
        candidate_workspace: Path,
        parent_workspace: Path,
        baseline_manifest: BaselineManifest,
        promotion_manifest_path: Path,
        selected_candidate_id: Optional[str] = None,
    ) -> PromotionResult: ...


class ValidateExpectedOutputsCallback(Protocol):
    def __call__(
        self,
        expected_outputs: List[Dict[str, Any]],
        workspace: Path,
    ) -> Dict[str, Any]: ...


@dataclass
class AdjudicationExecution:
    """Mutable state shared by the adjudication execution phases."""

    started: float
    deadline: AdjudicationDeadline
    step: Dict[str, Any]
    context: Dict[str, Any]
    state: Dict[str, Any]
    step_name: str
    step_id: str
    adjudicated: Dict[str, Any]
    resolved_expected_outputs: Optional[List[Dict[str, Any]]]
    resolved_output_bundle: Optional[Dict[str, Any]]
    output_contract_step: Dict[str, Any]
    run_root: Path
    frame_scope: str
    execution_frame_id: str
    call_frame_id: Optional[str]
    visit_count: Any
    visit_paths: AdjudicationVisitPaths
    candidates_config: List[Any]
    evaluator_config: Dict[str, Any]
    selection_config: Dict[str, Any]
    baseline_manifest: Optional[BaselineManifest] = None
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    scorer: Optional[Dict[str, Any]] = None
    evaluator_prompt: str = ""
    scorer_failure: Optional[Dict[str, Any]] = None
    resume_state: Optional[Dict[str, Any]] = None
    resume_loaded: bool = False
    resume_baseline_only: bool = False
    candidate_configs_to_run: List[tuple[int, Dict[str, Any]]] = field(default_factory=list)
    require_single_score: bool = False
    retry_policy: Optional[RetryPolicy] = None


@dataclass(frozen=True)
class AdjudicationSelection:
    """Successful selection state handed to promotion/final validation."""

    selection: SelectionResult
    selected: Dict[str, Any]
    selected_paths: CandidateRuntimePaths
    ledger_path: Optional[str]


@dataclass(frozen=True)
class AdjudicationBindings:
    """Explicit live collaborators and callbacks for adjudication execution.

    Accessors deliberately resolve mutable executor state at call time.  The
    runner therefore cannot retain stale retry, resume, step, registry, or
    monkeypatched callback values, and it never receives the executor itself.
    """

    workspace: Callable[[], Path]
    state_manager: Callable[[], AdjudicationStateManager]
    workflow_version: Callable[[], str]
    provider_registry: Callable[[], ProviderRegistry]
    prompt_composer: Callable[[], PromptComposer]
    current_step: Callable[[], int]
    resume_mode: Callable[[], bool]
    max_retries: Callable[[], int]
    retry_delay_ms: Callable[[], int]
    global_secrets: Callable[[], Sequence[str]]
    workflow_artifacts: Callable[[], Mapping[str, Any]]
    private_workflow_artifacts: Callable[[], Mapping[str, Any]]

    step_id: StepIdCallback
    compose_provider_prompt_for_step: ComposeProviderPromptCallback
    contract_violation_result: ContractViolationCallback
    create_provider_context: CreateProviderContextCallback
    prepare_provider_invocation: PrepareProviderInvocationCallback
    substitute_provider_params: SubstituteProviderParamsCallback
    execute_provider_invocation: ExecuteProviderInvocationCallback
    persist_control_flow_state: Callable[[Dict[str, Any]], None]
    provider_env_with_runtime_output_bundle_path: ProviderEnvCallback
    resolve_output_contract_paths: ResolveOutputPathsCallback
    substitute_path_template: SubstitutePathCallback
    uses_qualified_identities: Callable[[], bool]

    # Call-time hooks preserve the executor module's established monkeypatch
    # seams while the implementations themselves live in runner modules.
    create_baseline_snapshot: CreateBaselineCallback
    prepare_candidate_workspace_from_baseline: PrepareCandidateWorkspaceCallback
    select_candidate: SelectCandidateCallback
    materialize_run_score_ledger: MaterializeLedgerCallback
    materialize_score_ledger_mirror: MaterializeLedgerCallback
    promote_candidate_outputs: PromoteCandidateOutputsCallback
    validate_expected_outputs: ValidateExpectedOutputsCallback


class AdjudicationRunnerBase:
    """Live typed view over the explicit adjudication bindings."""

    def __init__(self, bindings: AdjudicationBindings) -> None:
        self._bindings = bindings

    @property
    def workspace(self) -> Path:
        return self._bindings.workspace()

    @property
    def state_manager(self) -> AdjudicationStateManager:
        return self._bindings.state_manager()

    @property
    def workflow_version(self) -> str:
        return self._bindings.workflow_version()

    @property
    def provider_registry(self) -> ProviderRegistry:
        return self._bindings.provider_registry()

    @property
    def prompt_composer(self) -> PromptComposer:
        return self._bindings.prompt_composer()

    @property
    def current_step(self) -> int:
        return self._bindings.current_step()

    @property
    def resume_mode(self) -> bool:
        return self._bindings.resume_mode()

    @property
    def max_retries(self) -> int:
        return self._bindings.max_retries()

    @property
    def retry_delay_ms(self) -> int:
        return self._bindings.retry_delay_ms()

    @property
    def global_secrets(self) -> Sequence[str]:
        return self._bindings.global_secrets()

    @property
    def workflow_artifacts(self) -> Mapping[str, Any]:
        return self._bindings.workflow_artifacts()

    @property
    def private_workflow_artifacts(self) -> Mapping[str, Any]:
        return self._bindings.private_workflow_artifacts()

    def _step_id(
        self,
        step: Dict[str, Any],
        fallback_index: Optional[int] = None,
    ) -> str:
        return self._bindings.step_id(step, fallback_index)

    def _compose_provider_prompt_for_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        workspace: Optional[Path] = None,
        output_contract_step: Optional[Dict[str, Any]] = None,
        runtime_step_id: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[Result]]:
        return self._bindings.compose_provider_prompt_for_step(
            step,
            context,
            state,
            workspace=workspace,
            output_contract_step=output_contract_step,
            runtime_step_id=runtime_step_id,
        )

    def _contract_violation_result(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Result:
        return self._bindings.contract_violation_result(message, context)

    def _create_provider_context(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any],
        *,
        parent_steps: Optional[Dict[str, Any]] = None,
        self_steps: Optional[Dict[str, Any]] = None,
        root_steps: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._bindings.create_provider_context(
            context,
            state,
            parent_steps=parent_steps,
            self_steps=self_steps,
            root_steps=root_steps,
        )

    def _execute_provider_invocation(
        self,
        invocation: ProviderInvocation,
        *,
        cwd: Optional[Path] = None,
        session_runtime: Optional[Dict[str, Any]] = None,
    ) -> ProviderExecutionResult:
        return self._bindings.execute_provider_invocation(
            invocation,
            cwd=cwd,
            session_runtime=session_runtime,
        )

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
    ) -> tuple[Optional[ProviderInvocation], Optional[Dict[str, Any]]]:
        return self._bindings.prepare_provider_invocation(
            provider_name=provider_name,
            params=params,
            context=context,
            prompt_content=prompt_content,
            session_request=session_request,
            env=env,
            secrets=secrets,
            timeout_sec=timeout_sec,
        )

    def _substitute_provider_params(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[str]]:
        return self._bindings.substitute_provider_params(params, context)

    def _persist_control_flow_state(self, state: Dict[str, Any]) -> None:
        self._bindings.persist_control_flow_state(state)

    def _provider_env_with_runtime_output_bundle_path(
        self,
        step: Dict[str, Any],
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, str]]:
        return self._bindings.provider_env_with_runtime_output_bundle_path(
            step,
            resolved_output_bundle,
        )

    def _resolve_output_contract_paths(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]], Optional[Result]]:
        return self._bindings.resolve_output_contract_paths(step, state, context)

    def _substitute_path_template(
        self,
        path_value: str,
        state: Dict[str, Any],
        *,
        step_name: str,
        field_name: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[Optional[str], Optional[Result]]:
        return self._bindings.substitute_path_template(
            path_value,
            state,
            step_name=step_name,
            field_name=field_name,
            context=context,
        )

    def _uses_qualified_identities(self) -> bool:
        return self._bindings.uses_qualified_identities()
