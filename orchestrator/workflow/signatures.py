"""Workflow-boundary input/output contract helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping

from orchestrator.contracts.output_contract import OutputContractError, validate_contract_value


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
    *,
    finite_floats: bool = False,
) -> Dict[str, Any]:
    """Bind and validate workflow inputs from CLI/runtime values.

    `finite_floats` refuses a non-finite `Float` input with `float_not_finite`
    (numeric surface N6); the caller derives it from the workflow's target.
    """
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
            bound_inputs[name] = validate_contract_value(
                candidate,
                spec,
                workspace=workspace,
                finite_floats=finite_floats,
            )
        except OutputContractError as exc:
            message = "Workflow input binding failed"
            for violation in exc.violations:
                if violation["type"] == "float_not_finite":
                    value = violation["context"]["value"]
                    message += f": float_not_finite: input '{name}' is {value}, not a finite Float"
            raise WorkflowSignatureError(
                message,
                context={
                    "scope": "workflow_inputs",
                    "input": name,
                    "reason": "invalid_value",
                    "violations": exc.violations,
                },
            ) from exc

    return bound_inputs
