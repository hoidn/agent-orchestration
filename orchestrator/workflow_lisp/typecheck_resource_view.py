"""Resource/view typecheck ownership for Workflow Lisp.

See `../../docs/design/workflow_lisp_frontend_specification.md` for the
declared/runtime-native `resource-transition` lane and the generated
`materialize-view` / `finalize-selected-item` stdlib contract.
"""

from __future__ import annotations

from .effects import (
    EMPTY_EFFECT_SUMMARY,
    MovesResourceEffect,
    UpdatesLedgerEffect,
    UsesCommandEffect,
    WriteEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import FinalizeSelectedItemExpr, MaterializeViewExpr, ResourceTransitionExpr
from .resource import (
    ensure_finalize_selected_item_inputs,
    ensure_item_context_type,
    ensure_resource_transition_members,
    ensure_resource_transition_resource_type,
)
from .typecheck_context import TypedExpr, raise_error, _type_label
from .type_env import (
    ListTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
)
from orchestrator.workflow.view_renderer import ViewRendererError, resolve_view_renderer


def _effect_subject(value: str) -> tuple[str, ...]:
    return tuple(segment for segment in value.split(".") if segment)


def _first_transition_runtime_forbidden_type(type_ref: TypeRef) -> str | None:
    if isinstance(type_ref, WorkflowRefTypeRef):
        return "WorkflowRef"
    if isinstance(type_ref, ProcRefTypeRef):
        return "ProcRef"
    if isinstance(type_ref, PrimitiveTypeRef) and type_ref.name in {"Json", "Provider", "Prompt"}:
        return type_ref.name
    if isinstance(type_ref, OptionalTypeRef):
        return _first_transition_runtime_forbidden_type(type_ref.item_type_ref)
    if hasattr(type_ref, "item_type_ref"):
        return _first_transition_runtime_forbidden_type(type_ref.item_type_ref)
    if hasattr(type_ref, "key_type_ref") and hasattr(type_ref, "value_type_ref"):
        return _first_transition_runtime_forbidden_type(type_ref.key_type_ref) or _first_transition_runtime_forbidden_type(
            type_ref.value_type_ref
        )
    if isinstance(type_ref, RecordTypeRef):
        for field_type in type_ref.field_types.values():
            forbidden = _first_transition_runtime_forbidden_type(field_type)
            if forbidden is not None:
                return forbidden
        return None
    if isinstance(type_ref, UnionTypeRef):
        for field_types in type_ref.variant_field_types.values():
            for field_type in field_types.values():
                forbidden = _first_transition_runtime_forbidden_type(field_type)
                if forbidden is not None:
                    return forbidden
        return None
    return None


def _materialize_view_path_contracts_compatible(
    target_type: PathTypeRef,
    returns_type: PathTypeRef,
) -> bool:
    return (
        target_type.definition.kind == returns_type.definition.kind
        and target_type.definition.under == returns_type.definition.under
    )


def typecheck_resource_transition_expr(
    expr: ResourceTransitionExpr,
    *,
    context,
    recurse,
    typed_factory,
) -> TypedExpr:
    type_env = context.type_env
    command_boundary_environment = context.command_boundary_environment

    if expr.spec.mode == "declared_transition":
        transition_def = type_env.resolve_transition_declaration(
            expr.spec.transition_ref_name or "",
            code="transition_unknown",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        resource_def = type_env.resolve_resource_declaration(
            expr.spec.resource_ref_name or "",
            code="transition_resource_unknown",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
        declared_resource = type_env.resolve_resource_declaration(
            transition_def.resource_name,
            code="transition_declaration_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
        if declared_resource != resource_def:
            raise_error(
                "declared transition resource does not match `resource-transition :resource`",
                code="transition_resource_kind_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        resource_state_type = type_env.resolve_type(
            resource_def.state_type_name,
            span=resource_def.span,
            form_path=resource_def.form_path,
        )
        if not isinstance(resource_state_type, RecordTypeRef):
            raise_error(
                "declared transition resources require record state types",
                code="transition_declaration_invalid",
                span=resource_def.span,
                form_path=resource_def.form_path,
            )
        forbidden = _first_transition_runtime_forbidden_type(resource_state_type)
        if forbidden is not None:
            raise_error(
                f"declared transition resource state cannot carry runtime-forbidden type `{forbidden}`",
                code="transition_declaration_invalid",
                span=resource_def.span,
                form_path=resource_def.form_path,
            )
        request_type = type_env.resolve_type(
            transition_def.request_type_name,
            span=transition_def.span,
            form_path=transition_def.form_path,
        )
        forbidden = _first_transition_runtime_forbidden_type(request_type)
        if forbidden is not None:
            raise_error(
                f"declared transition request type cannot carry runtime-forbidden type `{forbidden}`",
                code="transition_declaration_invalid",
                span=transition_def.span,
                form_path=transition_def.form_path,
            )
        result_type = type_env.resolve_type(
            transition_def.result_type_name,
            span=transition_def.span,
            form_path=transition_def.form_path,
        )
        typed_request = recurse(expr.spec.request_expr)
        if typed_request.type_ref != request_type:
            raise_error(
                f"`resource-transition :request` expected `{_type_label(request_type)}` but got `{_type_label(typed_request.type_ref)}`",
                code="transition_request_type_mismatch",
                span=expr.spec.request_expr.span,
                form_path=expr.spec.request_expr.form_path,
            )
        typed_expected_version = None
        if expr.spec.expected_version_expr is not None:
            typed_expected_version = recurse(expr.spec.expected_version_expr)
            if typed_expected_version.type_ref != PrimitiveTypeRef(name="String"):
                raise_error(
                    "`resource-transition :expect-version` must resolve to `String`",
                    code="transition_declaration_invalid",
                    span=expr.spec.expected_version_expr.span,
                    form_path=expr.spec.expected_version_expr.form_path,
                )
        transition_value_env = {
            "state": resource_state_type,
            "request": request_type,
        }
        for precondition_expr in transition_def.preconditions:
            typed_precondition = recurse(precondition_expr, value_env=transition_value_env)
            if typed_precondition.type_ref != PrimitiveTypeRef(name="Bool"):
                raise_error(
                    "declared transition preconditions must resolve to `Bool`",
                    code="transition_declaration_invalid",
                    span=precondition_expr.span,
                    form_path=precondition_expr.form_path,
                )
        for update in transition_def.updates:
            target_type = resource_state_type.field_types.get(update.target)
            if target_type is None:
                raise_error(
                    f"unknown transition update target `{update.target}`",
                    code="transition_update_target_unknown",
                    span=update.span,
                    form_path=update.form_path,
                )
            if update.op == "clear_field":
                if not isinstance(target_type, OptionalTypeRef):
                    raise_error(
                        f"`clear-field {update.target}` requires an `Optional` state field",
                        code="transition_declaration_invalid",
                        span=update.span,
                        form_path=update.form_path,
                    )
                continue
            assert update.value_expr is not None
            typed_value = recurse(update.value_expr, value_env=transition_value_env)
            expected_type = target_type.item_type_ref if update.op == "append_item" and isinstance(target_type, ListTypeRef) else target_type
            if typed_value.type_ref != expected_type:
                raise_error(
                    f"transition update `{update.target}` expected `{_type_label(expected_type)}` but got `{_type_label(typed_value.type_ref)}`",
                    code="transition_declaration_invalid",
                    span=update.value_expr.span,
                    form_path=update.value_expr.form_path,
                )
        typed_result_expr = recurse(transition_def.result_expr, value_env=transition_value_env)
        if typed_result_expr.type_ref != result_type:
            raise_error(
                f"declared transition result projection expected `{_type_label(result_type)}` but got `{_type_label(typed_result_expr.type_ref)}`",
                code="transition_result_projection_type_mismatch",
                span=transition_def.span,
                form_path=transition_def.form_path,
            )
        recurse(transition_def.audit_expr, value_env=transition_value_env)
        return typed_factory(
            expr=expr,
            type_ref=result_type,
            effect=merge_effect_summaries(
                typed_request.effect_summary,
                typed_expected_version.effect_summary if typed_expected_version is not None else EMPTY_EFFECT_SUMMARY,
                effect_summary_from_direct(
                    direct_effects=(
                        UsesCommandEffect(subject=("apply_resource_transition",)),
                    ),
                ),
            ),
        )
    resource_result = type_env.resolve_type(
        "ResourceTransitionResult",
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(resource_result, RecordTypeRef):
        raise_error(
            "`resource-transition` requires a record `ResourceTransitionResult` type",
            code="resource_transition_contract_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_ctx = recurse(expr.spec.ctx_expr)
    ensure_item_context_type(
        typed_ctx.type_ref,
        span=expr.spec.ctx_expr.span,
        form_path=expr.spec.ctx_expr.form_path,
    )
    typed_resource = recurse(expr.spec.resource_expr)
    ensure_resource_transition_resource_type(
        typed_resource.type_ref,
        span=expr.spec.resource_expr.span,
        form_path=expr.spec.resource_expr.form_path,
    )
    typed_ledger = recurse(expr.spec.ledger_expr)
    typed_when = None
    if expr.spec.when_expr is not None:
        typed_when = recurse(expr.spec.when_expr)
        if typed_when.type_ref != PrimitiveTypeRef(name="Bool"):
            raise_error(
                "`resource-transition :when` must resolve to `Bool`",
                code="type_mismatch",
                span=expr.spec.when_expr.span,
                form_path=expr.spec.when_expr.form_path,
            )
    if not isinstance(typed_ledger.type_ref, PathTypeRef) or typed_ledger.type_ref.definition.under != "state":
        raise_error(
            "`resource-transition :ledger` must be a relpath under `state`",
            code="resource_transition_contract_invalid",
            span=expr.spec.ledger_expr.span,
            form_path=expr.spec.ledger_expr.form_path,
        )
    transition_binding = (
        None
        if command_boundary_environment is None
        else command_boundary_environment.bindings_by_name.get("apply_resource_transition")
    )
    if (
        transition_binding is None
        or getattr(transition_binding, "output_type_name", None) != "ResourceTransitionResult"
        or getattr(transition_binding, "effects", ()) != ("resource_transition", "ledger_update")
    ):
        raise_error(
            "`resource-transition` requires the certified `apply_resource_transition` adapter",
            code="command_adapter_missing_contract",
            span=expr.span,
            form_path=expr.form_path,
        )
    ensure_resource_transition_members(
        resource_result,
        type_env=type_env,
        from_queue_name=expr.spec.from_queue_name,
        to_queue_name=expr.spec.to_queue_name,
        event_name=expr.spec.event_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    return typed_factory(
        expr=expr,
        type_ref=resource_result,
        effect=merge_effect_summaries(
            typed_ctx.effect_summary,
            typed_resource.effect_summary,
            typed_ledger.effect_summary,
            typed_when.effect_summary if typed_when is not None else EMPTY_EFFECT_SUMMARY,
            effect_summary_from_direct(
                direct_effects=(
                    UsesCommandEffect(subject=("apply_resource_transition",)),
                    MovesResourceEffect(
                        subject=_effect_subject(expr.spec.transition_name),
                        from_queue=_effect_subject(expr.spec.from_queue_name),
                        to_queue=_effect_subject(expr.spec.to_queue_name),
                    ),
                    UpdatesLedgerEffect(
                        subject=_effect_subject(expr.spec.transition_name),
                        event_name=_effect_subject(expr.spec.event_name),
                    ),
                ),
            ),
        ),
    )


def typecheck_materialize_view_expr(
    expr: MaterializeViewExpr,
    *,
    context,
    recurse,
    typed_factory,
) -> TypedExpr:
    type_env = context.type_env

    typed_value = recurse(expr.value_expr)
    returns_type = type_env.resolve_type(
        expr.returns_type_name,
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(returns_type, PathTypeRef):
        raise_error(
            "`materialize-view :returns` must resolve to a path type",
            code="materialize_view_target_contract_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    try:
        descriptor = resolve_view_renderer(expr.renderer_id, expr.renderer_version)
    except ViewRendererError:
        raise_error(
            f"unknown materialize-view renderer `{expr.renderer_id}` v{expr.renderer_version}",
            code="materialize_view_renderer_unknown",
            span=expr.span,
            form_path=expr.form_path,
        )
    forbidden = _first_transition_runtime_forbidden_type(typed_value.type_ref)
    if forbidden is not None:
        raise_error(
            f"`materialize-view :value` cannot carry runtime-forbidden type `{forbidden}`",
            code="materialize_view_value_type_invalid",
            span=expr.value_expr.span,
            form_path=expr.value_expr.form_path,
        )
    if descriptor.accepted_shape == "path_value" and not isinstance(typed_value.type_ref, PathTypeRef):
        raise_error(
            "`materialize-view` path-line rendering requires a path-typed value",
            code="materialize_view_value_type_invalid",
            span=expr.value_expr.span,
            form_path=expr.value_expr.form_path,
        )
    typed_target = None
    if expr.target_expr is not None:
        typed_target = recurse(expr.target_expr)
        if not isinstance(typed_target.type_ref, PathTypeRef) or not _materialize_view_path_contracts_compatible(
            typed_target.type_ref,
            returns_type,
        ):
            raise_error(
                "`materialize-view :target` must be a compatible path contract for `:returns`",
                code="materialize_view_target_contract_invalid",
                span=expr.target_expr.span,
                form_path=expr.target_expr.form_path,
            )
    return typed_factory(
        expr=expr,
        type_ref=returns_type,
        effect=merge_effect_summaries(
            typed_value.effect_summary,
            typed_target.effect_summary if typed_target is not None else EMPTY_EFFECT_SUMMARY,
            effect_summary_from_direct(
                direct_effects=(
                    WriteEffect(subject=_effect_subject(expr.view_name)),
                ),
            ),
        ),
    )


def typecheck_finalize_selected_item_expr(
    expr: FinalizeSelectedItemExpr,
    *,
    context,
    recurse,
    typed_factory,
) -> TypedExpr:
    type_env = context.type_env

    selected_item_result = type_env.resolve_type(
        "SelectedItemResult",
        span=expr.span,
        form_path=expr.form_path,
    )
    if not isinstance(selected_item_result, UnionTypeRef):
        raise_error(
            "`finalize-selected-item` requires a union `SelectedItemResult` type",
            code="finalize_selected_item_contract_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    typed_ctx = recurse(expr.spec.ctx_expr)
    ensure_item_context_type(
        typed_ctx.type_ref,
        span=expr.spec.ctx_expr.span,
        form_path=expr.spec.ctx_expr.form_path,
    )
    typed_selected = recurse(expr.spec.selected_expr)
    typed_queue_transition = recurse(expr.spec.queue_transition_expr)
    expected_transition = type_env.resolve_type(
        "ResourceTransitionResult",
        span=expr.span,
        form_path=expr.form_path,
    )
    if typed_queue_transition.type_ref != expected_transition:
        raise_error(
            "`finalize-selected-item :queue-transition` must resolve to `ResourceTransitionResult`",
            code="finalize_selected_item_contract_invalid",
            span=expr.spec.queue_transition_expr.span,
            form_path=expr.spec.queue_transition_expr.form_path,
        )
    typed_roadmap = recurse(expr.spec.roadmap_expr)
    typed_plan = recurse(expr.spec.plan_expr)
    typed_implementation = recurse(expr.spec.implementation_expr)
    if not isinstance(typed_plan.type_ref, UnionTypeRef) or not isinstance(typed_implementation.type_ref, UnionTypeRef):
        raise_error(
            "`finalize-selected-item` requires union plan and implementation results",
            code="finalize_selected_item_contract_invalid",
            span=expr.span,
            form_path=expr.form_path,
        )
    ensure_finalize_selected_item_inputs(
        type_env=type_env,
        selected_type=typed_selected.type_ref,
        roadmap_type=typed_roadmap.type_ref,
        plan_type=typed_plan.type_ref,
        implementation_type=typed_implementation.type_ref,
        span=expr.span,
        form_path=expr.form_path,
    )
    return typed_factory(
        expr=expr,
        type_ref=selected_item_result,
        effect=merge_effect_summaries(
            typed_ctx.effect_summary,
            typed_selected.effect_summary,
            typed_queue_transition.effect_summary,
            typed_roadmap.effect_summary,
            typed_plan.effect_summary,
            typed_implementation.effect_summary,
        ),
    )
