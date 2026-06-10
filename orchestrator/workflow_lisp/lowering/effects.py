"""Primitive provider/command lowering owners."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..expressions import CommandResultExpr, LiteralExpr, ProviderResultExpr
from ..phase import IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT
from ..type_env import TypeRef
from . import core as lowering_core
from .context import _TerminalResult
from .generated_paths import allocate_generated_result_bundle


_PROVIDER_BUNDLE_NEGATIVE_VALIDATION_CASES = (
    "missing_bundle",
    "stale_input",
    "schema_mismatch",
    "path_escape",
    "pointer_authority_rejected",
)


def _lower_command_result(
    typed_expr: Any,
    *,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    from ..contracts import derive_structured_result_contract
    from ..workflows import CertifiedAdapterBinding

    expr = typed_expr.expr
    assert isinstance(expr, CommandResultExpr)
    binding_name = expr.adapter_name or expr.step_name
    binding = context.command_boundary_environment.bindings_by_name.get(binding_name)
    if binding is None:
        raise lowering_core._compile_error(
            code="command_result_tool_invalid",
            message=f"unknown command boundary `{binding_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = f"{context.step_name_prefix}__{expr.step_name}"
    step_id = lowering_core._normalize_generated_step_id(step_name)
    bundle_contract = derive_structured_result_contract(
        typed_expr.type_ref,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=expr,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = allocation.concrete_path_template
    lowering_core._record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    if expr.adapter_name is not None:
        if not isinstance(binding, CertifiedAdapterBinding):
            raise lowering_core._compile_error(
                code="command_result_tool_invalid",
                message=f"`command-result` adapter `{expr.adapter_name}` is not a certified adapter during lowering",
                span=expr.span,
                form_path=expr.form_path,
            )
        command = [
            *binding.stable_command,
            _serialize_adapter_payload(
                expr=expr,
                binding=binding,
                local_values=local_values,
            ),
        ]
    else:
        command = [
            *binding.stable_command,
            *lowering_core._render_argv_tail(
                expr.argv[len(binding.stable_command) :],
                local_values=local_values,
            ),
        ]
    step = {
        "name": step_name,
        "id": step_id,
        "command": command,
        bundle_contract.contract_kind: authored_contract,
    }
    return [step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs=lowering_core._record_output_refs(step_name, typed_expr.type_ref),
        output_kind="step",
        hidden_inputs={
            allocation.generated_input_name: lowering_core._origin_from_context_source(context, expr)
        },
    )


def _serialize_adapter_payload(
    *,
    expr: CommandResultExpr,
    binding: Any,
    local_values: Mapping[str, Any],
) -> str:
    authored_inputs = {
        field_name: value_expr
        for field_name, value_expr in expr.adapter_inputs
    }
    payload_parts: list[str] = []
    for field in binding.input_signature:
        if field.name not in authored_inputs:
            continue
        payload_parts.append(
            json.dumps(field.transport_key, separators=(",", ":"))
            + ":"
            + _render_adapter_payload_value(
                authored_inputs[field.name],
                declared_type_name=field.type_name,
                local_values=local_values,
            )
        )
    return "{" + ",".join(payload_parts) + "}"


def _render_adapter_payload_value(
    expr: Any,
    *,
    declared_type_name: str,
    local_values: Mapping[str, Any],
) -> str:
    _ = declared_type_name
    resolved_value = lowering_core._resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(resolved_value, LiteralExpr):
        return json.dumps(resolved_value.value, separators=(",", ":"), ensure_ascii=False)
    if isinstance(resolved_value, str):
        return _json_template_for_ref(resolved_value)
    rendered_scalar = lowering_core._render_argv_tail([expr], local_values=local_values)[0]
    if rendered_scalar.startswith("${") and rendered_scalar.endswith("}"):
        return _json_template_for_template(rendered_scalar)
    return json.dumps(rendered_scalar, separators=(",", ":"), ensure_ascii=False)


def _json_template_for_ref(ref: str) -> str:
    return _json_template_for_template(lowering_core._template_for_ref(ref))


def _json_template_for_template(template: str) -> str:
    if not template.startswith("${") or not template.endswith("}"):
        raise ValueError(f"expected substitution template, got {template!r}")
    expression = template[2:-1]
    return "${" + expression + "|json}"


def _bundle_path_ref(path_template: str) -> str:
    if path_template.startswith("${") and path_template.endswith("}"):
        return path_template[2:-1]
    return path_template


def _provider_bundle_contract_metadata(
    *,
    context: Any,
    use_active_phase_bundle: bool,
) -> dict[str, Any]:
    bundle_under = "state"
    if use_active_phase_bundle and context.phase_scope is not None:
        bundle_under = IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT
    return {
        "bundle_under": bundle_under,
        "bundle_must_exist_target": False,
    }


def _lower_provider_result(
    expr: ProviderResultExpr,
    *,
    result_type: TypeRef,
    context: Any,
    local_values: Mapping[str, Any],
    step_name: str | None = None,
) -> tuple[list[dict[str, Any]], Any]:
    from ..contracts import derive_structured_result_contract

    provider_step_name = step_name or f"{context.step_name_prefix}__result"
    provider_step_id = lowering_core._normalize_generated_step_id(provider_step_name)
    provider_binding = context.extern_environment.bindings_by_name.get(expr.provider.name)
    prompt_binding = context.extern_environment.bindings_by_name.get(expr.prompt.name)
    if not isinstance(provider_binding, lowering_core.ProviderExtern) or not isinstance(
        prompt_binding, lowering_core.PromptExtern
    ):
        raise lowering_core._compile_error(
            code="provider_result_provider_invalid",
            message="provider-result lowering requires validated provider/prompt externs",
            span=expr.span,
            form_path=expr.form_path,
        )
    bundle_contract = derive_structured_result_contract(
        result_type,
        workflow_name=context.workflow_name,
        step_id=provider_step_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    hidden_inputs: dict[str, Any] = {}
    generated_steps: list[dict[str, Any]] = []
    allocation = None
    provider_bundle_contract_metadata = _provider_bundle_contract_metadata(
        context=context,
        use_active_phase_bundle=False,
    )
    provider_step: dict[str, Any] = {
        "name": provider_step_name,
        "id": provider_step_id,
        "provider": provider_binding.provider_id,
        "inject_output_contract": True,
        bundle_contract.contract_kind: authored_contract,
    }
    provider_step.update(lowering_core._prompt_source_step_fields(prompt_binding))
    if context.phase_scope is not None:
        use_active_phase_bundle = False
        if not context.is_generated_private_workflow:
            use_active_phase_bundle = lowering_core._phase_prompt_inputs_are_direct(
                (("inputs", tuple(expr.inputs)),),
                context=context,
                local_values=local_values,
            )
            if lowering_core._uses_legacy_phase_prompt_input_prelude(expr):
                use_active_phase_bundle = True
        provider_bundle_contract_metadata = _provider_bundle_contract_metadata(
            context=context,
            use_active_phase_bundle=use_active_phase_bundle,
        )
        if use_active_phase_bundle:
            allocation = allocate_generated_result_bundle(
                context=context,
                source_expr=expr,
                step_name=provider_step_name,
                step_id=provider_step_id,
                semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
                path_template=lowering_core._template_for_ref(context.phase_scope.bundle_path_ref),
            )
            authored_contract["path"] = allocation.concrete_path_template
        else:
            allocation = allocate_generated_result_bundle(
                context=context,
                source_expr=expr,
                step_name=provider_step_name,
                step_id=provider_step_id,
                semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
            )
            authored_contract["path"] = allocation.concrete_path_template
            hidden_inputs[allocation.generated_input_name] = lowering_core._origin_from_context_source(context, expr)
        if lowering_core._uses_legacy_phase_prompt_input_prelude(expr):
            generated_steps.extend(
                lowering_core._build_phase_prompt_input_prelude(
                    expr,
                    context=context,
                    local_values=local_values,
                )
            )
            provider_step["consumes"] = [
                {"artifact": "design", "policy": "latest_successful", "freshness": "any"},
                {"artifact": "plan", "policy": "latest_successful", "freshness": "any"},
                {"artifact": "execution_report_target", "policy": "latest_successful", "freshness": "any"},
                {"artifact": "progress_report_target", "policy": "latest_successful", "freshness": "any"},
            ]
            provider_step["prompt_consumes"] = [
                "design",
                "plan",
                "execution_report_target",
                "progress_report_target",
            ]
        else:
            phase_steps, consumes, prompt_consumes, phase_hidden_inputs = (
                lowering_core._build_phase_stdlib_prompt_input_prelude(
                    (("inputs", tuple(expr.inputs)),),
                    context=context,
                    local_values=local_values,
                    source_expr=expr,
                )
            )
            generated_steps.extend(phase_steps)
            hidden_inputs.update(phase_hidden_inputs)
            if consumes:
                provider_step["consumes"] = consumes
            if prompt_consumes:
                provider_step["prompt_consumes"] = prompt_consumes
    else:
        allocation = allocate_generated_result_bundle(
            context=context,
            source_expr=expr,
            step_name=provider_step_name,
            step_id=provider_step_id,
            semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
        )
        authored_contract["path"] = allocation.concrete_path_template
        hidden_inputs[allocation.generated_input_name] = lowering_core._origin_from_context_source(context, expr)
    lowering_core._record_step_origin(
        context,
        step_name=provider_step_name,
        step_id=provider_step_id,
        source=expr,
    )
    generated_steps.append(provider_step)
    return generated_steps, _TerminalResult(
        step_name=provider_step_name,
        step_id=provider_step_id,
        output_refs=lowering_core._record_output_refs(provider_step_name, result_type),
        output_kind="step",
        hidden_inputs=hidden_inputs,
        provider_bundle_identity={
            "source_step_name": provider_step_name,
            "source_step_id": provider_step_id,
            "output_kind": bundle_contract.contract_kind,
            "bundle_path_ref": _bundle_path_ref(authored_contract["path"]),
            "path_template": authored_contract["path"],
            "allocation_id": allocation.allocation_id if allocation is not None else None,
            "generated_input_name": allocation.generated_input_name if allocation is not None else None,
            "projection_class": "provider_bundle_path_projection",
            "authority_class": "materialized_view",
            "semantic_authority": "provider_structured_output_bundle",
            "negative_validation_cases": _PROVIDER_BUNDLE_NEGATIVE_VALIDATION_CASES,
            **provider_bundle_contract_metadata,
        },
    )
