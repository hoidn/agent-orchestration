"""Structural runtime contracts for extracted loop and call executors.

The measured loop and call executor surfaces share four members: ``_step_id``,
``current_step``, ``debug``, and ``state_manager``.  The overlap is 4/27 loop
members and 4/15 call members, so both ratios are below one third and separate
protocols preserve the narrower dependency boundaries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol, runtime_checkable

from ..state import ForEachState, RunState, StepResult
from ..variables.substitution import VariableSubstitutor
from .executable_ir import ExecutableNode, ExecutableTransfer, ExecutableWorkflow
from .loaded_bundle import LoadedWorkflowBundle
from .runtime_context import RuntimeContext
from .runtime_step import RuntimeStep
from .state_projection import WorkflowStateProjection
from .surface_ast import PrivateExecContextBinding


RuntimeStepInput = Dict[str, Any] | RuntimeStep


class LoopStateManager(Protocol):
    """State persistence surface used directly by loop orchestration."""

    def backup_state(self, step_name: str) -> None: ...

    def clear_loop_step(self, loop_name: str, index: int, step_name: str) -> None: ...

    def load(self) -> RunState: ...

    def update_for_each(self, loop_name: str, state: ForEachState) -> None: ...

    def update_loop_results(
        self,
        loop_name: str,
        loop_results: List[Dict[str, Any]],
    ) -> None: ...

    def update_loop_step(
        self,
        loop_name: str,
        index: int,
        step_name: str,
        result: StepResult,
    ) -> None: ...

    def update_repeat_until_state(
        self,
        loop_name: str,
        progress: Dict[str, Any],
        frame_result: Optional[Dict[str, Any]] = None,
    ) -> None: ...


class CallStateManager(Protocol):
    """State identity and checksum surface used directly by call orchestration."""

    @property
    def run_id(self) -> str: ...

    def calculate_checksum(self, file_path: Path, /) -> str: ...


class ParentCallStateManager(CallStateManager, Protocol):
    """Parent persistence surface needed to host a nested call frame."""

    @property
    def run_root(self) -> Path: ...

    @property
    def workspace(self) -> Path: ...

    def read_runtime_sidecar_json(
        self,
        path: Path | str,
    ) -> Optional[Dict[str, Any]]: ...

    def update_call_frame(
        self,
        frame_id: str,
        frame_state: Dict[str, Any],
    ) -> None: ...

    def workflow_lisp_checkpoint_shadow_report_path(self) -> Path: ...

    def write_runtime_sidecar_json(
        self,
        path: Path | str,
        payload: Dict[str, Any],
    ) -> None: ...


@runtime_checkable
class CallFrameStateManager(ParentCallStateManager, Protocol):
    """Runtime-checkable child manager carrying its structural frame identity."""

    @property
    def frame_id(self) -> str: ...


class LoopRuntime(Protocol):
    """Workflow runtime surface consumed by :class:`LoopExecutor`."""

    @property
    def current_step(self) -> int: ...

    @property
    def debug(self) -> bool: ...

    @property
    def executable_ir(self) -> ExecutableWorkflow: ...

    @property
    def projection(self) -> Optional[WorkflowStateProjection]: ...

    @property
    def state_manager(self) -> LoopStateManager: ...

    @property
    def variable_substitutor(self) -> VariableSubstitutor: ...

    @property
    def variables(self) -> Mapping[str, Any]: ...

    @property
    def workflow_context_defaults(self) -> Mapping[str, Any]: ...

    def _attach_outcome(
        self,
        step: RuntimeStepInput,
        result: Dict[str, Any],
        phase_hint: Optional[str] = None,
        class_hint: Optional[str] = None,
        retryable_hint: Optional[bool] = None,
    ) -> Dict[str, Any]: ...

    def _emit_lexical_checkpoint_shadow_after_repeat_until_commit(
        self,
        step: RuntimeStepInput,
        progress: Dict[str, Any],
    ) -> None: ...

    def _enforce_consumes_contract(
        self,
        step: RuntimeStepInput,
        step_name: str,
        state: Dict[str, Any],
        runtime_step_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]: ...

    def _evaluate_condition_expression(
        self,
        condition: Any,
        variables: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool: ...

    def _executable_node_for_step(
        self,
        step: RuntimeStepInput,
    ) -> Optional[ExecutableNode]: ...

    def _execute_nested_loop_step(
        self,
        step: RuntimeStepInput,
        context: Dict[str, Any],
        state: Dict[str, Any],
        iteration_state: Dict[str, Any],
        parent_scope_steps: Dict[str, Any],
        *,
        loop_step: Optional[RuntimeStepInput] = None,
        parent_scope_node_results: Optional[Dict[str, Any]] = None,
        runtime_step_id: Optional[str] = None,
        loop_name: Optional[str] = None,
        iteration_index: Optional[int] = None,
    ) -> Dict[str, Any]: ...

    def _finalize_consumes(
        self,
        step: RuntimeStepInput,
        step_name: str,
        state: Dict[str, Any],
        *,
        succeeded: bool,
        runtime_step_id: Optional[str] = None,
    ) -> None: ...

    def _implicit_typed_transfer_for_result(
        self,
        current_node_id: str,
        *,
        skipped: bool,
    ) -> Optional[ExecutableTransfer]: ...

    def _record_step_error(
        self,
        state: Dict[str, Any],
        step_name: str,
        exit_code: int,
        error: Dict[str, Any],
    ) -> Dict[str, Any]: ...

    def _repeat_until_condition(self, step: RuntimeStepInput) -> Any: ...

    def _repeat_until_output_contracts(
        self,
        step: RuntimeStepInput,
    ) -> Mapping[str, Any]: ...

    def _resolve_structured_output_artifacts(
        self,
        outputs: Mapping[str, Any],
        state: Dict[str, Any],
        *,
        failure_message: str,
        selection_key: str,
        selection_value: str,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]: ...

    def _restore_overlay_loop_frame(
        self,
        loop_name: str,
    ) -> Optional[Dict[str, Any]]: ...

    def _resume_entry_is_terminal(self, entry: Any) -> bool: ...

    def _runtime_context(
        self,
        context: Optional[Dict[str, Any]],
        state: Dict[str, Any],
        *,
        default_context: Optional[Dict[str, Any]] = None,
        parent_steps: Optional[Dict[str, Any]] = None,
    ) -> RuntimeContext: ...

    def _runtime_step_for_node_id(
        self,
        node_id: str,
        *,
        presentation_name: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> RuntimeStep: ...

    def _step_id(
        self,
        step: RuntimeStepInput,
        fallback_index: Optional[int] = None,
    ) -> str: ...

    def _structured_guard_condition(
        self,
        step: RuntimeStepInput,
    ) -> tuple[Any, bool]: ...

    def _when_condition(self, step: RuntimeStepInput) -> Any: ...


class CallRuntime(Protocol):
    """Workflow runtime surface consumed by :class:`CallExecutor`."""

    @property
    def current_step(self) -> int: ...

    @property
    def debug(self) -> bool: ...

    @property
    def loaded_bundle(self) -> Optional[LoadedWorkflowBundle]: ...

    @property
    def max_retries(self) -> int: ...

    @property
    def observability(self) -> Dict[str, Any]: ...

    @property
    def resume_mode(self) -> bool: ...

    @property
    def retry_delay_ms(self) -> int: ...

    @property
    def state_manager(self) -> ParentCallStateManager: ...

    @property
    def step_heartbeat_interval_sec(self) -> float: ...

    @property
    def stream_output(self) -> bool: ...

    @property
    def workspace(self) -> Path: ...

    def _call_input_bindings(
        self,
        step: RuntimeStepInput,
    ) -> Mapping[str, Any]: ...

    def _private_exec_context_binding_value(
        self,
        *,
        binding: PrivateExecContextBinding,
        input_name: str,
        contract: Optional[Mapping[str, Any]] = None,
        bound_inputs: Optional[Mapping[str, Any]] = None,
    ) -> Any: ...

    def _resolve_runtime_value(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Any: ...

    def _step_id(
        self,
        step: RuntimeStepInput,
        fallback_index: Optional[int] = None,
    ) -> str: ...
