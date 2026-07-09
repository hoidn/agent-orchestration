"""Interpret scalar workflow steps."""

from __future__ import annotations

from typing import Any, Dict

from ..executor_runtime import RuntimeStepInput
from .runtime import StepRuntime


def execute_scalar_step(
    runtime: StepRuntime,
    step: RuntimeStepInput,
    artifact_name: Any,
    candidate_value: Any,
) -> Dict[str, Any]:
    """Validate and report one scalar artifact value."""
    registry = runtime.workflow_artifacts
    artifact_spec = registry.get(artifact_name, {}) if isinstance(registry, dict) else {}
    validated_value = runtime._validate_scalar_value(artifact_name, artifact_spec, candidate_value)
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
