"""Interpret runtime-native resource-transition workflow steps."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from ...contracts.output_contract import OutputContractError
from ..executor_runtime import RuntimeStepInput
from ..transition_executor import TransitionExecutionError, execute_transition
from .runtime import StepRuntime


def execute_resource_transition(
    runtime: StepRuntime,
    step: RuntimeStepInput,
    state: Dict[str, Any],
    *,
    scope: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Resolve, execute, and report one runtime-native resource transition."""
    config = step.get("resource_transition")
    if not isinstance(config, dict):
        return runtime._contract_violation_result(
            "Resource transition execution failed",
            {"reason": "missing_resource_transition_config"},
        )
    declaration = config.get("declaration")
    resource = config.get("resource")
    request_bindings = config.get("request_bindings")
    expected_version_value = config.get("expected_version")
    if declaration is None or not hasattr(declaration, "transition"):
        return runtime._contract_violation_result(
            "Resource transition execution failed",
            {"reason": "invalid_transition_declaration"},
        )
    if not isinstance(resource, Mapping) or not isinstance(request_bindings, Mapping):
        return runtime._contract_violation_result(
            "Resource transition execution failed",
            {"reason": "invalid_resource_transition_config"},
        )
    resolved_resource, resource_error = runtime._resolve_resource_transition_bindings(
        resource,
        state,
        scope=scope,
    )
    if resource_error is not None:
        return resource_error
    resolved_request, request_error = runtime._resolve_resource_transition_bindings(
        request_bindings,
        state,
        scope=scope,
    )
    if request_error is not None:
        return request_error
    resolved_expected_version = None
    if expected_version_value is not None:
        resolved_expected_version, version_error = runtime._resolve_resource_transition_bindings(
            expected_version_value,
            state,
            scope=scope,
        )
        if version_error is not None:
            return version_error
        if resolved_expected_version is not None and not isinstance(resolved_expected_version, str):
            return runtime._contract_violation_result(
                "Resource transition execution failed",
                {"reason": "invalid_expected_version"},
            )

    normalized_resource = runtime._normalize_resource_transition_paths(dict(resolved_resource))
    path_error = normalized_resource.pop("_path_error", None)
    if path_error is not None:
        return runtime._contract_violation_result(
            "Resource transition execution failed",
            {"reason": "invalid_resource_path", "field": path_error},
        )

    backend_kind = declaration.transition.backend.get("kind")
    try:
        transition_result = execute_transition(
            declaration,
            normalized_resource,
            resolved_request,
            resolved_expected_version,
            backend=backend_kind,
        )
        artifacts = runtime._resource_transition_artifacts(
            step,
            transition_result=transition_result,
        )
    except OutputContractError as exc:
        return runtime._contract_violation_result(
            "Resource transition execution failed",
            {"reason": "resource_transition_contract_invalid", "violations": exc.violations},
        )
    except TransitionExecutionError as exc:
        return runtime._v214_failure_result(exc.code, str(exc), context=dict(exc.metadata))
    except Exception as exc:
        return runtime._v214_failure_result(
            "resource_transition_failed",
            "Resource transition execution failed",
            context={"error": str(exc)},
        )
    return {
        "status": "completed",
        "exit_code": 0,
        "duration_ms": 0,
        "artifacts": artifacts,
        "debug": {
            "resource_transition": {
                "backend": backend_kind,
                "resource_id": normalized_resource.get("resource_id"),
                "version": transition_result["version"],
                "replayed": transition_result["replayed"],
            }
        },
    }
