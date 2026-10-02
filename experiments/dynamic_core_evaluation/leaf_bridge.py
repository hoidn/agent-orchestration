"""One closed adapter from dynamic effects to real compiled workflow leaves."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

from orchestrator.providers.types import ProviderTemplate
from orchestrator.state import StateManager
from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import (
    workflow_context,
    workflow_public_input_contracts,
)
from orchestrator.workflow.signatures import (
    WorkflowSignatureError,
    bind_workflow_inputs,
)
from orchestrator.workflow.type_descriptor import (
    transport_descriptor_for_schema,
    validate_transport_value,
)
from orchestrator.workflow_lisp.command_boundaries import CertifiedAdapterBinding, ExternalToolBinding
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    linked_module_type_environment,
)
from orchestrator.workflow_lisp.expressions import CommandResultExpr, ProviderResultExpr
from orchestrator.workflow_lisp.normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
)
from orchestrator.workflow_lisp.workflows import TypedWorkflowDef

from .program import strict_json_loads


@dataclass(frozen=True)
class _Leaf:
    operation: str
    workflow_name: str
    source_path: Path
    source_sha256: str
    bundle: Any
    typed_workflow: TypedWorkflowDef
    input_contracts: Mapping[str, Mapping[str, Any]]
    input_descriptors: Mapping[str, Mapping[str, Any]]
    result_descriptor: Mapping[str, Any]


class _GuardedWorkflowExecutor(WorkflowExecutor):
    """Use existing resolution/read owners, then hand one byte snapshot on."""

    def __init__(self, *args: Any, result_descriptor: Mapping[str, Any], operation: str, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._dynamic_result_descriptor = result_descriptor
        self._dynamic_operation = operation
        self._dynamic_location: str | None = None

    @staticmethod
    def _failed(result: Mapping[str, Any], *, cause_code: str, operation: str, run_id: str, location: str | None, validator_error: str | None = None) -> dict[str, Any]:
        failed = dict(result)
        failed["status"] = "failed"
        failed["exit_code"] = 2
        context: dict[str, Any] = {
            "operation": operation,
            "leaf_run_id": run_id,
            "location": location,
            "cause_code": cause_code,
        }
        if validator_error is not None:
            context["validator_error"] = validator_error
        failed["error"] = {
            "type": "dynamic_boundary_invalid",
            "message": "leaf result did not satisfy its declared boundary",
            "context": context,
        }
        return failed

    def _apply_expected_outputs_contract(self, step, result, state, context=None, *, document_bytes=None):
        if result.get("exit_code", 0) != 0:
            return super()._apply_expected_outputs_contract(
                step, result, state, context=context, document_bytes=document_bytes
            )

        _expected, resolved_bundle, path_error = self._resolve_output_contract_paths(
            step,
            state,
            context=context,
        )
        if path_error is not None:
            return self._failed(
                result,
                cause_code="leaf_result_path_invalid",
                operation=self._dynamic_operation,
                run_id=self.state_manager.run_id,
                location=self._dynamic_location,
            )
        bundle_path = resolved_bundle.get("path") if isinstance(resolved_bundle, Mapping) else None
        if not isinstance(bundle_path, str) or not bundle_path:
            return self._failed(
                result,
                cause_code="leaf_result_path_missing",
                operation=self._dynamic_operation,
                run_id=self.state_manager.run_id,
                location=self._dynamic_location,
            )
        try:
            captured = self.workspace_files.read(bundle_path)
        except (OSError, TypeError, ValueError):
            return self._failed(
                result,
                cause_code="leaf_result_bundle_unavailable",
                operation=self._dynamic_operation,
                run_id=self.state_manager.run_id,
                location=self._dynamic_location,
            )
        try:
            raw = strict_json_loads(captured.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError, RecursionError):
            return self._failed(
                result,
                cause_code="leaf_result_json_invalid",
                operation=self._dynamic_operation,
                run_id=self.state_manager.run_id,
                location=self._dynamic_location,
            )
        try:
            validate_transport_value(
                raw,
                self._dynamic_result_descriptor,
                allow_nested_structures=True,
            )
        except (TypeError, ValueError, RecursionError) as exc:
            return self._failed(
                result,
                cause_code="leaf_result_schema_invalid",
                operation=self._dynamic_operation,
                run_id=self.state_manager.run_id,
                location=self._dynamic_location,
                validator_error=str(exc),
            )
        return super()._apply_expected_outputs_contract(
            step,
            result,
            state,
            context=context,
            document_bytes=captured,
        )


class LeafBridge:
    """A closed set of freshly compiled provider/command leaf operations."""

    def __init__(
        self,
        *,
        source_path: Path,
        workspace: Path,
        leaves: Mapping[str, _Leaf],
        provider_templates: Sequence[ProviderTemplate],
        type_env: Any,
    ) -> None:
        self.source_path = Path(source_path).resolve()
        self.workspace = Path(workspace).resolve()
        self._leaves = MappingProxyType(dict(leaves))
        self._provider_templates = tuple(provider_templates)
        self.type_env = type_env
        self.source_sha256 = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        self.identities = MappingProxyType({
            operation: MappingProxyType({
                "workflow": leaf.workflow_name,
                "source_sha256": leaf.source_sha256,
                "result_descriptor_sha256": hashlib.sha256(
                    json.dumps(dict(leaf.result_descriptor), sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
            })
            for operation, leaf in self._leaves.items()
        })

    @classmethod
    def compile(
        cls,
        source_path: Path,
        workspace: Path,
        operations: Mapping[str, str],
        *,
        provider_externs: Mapping[str, str] | None = None,
        command_boundaries: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding] | None = None,
        provider_templates: Sequence[ProviderTemplate] = (),
    ) -> LeafBridge:
        source_path = Path(source_path).resolve()
        operation_map = dict(operations)
        if not operation_map or any(not isinstance(name, str) or not name for name in operation_map):
            raise ValueError("the trusted leaf registry must have operation identifiers")
        workflow_names = tuple(operation_map.values())
        if any(not isinstance(name, str) or not name for name in workflow_names):
            raise ValueError("trusted leaf workflow names must be non-empty strings")
        compiled = compile_stage3_entrypoint(
            source_path,
            entry_workflow=workflow_names[0],
            provider_externs=provider_externs,
            command_boundaries=command_boundaries,
            validate_shared=True,
            workspace_root=Path(workspace).resolve(),
        )
        module_name = compiled.graph.entry_module_name
        module_result = compiled.compiled_results_by_name[module_name]
        typed_by_name = {
            workflow.definition.name: workflow
            for workflow in module_result.typed_workflows
        }
        type_env = linked_module_type_environment(compiled, module_name)
        source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        leaves: dict[str, _Leaf] = {}
        for operation, workflow_name in operation_map.items():
            try:
                typed_workflow = typed_by_name[workflow_name]
                bundle = compiled.validated_bundles_by_name[workflow_name]
            except KeyError as exc:
                raise ValueError("trusted leaf must name a workflow in the compiled module") from exc
            expression = typed_workflow.typed_body.expr
            if isinstance(expression, ProviderResultExpr):
                if (
                    expression.session_artifact is not None
                    or expression.delivery is not None
                    or expression.materialization_attempts is not None
                    or expression.context_expr is not None
                    or expression.capture_context is not None
                    or expression.prompt_dependencies is not None
                ):
                    raise ValueError("provider leaf must use one ordinary fresh result")
            elif not isinstance(expression, CommandResultExpr):
                raise EvaluatedValueError(
                    "dynamic_effect_unlinked",
                    "trusted leaf must directly contain one provider or command result",
                    location="/effects",
                    metadata={"operation": operation, "workflow": workflow_name},
                )
            contracts = workflow_public_input_contracts(bundle)
            descriptors = {
                name: transport_descriptor_for_schema(schema)
                for name, schema in contracts.items()
            }
            result_descriptor = compiler_normalized_type_descriptor(
                typed_workflow.signature.return_type_ref,
                type_env=type_env,
            )
            leaves[operation] = _Leaf(
                operation=operation,
                workflow_name=workflow_name,
                source_path=source_path,
                source_sha256=source_digest,
                bundle=bundle,
                typed_workflow=typed_workflow,
                input_contracts=MappingProxyType(dict(contracts)),
                input_descriptors=MappingProxyType(descriptors),
                result_descriptor=MappingProxyType(result_descriptor),
            )
        return cls(
            source_path=source_path,
            workspace=workspace,
            leaves=leaves,
            provider_templates=provider_templates,
            type_env=type_env,
        )

    def link(self, effects: Sequence[str]) -> None:
        declared = tuple(effects)
        if len(set(declared)) != len(declared) or set(declared) != set(self._leaves):
            raise EvaluatedValueError(
                "dynamic_effect_unlinked",
                "artifact operations do not match the trusted compiled leaf registry",
                location="/effects",
                metadata={"declared_operations": declared, "registered_operations": tuple(self._leaves)},
            )

    def invoke(
        self,
        operation: str,
        inputs: Any,
        *,
        location: str,
        call_context: tuple[Any, ...],
    ) -> Mapping[str, Any]:
        leaf = self._leaves.get(operation)
        if leaf is None:
            raise EvaluatedValueError(
                "dynamic_effect_unlinked",
                "leaf operation is not in the trusted registry",
                location=location,
                metadata={"operation": operation, "call_context": call_context},
            )
        if not isinstance(inputs, Mapping):
            raise EvaluatedValueError(
                "dynamic_boundary_invalid",
                "leaf inputs must be an object keyed by public input names",
                location=location,
                metadata={"operation": operation, "call_context": call_context},
            )
        if set(inputs) != set(leaf.input_descriptors):
            raise EvaluatedValueError(
                "dynamic_boundary_invalid",
                "leaf inputs do not match the declared public inputs",
                location=location,
                metadata={
                    "operation": operation,
                    "call_context": call_context,
                    "expected_inputs": tuple(leaf.input_descriptors),
                },
            )
        normalized: dict[str, Any] = {}
        for name, descriptor in leaf.input_descriptors.items():
            try:
                normalized[name] = validate_transport_value(
                    inputs[name],
                    descriptor,
                    allow_nested_structures=True,
                )
            except (TypeError, ValueError, RecursionError) as exc:
                raise EvaluatedValueError(
                    "dynamic_boundary_invalid",
                    "leaf input does not satisfy its declared contract",
                    location=location,
                    metadata={
                        "operation": operation,
                        "call_context": call_context,
                        "validator_error": str(exc),
                    },
                ) from exc
        try:
            bound_inputs = bind_workflow_inputs(
                leaf.input_contracts,
                normalized,
                self.workspace,
                finite_floats=True,
            )
        except WorkflowSignatureError as exc:
            raise EvaluatedValueError(
                "dynamic_boundary_invalid",
                "leaf inputs were refused by the workflow boundary owner",
                location=location,
                metadata={"operation": operation, "call_context": call_context, "cause_code": exc.error["context"].get("reason")},
            ) from exc

        if hashlib.sha256(self.source_path.read_bytes()).hexdigest() != leaf.source_sha256:
            raise EvaluatedValueError(
                "dynamic_effect_failed",
                "compiled leaf source changed after registry construction",
                location=location,
                metadata={"operation": operation, "call_context": call_context, "cause_code": "leaf_source_changed"},
            )
        manager = StateManager(self.workspace)
        try:
            manager.initialize(
                str(self.source_path),
                context=dict(workflow_context(leaf.bundle)),
                bound_inputs=bound_inputs,
            )
        except Exception as exc:
            manager.close()
            raise EvaluatedValueError(
                "dynamic_effect_failed",
                "fresh leaf state could not be initialized",
                location=location,
                metadata={
                    "operation": operation,
                    "leaf_run_id": manager.run_id,
                    "call_context": call_context,
                    "cause_code": type(exc).__name__,
                },
            ) from exc

        executor = _GuardedWorkflowExecutor(
            leaf.bundle,
            self.workspace,
            manager,
            logs_dir=manager.logs_dir,
            retry_delay_ms=0,
            max_retries=0,
            result_descriptor=leaf.result_descriptor,
            operation=operation,
        )
        executor._dynamic_location = location
        for provider in self._provider_templates:
            executor.provider_registry.register(provider)
        try:
            state = executor.execute(on_error="stop")
        except Exception as exc:
            raise EvaluatedValueError(
                "dynamic_effect_failed",
                "leaf workflow execution failed",
                location=location,
                metadata={
                    "operation": operation,
                    "leaf_run_id": manager.run_id,
                    "call_context": call_context,
                    "cause_code": type(exc).__name__,
                },
            ) from exc
        finally:
            manager.close()
        if state.get("status") != "completed" or state.get("exit_code", 0) != 0:
            cause_code = None
            error = state.get("error")
            if isinstance(error, Mapping):
                cause_code = error.get("type")
                if not isinstance(cause_code, str):
                    cause_code = None
            raise EvaluatedValueError(
                "dynamic_effect_failed",
                "leaf workflow did not complete successfully",
                location=location,
                metadata={
                    "operation": operation,
                    "leaf_run_id": manager.run_id,
                    "call_context": call_context,
                    **({"cause_code": cause_code} if cause_code else {}),
                },
            )
        outputs = state.get("workflow_outputs")
        if not isinstance(outputs, Mapping):
            raise EvaluatedValueError(
                "dynamic_effect_failed",
                "completed leaf did not publish workflow outputs",
                location=location,
                metadata={"operation": operation, "leaf_run_id": manager.run_id, "call_context": call_context},
            )
        return MappingProxyType(dict(outputs))


__all__ = ["LeafBridge"]
