"""Workflow-boundary input/output contract helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Mapping

from orchestrator.contracts.output_contract import OutputContractError, validate_contract_value

from .executable_ir import ExecutableContract
from .references import ReferenceResolutionError, ReferenceResolver


WORKFLOW_SIGNATURE_VERSION = "2.1"


class WorkflowSignatureError(ValueError):
    """Raised when workflow-boundary input/output contracts fail."""

    def __init__(self, message: str, *, context: Dict[str, Any]):
        self.error = {
            "type": "contract_violation",
            "message": message,
            "context": context,
        }
        super().__init__(message)


def bind_workflow_inputs(
    input_specs: Mapping[str, Dict[str, Any]] | None,
    provided_inputs: Mapping[str, Any] | None,
    workspace: Path,
) -> Dict[str, Any]:
    """Bind and validate workflow inputs from CLI/runtime values."""
    specs = dict(input_specs or {})
    raw_inputs = dict(provided_inputs or {})
    bound_inputs: Dict[str, Any] = {}

    unexpected = sorted(name for name in raw_inputs if name not in specs)
    if unexpected:
        raise WorkflowSignatureError(
            "Workflow input binding failed",
            context={
                "scope": "workflow_inputs",
                "reason": "unknown_inputs",
                "inputs": unexpected,
            },
        )

    for name, spec in specs.items():
        if name in raw_inputs:
            candidate = raw_inputs[name]
        elif "default" in spec:
            candidate = spec["default"]
        elif spec.get("required", True):
            raise WorkflowSignatureError(
                "Workflow input binding failed",
                context={
                    "scope": "workflow_inputs",
                    "input": name,
                    "reason": "missing_required_input",
                },
            )
        else:
            continue

        try:
            bound_inputs[name] = validate_contract_value(candidate, spec, workspace=workspace)
        except OutputContractError as exc:
            raise WorkflowSignatureError(
                "Workflow input binding failed",
                context={
                    "scope": "workflow_inputs",
                    "input": name,
                    "reason": "invalid_value",
                    "violations": exc.violations,
                },
            ) from exc

    return bound_inputs


def resolve_workflow_outputs(
    output_specs: Mapping[str, Any] | None,
    state: Dict[str, Any],
    workspace: Path,
    *,
    resolve_source: Callable[[Any, Dict[str, Any]], Any] | None = None,
) -> Dict[str, Any]:
    """Resolve and validate declared workflow outputs from run state."""
    specs = dict(output_specs or {})
    if not specs:
        return {}

    resolver = ReferenceResolver()
    resolved_outputs: Dict[str, Any] = {}
    for name, spec in specs.items():
        validation_spec: Any = spec.definition if isinstance(spec, ExecutableContract) else spec
        binding = validation_spec.get("from") if isinstance(validation_spec, Mapping) else None
        ref = binding.get("ref") if isinstance(binding, Mapping) else None
        source = spec.source_address if isinstance(spec, ExecutableContract) else None
        if source is None and isinstance(ref, str) and ref:
            source = {"ref": ref}
        if source is None:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "missing_from_ref",
                },
            )

        try:
            if resolve_source is not None:
                raw_value = resolve_source(source, state)
            else:
                raw_value = resolver.resolve(ref, state).value
        except ReferenceResolutionError as exc:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "unresolved_source",
                    "ref": ref,
                    "error": str(exc),
                },
            ) from exc

        try:
            resolved_outputs[name] = validate_contract_value(raw_value, validation_spec, workspace=workspace)
        except OutputContractError as exc:
            raise WorkflowSignatureError(
                "Workflow output export failed",
                context={
                    "scope": "workflow_outputs",
                    "output": name,
                    "reason": "invalid_export_value",
                    "ref": ref,
                    "violations": exc.violations,
                },
            ) from exc

    return resolved_outputs
