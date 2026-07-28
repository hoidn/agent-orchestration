"""Effect-bearing typecheck ownership for Workflow Lisp."""

from __future__ import annotations

from dataclasses import replace

from .diagnostics import build_authored_phased_delivery_diagnostic
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    LivePeerMessagingEffect,
    LiveSupervisionEffect,
    UsesCommandEffect,
    UsesProviderEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import (
    CommandResultExpr,
    EnumMemberExpr,
    ExprNode,
    FieldAccessExpr,
    LiveProviderPeerBinding,
    LiveProviderBinding,
    LiteralExpr,
    NameExpr,
    ProviderBundlePathExpr,
    ProviderResultExpr,
    WithLiveProviderPeersExpr,
    WithLiveProvidersExpr,
)
from .syntax import (
    MAX_STATIC_LIVE_PROVIDER_PEERS,
    PROVIDER_STEERING_DIRECTIVE_TYPE_NAME,
    target_dsl_supports_provider_peer_messaging,
    target_dsl_supports_provider_supervision,
    target_dsl_supports_phased_contract_delivery,
)
from .phase import is_implementation_attempt_result_type
from .prompts import (
    PromptApplicationExpr,
    typecheck_prompt_application,
    with_phased_prompt_attempt_identity,
)
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


def typecheck_with_live_providers_expr(
    expr: WithLiveProvidersExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    """Type one bounded live-provider group and infer its ownership effect."""

    if not target_dsl_supports_provider_supervision(
        context.type_env.target_dsl_version
    ):
        raise_error(
            "`with-live-providers` requires target DSL 2.16 or newer",
            code="provider_supervision_target_dsl_unsupported",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    supervisor_binding, worker_binding = _validated_live_provider_roles(expr)

    typed_members = {
        binding.name: recurse(binding.value_expr)
        for binding in expr.bindings
    }
    typed_supervisor = typed_members[supervisor_binding.name]
    typed_worker = typed_members[worker_binding.name]

    directive_type = context.type_env.resolve_type(
        PROVIDER_STEERING_DIRECTIVE_TYPE_NAME,
        span=supervisor_binding.value_expr.span,
        form_path=supervisor_binding.value_expr.form_path,
        expansion_stack=supervisor_binding.value_expr.expansion_stack,
    )
    if (
        not isinstance(typed_supervisor.type_ref, UnionTypeRef)
        or typed_supervisor.type_ref != directive_type
    ):
        raise_error(
            (
                "the observing provider must return the exact compiler-owned "
                f"`{PROVIDER_STEERING_DIRECTIVE_TYPE_NAME}` union"
            ),
            code="provider_supervision_supervisor_type_invalid",
            span=supervisor_binding.value_expr.span,
            form_path=supervisor_binding.value_expr.form_path,
            expansion_stack=supervisor_binding.value_expr.expansion_stack,
        )

    from .contracts import is_transportable_result_type

    if not is_transportable_result_type(typed_worker.type_ref):
        raise_error(
            "the observed provider must return a transportable result type",
            code="provider_supervision_worker_type_invalid",
            span=worker_binding.value_expr.span,
            form_path=worker_binding.value_expr.form_path,
            expansion_stack=worker_binding.value_expr.expansion_stack,
        )

    typed_body = recurse(
        expr.body,
        value_env={
            **context.value_env,
            **{
                binding.name: typed_members[binding.name].type_ref
                for binding in expr.bindings
            },
        },
    )
    body_effects = typed_body.effect_summary
    if (
        body_effects.direct_effects
        or body_effects.transitive_effects
        or body_effects.procedure_edges
    ):
        raise_error(
            "`with-live-providers` settlement body must be pure",
            code="provider_supervision_settlement_effectful",
            span=expr.body.span,
            form_path=expr.body.form_path,
            expansion_stack=expr.body.expansion_stack,
        )

    rewritten_bindings = tuple(
        replace(
            binding,
            value_expr=typed_members[binding.name].expr,
        )
        for binding in expr.bindings
    )
    live_summary = effect_summary_from_direct(
        direct_effects=(
            LiveSupervisionEffect(
                supervisor=supervisor_binding.name,
                worker=worker_binding.name,
            ),
        )
    )
    return typed_factory(
        expr=replace(
            expr,
            bindings=rewritten_bindings,
            body=typed_body.expr,
        ),
        type_ref=typed_body.type_ref,
        effect=merge_effect_summaries(
            *(typed_member.effect_summary for typed_member in typed_members.values()),
            typed_body.effect_summary,
            live_summary,
        ),
    )


def typecheck_with_live_provider_peers_expr(
    expr: WithLiveProviderPeersExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    """Type one static provider peer group and infer its ownership effect."""

    if not target_dsl_supports_provider_peer_messaging(
        context.type_env.target_dsl_version
    ):
        raise_error(
            (
                "`with-live-provider-peers` requires target DSL "
                "2.17 or newer"
            ),
            code="provider_peer_messaging_target_dsl_unsupported",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    bindings = _validated_live_provider_peer_bindings(expr)
    typed_members = {
        binding.name: recurse(binding.value_expr)
        for binding in bindings
    }

    from .contracts import is_transportable_result_type

    for binding in bindings:
        typed_member = typed_members[binding.name]
        if not is_transportable_result_type(typed_member.type_ref):
            raise_error(
                (
                    f"provider-peer member `{binding.name}` must return "
                    "a transportable result type"
                ),
                code="provider_peer_messaging_member_type_invalid",
                span=binding.value_expr.span,
                form_path=binding.value_expr.form_path,
                expansion_stack=(
                    binding.value_expr.expansion_stack
                ),
            )

    typed_body = recurse(
        expr.body,
        value_env={
            binding.name: typed_members[binding.name].type_ref
            for binding in bindings
        },
    )
    body_effects = typed_body.effect_summary
    if (
        body_effects.direct_effects
        or body_effects.transitive_effects
        or body_effects.procedure_edges
    ):
        raise_error(
            (
                "`with-live-provider-peers` settlement body must be "
                "pure"
            ),
            code="provider_peer_messaging_settlement_effectful",
            span=expr.body.span,
            form_path=expr.body.form_path,
            expansion_stack=expr.body.expansion_stack,
        )
    if not is_transportable_result_type(typed_body.type_ref):
        raise_error(
            (
                "`with-live-provider-peers` settlement must return a "
                "transportable result type"
            ),
            code="provider_peer_messaging_settlement_type_invalid",
            span=expr.body.span,
            form_path=expr.body.form_path,
            expansion_stack=expr.body.expansion_stack,
        )

    rewritten_bindings = tuple(
        replace(
            binding,
            value_expr=typed_members[binding.name].expr,
        )
        for binding in bindings
    )
    live_summary = effect_summary_from_direct(
        direct_effects=(
            LivePeerMessagingEffect(
                members=tuple(
                    binding.name for binding in bindings
                ),
            ),
        )
    )
    return typed_factory(
        expr=replace(
            expr,
            bindings=rewritten_bindings,
            body=typed_body.expr,
        ),
        type_ref=typed_body.type_ref,
        effect=merge_effect_summaries(
            *(
                typed_members[binding.name].effect_summary
                for binding in bindings
            ),
            typed_body.effect_summary,
            live_summary,
        ),
    )


def _validated_live_provider_peer_bindings(
    expr: WithLiveProviderPeersExpr,
) -> tuple[LiveProviderPeerBinding, ...]:
    """Revalidate exported peer AST invariants before type selection."""

    if not 2 <= len(expr.bindings) <= MAX_STATIC_LIVE_PROVIDER_PEERS:
        raise_error(
            (
                "`with-live-provider-peers` requires between two and "
                f"{MAX_STATIC_LIVE_PROVIDER_PEERS} bindings"
            ),
            code="with_live_provider_peers_bindings_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    seen_names: set[str] = set()
    for binding in expr.bindings:
        if binding.name in seen_names:
            raise_error(
                f"duplicate provider-peer binding `{binding.name}`",
                code="with_live_provider_peers_binding_duplicate",
                span=binding.name_span,
                form_path=binding.form_path,
                expansion_stack=binding.expansion_stack,
            )
        seen_names.add(binding.name)
    return expr.bindings


def _validated_live_provider_roles(
    expr: WithLiveProvidersExpr,
) -> tuple[LiveProviderBinding, LiveProviderBinding]:
    """Revalidate exported AST invariants before selecting member roles."""

    if len(expr.bindings) != 2:
        raise_error(
            "`with-live-providers` requires exactly two bindings",
            code="with_live_providers_bindings_invalid",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    seen_names: set[str] = set()
    for binding in expr.bindings:
        if binding.name in seen_names:
            raise_error(
                f"duplicate live-provider binding `{binding.name}`",
                code="with_live_providers_binding_duplicate",
                span=binding.name_span,
                form_path=binding.form_path,
                expansion_stack=binding.expansion_stack,
            )
        seen_names.add(binding.name)

    observers = tuple(
        binding for binding in expr.bindings if binding.observes is not None
    )
    if not observers:
        raise_error(
            "`with-live-providers` requires exactly one `:observes` edge",
            code="with_live_providers_observation_missing",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    if len(observers) != 1:
        duplicate = observers[1]
        raise_error(
            "`with-live-providers` permits exactly one `:observes` edge",
            code="with_live_providers_observation_duplicate",
            span=duplicate.observes_span or duplicate.span,
            form_path=duplicate.form_path,
            expansion_stack=duplicate.expansion_stack,
        )

    supervisor_binding = observers[0]
    worker_binding = next(
        (
            binding
            for binding in expr.bindings
            if binding.name == supervisor_binding.observes
            and binding is not supervisor_binding
        ),
        None,
    )
    if worker_binding is None:
        raise_error(
            "`:observes` must name the sibling live-provider binding",
            code="with_live_providers_observed_peer_invalid",
            span=(
                supervisor_binding.observed_name_span
                or supervisor_binding.span
            ),
            form_path=supervisor_binding.form_path,
            expansion_stack=supervisor_binding.expansion_stack,
        )
    return supervisor_binding, worker_binding


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

    def phased_diagnostic(
        reason: str,
        *,
        canonical_value: bool | int | str | None,
        primary_owner: str,
        primary_span,
    ):
        return build_authored_phased_delivery_diagnostic(
            reason,
            canonical_value=canonical_value,
            source_spans_by_owner={
                primary_owner: primary_span,
                "provider_application": expr.span,
            },
        )

    if is_macro_introduced_effect(expr.span, expr.expansion_stack):
        raise_required_lint(
            "macro expansion introduced a hidden provider effect; move the `provider-result` to authored workflow code",
            code="macro_hidden_effect",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    return_type = (
        expr.prompt.prompt.return_type_ref
        if isinstance(expr.prompt, PromptApplicationExpr)
        else context.type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
        )
    )
    typed_prompt_application = None
    prompt_fill_summaries = ()
    if isinstance(expr.prompt, PromptApplicationExpr):
        (
            typed_prompt_application,
            prompt_fill_summaries,
        ) = typecheck_prompt_application(
            expr.prompt,
            recurse=recurse,
            type_env=context.type_env,
        )
        if expr.prompt.return_redeclaration_span is not None:
            raise_error(
                "fragment-backed provider calls cannot redeclare `:returns`",
                code="prompt_return_redeclaration_forbidden",
                span=expr.prompt.return_redeclaration_span,
                form_path=expr.form_path,
                expansion_stack=expr.prompt.return_redeclaration_expansion_stack,
            )
    delivery = (
        expr.delivery.value
        if isinstance(expr.delivery, LiteralExpr)
        and expr.delivery.literal_kind == "string"
        and isinstance(expr.delivery.value, str)
        else None
    )
    phased = delivery == "phased"
    if expr.delivery is not None:
        if not target_dsl_supports_phased_contract_delivery(
            context.type_env.target_dsl_version
        ):
            raise_error(
                "`provider-result :delivery` requires target DSL 2.23",
                code="provider_phased_delivery_requires_dsl_2_23",
                span=expr.delivery.span,
                form_path=expr.delivery.form_path,
                expansion_stack=expr.delivery.expansion_stack,
                phased_delivery_diagnostic=phased_diagnostic(
                    "target_below_2_23",
                    canonical_value=context.type_env.target_dsl_version,
                    primary_owner="delivery_keyword",
                    primary_span=expr.delivery.span,
                ),
            )
        if delivery not in {"composed", "phased"}:
            reason = (
                "delivery_enum_invalid"
                if isinstance(expr.delivery, LiteralExpr)
                and expr.delivery.literal_kind == "string"
                else "delivery_type_invalid"
            )
            raise_error(
                "`provider-result :delivery` must be the literal :composed or :phased",
                code="provider_phased_delivery_policy_invalid",
                span=expr.delivery.span,
                form_path=expr.delivery.form_path,
                expansion_stack=expr.delivery.expansion_stack,
                phased_delivery_diagnostic=phased_diagnostic(
                    reason,
                    canonical_value=None,
                    primary_owner="delivery_keyword",
                    primary_span=expr.delivery.span,
                ),
            )
    attempts = expr.materialization_attempts
    if attempts is not None:
        if (
            not isinstance(attempts, LiteralExpr)
            or attempts.literal_kind != "int"
            or isinstance(attempts.value, bool)
            or not isinstance(attempts.value, int)
            or attempts.value not in {1, 2, 3}
        ):
            if not isinstance(attempts, LiteralExpr):
                reason = "attempts_literal_required"
                canonical_attempts = None
            elif (
                attempts.literal_kind != "int"
                or isinstance(attempts.value, bool)
                or not isinstance(attempts.value, int)
            ):
                reason = "attempts_type_invalid"
                canonical_attempts = None
            else:
                reason = "attempts_out_of_range"
                canonical_attempts = (
                    attempts.value
                    if -(2**63) <= attempts.value <= 2**63 - 1
                    else None
                )
            raise_error(
                "`provider-result :materialization-attempts` requires an integer literal in 1..3",
                code="provider_phased_delivery_policy_invalid",
                span=attempts.span,
                form_path=attempts.form_path,
                expansion_stack=attempts.expansion_stack,
                phased_delivery_diagnostic=phased_diagnostic(
                    reason,
                    canonical_value=canonical_attempts,
                    primary_owner="materialization_attempts_keyword",
                    primary_span=attempts.span,
                ),
            )
        if not phased:
            raise_error(
                "`provider-result :materialization-attempts` requires :delivery :phased",
                code="provider_phased_delivery_policy_invalid",
                span=attempts.span,
                form_path=attempts.form_path,
                expansion_stack=attempts.expansion_stack,
                phased_delivery_diagnostic=phased_diagnostic(
                    "attempts_pairing_invalid",
                    canonical_value=None,
                    primary_owner="materialization_attempts_keyword",
                    primary_span=attempts.span,
                ),
            )
    if phased and typed_prompt_application is None:
        raise_error(
            "`provider-result :delivery :phased` requires a prompt fragment application",
            code="provider_phased_delivery_policy_invalid",
            span=expr.delivery.span,
            form_path=expr.delivery.form_path,
            expansion_stack=expr.delivery.expansion_stack,
            phased_delivery_diagnostic=phased_diagnostic(
                "fragment_application_required",
                canonical_value=None,
                primary_owner="fragment_contract",
                primary_span=expr.prompt.span,
            ),
        )
    if (
        phased
        and isinstance(return_type, RecordTypeRef)
        and not return_type.field_types
    ):
        raise_error(
            "contract_suffix_required: phased delivery requires a non-empty generated result contract",
            code="provider_phased_delivery_policy_invalid",
            span=expr.prompt.span,
            form_path=expr.prompt.form_path,
            expansion_stack=expr.prompt.expansion_stack,
            phased_delivery_diagnostic=phased_diagnostic(
                "contract_suffix_required",
                canonical_value=None,
                primary_owner="result_contract_suffix",
                primary_span=(
                    expr.prompt.prompt.declaration.return_spec.span
                    if isinstance(expr.prompt, PromptApplicationExpr)
                    else expr.prompt.span
                ),
            ),
        )
    if phased:
        typed_prompt_application = with_phased_prompt_attempt_identity(
            typed_prompt_application
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
    if typed_prompt_application is not None:
        typed_prompt = typed_factory(
            expr=typed_prompt_application,
            type_ref=PrimitiveTypeRef(name="Prompt"),
            effect=merge_effect_summaries(*prompt_fill_summaries),
        )
    else:
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
    if typed_prompt_application is None:
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
    policy_summaries = []
    for field_name, policy_expr in (("model", expr.model), ("effort", expr.effort)):
        if policy_expr is None:
            continue
        typed_policy = recurse(policy_expr)
        if typed_policy.type_ref != PrimitiveTypeRef(name="String"):
            raise_error(
                f"`provider-result :{field_name}` must have type `String`",
                code=f"provider_result_{field_name}_type_invalid",
                span=policy_expr.span,
                form_path=policy_expr.form_path,
                expansion_stack=policy_expr.expansion_stack,
            )
        if (
            not isinstance(policy_expr, (LiteralExpr, NameExpr, FieldAccessExpr))
            or typed_policy.effect_summary.direct_effects
            or typed_policy.effect_summary.transitive_effects
        ):
            raise_error(
                f"`provider-result :{field_name}` must use an inline-lowerable String operand",
                code="provider_result_policy_operand_not_inline_lowerable",
                span=policy_expr.span,
                form_path=policy_expr.form_path,
                expansion_stack=policy_expr.expansion_stack,
            )
        policy_summaries.append(typed_policy.effect_summary)
    if expr.timeout_sec is not None:
        typed_timeout = recurse(expr.timeout_sec)
        if not isinstance(expr.timeout_sec, LiteralExpr):
            raise_error(
                "`provider-result :timeout-sec` requires an integer literal",
                code="provider_result_timeout_literal_required",
                span=expr.timeout_sec.span,
                form_path=expr.timeout_sec.form_path,
                expansion_stack=expr.timeout_sec.expansion_stack,
            )
        if typed_timeout.type_ref != PrimitiveTypeRef(name="Int"):
            raise_error(
                "`provider-result :timeout-sec` literal must have type `Int`",
                code="provider_result_timeout_type_invalid",
                span=expr.timeout_sec.span,
                form_path=expr.timeout_sec.form_path,
                expansion_stack=expr.timeout_sec.expansion_stack,
            )
        if not isinstance(expr.timeout_sec.value, int) or isinstance(expr.timeout_sec.value, bool):
            raise_error(
                "`provider-result :timeout-sec` literal must have type `Int`",
                code="provider_result_timeout_type_invalid",
                span=expr.timeout_sec.span,
                form_path=expr.timeout_sec.form_path,
                expansion_stack=expr.timeout_sec.expansion_stack,
            )
        if expr.timeout_sec.value <= 0:
            raise_error(
                "`provider-result :timeout-sec` must be greater than zero",
                code="provider_result_timeout_nonpositive",
                span=expr.timeout_sec.span,
                form_path=expr.timeout_sec.form_path,
                expansion_stack=expr.timeout_sec.expansion_stack,
            )
        policy_summaries.append(typed_timeout.effect_summary)
    prompt_dependency_summaries = []
    if expr.prompt_dependencies is not None:
        for dependency_expr in (
            *expr.prompt_dependencies.required,
            *expr.prompt_dependencies.optional,
        ):
            dependency_extern_name = _extern_operand_name(dependency_expr)
            dependency_extern = (
                context.extern_environment.bindings_by_name.get(dependency_extern_name)
                if dependency_extern_name is not None and context.extern_environment is not None
                else None
            )
            if isinstance(dependency_extern, ProviderExtern):
                typed_dependency = typed_factory(
                    expr=dependency_expr,
                    type_ref=PrimitiveTypeRef(name="Provider"),
                    effect=EMPTY_EFFECT_SUMMARY,
                )
            elif isinstance(dependency_extern, PromptExtern):
                typed_dependency = typed_factory(
                    expr=dependency_expr,
                    type_ref=PrimitiveTypeRef(name="Prompt"),
                    effect=EMPTY_EFFECT_SUMMARY,
                )
            else:
                typed_dependency = recurse(dependency_expr)
            if (
                not isinstance(typed_dependency.type_ref, PathTypeRef)
                or typed_dependency.type_ref.definition.kind != "relpath"
            ):
                raise_error(
                    "prompt dependency operands must resolve to a relpath type",
                    code="prompt_dependency_operand_type_invalid",
                    span=dependency_expr.span,
                    form_path=dependency_expr.form_path,
                    expansion_stack=dependency_expr.expansion_stack,
                )
            if (
                not isinstance(dependency_expr, (NameExpr, FieldAccessExpr))
                or typed_dependency.effect_summary.direct_effects
                or typed_dependency.effect_summary.transitive_effects
            ):
                raise_error(
                    "prompt dependency operands must be inline-lowerable references",
                    code="prompt_dependency_operand_not_inline_lowerable",
                    span=dependency_expr.span,
                    form_path=dependency_expr.form_path,
                    expansion_stack=dependency_expr.expansion_stack,
                )
            prompt_dependency_summaries.append(typed_dependency.effect_summary)
    input_summaries = []
    for input_expr in expr.inputs:
        typed_input = recurse(input_expr)
        input_summaries.append(typed_input.effect_summary)
    provider_name = provider_extern_name or "provider-result"
    provider_summary = effect_summary_from_direct(
        direct_effects=(UsesProviderEffect(subject=tuple(provider_name.split("."))),)
    )
    return typed_factory(
        expr=(
            replace(expr, prompt=typed_prompt_application)
            if typed_prompt_application is not None
            else expr
        ),
        type_ref=return_type,
        effect=merge_effect_summaries(
            typed_provider.effect_summary,
            typed_prompt.effect_summary,
            *policy_summaries,
            *prompt_dependency_summaries,
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
