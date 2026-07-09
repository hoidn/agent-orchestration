"""Call orchestration helpers for workflow execution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..contracts.output_contract import OutputContractError, validate_contract_value
from .executable_ir import (
    BlockOutputAddress,
    CallOutputAddress,
    NodeResultAddress,
    LoopOutputAddress,
    WorkflowInputAddress,
)
from .executor_runtime import CallFrameStateManager, CallRuntime, RuntimeStepInput
from .loaded_bundle import (
    workflow_boundary_projection,
    workflow_bundle,
    workflow_generated_path_allocations,
    workflow_import_bundle,
    workflow_import_metadata,
    workflow_managed_write_root_inputs,
    workflow_provenance,
    workflow_runtime_input_contracts,
    workflow_runtime_context_inputs,
)
from .predicates import PredicateEvaluationError
from .references import ReferenceResolutionError
from . import step_results


class CallExecutor:
    """Extract nested workflow call orchestration from WorkflowExecutor."""

    def __init__(self, executor: CallRuntime) -> None:
        self.executor = executor

    @staticmethod
    def _is_workflow_lisp_target(workflow: Any) -> bool:
        provenance = workflow_provenance(workflow)
        workflow_path = getattr(provenance, "workflow_path", None)
        if isinstance(workflow_path, Path) and workflow_path.suffix == ".orc":
            return True
        return False

    @staticmethod
    def _retry_frame_id(frame_id: str, call_frames: Mapping[str, Any]) -> str:
        retry_index = 1
        while True:
            candidate = f"{frame_id}::retry::{retry_index}"
            if candidate not in call_frames:
                return candidate
            retry_index += 1

    @staticmethod
    def _retry_family_base(frame_id: str) -> str:
        marker = "::retry::"
        if marker not in frame_id:
            return frame_id
        return frame_id.split(marker, 1)[0]

    @classmethod
    def _is_failed_retry_family_frame(
        cls,
        *,
        frame_id: str,
        prior_frame_id: str,
        prior_frame: Mapping[str, Any],
    ) -> bool:
        if prior_frame.get("status") != "failed":
            return False
        if "::retry::" not in frame_id:
            return False
        return cls._retry_family_base(frame_id) == cls._retry_family_base(prior_frame_id)

    @staticmethod
    def _source_ref_for_address(bundle: Any, address: Any) -> Optional[str]:
        """Render a stable compatibility ref string from one bound output address."""
        projection = getattr(bundle, "projection", None)
        if isinstance(address, WorkflowInputAddress):
            return f"inputs.{address.input_name}"
        if projection is None:
            return None
        if isinstance(address, NodeResultAddress):
            presentation_key = projection.presentation_key_by_node_id.get(address.node_id)
            if not isinstance(presentation_key, str) or not presentation_key:
                return None
            if address.field == "exit_code":
                return f"root.steps.{presentation_key}.exit_code"
            if address.member is None:
                return f"root.steps.{presentation_key}.{address.field}"
            return f"root.steps.{presentation_key}.{address.field}.{address.member}"
        if isinstance(address, (BlockOutputAddress, LoopOutputAddress, CallOutputAddress)):
            presentation_key = projection.presentation_key_by_node_id.get(address.node_id)
            if not isinstance(presentation_key, str) or not presentation_key:
                return None
            return f"root.steps.{presentation_key}.artifacts.{address.output_name}"
        return None

    @staticmethod
    def _source_provenance_for_output(bundle: Any, output_name: str) -> Optional[Dict[str, Any]]:
        """Return canonical export provenance from typed output contracts when available."""
        ir = getattr(bundle, "ir", None)
        projection = getattr(bundle, "projection", None)
        if ir is None or projection is None:
            return None
        output_contract = ir.outputs.get(output_name)
        if output_contract is None:
            return None
        source_address = output_contract.source_address
        source_ref = CallExecutor._source_ref_for_address(bundle, source_address)
        if source_ref is None:
            return None

        provenance: Dict[str, Any] = {"source_ref": source_ref}
        if isinstance(
            source_address,
            (NodeResultAddress, BlockOutputAddress, LoopOutputAddress, CallOutputAddress),
        ):
            projection_entry = projection.entries_by_node_id.get(source_address.node_id)
            if projection_entry is not None:
                provenance["source_step_name"] = projection_entry.presentation_key
                provenance["source_step_id"] = projection_entry.step_id
        return provenance

    def frame_id(self, step: RuntimeStepInput, state: Dict[str, Any]) -> str:
        """Derive a durable call-frame id from the authored call step and visit count."""
        return self.frame_id_with_overrides(step, state)

    def frame_id_with_overrides(
        self,
        step: RuntimeStepInput,
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
        frame_id = f"{effective_step_id}::visit::{visit_count}"
        state_manager = self.executor.state_manager
        parent_frame_id = (
            state_manager.frame_id
            if isinstance(state_manager, CallFrameStateManager)
            else None
        )
        if isinstance(parent_frame_id, str) and parent_frame_id:
            return f"{parent_frame_id}.{frame_id}"
        return frame_id

    def resolve_bound_inputs(
        self,
        step: RuntimeStepInput,
        imported_workflow: Any,
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
            return None, step_results.contract_violation_result(
                "Call input binding failed",
                {
                    "step": step.get("name", f"step_{self.executor.current_step}"),
                    "reason": "invalid_with_bindings",
                },
            )

        input_specs = workflow_runtime_input_contracts(imported_workflow)

        bound_inputs: Dict[str, Any] = {}
        for input_name, input_spec in input_specs.items():
            if not isinstance(input_spec, Mapping):
                continue

            if input_name in bindings:
                raw_value = bindings[input_name]
                try:
                    raw_value = self.executor._resolve_runtime_value(raw_value, state, scope=scope)
                except (PredicateEvaluationError, ReferenceResolutionError) as exc:
                    return None, step_results.contract_violation_result(
                        "Call input binding failed",
                        {
                            "step": step_name_override or step.get("name", f"step_{self.executor.current_step}"),
                            "input": input_name,
                            "reason": "unresolved_ref",
                            "ref": step_results.json_safe_runtime_value(raw_value),
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
                    return None, step_results.contract_violation_result(
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
                return None, step_results.contract_violation_result(
                    "Call input binding failed",
                    {
                        "step": step_name_override or step.get("name", f"step_{self.executor.current_step}"),
                        "input": input_name,
                        "reason": "missing_required_input",
                    },
                )

        return bound_inputs, None

    def _managed_write_root_allocations(
        self,
        *,
        step: RuntimeStepInput,
        imported_workflow: Any,
    ) -> Dict[str, Any]:
        allocations: Dict[str, Any] = {}
        call_alias = step.get("call")
        if isinstance(call_alias, str):
            import_metadata = workflow_import_metadata(self.executor.loaded_bundle, call_alias)
            if import_metadata is not None:
                for allocation in import_metadata.generated_path_allocations:
                    input_name = getattr(allocation, "generated_input_name", None)
                    if isinstance(input_name, str) and input_name:
                        allocations.setdefault(input_name, allocation)
        for allocation in workflow_generated_path_allocations(imported_workflow):
            input_name = getattr(allocation, "generated_input_name", None)
            if isinstance(input_name, str) and input_name:
                allocations.setdefault(input_name, allocation)
        return allocations

    def _managed_write_root_value(
        self,
        *,
        frame_id: str,
        input_name: str,
        imported_workflow: Any,
        contract: Mapping[str, Any] | None,
        allocation: Any | None,
    ) -> str:
        from .call_frame_state import _path_safe_frame_scope_token

        frame_token = _path_safe_frame_scope_token(frame_id)
        workflow_name = getattr(getattr(imported_workflow, "surface", None), "name", None)
        workflow_token = (
            "".join(char if char.isalnum() else "-" for char in workflow_name).strip("-")
            if isinstance(workflow_name, str)
            else ""
        ) or "workflow"
        filename = f"{hashlib.sha1(input_name.encode('utf-8')).hexdigest()[:16]}.json"
        under_root = contract.get("under") if isinstance(contract, Mapping) else None
        if isinstance(under_root, str) and under_root:
            base_root = Path(under_root) / "workflow_lisp" / "calls"
        else:
            base_root = Path("state") / "workflow_lisp" / "calls"
        return (
            base_root
            / self.executor.state_manager.run_id
            / frame_token
            / workflow_token
            / filename
        ).as_posix()

    def finalize_bound_inputs(
        self,
        *,
        step: RuntimeStepInput,
        step_name: str,
        frame_id: str,
        imported_workflow: Any,
        bound_inputs: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        contracts = workflow_runtime_input_contracts(imported_workflow)
        finalized = dict(bound_inputs)
        allocation_by_input = self._managed_write_root_allocations(
            step=step,
            imported_workflow=imported_workflow,
        )
        for input_name in workflow_managed_write_root_inputs(imported_workflow):
            if input_name in finalized:
                continue
            contract = contracts.get(input_name, {})
            allocation = allocation_by_input.get(input_name)
            expected_value = self._managed_write_root_value(
                frame_id=frame_id,
                input_name=input_name,
                imported_workflow=imported_workflow,
                contract=contract if isinstance(contract, Mapping) else None,
                allocation=allocation,
            )
            finalized[input_name] = expected_value

        for binding in workflow_boundary_projection(imported_workflow).private_runtime_context_bindings:
            for input_name in binding.generated_input_names:
                if not isinstance(input_name, str):
                    continue
                if input_name in finalized:
                    continue
                contract = contracts.get(input_name, {})
                expected_value = self.executor._private_exec_context_binding_value(
                    binding=binding,
                    input_name=input_name,
                    contract=contract,
                    bound_inputs=finalized,
                )
                if expected_value is None and isinstance(contract, Mapping):
                    expected_value = contract.get("default")
                if expected_value is None:
                    if input_name not in finalized:
                        return None, step_results.contract_violation_result(
                            "Call input binding failed",
                            {
                                "step": step_name,
                                "reason": "call_runtime_context_binding_invalid",
                                "input": input_name,
                                "binding_id": getattr(binding, "binding_id", None),
                            },
                        )
                    continue
                finalized[input_name] = expected_value

        for input_name in workflow_runtime_context_inputs(imported_workflow):
            if input_name in finalized:
                continue
            return None, step_results.contract_violation_result(
                "Call input binding failed",
                {
                    "step": step_name,
                    "reason": "call_runtime_context_binding_invalid",
                    "input": input_name,
                    "detail": "missing_runtime_context_binding",
                },
            )

        return finalized, None

    def validate_write_root_bindings(
        self,
        *,
        step_name: str,
        step_id: str,
        frame_id: str,
        imported_workflow: Any,
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
                return step_results.contract_violation_result(
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
            if (
                prior_frame.get("call_step_id") == step_id
                and self._is_failed_retry_family_frame(
                    frame_id=frame_id,
                    prior_frame_id=prior_frame_id,
                    prior_frame=prior_frame,
                )
            ):
                continue

            prior_alias = prior_frame.get("import_alias")
            prior_bundle = (
                workflow_import_bundle(self.executor.loaded_bundle, prior_alias)
                if isinstance(prior_alias, str)
                else None
            )
            if prior_bundle is None:
                continue

            prior_managed_inputs = workflow_managed_write_root_inputs(prior_bundle)
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

                return step_results.contract_violation_result(
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
        step: RuntimeStepInput,
        imported_workflow: Any,
        child_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build observability metadata for one executed call frame."""
        from .call_frame_state import _display_workflow_path

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
        imported_bundle = workflow_bundle(imported_workflow)
        workflow_outputs = child_state.get("workflow_outputs", {})
        if isinstance(workflow_outputs, dict):
            for output_name in workflow_outputs:
                if not isinstance(output_name, str):
                    continue
                export_entry = (
                    self._source_provenance_for_output(imported_bundle, output_name)
                    if imported_bundle is not None
                    else None
                )
                if export_entry is None:
                    export_entry = {}
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

    def resume_bound_input_mismatch_result(
        self,
        *,
        error_type: str,
        step_name: str,
        call_alias: Any,
        frame_id: str,
        input_name: str,
        persisted_value: Any = None,
        expected_value: Any = None,
        detail: Optional[str] = None,
    ) -> Dict[str, Any]:
        message_by_type = {
            "call_resume_bound_input_missing": "Called workflow is missing persisted bound inputs required for resume",
            "call_resume_bound_input_mismatch": "Called workflow bound inputs changed since the run started",
            "call_resume_bound_input_extra": "Called workflow persisted unexpected bound inputs for resume",
            "call_resume_bound_input_unknown": "Called workflow persisted unsupported hidden inputs for resume",
        }
        return {
            "status": "failed",
            "exit_code": 2,
            "duration_ms": 0,
            "error": {
                "type": error_type,
                "message": message_by_type.get(
                    error_type,
                    "Called workflow bound inputs failed resume validation",
                ),
                "context": {
                    "step": step_name,
                    "call": call_alias,
                    "call_frame_id": frame_id,
                    "input": input_name,
                    "persisted": step_results.json_safe_runtime_value(persisted_value),
                    "expected": step_results.json_safe_runtime_value(expected_value),
                    "detail": detail,
                },
            },
        }

    def validate_resume_bound_inputs(
        self,
        *,
        step_name: str,
        call_alias: Any,
        frame_id: str,
        imported_workflow: Any,
        existing_frame: Optional[Dict[str, Any]],
        expected_bound_inputs: Dict[str, Any],
    ) -> tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        validation_payload = {
            "status": "fresh",
            "diagnostics": [],
        }
        if not getattr(self.executor, "resume_mode", False) or not isinstance(existing_frame, dict):
            return None, validation_payload

        persisted_bound_inputs = existing_frame.get("bound_inputs")
        if not isinstance(persisted_bound_inputs, dict):
            persisted_state = existing_frame.get("state")
            persisted_bound_inputs = (
                persisted_state.get("bound_inputs")
                if isinstance(persisted_state, dict)
                else None
            )
        if not isinstance(persisted_bound_inputs, dict):
            validation_payload["status"] = "missing"
            validation_payload["diagnostics"] = ["call_resume_bound_input_missing"]
            return (
                self.resume_bound_input_mismatch_result(
                    error_type="call_resume_bound_input_missing",
                    step_name=step_name,
                    call_alias=call_alias,
                    frame_id=frame_id,
                    input_name="*",
                    detail="missing_persisted_bound_inputs",
                ),
                validation_payload,
            )

        for input_name, expected_value in expected_bound_inputs.items():
            if input_name not in persisted_bound_inputs:
                validation_payload["status"] = "missing"
                validation_payload["diagnostics"] = ["call_resume_bound_input_missing"]
                return (
                    self.resume_bound_input_mismatch_result(
                        error_type="call_resume_bound_input_missing",
                        step_name=step_name,
                        call_alias=call_alias,
                        frame_id=frame_id,
                        input_name=input_name,
                        expected_value=expected_value,
                    ),
                    validation_payload,
                )
            persisted_value = persisted_bound_inputs[input_name]
            if persisted_value != expected_value:
                validation_payload["status"] = "mismatch"
                validation_payload["diagnostics"] = ["call_resume_bound_input_mismatch"]
                return (
                    self.resume_bound_input_mismatch_result(
                        error_type="call_resume_bound_input_mismatch",
                        step_name=step_name,
                        call_alias=call_alias,
                        frame_id=frame_id,
                        input_name=input_name,
                        persisted_value=persisted_value,
                        expected_value=expected_value,
                    ),
                    validation_payload,
                )

        managed_inputs = set(workflow_managed_write_root_inputs(imported_workflow))
        runtime_context_inputs = set(workflow_runtime_context_inputs(imported_workflow))
        compatibility_inputs = set(
            workflow_boundary_projection(imported_workflow).private_compatibility_bridge_inputs
        )
        known_hidden_inputs = managed_inputs | runtime_context_inputs | compatibility_inputs
        for input_name in persisted_bound_inputs:
            if input_name in expected_bound_inputs:
                continue
            detail = (
                "persisted_hidden_input_not_declared"
                if input_name in known_hidden_inputs
                else "persisted_unexpected_input"
            )
            validation_payload["status"] = "extra"
            validation_payload["diagnostics"] = ["call_resume_bound_input_extra"]
            return (
                self.resume_bound_input_mismatch_result(
                    error_type="call_resume_bound_input_extra",
                    step_name=step_name,
                    call_alias=call_alias,
                    frame_id=frame_id,
                    input_name=input_name,
                    persisted_value=persisted_bound_inputs[input_name],
                    detail=detail,
                ),
                validation_payload,
            )

        validation_payload["status"] = "reused"
        return None, validation_payload

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
        imported_workflow: Any,
        existing_frame: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Reject resumed call frames when the imported workflow checksum changed."""
        from .call_frame_state import _display_workflow_path

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
        step: RuntimeStepInput,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
        runtime_step_id: Optional[str] = None,
        step_name_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute an imported workflow inline and persist call-frame state."""
        from .call_frame_state import _CallFrameStateManager
        from .executor import WorkflowExecutor

        call_alias = step.get("call")
        imported_bundle = workflow_import_bundle(self.executor.loaded_bundle, call_alias)
        imported_target = imported_bundle
        step_name = step_name_override or step.get("name", f"step_{self.executor.current_step}")
        step_id = runtime_step_id or self.executor._step_id(step)
        if imported_target is None:
            return step_results.contract_violation_result(
                "Call execution failed",
                {
                    "step": step_name,
                    "reason": "unknown_import_alias",
                    "call": call_alias,
                },
            )

        bound_inputs, binding_error = self.resolve_bound_inputs(
            step,
            imported_target,
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

        child_resume = self.executor.resume_mode
        child_existing_frame = existing_frame if isinstance(existing_frame, dict) else None
        force_fresh_workflow_lisp_retry = (
            child_resume
            and child_existing_frame is not None
            and child_existing_frame.get("status") == "failed"
            and self._is_workflow_lisp_target(imported_target)
        )
        if force_fresh_workflow_lisp_retry:
            frame_id = self._retry_frame_id(frame_id, call_frames)
            existing_frame = None
            child_existing_frame = None
            child_resume = False

        bound_inputs, finalization_error = self.finalize_bound_inputs(
            step=step,
            step_name=step_name,
            frame_id=frame_id,
            imported_workflow=imported_target,
            bound_inputs=bound_inputs,
        )
        if finalization_error is not None:
            return finalization_error
        assert bound_inputs is not None

        write_root_error = self.validate_write_root_bindings(
            step_name=step_name,
            step_id=step_id,
            frame_id=frame_id,
            imported_workflow=imported_target,
            state=state,
            bound_inputs=bound_inputs,
        )
        if write_root_error is not None:
            return write_root_error

        checksum_error = self.validate_resume_checksum(
            step_name=step_name,
            call_alias=call_alias,
            frame_id=frame_id,
            imported_workflow=imported_target,
            existing_frame=existing_frame if isinstance(existing_frame, dict) else None,
        )
        if checksum_error is not None:
            return checksum_error

        resume_bound_input_error, resume_validation = self.validate_resume_bound_inputs(
            step_name=step_name,
            call_alias=call_alias,
            frame_id=frame_id,
            imported_workflow=imported_target,
            existing_frame=existing_frame if isinstance(existing_frame, dict) else None,
            expected_bound_inputs=bound_inputs,
        )
        if resume_bound_input_error is not None:
            return resume_bound_input_error

        child_state_manager = _CallFrameStateManager(
            parent_manager=self.executor.state_manager,
            workflow=imported_target,
            frame_id=frame_id,
            call_step_name=step_name,
            call_step_id=step_id,
            import_alias=str(call_alias),
            bound_inputs=bound_inputs,
            existing_frame=child_existing_frame,
            observability=self.executor.observability,
        )
        child_state_manager.update_bound_input_resume_validation(
            status=str(resume_validation.get("status", "fresh")),
            diagnostics=[
                str(item)
                for item in resume_validation.get("diagnostics", ())
                if isinstance(item, str)
            ],
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
        child_state = child_executor.execute(resume=child_resume)
        call_frames[frame_id] = child_state_manager._snapshot()

        debug_payload = self.build_debug_payload(
            frame_id=frame_id,
            step=step,
            imported_workflow=imported_target,
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
        else:
            workflow_outputs = dict(workflow_outputs)
        selected_variant = workflow_outputs.get("return__variant")
        if isinstance(selected_variant, str) and "variant" not in workflow_outputs:
            workflow_outputs["variant"] = selected_variant
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": workflow_outputs,
            "debug": {"call": debug_payload},
        }
