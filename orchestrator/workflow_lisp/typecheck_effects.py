"""Effect-bearing typecheck ownership for Workflow Lisp."""

from __future__ import annotations

from .effects import (
    EMPTY_EFFECT_SUMMARY,
    UsesCommandEffect,
    UsesProviderEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import (
    CommandResultExpr,
    EnumMemberExpr,
    ExprNode,
    LiteralExpr,
    NameExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
)
from .phase import is_implementation_attempt_result_type
from .type_env import PathTypeRef, PrimitiveTypeRef, RecordTypeRef, UnionTypeRef, type_refs_compatible
from .typecheck_context import raise_error, raise_required_lint


def typecheck_expected_extern_operand(
    expr: ExprNode,
    *,
    expected_primitive: str,
    context,
    recurse,
    typed_factory,
):
    extern_name = _extern_operand_name(expr)
    if extern_name is not None and extern_name not in context.value_env:
        return typed_factory(
            expr=expr,
            type_ref=PrimitiveTypeRef(name=expected_primitive),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    return recurse(expr)


def _extern_operand_name(expr: ExprNode) -> str | None:
    if isinstance(expr, (NameExpr, EnumMemberExpr)):
        return expr.name
    return None


def _literal_string(expr: ExprNode) -> str | None:
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "string" and isinstance(expr.value, str):
        return expr.value
    return None


def validate_command_argv(
    expr: CommandResultExpr,
    binding,
) -> None:
    argv = list(expr.argv)
    first = _literal_string(argv[0]) if argv else None
    if first:
        packed_head = first.split()
        if len(packed_head) >= 2:
            head = packed_head[0]
            flag = packed_head[1]
            if head.startswith("python") and flag in {"-c", "-"}:
                raise_error(
                    "inline Python command glue is not allowed in `command-result`",
                    code="inline_python_command_in_workflow",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            if head in {"bash", "sh"} and flag in {"-c", "-lc"}:
                raise_error(
                    "one-string shell wrappers are not allowed in `command-result`",
                    code="command_result_argv_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                )
    if len(argv) >= 2:
        second = _literal_string(argv[1])
        if first and first.startswith("python") and second in {"-c", "-"}:
            raise_error(
                "inline Python command glue is not allowed in `command-result`",
                code="inline_python_command_in_workflow",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        if first in {"bash", "sh"} and second in {"-c", "-lc"}:
            raise_error(
                "inline shell command glue is not allowed in `command-result`",
                code="inline_shell_command_in_workflow",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
    if not argv:
        raise_error(
            "`command-result` requires a non-empty argv list",
            code="command_result_argv_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if binding is None:
        return
    stable_prefix = list(binding.stable_command)
    if len(argv) < len(stable_prefix):
        raise_error(
            f"`command-result` `{expr.step_name}` must start with the stable command {' '.join(stable_prefix)!r}",
            code="command_result_argv_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    for index, token in enumerate(stable_prefix):
        actual = _literal_string(argv[index])
        if actual != token:
            raise_error(
                f"`command-result` `{expr.step_name}` must start with the stable command {' '.join(stable_prefix)!r}",
                code="command_result_argv_invalid",
                span=expr.argv[index].span,
                form_path=expr.argv[index].form_path,
                expansion_stack=expr.argv[index].expansion_stack,
            )
    if len(argv) == 1:
        only = _literal_string(argv[0])
        if only and (" " in only or ";" in only or "|" in only):
            raise_error(
                "one-string shell wrappers are not allowed in `command-result`",
                code="command_result_argv_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )


def validate_semantic_command_adapter_usage(
    expr: CommandResultExpr,
    binding,
) -> None:
    effects = set(binding.effects)
    transition_binding = getattr(binding, "transition_binding", None)
    allow_migration_backend_call = (
        transition_binding is not None
        and getattr(transition_binding, "contract_role", None) == "migration_backend"
    )
    if (
        (
            "resource_transition" in effects
            or "ledger_update" in effects
            or binding.behavior_class == "resource_transition"
        )
        and not allow_migration_backend_call
    ):
        raise_error(
            "resource movement must use `resource-transition` or a certified resource_transition adapter",
            code="resource_move_without_transition",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if "resume_state_reuse" in effects or binding.behavior_class == "resume_state_reuse":
        raise_error(
            "reusable-state gating must use `resume-or-start` instead of a raw `command-result` adapter call",
            code="recovery_gate_without_resume_or_start",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )


def _span_contains(outer, inner) -> bool:
    if outer is None:
        return False
    if outer.start.path != inner.start.path or outer.end.path != inner.end.path:
        return False
    return outer.start.offset <= inner.start.offset and inner.end.offset <= outer.end.offset


def is_macro_introduced_effect(
    span,
    expansion_stack: tuple[object, ...],
) -> bool:
    for frame in expansion_stack:
        definition_span = getattr(frame, "definition_span", None)
        if _span_contains(definition_span, span):
            return True
    return False


def typecheck_provider_result_expr(
    expr: ProviderResultExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    from .contracts import is_transportable_result_type
    from .workflows import PromptExtern, ProviderExtern

    if is_macro_introduced_effect(expr.span, expr.expansion_stack):
        raise_required_lint(
            "macro expansion introduced a hidden provider effect; move the `provider-result` to authored workflow code",
            code="macro_hidden_effect",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    return_type = context.type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    from .result_guidance import validate_result_guidance_example

    validate_result_guidance_example(
        expr.return_spec.guidance,
        expected_type=return_type,
        type_env=context.type_env,
    )
    if not is_transportable_result_type(return_type):
        raise_error(
            f"`provider-result` must return a transportable result type, got `{expr.returns_type_name}`",
            code="provider_result_return_type_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    active_phase_scope = context.active_phase_scope
    if (
        getattr(active_phase_scope, "uses_legacy_bridge", False)
        and not is_implementation_attempt_result_type(return_type)
    ):
        raise_error(
            "legacy implementation `with-phase` provider-result must return `ImplementationAttempt`",
            code="provider_result_return_type_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    typed_provider = typecheck_expected_extern_operand(
        expr.provider,
        expected_primitive="Provider",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    typed_prompt = typecheck_expected_extern_operand(
        expr.prompt,
        expected_primitive="Prompt",
        context=context,
        recurse=recurse,
        typed_factory=typed_factory,
    )
    if typed_provider.type_ref != PrimitiveTypeRef(name="Provider"):
        raise_error(
            "`provider-result` provider operand must resolve to `Provider`",
            code="provider_result_provider_invalid",
            span=expr.provider.span,
            form_path=expr.provider.form_path,
            expansion_stack=expr.provider.expansion_stack,
        )
    if typed_prompt.type_ref != PrimitiveTypeRef(name="Prompt"):
        raise_error(
            "`provider-result` prompt operand must resolve to `Prompt`",
            code="provider_result_prompt_invalid",
            span=expr.prompt.span,
            form_path=expr.prompt.form_path,
            expansion_stack=expr.prompt.expansion_stack,
        )
    provider_extern_name = _extern_operand_name(expr.provider)
    if provider_extern_name is None or context.extern_environment is None:
        raise_error(
            "`provider-result` requires a compiler-known provider extern",
            code="provider_result_provider_invalid",
            span=expr.provider.span,
            form_path=expr.provider.form_path,
            expansion_stack=expr.provider.expansion_stack,
        )
    provider_binding = context.extern_environment.bindings_by_name.get(provider_extern_name)
    if not isinstance(provider_binding, ProviderExtern):
        raise_error(
            f"`provider-result` provider `{provider_extern_name}` is not a declared provider extern",
            code="provider_result_provider_invalid",
            span=expr.provider.span,
            form_path=expr.provider.form_path,
            expansion_stack=expr.provider.expansion_stack,
        )
    prompt_extern_name = _extern_operand_name(expr.prompt)
    if prompt_extern_name is None or context.extern_environment is None:
        raise_error(
            "`provider-result` requires a compiler-known prompt extern",
            code="provider_result_prompt_invalid",
            span=expr.prompt.span,
            form_path=expr.prompt.form_path,
            expansion_stack=expr.prompt.expansion_stack,
        )
    prompt_binding = context.extern_environment.bindings_by_name.get(prompt_extern_name)
    if not isinstance(prompt_binding, PromptExtern):
        raise_error(
            f"`provider-result` prompt `{prompt_extern_name}` is not a declared prompt extern",
            code="provider_result_prompt_invalid",
            span=expr.prompt.span,
            form_path=expr.prompt.form_path,
            expansion_stack=expr.prompt.expansion_stack,
        )
    input_summaries = []
    for input_expr in expr.inputs:
        typed_input = recurse(input_expr)
        input_summaries.append(typed_input.effect_summary)
    provider_name = provider_extern_name or "provider-result"
    provider_summary = effect_summary_from_direct(
        direct_effects=(UsesProviderEffect(subject=tuple(provider_name.split("."))),)
    )
    return typed_factory(
        expr=expr,
        type_ref=return_type,
        effect=merge_effect_summaries(
            typed_provider.effect_summary,
            typed_prompt.effect_summary,
            *input_summaries,
            provider_summary,
        ),
    )


def typecheck_provider_bundle_path_expr(
    expr: ProviderBundlePathExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    typed_source = recurse(expr.source_expr)
    target_type = context.type_env.resolve_type(
        expr.target_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(target_type, PathTypeRef) or target_type.definition.kind != "relpath":
        raise_error(
            "`provider-bundle-path :as` must resolve to a relpath type",
            code="provider_bundle_path_target_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if ".." in target_type.definition.under.split("/"):
        raise_error(
            "`provider-bundle-path :as` may not escape the workspace",
            code="provider_bundle_path_target_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    value_expr_env = getattr(context.session_state, "value_expr_env", {})
    source_expr = None
    if isinstance(expr.source_expr, NameExpr):
        source_expr = value_expr_env.get(expr.source_expr.name)
        while isinstance(source_expr, NameExpr):
            source_expr = value_expr_env.get(source_expr.name)
    if not isinstance(source_expr, ProviderResultExpr):
        raise_error(
            "`provider-bundle-path` source must resolve to an in-scope provider-result binding",
            code="provider_bundle_path_source_invalid",
            span=expr.source_expr.span,
            form_path=expr.source_expr.form_path,
            expansion_stack=expr.source_expr.expansion_stack,
        )

    return typed_factory(
        expr=expr,
        type_ref=target_type,
        effect=typed_source.effect_summary,
    )


def typecheck_command_result_expr(
    expr: CommandResultExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    from .command_boundaries import (
        CertifiedAdapterBinding,
        certified_adapter_supports_promoted_calls,
    )
    from .contracts import is_transportable_result_type

    if is_macro_introduced_effect(expr.span, expr.expansion_stack):
        raise_required_lint(
            "macro expansion introduced a hidden command effect; move the `command-result` to authored workflow code",
            code="macro_hidden_effect",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    return_type = context.type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    from .result_guidance import validate_result_guidance_example

    validate_result_guidance_example(
        expr.return_spec.guidance,
        expected_type=return_type,
        type_env=context.type_env,
    )
    if not is_transportable_result_type(return_type):
        raise_error(
            f"`command-result` must return a transportable result type, got `{expr.returns_type_name}`",
            code="command_result_return_type_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    command_binding = None
    if context.command_boundary_environment is not None:
        binding_name = expr.adapter_name or expr.step_name
        command_binding = context.command_boundary_environment.bindings_by_name.get(binding_name)
        if command_binding is None:
            raise_error(
                f"`command-result` `{binding_name}` is missing command boundary metadata",
                code="command_adapter_missing_contract",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
    arg_summaries = []
    if expr.adapter_name is not None:
        if not isinstance(command_binding, CertifiedAdapterBinding) or not certified_adapter_supports_promoted_calls(
            command_binding
        ):
            raise_error(
                f"`command-result` adapter `{expr.adapter_name}` is missing promoted declaration metadata",
                code="command_adapter_missing_contract",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        validate_semantic_command_adapter_usage(expr, command_binding)
        if command_binding.output_type_name != expr.returns_type_name:
            raise_error(
                f"`command-result` `{expr.step_name}` must return `{command_binding.output_type_name}`",
                code="command_result_return_type_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        typed_inputs = {
            field_name: recurse(value_expr)
            for field_name, value_expr in expr.adapter_inputs
        }
        arg_summaries.extend(typed_input.effect_summary for typed_input in typed_inputs.values())
        expected_fields = {field.name: field for field in command_binding.input_signature}
        missing_fields = tuple(
            field.name
            for field in command_binding.input_signature
            if field.required and field.name not in typed_inputs
        )
        if missing_fields:
            raise_error(
                f"`command-result` adapter `{expr.adapter_name}` is missing required inputs: {', '.join(missing_fields)}",
                code="command_result_adapter_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        extra_fields = tuple(name for name in typed_inputs if name not in expected_fields)
        if extra_fields:
            raise_error(
                f"`command-result` adapter `{expr.adapter_name}` declares unknown inputs: {', '.join(extra_fields)}",
                code="command_result_adapter_invalid",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
        for field_name, typed_input in typed_inputs.items():
            declared_field = expected_fields[field_name]
            expected_type = context.type_env.resolve_type(
                declared_field.type_name,
                span=expr.span,
                form_path=expr.form_path,
            )
            if not type_refs_compatible(expected_type, typed_input.type_ref):
                raise_error(
                    f"`command-result` adapter `{expr.adapter_name}` input `{field_name}` must resolve to `{declared_field.type_name}`",
                    code="type_mismatch",
                    span=typed_input.expr.span,
                    form_path=typed_input.expr.form_path,
                    expansion_stack=typed_input.expr.expansion_stack,
                )
            _validate_adapter_input_projectable(
                field_name=field_name,
                typed_input=typed_input,
            )
    else:
        for arg_expr in expr.argv:
            typed_arg = recurse(arg_expr)
            arg_summaries.append(typed_arg.effect_summary)
        if command_binding is not None:
            validate_command_argv(expr, command_binding)
        else:
            validate_command_argv(expr, None)
        if isinstance(command_binding, CertifiedAdapterBinding):
            validate_semantic_command_adapter_usage(expr, command_binding)
            if command_binding.output_type_name != expr.returns_type_name:
                raise_error(
                    f"`command-result` `{expr.step_name}` must return `{command_binding.output_type_name}`",
                    code="command_result_return_type_invalid",
                    span=expr.span,
                    form_path=expr.form_path,
                    expansion_stack=expr.expansion_stack,
                )
    command_summary = effect_summary_from_direct(
        direct_effects=(UsesCommandEffect(subject=(expr.step_name,)),)
    )
    return typed_factory(
        expr=expr,
        type_ref=return_type,
        effect=merge_effect_summaries(*arg_summaries, command_summary),
    )


def _validate_adapter_input_projectable(*, field_name: str, typed_input) -> None:
    if isinstance(typed_input.type_ref, PathTypeRef):
        return
    if isinstance(typed_input.type_ref, PrimitiveTypeRef) and typed_input.type_ref.name not in {
        "Json",
        "Provider",
        "Prompt",
    }:
        return
    raise_error(
        f"`command-result` adapter input `{field_name}` cannot lower through `json_object_positional_arg`",
        code="command_adapter_input_not_projectable",
        span=typed_input.expr.span,
        form_path=typed_input.expr.form_path,
        expansion_stack=typed_input.expr.expansion_stack,
    )
