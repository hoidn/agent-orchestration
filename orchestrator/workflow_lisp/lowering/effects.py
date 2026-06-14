"""Primitive provider/command lowering owners."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..expressions import CommandResultExpr, LiteralExpr, ProviderResultExpr
from ..phase import IMPLEMENTATION_ATTEMPT_ARTIFACT_ROOT
from ..type_env import TypeRef
from . import core as lowering_core
from .context import _TerminalResult
from .generated_paths import allocate_generated_result_bundle
from .phase_scope import _build_typed_prompt_inputs_for_prompt_specs


_PROVIDER_BUNDLE_NEGATIVE_VALIDATION_CASES = (
    "missing_bundle",
    "stale_input",
    "schema_mismatch",
    "path_escape",
    "pointer_authority_rejected",
)


@dataclass(frozen=True)
class LowerableCommandResult:
    """Owner-level command-result payload shared by frontend and WCC lowering."""

    step_name: str
    argv: tuple[Any, ...]
    span: Any
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()
    adapter_name: str | None = None
    adapter_inputs: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class LowerableProviderResult:
    """Owner-level provider-result payload shared by frontend and WCC lowering."""

    provider_name: str
    prompt_name: str
    inputs: tuple[Any, ...]
    span: Any
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()


def _lower_command_result(
    typed_expr: Any,
    *,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    expr = typed_expr.expr
    assert isinstance(expr, CommandResultExpr)
    return _lower_command_result_operation(
        LowerableCommandResult(
            step_name=expr.step_name,
            argv=tuple(expr.argv),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            adapter_name=expr.adapter_name,
            adapter_inputs=tuple(expr.adapter_inputs),
        ),
        result_type=typed_expr.type_ref,
        context=context,
        local_values=local_values,
    )


def _lower_command_result_operation(
    command_result: LowerableCommandResult,
    *,
    result_type: TypeRef,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    from ..contracts import derive_structured_result_contract
    from ..workflows import CertifiedAdapterBinding

    binding_name = command_result.adapter_name or command_result.step_name
    binding = context.command_boundary_environment.bindings_by_name.get(binding_name)
    if binding is None:
        raise lowering_core._compile_error(
            code="command_result_tool_invalid",
            message=f"unknown command boundary `{binding_name}` during lowering",
            span=command_result.span,
            form_path=command_result.form_path,
        )
    step_name = f"{context.step_name_prefix}__{command_result.step_name}"
    step_id = lowering_core._normalize_generated_step_id(step_name)
    bundle_contract = derive_structured_result_contract(
        result_type,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=command_result.span,
        form_path=command_result.form_path,
    )
    allocation = allocate_generated_result_bundle(
        context=context,
        source_expr=command_result,
        step_name=step_name,
        step_id=step_id,
        semantic_role=GeneratedPathSemanticRole.COMMAND_RESULT_BUNDLE,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = allocation.concrete_path_template
    lowering_core._record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=command_result,
    )
    if command_result.adapter_name is not None:
        if not isinstance(binding, CertifiedAdapterBinding):
            raise lowering_core._compile_error(
                code="command_result_tool_invalid",
                message=f"`command-result` adapter `{command_result.adapter_name}` is not a certified adapter during lowering",
                span=command_result.span,
                form_path=command_result.form_path,
            )
        command = [
            *binding.stable_command,
            _serialize_adapter_payload(
                adapter_inputs=command_result.adapter_inputs,
                binding=binding,
                local_values=local_values,
            ),
        ]
    else:
        command = [
            *binding.stable_command,
            *lowering_core._render_argv_tail(
                command_result.argv[len(binding.stable_command) :],
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
        output_refs=lowering_core._record_output_refs(step_name, result_type),
        output_kind="step",
        hidden_inputs={
            allocation.generated_input_name: lowering_core._origin_from_context_source(context, command_result)
        },
    )


def _serialize_adapter_payload(
    *,
    adapter_inputs: tuple[tuple[str, Any], ...],
    binding: Any,
    local_values: Mapping[str, Any],
) -> str:
    authored_inputs = {
        field_name: value_expr
        for field_name, value_expr in adapter_inputs
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
    return _lower_provider_result_operation(
        LowerableProviderResult(
            provider_name=expr.provider.name,
            prompt_name=expr.prompt.name,
            inputs=tuple(expr.inputs),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result_type=result_type,
        context=context,
        local_values=local_values,
        step_name=step_name,
    )


def _lower_provider_result_operation(
    provider_result: LowerableProviderResult,
    *,
    result_type: TypeRef,
    context: Any,
    local_values: Mapping[str, Any],
    step_name: str | None = None,
) -> tuple[list[dict[str, Any]], Any]:
    from ..contracts import derive_structured_result_contract

    provider_step_name = step_name or f"{context.step_name_prefix}__result"
    provider_step_id = lowering_core._normalize_generated_step_id(provider_step_name)
    provider_binding = context.extern_environment.bindings_by_name.get(provider_result.provider_name)
    prompt_binding = context.extern_environment.bindings_by_name.get(provider_result.prompt_name)
    if not isinstance(provider_binding, lowering_core.ProviderExtern) or not isinstance(
        prompt_binding, lowering_core.PromptExtern
    ):
        raise lowering_core._compile_error(
            code="provider_result_provider_invalid",
            message="provider-result lowering requires validated provider/prompt externs",
            span=provider_result.span,
            form_path=provider_result.form_path,
        )
    bundle_contract = derive_structured_result_contract(
        result_type,
        workflow_name=context.workflow_name,
        step_id=provider_step_name,
        span=provider_result.span,
        form_path=provider_result.form_path,
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
                (("inputs", provider_result.inputs),),
                context=context,
                local_values=local_values,
            )
            if lowering_core._uses_legacy_phase_prompt_input_prelude(
                provider_result,
                local_values=local_values,
            ):
                use_active_phase_bundle = True
        provider_bundle_contract_metadata = _provider_bundle_contract_metadata(
            context=context,
            use_active_phase_bundle=use_active_phase_bundle,
        )
        if use_active_phase_bundle:
            allocation = allocate_generated_result_bundle(
                context=context,
                source_expr=provider_result,
                step_name=provider_step_name,
                step_id=provider_step_id,
                semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
                path_template=lowering_core._template_for_ref(context.phase_scope.bundle_path_ref),
            )
            authored_contract["path"] = allocation.concrete_path_template
        else:
            allocation = allocate_generated_result_bundle(
                context=context,
                source_expr=provider_result,
                step_name=provider_step_name,
                step_id=provider_step_id,
                semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
            )
            authored_contract["path"] = allocation.concrete_path_template
            hidden_inputs[allocation.generated_input_name] = lowering_core._origin_from_context_source(context, provider_result)
        if lowering_core._uses_legacy_phase_prompt_input_prelude(
            provider_result,
            local_values=local_values,
        ):
            generated_steps.extend(
                lowering_core._build_phase_prompt_input_prelude(
                    provider_result,
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
                    (("inputs", provider_result.inputs),),
                    context=context,
                    local_values=local_values,
                    source_expr=provider_result,
                )
            )
            generated_steps.extend(phase_steps)
            hidden_inputs.update(phase_hidden_inputs)
            if consumes:
                provider_step["consumes"] = consumes
            if prompt_consumes:
                provider_step["prompt_consumes"] = prompt_consumes
        typed_prompt_inputs, typed_hidden_inputs = _build_typed_prompt_inputs_for_prompt_specs(
            (("inputs", provider_result.inputs),),
            context=context,
            local_values=local_values,
            source_expr=provider_result,
        )
        if typed_prompt_inputs:
            hidden_inputs.update(typed_hidden_inputs)
            provider_step.pop("consumes", None)
            provider_step.pop("prompt_consumes", None)
            generated_steps = [
                step
                for step in generated_steps
                if not (
                    isinstance(step, dict)
                    and "materialize_artifacts" in step
                    and "prompt_inputs" in str(step.get("id", ""))
                )
            ]
            provider_step["typed_prompt_inputs"] = typed_prompt_inputs
    else:
        allocation = allocate_generated_result_bundle(
            context=context,
            source_expr=provider_result,
            step_name=provider_step_name,
            step_id=provider_step_id,
            semantic_role=GeneratedPathSemanticRole.PROVIDER_RESULT_BUNDLE,
        )
        authored_contract["path"] = allocation.concrete_path_template
        typed_prompt_inputs, _typed_hidden_inputs = _build_typed_prompt_inputs_for_prompt_specs(
            (("inputs", provider_result.inputs),),
            context=context,
            local_values=local_values,
            source_expr=provider_result,
        )
        if typed_prompt_inputs:
            provider_step["typed_prompt_inputs"] = typed_prompt_inputs
        hidden_inputs[allocation.generated_input_name] = lowering_core._origin_from_context_source(context, provider_result)
    lowering_core._record_step_origin(
        context,
        step_name=provider_step_name,
        step_id=provider_step_id,
        source=provider_result,
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
