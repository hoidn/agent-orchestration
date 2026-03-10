"""Call orchestration helpers for workflow execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..contracts.output_contract import OutputContractError, validate_contract_value
from .loaded_bundle import (
    workflow_import_bundle,
    workflow_legacy_dict,
    workflow_managed_write_root_inputs,
    workflow_provenance,
)
from .predicates import PredicateEvaluationError
from .references import ReferenceResolutionError


class CallExecutor:
    """Extract nested workflow call orchestration from WorkflowExecutor."""

    def __init__(self, executor: Any) -> None:
        self.executor = executor

    def frame_id(self, step: Dict[str, Any], state: Dict[str, Any]) -> str:
        """Derive a durable call-frame id from the authored call step and visit count."""
        return self.frame_id_with_overrides(step, state)

    def frame_id_with_overrides(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        step_name: Optional[str] = None,
        step_id: Optional[str] = None,
    ) -> str:
        """Derive a durable call-frame id from an optional runtime-local step identity."""
        if getattr(self.executor, "resume_mode", False):
            call_frames = state.get("call_frames", {})
            effective_step_id = step_id or self.executor._step_id(step)
            if isinstance(call_frames, dict):
                for frame_id, frame in call_frames.items():
                    if not isinstance(frame, dict):
                        continue
                    if frame.get("call_step_id") != effective_step_id:
                        continue
                    if frame.get("status") == "completed":
                        continue
                    return frame_id

        effective_step_name = step_name or step.get("name", f"step_{self.executor.current_step}")
        step_visits = state.get("step_visits", {})
        visit_count = step_visits.get(effective_step_name, 1) if isinstance(step_visits, dict) else 1
        effective_step_id = step_id or self.executor._step_id(step)
        return f"{effective_step_id}::visit::{visit_count}"

    def resolve_bound_inputs(
        self,
        step: Dict[str, Any],
        imported_workflow: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
        step_name_override: Optional[str] = None,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Resolve call-site literal and structured-ref bindings into typed callee inputs."""
        bindings = self.executor._call_input_bindings(step)
        if bindings is None:
            bindings = {}
        if not isinstance(bindings, Mapping):
            return None, self.executor._contract_violation_result(
                "Call input binding failed",
                {
                    "step": step.get("name", f"step_{self.executor.current_step}"),
                    "reason": "invalid_with_bindings",
                },
            )

        input_specs = imported_workflow.get("inputs", {})
        if not isinstance(input_specs, dict):
            input_specs = {}

        bound_inputs: Dict[str, Any] = {}
        for input_name, input_spec in input_specs.items():
            if not isinstance(input_spec, dict):
                continue

            if input_name in bindings:
                raw_value = bindings[input_name]
                try:
                    raw_value = self.executor._resolve_runtime_value(raw_value, state, scope=scope)
                except (PredicateEvaluationError, ReferenceResolutionError) as exc:
                    return None, self.executor._contract_violation_result(
                        "Call input binding failed",
                        {
                            "step": step_name_override or step.get("name", f"step_{self.executor.current_step}"),
                            "input": input_name,
                            "reason": "unresolved_ref",
                            "ref": self.executor._json_safe_runtime_value(raw_value),
                            "error": str(exc),
                        },
                    )
                try:
                    bound_inputs[input_name] = validate_contract_value(
                        raw_value,
                        input_spec,
                        workspace=self.executor.workspace,
                    )
                except OutputContractError as exc:
                    return None, self.executor._contract_violation_result(
                        "Call input binding failed",
                        {
                            "step": step_name_override or step.get("name", f"step_{self.executor.current_step}"),
                            "input": input_name,
                            "reason": "invalid_value",
                            "violations": exc.violations,
                        },
                    )
                continue

            if "default" in input_spec:
                bound_inputs[input_name] = input_spec["default"]
                continue
            if input_spec.get("required", True):
                return None, self.executor._contract_violation_result(
                    "Call input binding failed",
                    {
                        "step": step_name_override or step.get("name", f"step_{self.executor.current_step}"),
                        "input": input_name,
                        "reason": "missing_required_input",
                    },
                )

        return bound_inputs, None

    def validate_write_root_bindings(
        self,
        *,
        step_name: str,
        frame_id: str,
        imported_workflow: Dict[str, Any],
        state: Dict[str, Any],
        bound_inputs: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Reject repeated or aliased managed write roots across call frames."""
        managed_inputs = workflow_managed_write_root_inputs(imported_workflow)
        if not managed_inputs:
            return None

        current_roots: Dict[str, str] = {}
        for input_name in managed_inputs:
            value = bound_inputs.get(input_name)
            if not isinstance(value, str):
                continue
            prior_input = current_roots.get(value)
            if prior_input is not None:
                return self.executor._contract_violation_result(
                    "Call input binding failed",
                    {
                        "step": step_name,
                        "reason": "colliding_write_root_binding",
                        "input": input_name,
                        "value": value,
                        "collides_with": {
                            "step": step_name,
                            "input": prior_input,
                        },
                    },
                )
            current_roots[value] = input_name

        call_frames = state.get("call_frames", {})
        if not isinstance(call_frames, dict) or not current_roots:
            return None

        for prior_frame_id, prior_frame in call_frames.items():
            if prior_frame_id == frame_id or not isinstance(prior_frame, dict):
                continue

            prior_alias = prior_frame.get("import_alias")
            prior_bundle = (
                workflow_import_bundle(self.executor.loaded_bundle or self.executor.workflow, prior_alias)
                if isinstance(prior_alias, str)
                else None
            )
            prior_workflow = workflow_legacy_dict(prior_bundle)
            if prior_workflow is None:
                continue

            prior_managed_inputs = workflow_managed_write_root_inputs(prior_workflow)
            prior_bound_inputs = prior_frame.get("bound_inputs")
            if not prior_managed_inputs or not isinstance(prior_bound_inputs, dict):
                continue

            for prior_input in prior_managed_inputs:
                prior_value = prior_bound_inputs.get(prior_input)
                if not isinstance(prior_value, str):
                    continue

                current_input = current_roots.get(prior_value)
                if current_input is None:
                    continue

                return self.executor._contract_violation_result(
                    "Call input binding failed",
                    {
                        "step": step_name,
                        "reason": "colliding_write_root_binding",
                        "input": current_input,
                        "value": prior_value,
                        "collides_with": {
                            "call_frame_id": prior_frame_id,
                            "step": prior_frame.get("call_step_name"),
                            "input": prior_input,
                        },
                    },
                )

        return None

    def build_debug_payload(
        self,
        *,
        frame_id: str,
        step: Dict[str, Any],
        imported_workflow: Dict[str, Any],
        child_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build observability metadata for one executed call frame."""
        from .executor import _display_workflow_path

        provenance = workflow_provenance(imported_workflow)
        workflow_path = provenance.workflow_path if provenance is not None else None
        workflow_file = (
            _display_workflow_path(self.executor.workspace, workflow_path)
            if workflow_path is not None
            else None
        )
        call_frames = child_state.get("call_frames", {})
        nested_frames = list(call_frames.keys()) if isinstance(call_frames, dict) else []
        finalization = child_state.get("finalization", {})
        exports: Dict[str, Any] = {}
        output_specs = imported_workflow.get("outputs", {})
        workflow_outputs = child_state.get("workflow_outputs", {})
        if isinstance(output_specs, dict) and isinstance(workflow_outputs, dict):
            child_steps = child_state.get("steps", {}) if isinstance(child_state.get("steps"), dict) else {}
            for output_name, output_spec in output_specs.items():
                if output_name not in workflow_outputs or not isinstance(output_spec, dict):
                    continue
                binding = output_spec.get("from")
                ref = binding.get("ref") if isinstance(binding, dict) else None
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
            "call_frame_id": frame_id,
            "import_alias": step.get("call"),
            "workflow_file": workflow_file,
            "status": child_state.get("status"),
            "finalization": finalization if isinstance(finalization, dict) else {},
            "bound_inputs": child_state.get("bound_inputs", {}),
            "workflow_outputs": workflow_outputs if isinstance(workflow_outputs, dict) else {},
            "exports": exports,
            "nested_call_frames": nested_frames,
        }

    def resume_checksum_mismatch_result(
        self,
        *,
        step_name: str,
        call_alias: Any,
        frame_id: str,
        workflow_file: Optional[str],
        persisted_checksum: Optional[str],
        current_checksum: Optional[str],
        reason: str,
    ) -> Dict[str, Any]:
        """Build a deterministic failure when nested resume checksum validation fails."""
        return {
            "status": "failed",
            "exit_code": 2,
            "duration_ms": 0,
            "error": {
                "type": "call_resume_checksum_mismatch",
                "message": "Called workflow has been modified since the run started",
                "context": {
                    "step": step_name,
                    "call": call_alias,
                    "call_frame_id": frame_id,
                    "workflow_file": workflow_file,
                    "persisted_checksum": persisted_checksum,
                    "current_checksum": current_checksum,
                    "reason": reason,
                },
            },
        }

    def validate_resume_checksum(
        self,
        *,
        step_name: str,
        call_alias: Any,
        frame_id: str,
        imported_workflow: Dict[str, Any],
        existing_frame: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Reject resumed call frames when the imported workflow checksum changed."""
        from .executor import _display_workflow_path

        if not getattr(self.executor, "resume_mode", False) or not isinstance(existing_frame, dict):
            return None

        provenance = workflow_provenance(imported_workflow)
        workflow_path = provenance.workflow_path if provenance is not None else None
        workflow_file = (
            _display_workflow_path(self.executor.workspace, workflow_path)
            if workflow_path is not None
            else None
        )
        persisted_state = existing_frame.get("state")
        persisted_checksum = (
            persisted_state.get("workflow_checksum")
            if isinstance(persisted_state, dict)
            else None
        )
        if not isinstance(persisted_checksum, str) or not persisted_checksum.startswith("sha256:"):
            return self.resume_checksum_mismatch_result(
                step_name=step_name,
                call_alias=call_alias,
                frame_id=frame_id,
                workflow_file=workflow_file,
                persisted_checksum=persisted_checksum if isinstance(persisted_checksum, str) else None,
                current_checksum=None,
                reason="missing_recorded_checksum",
            )

        if workflow_path is None:
            return self.resume_checksum_mismatch_result(
                step_name=step_name,
                call_alias=call_alias,
                frame_id=frame_id,
                workflow_file=workflow_file,
                persisted_checksum=persisted_checksum,
                current_checksum=None,
                reason="missing_workflow_path",
            )

        try:
            current_checksum = self.executor.state_manager.calculate_checksum(Path(workflow_path))
        except FileNotFoundError:
            return self.resume_checksum_mismatch_result(
                step_name=step_name,
                call_alias=call_alias,
                frame_id=frame_id,
                workflow_file=workflow_file,
                persisted_checksum=persisted_checksum,
                current_checksum=None,
                reason="workflow_unavailable",
            )
        if current_checksum != persisted_checksum:
            return self.resume_checksum_mismatch_result(
                step_name=step_name,
                call_alias=call_alias,
                frame_id=frame_id,
                workflow_file=workflow_file,
                persisted_checksum=persisted_checksum,
                current_checksum=current_checksum,
                reason="workflow_modified",
            )
        return None

    def execute_call(
        self,
        step: Dict[str, Any],
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
        runtime_step_id: Optional[str] = None,
        step_name_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute an imported workflow inline and persist call-frame state."""
        from .executor import WorkflowExecutor, _CallFrameStateManager

        call_alias = step.get("call")
        imported_bundle = workflow_import_bundle(self.executor.loaded_bundle or self.executor.workflow, call_alias)
        imported_workflow = workflow_legacy_dict(imported_bundle)
        step_name = step_name_override or step.get("name", f"step_{self.executor.current_step}")
        step_id = runtime_step_id or self.executor._step_id(step)
        if imported_workflow is None:
            return self.executor._contract_violation_result(
                "Call execution failed",
                {
                    "step": step_name,
                    "reason": "unknown_import_alias",
                    "call": call_alias,
                },
            )

        bound_inputs, binding_error = self.resolve_bound_inputs(
            step,
            imported_workflow,
            state,
            scope=scope,
            step_name_override=step_name,
        )
        if binding_error is not None:
            return binding_error
        assert bound_inputs is not None

        frame_id = self.frame_id_with_overrides(
            step,
            state,
            step_name=step_name,
            step_id=step_id,
        )
        call_frames = state.setdefault("call_frames", {})
        existing_frame = call_frames.get(frame_id) if isinstance(call_frames, dict) else None
        if not isinstance(call_frames, dict):
            call_frames = {}
            state["call_frames"] = call_frames

        write_root_error = self.validate_write_root_bindings(
            step_name=step_name,
            frame_id=frame_id,
            imported_workflow=imported_workflow,
            state=state,
            bound_inputs=bound_inputs,
        )
        if write_root_error is not None:
            return write_root_error

        checksum_error = self.validate_resume_checksum(
            step_name=step_name,
            call_alias=call_alias,
            frame_id=frame_id,
            imported_workflow=imported_workflow,
            existing_frame=existing_frame if isinstance(existing_frame, dict) else None,
        )
        if checksum_error is not None:
            return checksum_error

        child_state_manager = _CallFrameStateManager(
            parent_manager=self.executor.state_manager,
            workflow=imported_workflow,
            frame_id=frame_id,
            call_step_name=step_name,
            call_step_id=step_id,
            import_alias=str(call_alias),
            bound_inputs=bound_inputs,
            existing_frame=existing_frame if isinstance(existing_frame, dict) else None,
            observability=self.executor.observability,
        )
        child_executor = WorkflowExecutor(
            workflow=imported_bundle or imported_workflow,
            workspace=self.executor.workspace,
            state_manager=child_state_manager,
            debug=self.executor.debug,
            stream_output=self.executor.stream_output,
            max_retries=self.executor.max_retries,
            retry_delay_ms=self.executor.retry_delay_ms,
            observability=self.executor.observability,
            step_heartbeat_interval_sec=self.executor.step_heartbeat_interval_sec,
        )
        child_state = child_executor.execute(resume=self.executor.resume_mode)
        call_frames[frame_id] = child_state_manager._snapshot()

        debug_payload = self.build_debug_payload(
            frame_id=frame_id,
            step=step,
            imported_workflow=imported_workflow,
            child_state=child_state,
        )
        if child_state.get("status") != "completed":
            return {
                "status": "failed",
                "exit_code": 2,
                "duration_ms": 0,
                "error": {
                    "type": "call_failed",
                    "message": "Called workflow failed",
                    "context": {
                        "call": call_alias,
                        "call_frame_id": frame_id,
                        "workflow_file": debug_payload.get("workflow_file"),
                        "error": child_state.get("error"),
                    },
                },
                "debug": {"call": debug_payload},
            }

        workflow_outputs = child_state.get("workflow_outputs", {})
        if not isinstance(workflow_outputs, dict):
            workflow_outputs = {}
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": workflow_outputs,
            "debug": {"call": debug_payload},
        }
