"""Review-loop lowering ownership and promoted-route guards."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expressions import StdlibSpecializationExpr
from ..phase_stdlib import (
    ReviewLoopLegacyBridgePolicy,
    REVIEW_LOOP_LEGACY_BRIDGE_POLICY_DENY,
    is_review_loop_request_kind,
)
from ..type_env import UnionTypeRef


def _walk_nodes(node: object):
    if is_dataclass(node):
        yield node
        for field in fields(node):
            yield from _walk_nodes(getattr(node, field.name))
        return
    if isinstance(node, tuple | list):
        for item in node:
            yield from _walk_nodes(item)


def assert_review_loop_special_lowerer_allowed(
    *,
    typed_workflows: tuple[object, ...],
    typed_procedures: tuple[object, ...],
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy,
) -> None:
    """Fail closed if deny-mode lowering still sees the legacy review-loop bridge."""

    if review_loop_legacy_bridge_policy != REVIEW_LOOP_LEGACY_BRIDGE_POLICY_DENY:
        return
    for owner in (*typed_workflows, *typed_procedures):
        for node in _walk_nodes(owner):
            if isinstance(node, StdlibSpecializationExpr) and is_review_loop_request_kind(node.request_kind):
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="review_loop_special_lowerer_used",
                            message=(
                                "promoted mode cannot lower the legacy `review-revise-loop` compatibility bridge"
                            ),
                            span=node.span,
                            form_path=node.form_path,
                            expansion_stack=node.expansion_stack,
                        ),
                    )
                )


def _surface_contract_from_structured_field(field: Mapping[str, Any]) -> dict[str, Any]:
    definition = {
        key: value
        for key, value in field.items()
        if key in {"type", "allowed", "under", "must_exist_target"}
    }
    definition["kind"] = "relpath" if definition.get("type") == "relpath" else "scalar"
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
