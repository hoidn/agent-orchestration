"""Primitive provider/command lowering owners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..expressions import CommandResultExpr, ProviderResultExpr
from ..type_env import TypeRef
from . import core as lowering_core
from .context import _TerminalResult
from .generated_paths import allocate_generated_result_bundle


def _lower_command_result(
    typed_expr: Any,
    *,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    from ..contracts import derive_structured_result_contract

    expr = typed_expr.expr
    assert isinstance(expr, CommandResultExpr)
    binding = context.command_boundary_environment.bindings_by_name.get(expr.step_name)
    if binding is None:
        raise lowering_core._compile_error(
            code="command_result_tool_invalid",
            message=f"unknown command boundary `{expr.step_name}` during lowering",
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
    step = {
        "name": step_name,
        "id": step_id,
        "command": [
            *binding.stable_command,
            *lowering_core._render_argv_tail(
                expr.argv[len(binding.stable_command) :],
                local_values=local_values,
            ),
        ],
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
    provider_step: dict[str, Any] = {
        "name": provider_step_name,
        "id": provider_step_id,
        "provider": provider_binding.provider_id,
        "asset_file": prompt_binding.asset_file,
        "inject_output_contract": True,
        bundle_contract.contract_kind: authored_contract,
    }
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
    )
