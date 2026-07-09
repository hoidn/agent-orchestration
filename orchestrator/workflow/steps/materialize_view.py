"""Interpret runtime-native materialize-view workflow steps."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from ...contracts.output_contract import OutputContractError
from ..pure_expr import canonical_json_for_pure_value
from ..references import MaterializeViewBindingReference
from ..view_renderer import (
    ViewRendererError,
    view_bytes_digest,
    view_evidence_key,
)
from .runtime import StepRuntime


def execute_materialize_view(
    runtime: StepRuntime,
    step: Dict[str, Any],
    state: Dict[str, Any],
    *,
    scope: Optional[Dict[str, Dict[str, Any]]] = None,
    render_view_fn: Callable[[str, int, Any], bytes],
) -> Dict[str, Any]:
    """Resolve, render, and commit one runtime-native materialized view."""
    config = step.get("materialize_view")
    if not isinstance(config, dict):
        return runtime._contract_violation_result(
            "Materialize view execution failed",
            {"reason": "missing_materialize_view_config"},
        )
    publication = config.get("publication")
    if (
        isinstance(publication, Mapping)
        and publication.get("entry_boundary_only") is True
        and isinstance(getattr(runtime.state_manager, "frame_id", None), str)
    ):
        return {
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 0,
            "artifacts": {},
            "debug": {
                "entry_publication": {
                    "skipped": True,
                    "reason": "call_frame_not_entry_boundary",
                    "row_id": publication.get("row_id"),
                    "role": publication.get("role"),
                    "variant": publication.get("variant"),
                }
            },
        }
    renderer_id = config.get("renderer_id")
    renderer_version = config.get("renderer_version")
    renderer_schema_version = config.get("view_renderer_schema_version")
    value_document = config.get("value_document")
    value_type = config.get("value_type")
    target_path_value = config.get("target_path")
    output_contracts = config.get("output_contracts")
    if (
        not isinstance(renderer_id, str)
        or not isinstance(renderer_version, int)
        or not isinstance(renderer_schema_version, int)
        or not isinstance(
            value_document,
            (dict, list, tuple, str, int, float, bool, MaterializeViewBindingReference),
        )
        and value_document is not None
        or not isinstance(value_type, Mapping)
        or not isinstance(output_contracts, dict)
    ):
        return runtime._contract_violation_result(
            "Materialize view execution failed",
            {"reason": "invalid_materialize_view_config"},
        )
    resolved_target_value, target_binding_error = runtime._resolve_materialize_view_target_value(
        target_path_value,
        state,
        scope=scope,
    )
    if target_binding_error is not None:
        return target_binding_error
    if not isinstance(resolved_target_value, str):
        return runtime._contract_violation_result(
            "Materialize view execution failed",
            {"reason": "materialize_view_target_path_invalid", "path": resolved_target_value},
        )
    target_path = runtime._resolve_workspace_path(resolved_target_value)
    if target_path is None:
        return runtime._contract_violation_result(
            "Materialize view execution failed",
            {"reason": "materialize_view_target_path_invalid", "path": resolved_target_value},
        )
    resolved_value, binding_error = runtime._resolve_materialize_view_value(
        value_document,
        state,
        scope=scope,
    )
    if binding_error is not None:
        return binding_error
    try:
        rendered = render_view_fn(renderer_id, renderer_version, resolved_value)
    except ViewRendererError as exc:
        return runtime._v214_failure_result(
            "materialize_view_render_failed",
            str(exc),
            context={"code": exc.code, "metadata": exc.metadata},
        )
    except Exception as exc:
        return runtime._v214_failure_result(
            "materialize_view_render_failed",
            "Materialize view rendering failed",
            context={"error": str(exc)},
        )
    value_digest = view_bytes_digest(canonical_json_for_pure_value(resolved_value).encode("utf-8"))
    evidence_key = view_evidence_key(
        renderer_id,
        renderer_version,
        renderer_schema_version,
        value_digest,
    )
    rendered_digest = view_bytes_digest(rendered)
    evidence_path = runtime._materialize_view_evidence_path(target_path)
    reused_result, reuse_error = runtime._reuse_materialized_view(
        target_path=target_path,
        evidence_path=evidence_path,
        renderer_id=renderer_id,
        renderer_version=renderer_version,
        renderer_schema_version=renderer_schema_version,
        evidence_key=evidence_key,
        rendered_digest=rendered_digest,
    )
    if reuse_error is not None:
        return reuse_error
    if reused_result is not None:
        artifacts = runtime._materialize_view_artifacts(
            runtime._workspace_relative_path(target_path),
            output_contracts=output_contracts,
        )
        reused_result["artifacts"] = artifacts
        return reused_result
    evidence_record = {
        "view_renderer_schema_version": renderer_schema_version,
        "renderer_id": renderer_id,
        "renderer_version": renderer_version,
        "value_type": dict(value_type),
        "value_digest": value_digest,
        "view_digest": rendered_digest,
        "evidence_key": evidence_key,
        "target_path": runtime._workspace_relative_path(target_path),
    }
    evidence_bytes = (canonical_json_for_pure_value(evidence_record) + "\n").encode("utf-8")
    previous_target_bytes = runtime._capture_existing_file_bytes(target_path)
    previous_evidence_bytes = runtime._capture_existing_file_bytes(evidence_path)
    try:
        runtime._atomic_write_bytes(target_path, rendered)
        runtime._atomic_write_bytes(evidence_path, evidence_bytes)
        artifacts = runtime._materialize_view_artifacts(
            runtime._workspace_relative_path(target_path),
            output_contracts=output_contracts,
        )
    except OutputContractError as exc:
        runtime._restore_file_bytes(target_path, previous_target_bytes)
        runtime._restore_file_bytes(evidence_path, previous_evidence_bytes)
        return runtime._contract_violation_result(
            "Materialize view execution failed",
            {"reason": "materialize_view_contract_invalid", "violations": exc.violations},
        )
    except Exception as exc:
        runtime._restore_file_bytes(target_path, previous_target_bytes)
        runtime._restore_file_bytes(evidence_path, previous_evidence_bytes)
        return runtime._v214_failure_result(
            "materialize_view_render_failed",
            "Materialize view commit failed",
            context={"error": str(exc)},
        )
    return {
        "status": "completed",
        "exit_code": 0,
        "duration_ms": 0,
        "artifacts": artifacts,
        "debug": {
            "materialize_view": {
                "reused_view": False,
                "target_path": runtime._workspace_relative_path(target_path),
                "view_digest": rendered_digest,
                "evidence_key": evidence_key,
                "evidence_path": runtime._workspace_relative_path(evidence_path),
            }
        },
    }
