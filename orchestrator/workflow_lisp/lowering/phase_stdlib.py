"""Phase/resource/drain lowering facade plus the residual review-loop quarantine.

The remaining review-loop-specific ownership here is limited to shaping the
typed union result contracts for the ordinary stdlib lowering route. Other
lowering owner modules must not duplicate these helpers or reintroduce a hidden
review-loop special lowerer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..type_env import UnionTypeRef
from .phase_drain import _lower_backlog_drain as _phase_drain_lower
from .phase_flow import (
    _lower_produce_one_of as _phase_flow_lower_produce_one_of,
    _lower_resume_or_start as _phase_flow_lower_resume_or_start,
    _lower_run_provider_phase as _phase_flow_lower_run_provider_phase,
)
from .phase_resource import (
    _lower_finalize_selected_item as _phase_resource_lower_finalize_selected_item,
    _lower_resource_transition as _phase_resource_lower_resource_transition,
)
from .phase_scope import _lower_with_phase as _phase_scope_lower_with_phase


def _surface_contract_from_structured_field(field: Mapping[str, Any]) -> dict[str, Any]:
    definition = {
        key: value
        for key, value in field.items()
        if key in {"type", "allowed", "under", "must_exist_target", "item", "items", "keys", "values"}
    }
    if definition.get("type") == "relpath":
        definition["kind"] = "relpath"
    elif definition.get("type") in {"optional", "list", "map"}:
        definition["kind"] = "collection"
    else:
        definition["kind"] = "scalar"
    return definition


def _review_loop_compile_error(
    *,
    code: str,
    message: str,
    span,
    form_path: tuple[str, ...],
) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=span,
                form_path=form_path,
            ),
        )
    )


def _union_case_contract_definitions(
    type_ref: UnionTypeRef,
    *,
    variant_name: str,
    workflow_name: str,
    step_name: str,
    span,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    from ..contracts import derive_structured_result_contract

    # Boundary projection only: this payload shapes case outputs, not a runtime contract.
    contract = derive_structured_result_contract(
        type_ref,
        workflow_name=workflow_name,
        step_id=step_name,
        span=span,
        form_path=form_path,
    )
    payload = contract.payload
    outputs = {
        "variant": _surface_contract_from_structured_field(payload["discriminant"]),
    }
    for field in payload["shared_fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    variant_payload = payload["variants"][variant_name]
    for field in variant_payload["fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    return outputs


def review_loop_result_case_outputs(
    type_ref: Any,
    *,
    variant_name: str,
    source_step_name: str,
    context: Any,
    span,
    form_path: tuple[str, ...],
) -> dict[str, Any]:
    """Build branch outputs for one review-loop terminal variant."""

    if not isinstance(type_ref, UnionTypeRef):
        raise _review_loop_compile_error(
            code="review_loop_result_contract_invalid",
            message="`review-revise-loop` lowering requires a union return type",
            span=span,
            form_path=form_path,
        )
    contracts = _union_case_contract_definitions(
        type_ref,
        variant_name=variant_name,
        workflow_name=context.workflow_name,
        step_name=context.step_name_prefix,
        span=span,
        form_path=form_path,
    )
    return {
        field_name: {
            **definition,
            "from": {"ref": f"root.steps.{source_step_name}.artifacts.{field_name}"},
        }
        for field_name, definition in contracts.items()
    }


def review_loop_result_output_contracts(
    type_ref: Any,
    *,
    context: Any,
    span,
    form_path: tuple[str, ...],
) -> dict[str, dict[str, Any]]:
    """Build all flattened output contracts for a review-loop result union."""

    from ..contracts import derive_structured_result_contract

    if not isinstance(type_ref, UnionTypeRef):
        raise _review_loop_compile_error(
            code="review_loop_result_contract_invalid",
            message="`review-revise-loop` lowering requires a union return type",
            span=span,
            form_path=form_path,
        )
    # Boundary projection only: this payload shapes outputs, not a runtime contract.
    payload = derive_structured_result_contract(
        type_ref,
        workflow_name=context.workflow_name,
        step_id=context.step_name_prefix,
        span=span,
        form_path=form_path,
    ).payload
    outputs = {
        "variant": _surface_contract_from_structured_field(payload["discriminant"]),
    }
    for field in payload["shared_fields"]:
        outputs[field["name"]] = _surface_contract_from_structured_field(field)
    for variant_payload in payload["variants"].values():
        for field in variant_payload["fields"]:
            definition = _surface_contract_from_structured_field(field)
            if definition.get("type") == "relpath":
                definition["must_exist_target"] = False
            outputs.setdefault(field["name"], definition)
    return outputs


def _lower_with_phase(*args, **kwargs):
    # G6 keeps the intrinsic lane callable while `std/phase/phase-scope` proves redundancy for G8.
    return _phase_scope_lower_with_phase(*args, **kwargs)


def _lower_run_provider_phase(*args, **kwargs):
    return _phase_flow_lower_run_provider_phase(*args, **kwargs)


def _lower_produce_one_of(*args, **kwargs):
    return _phase_flow_lower_produce_one_of(*args, **kwargs)


def _lower_resume_or_start(*args, **kwargs):
    return _phase_flow_lower_resume_or_start(*args, **kwargs)


def _lower_resource_transition(*args, **kwargs):
    return _phase_resource_lower_resource_transition(*args, **kwargs)


def _lower_finalize_selected_item(*args, **kwargs):
    # G6 keeps the intrinsic lane callable while `std/resource/finalize-selected-item` proves redundancy for G8.
    return _phase_resource_lower_finalize_selected_item(*args, **kwargs)


def _lower_backlog_drain(*args, **kwargs):
    # G6 keeps the intrinsic lane callable while `std/drain/backlog-drain` proves redundancy for G8.
    return _phase_drain_lower(*args, **kwargs)
