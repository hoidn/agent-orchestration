"""Interpret runtime-native pure-projection workflow steps."""

from __future__ import annotations

from hashlib import sha256
from typing import Any, Dict, Optional

from ...contracts.output_contract import OutputContractError
from ..pure_expr import (
    PureExprEvaluationError,
    canonical_json_for_pure_value,
    evaluate_pure_expr,
)
from .runtime import StepRuntime


def execute_pure_projection(
    runtime: StepRuntime,
    step: Dict[str, Any],
    state: Dict[str, Any],
    *,
    scope: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Resolve, evaluate, and report one runtime-native pure projection."""
    config = step.get("pure_projection")
    if not isinstance(config, dict):
        return runtime._contract_violation_result(
            "Pure projection execution failed",
            {"reason": "missing_pure_projection_config"},
        )
    payload = config.get("payload")
    binding_refs = config.get("binding_refs")
    payload_digest = config.get("payload_digest")
    output_contracts = config.get("output_contracts")
    if not isinstance(payload, dict) or not isinstance(binding_refs, dict) or not isinstance(payload_digest, str):
        return runtime._contract_violation_result(
            "Pure projection execution failed",
            {"reason": "invalid_pure_projection_config"},
        )
    resolved_expected_outputs, resolved_output_bundle, path_error = runtime._resolve_output_contract_paths(
        step,
        state,
        context=scope,
    )
    if path_error is not None:
        return path_error
    bundle_path = None
    if isinstance(resolved_output_bundle, dict):
        raw_path = resolved_output_bundle.get("path")
        if isinstance(raw_path, str) and raw_path:
            bundle_path = (runtime.workspace / raw_path).resolve()
            bundle_path = runtime._bounded_private_runtime_bundle_path(
                bundle_path,
                namespace="pure_projection",
            )
    resolved_bindings, binding_error = runtime._resolve_pure_projection_bindings(
        binding_refs,
        state,
        scope=scope,
    )
    if binding_error is not None:
        return binding_error
    bindings_digest = (
        f"sha256:{sha256(canonical_json_for_pure_value(resolved_bindings).encode('utf-8')).hexdigest()}"
    )
    if bundle_path is not None:
        bundle_parent_error = runtime._prepare_runtime_output_bundle_parent(resolved_output_bundle)
        if bundle_parent_error is not None:
            return bundle_parent_error
        reused_result, reuse_error = runtime._reuse_pure_projection_bundle(
            bundle_path=bundle_path,
            payload=payload,
            payload_digest=payload_digest,
            bindings_digest=bindings_digest,
        )
        if reuse_error is not None:
            return reuse_error
        if reused_result is not None:
            try:
                artifacts = runtime._pure_projection_artifacts(
                    reused_result,
                    output_contracts=output_contracts,
                )
            except OutputContractError as exc:
                return runtime._contract_violation_result(
                    "Pure projection execution failed",
                    {"reason": "invalid_reused_pure_projection_result", "violations": exc.violations},
                )
            return {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 0,
                "artifacts": artifacts,
                "debug": {"pure_projection": {"reused_bundle": True}},
            }
    try:
        result_value = evaluate_pure_expr(payload, resolved_bindings=resolved_bindings)
        artifacts = runtime._pure_projection_artifacts(
            result_value,
            output_contracts=output_contracts,
        )
    except OutputContractError as exc:
        return runtime._contract_violation_result(
            "Pure projection execution failed",
            {"reason": "pure_projection_contract_invalid", "violations": exc.violations},
        )
    except PureExprEvaluationError as exc:
        context: Dict[str, Any] = {"error": str(exc)}
        if exc.metadata:
            context["metadata"] = exc.metadata
        if exc.source is not None:
            context["source"] = exc.source
        return runtime._v214_failure_result(
            exc.code,
            str(exc),
            context=context,
        )
    except Exception as exc:
        return runtime._v214_failure_result(
            "pure_projection_failed",
            "Pure projection evaluation failed",
            context={"error": str(exc)},
        )
    if bundle_path is not None:
        bundle_record = {
            "pure_expr_schema_version": payload.get("pure_expr_schema_version"),
            "payload_digest": payload_digest,
            "bindings_digest": bindings_digest,
            "result": result_value,
        }
        runtime._atomic_write_text(bundle_path, canonical_json_for_pure_value(bundle_record))
    return {
        "status": "completed",
        "exit_code": 0,
        "duration_ms": 0,
        "artifacts": artifacts,
        "debug": {"pure_projection": {"reused_bundle": False}},
    }
