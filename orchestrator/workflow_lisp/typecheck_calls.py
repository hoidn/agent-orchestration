"""Call-family typing ownership for Workflow Lisp."""

from __future__ import annotations

from .context_classification import classify_structural_private_exec_context
from .diagnostics import LispFrontendCompileError
from .effects import (
    EMPTY_EFFECT_SUMMARY,
    CallsWorkflowEffect,
    ProcedureCallEdge,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import CallExpr, EnumMemberExpr, ExprNode, FunctionCallExpr, NameExpr, WorkflowRefLiteralExpr
from .phase import (
    PHASE_CONTEXT_NAME,
    derived_private_child_context_eligibility,
    private_exec_context_kind,
)
from .procedure_refs import (
    ProcRefResolutionContext,
    ResolvedProcRefValue,
    resolve_proc_ref_name,
    resolve_proc_ref_value,
)
from .type_env import (
    FrontendTypeEnvironment,
    PathTypeRef,
    PrimitiveTypeRef,
    ProcRefTypeRef,
    RecordTypeRef,
    TypeRef,
    UnionTypeRef,
    WorkflowRefTypeRef,
    type_refs_compatible,
)
from .workflow_refs import (
    resolve_workflow_ref_name,
    workflow_ref_target_name,
    workflow_ref_type_from_signature,
)

def hidden_context_omission_allowed(
    *,
    session_state,
    callee_signature,
    param_name: str,
    expected_type: TypeRef,
    span,
    form_path: tuple[str, ...],
) -> bool:
    from . import typecheck as compat

    active_signature = session_state.workflow_signature
    if callee_signature is None or active_signature is None:
        return False
    if not isinstance(expected_type, RecordTypeRef):
        return False
    if (
        private_exec_context_kind(expected_type) is None
        and classify_structural_private_exec_context(expected_type) is None
    ):
        return False

    ambiguities = getattr(callee_signature, "hidden_context_ambiguities", {})
    requirements = getattr(callee_signature, "hidden_context_requirements", {})
    requirement = requirements.get(param_name) if isinstance(requirements, dict) else None
    active_has_private_context_source = any(
        private_exec_context_kind(type_ref) is not None
        or classify_structural_private_exec_context(type_ref) is not None
        for _, type_ref in active_signature.params
    )
    if requirement is not None and requirement.binding_kind == "derived_private_child_context":
        if requirement.phase_name is None or param_name in ambiguities:
            compat._raise_error(
                f"derived child phase context for `{param_name}` is ambiguous in this callee",
                code="derived_phase_context_ambiguous",
                span=span,
                form_path=form_path,
            )
        eligibility = derived_private_child_context_eligibility(
            active_signature,
            param_name=param_name,
        )
        if not eligibility.allowed:
            allowed_callees = getattr(active_signature, "allowed_hidden_context_callees", frozenset())
            if requirement.allows_entry_bootstrap and (
                callee_signature.name in allowed_callees
                or not active_has_private_context_source
            ):
                return True
            compat._raise_error(
                eligibility.diagnostic_message or f"invalid derived child phase context for `{param_name}`",
                code=eligibility.diagnostic_code or "derived_phase_context_binding_invalid",
                span=span,
                form_path=form_path,
            )
        return True

    allowed_callees = getattr(active_signature, "allowed_hidden_context_callees", frozenset())
    if (
        requirement is not None
        and requirement.context_kind == PHASE_CONTEXT_NAME
        and requirement.phase_name is not None
    ):
        eligibility = derived_private_child_context_eligibility(
            active_signature,
            param_name=param_name,
        )
        if eligibility.allowed:
            return True
        if callee_signature.name in allowed_callees:
            return True
        if not active_has_private_context_source:
            return True
        compat._raise_error(
            eligibility.diagnostic_message or f"invalid derived child phase context for `{param_name}`",
            code=eligibility.diagnostic_code or "derived_phase_context_binding_invalid",
            span=span,
            form_path=form_path,
        )

    if callee_signature.name not in allowed_callees:
        return False

    if param_name in ambiguities:
        phase_names = ambiguities[param_name]
        compat._raise_error(
            (
                f"promoted-entry hidden `{param_name}` binding is ambiguous across phases "
                f"`{phase_names[0]}` and `{phase_names[-1]}`"
            ),
            code="promoted_entry_hidden_phase_ctx_ambiguous",
            span=span,
            form_path=form_path,
        )

    if requirement is None:
        compat._raise_error(
            f"promoted-entry hidden binding for `{param_name}` is unavailable in this callee",
            code="promoted_entry_hidden_context_binding_invalid",
            span=span,
            form_path=form_path,
        )
    return True


def compatibility_bridge_omission_allowed(
    *,
    session_state,
    callee_signature,
    param_name: str,
) -> bool:
    active_signature = session_state.workflow_signature
    if active_signature is None or callee_signature is None:
        return False
    if param_name not in getattr(callee_signature, "private_compatibility_bridge_types", {}):
        return False
    if not getattr(active_signature, "allow_private_compatibility_bridge_omission", False):
        return False
    return callee_signature.name in getattr(
        active_signature,
        "allowed_private_compatibility_bridge_callees",
        frozenset(),
    )


def _shared_proof_compatibility_bridge_eligibility(signature) -> bool:
    return bool(getattr(signature, "allowed_private_compatibility_bridge_callees", frozenset()))


def typecheck_workflow_ref_argument(
    expr: ExprNode,
    *,
    expected_type: WorkflowRefTypeRef,
    value_env: dict[str, TypeRef],
    workflow_catalog,
    typed_factory,
) :
    from . import typecheck as compat

    if workflow_catalog is None:
        raise TypeError("workflow_catalog is required for workflow-ref arguments")
    if isinstance(expr, NameExpr):
        bound_type = value_env.get(expr.name)
        if isinstance(bound_type, WorkflowRefTypeRef):
            return typed_factory(expr=expr, type_ref=bound_type, effect=EMPTY_EFFECT_SUMMARY)
        if bound_type is not None:
            compat._raise_error(
                "workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                code="workflow_ref_literal_required",
                span=expr.span,
                form_path=expr.form_path,
                expansion_stack=expr.expansion_stack,
            )
    if isinstance(expr, (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr)):
        resolved_ref = resolve_workflow_ref_name(
            workflow_ref_target_name(expr),
            workflow_catalog=workflow_catalog,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=getattr(expr, "expansion_stack", ()),
            allow_extern_rebinding=True,
        )
        return typed_factory(
            expr=expr,
            type_ref=workflow_ref_type_from_signature(
                type(
                    "WorkflowRefSignature",
                    (),
                    {
                        "params": resolved_ref.signature_params,
                        "return_type_ref": resolved_ref.return_type_ref,
                    },
                )()
            ),
            effect=EMPTY_EFFECT_SUMMARY,
        )
    compat._raise_error(
        "workflow-ref arguments must be literals or forwarded workflow-ref bindings",
        code="workflow_ref_literal_required",
        span=expr.span,
        form_path=expr.form_path,
    )


def typecheck_proc_ref_argument(
    expr: ExprNode,
    *,
    expected_type: ProcRefTypeRef,
    value_env: dict[str, TypeRef],
    procedure_catalog,
    proc_ref_resolution_context: ProcRefResolutionContext | None,
    active_proc_ref_value_env,
    typed_factory,
) -> tuple[object, ResolvedProcRefValue | None]:
    from . import typecheck as compat

    if procedure_catalog is None:
        raise TypeError("procedure_catalog is required for proc-ref arguments")
    resolved = resolve_proc_ref_value(
        expr,
        procedure_catalog=procedure_catalog,
        proc_ref_env=active_proc_ref_value_env,
        resolution_context=proc_ref_resolution_context,
        expected_type=expected_type,
    )
    if resolved is not None:
        bound_type = value_env.get(expr.name) if isinstance(expr, NameExpr) else resolved.residual_type_ref
        type_ref = bound_type if isinstance(bound_type, ProcRefTypeRef) else resolved.residual_type_ref
        return typed_factory(expr=expr, type_ref=type_ref, effect=EMPTY_EFFECT_SUMMARY), resolved
    if isinstance(expr, NameExpr):
        bound_type = value_env.get(expr.name)
        if isinstance(bound_type, ProcRefTypeRef):
            return typed_factory(expr=expr, type_ref=bound_type, effect=EMPTY_EFFECT_SUMMARY), None
    compat._raise_error(
        "proc-ref arguments must be literals or forwarded proc-ref bindings",
        code="proc_ref_literal_required",
        span=expr.span,
        form_path=expr.form_path,
    )


def workflow_ref_signature(
    workflow_catalog,
    *,
    workflow_name: str,
    span,
    form_path: tuple[str, ...],
):
    from . import typecheck as compat

    if workflow_catalog is None:
        raise TypeError("workflow_catalog is required for workflow ref validation")
    try:
        resolved_ref = resolve_workflow_ref_name(
            workflow_name,
            workflow_catalog=workflow_catalog,
            span=span,
            form_path=form_path,
            allow_extern_rebinding=True,
        )
    except LispFrontendCompileError as exc:
        diagnostic = exc.diagnostics[0]
        compat._raise_required_lint(
            diagnostic.message,
            code=diagnostic.code,
            span=span,
            form_path=form_path,
        )
    return type(
        "WorkflowRefSignature",
        (),
        {
            "name": resolved_ref.workflow_name,
            "params": resolved_ref.signature_params,
            "return_type_ref": resolved_ref.return_type_ref,
        },
    )()


def require_union_variant_field(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    span,
    form_path: tuple[str, ...],
) -> TypeRef:
    from . import typecheck as compat

    variant_fields = union_type.variant_field_types.get(variant_name)
    if variant_fields is None or field_name not in variant_fields:
        compat._raise_required_lint(
            f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return variant_fields[field_name]


def require_union_variant_path_field(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    expected_under: str,
    span,
    form_path: tuple[str, ...],
) -> PathTypeRef:
    from . import typecheck as compat

    field_type = require_union_variant_field(
        union_type,
        variant_name,
        field_name,
        span=span,
        form_path=form_path,
    )
    if not isinstance(field_type, PathTypeRef) or field_type.definition.under != expected_under:
        compat._raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}` "
                f"as a relpath under `{expected_under}`"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def require_union_variant_exact_type(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    expected_type: TypeRef,
    span,
    form_path: tuple[str, ...],
) -> TypeRef:
    from . import typecheck as compat

    field_type = require_union_variant_field(
        union_type,
        variant_name,
        field_name,
        span=span,
        form_path=form_path,
    )
    if field_type != expected_type:
        compat._raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}.{field_name}` "
                f"as `{getattr(expected_type, 'name', type(expected_type).__name__)}`"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def require_union_variant_exact_field_names(
    union_type: UnionTypeRef,
    variant_name: str,
    *,
    expected_fields: tuple[str, ...],
    span,
    form_path: tuple[str, ...],
) -> None:
    from . import typecheck as compat

    variant_fields = union_type.variant_field_types.get(variant_name)
    actual_fields = tuple(sorted(variant_fields)) if variant_fields is not None else ()
    if actual_fields != tuple(sorted(expected_fields)):
        compat._raise_required_lint(
            (
                f"workflow ref return union `{union_type.name}` must expose `{variant_name}` "
                f"with exactly {expected_fields}"
            ),
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )


def require_union_variant_record_field(
    union_type: UnionTypeRef,
    variant_name: str,
    field_name: str,
    *,
    span,
    form_path: tuple[str, ...],
) -> RecordTypeRef:
    from . import typecheck as compat

    field_type = require_union_variant_field(
        union_type,
        variant_name,
        field_name,
        span=span,
        form_path=form_path,
    )
    if not isinstance(field_type, RecordTypeRef):
        compat._raise_required_lint(
            f"workflow ref return union `{union_type.name}` must expose record field `{variant_name}.{field_name}`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    return field_type


def validate_selector_workflow_ref(
    signature,
    *,
    type_env: FrontendTypeEnvironment,
    span,
    form_path: tuple[str, ...],
) -> tuple[RecordTypeRef, RecordTypeRef]:
    from . import typecheck as compat
    from .resource import ensure_drain_context_type

    if len(signature.params) != 1:
        compat._raise_error(
            f"workflow ref `{signature.name}` must accept exactly one `DrainCtx` parameter for `selector`",
            code="backlog_drain_contract_invalid",
            span=span,
            form_path=form_path,
        )
    ensure_drain_context_type(signature.params[0][1], span=span, form_path=form_path)
    if not isinstance(signature.return_type_ref, UnionTypeRef):
        compat._raise_required_lint(
            f"workflow ref `{signature.name}` must return `SelectionResult`-shaped union output",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    require_union_variant_exact_field_names(
        signature.return_type_ref,
        "EMPTY",
        expected_fields=(),
        span=span,
        form_path=form_path,
    )
    gap_payload_type = require_union_variant_record_field(
        signature.return_type_ref,
        "GAP",
        "gap",
        span=span,
        form_path=form_path,
    )
    selected_payload_type = require_union_variant_record_field(
        signature.return_type_ref,
        "SELECTED",
        "selection",
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_type(
        signature.return_type_ref,
        "BLOCKED",
        "reason",
        expected_type=PrimitiveTypeRef(name="String"),
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_field_names(
        signature.return_type_ref,
        "BLOCKED",
        expected_fields=("reason",),
        span=span,
        form_path=form_path,
    )
    return selected_payload_type, gap_payload_type


def _backlog_drain_blocker_class_type(
    type_env: FrontendTypeEnvironment,
    *,
    span,
    form_path: tuple[str, ...],
) -> TypeRef:
    blocker_type_name = (
        "BlockerClass"
        if "BlockerClass" in getattr(type_env, "_type_refs", {})
        else "std/resource::BlockerClass"
    )
    return type_env.resolve_type(blocker_type_name, span=span, form_path=form_path)


def validate_run_item_workflow_ref(
    signature,
    *,
    type_env: FrontendTypeEnvironment,
    selected_payload_type: RecordTypeRef,
    span,
    form_path: tuple[str, ...],
) -> None:
    from . import typecheck as compat
    from .resource import ensure_item_context_type

    if len(signature.params) != 2:
        if len(signature.params) > 2:
            extra_param_name = signature.params[2][0]
            compat._raise_error(
                f"workflow ref `{signature.name}` must not expose public binding `{extra_param_name}`",
                code="workflow_signature_mismatch",
                span=span,
                form_path=form_path,
            )
        compat._raise_error(
            f"workflow ref `{signature.name}` must accept `ItemCtx` and the selector payload for `run-item`",
            code="backlog_drain_contract_invalid",
            span=span,
            form_path=form_path,
        )
    ensure_item_context_type(signature.params[0][1], span=span, form_path=form_path)
    if signature.params[1][1] != selected_payload_type:
        compat._raise_required_lint(
            f"workflow ref `{signature.name}` second parameter must match the selector `SELECTED.selection` payload",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    if not isinstance(signature.return_type_ref, UnionTypeRef):
        compat._raise_required_lint(
            f"workflow ref `{signature.name}` must return a union for `run-item`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    blocker_class = _backlog_drain_blocker_class_type(
        type_env,
        span=span,
        form_path=form_path,
    )
    require_union_variant_path_field(
        signature.return_type_ref,
        "CONTINUE",
        "summary-path",
        expected_under="artifacts/work",
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_field_names(
        signature.return_type_ref,
        "CONTINUE",
        expected_fields=("summary-path",),
        span=span,
        form_path=form_path,
    )
    require_union_variant_path_field(
        signature.return_type_ref,
        "BLOCKED",
        "summary-path",
        expected_under="artifacts/work",
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_type(
        signature.return_type_ref,
        "BLOCKED",
        "blocker-class",
        expected_type=blocker_class,
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_field_names(
        signature.return_type_ref,
        "BLOCKED",
        expected_fields=("summary-path", "blocker-class"),
        span=span,
        form_path=form_path,
    )


def validate_gap_drafter_workflow_ref(
    signature,
    *,
    type_env: FrontendTypeEnvironment,
    gap_payload_type: RecordTypeRef,
    span,
    form_path: tuple[str, ...],
) -> None:
    from . import typecheck as compat
    from .resource import ensure_drain_context_type

    if len(signature.params) != 2:
        compat._raise_error(
            f"workflow ref `{signature.name}` must accept `DrainCtx` and the selector gap payload for `gap-drafter`",
            code="backlog_drain_contract_invalid",
            span=span,
            form_path=form_path,
        )
    ensure_drain_context_type(signature.params[0][1], span=span, form_path=form_path)
    if signature.params[1][1] != gap_payload_type:
        compat._raise_required_lint(
            f"workflow ref `{signature.name}` second parameter must match the selector `GAP.gap` payload",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    if isinstance(signature.return_type_ref, RecordTypeRef):
        return
    if not isinstance(signature.return_type_ref, UnionTypeRef):
        compat._raise_required_lint(
            f"workflow ref `{signature.name}` must return a record or union for `gap-drafter`",
            code="workflow_call_signature_erased",
            span=span,
            form_path=form_path,
        )
    blocker_class = _backlog_drain_blocker_class_type(
        type_env,
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_field_names(
        signature.return_type_ref,
        "CONTINUE",
        expected_fields=(),
        span=span,
        form_path=form_path,
    )
    require_union_variant_path_field(
        signature.return_type_ref,
        "BLOCKED",
        "progress-report-path",
        expected_under="artifacts/work",
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_type(
        signature.return_type_ref,
        "BLOCKED",
        "blocker-class",
        expected_type=blocker_class,
        span=span,
        form_path=form_path,
    )
    require_union_variant_exact_field_names(
        signature.return_type_ref,
        "BLOCKED",
        expected_fields=("progress-report-path", "blocker-class"),
        span=span,
        form_path=form_path,
    )


def typecheck_call_expr(
    expr: CallExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    from . import typecheck as compat

    if context.workflow_catalog is None:
        raise TypeError("workflow_catalog is required for CallExpr typechecking")
    workflow_ref_type = context.value_env.get(expr.callee_name)
    signature = None
    if isinstance(workflow_ref_type, WorkflowRefTypeRef):
        if len(expr.bindings) != len(workflow_ref_type.param_type_refs):
            compat._raise_error(
                f"call is missing required binding for workflow ref `{expr.callee_name}`",
                code="workflow_signature_mismatch",
                span=expr.span,
                form_path=expr.form_path,
            )
        expected_bindings = {
            binding_name: type_ref
            for (binding_name, _), type_ref in zip(expr.bindings, workflow_ref_type.param_type_refs, strict=True)
        }
        signature_name = expr.callee_name
        return_type = workflow_ref_type.return_type_ref
        ordered_params = tuple(
            (binding_name, type_ref)
            for (binding_name, _), type_ref in zip(expr.bindings, workflow_ref_type.param_type_refs, strict=True)
        )
    else:
        signature = context.workflow_catalog.signatures_by_name.get(expr.callee_name)
        if signature is None:
            compat._raise_error(
                f"unknown workflow callee `{expr.callee_name}`",
                code="workflow_call_unknown",
                span=expr.span,
                form_path=expr.form_path,
            )
        expected_bindings = dict(signature.params)
        expected_bindings.update(signature.private_compatibility_bridge_types)
        signature_name = signature.name
        return_type = signature.return_type_ref
        ordered_params = signature.params
    defaulted_bindings = (
        frozenset()
        if isinstance(workflow_ref_type, WorkflowRefTypeRef)
        else frozenset(signature.param_defaults)
    )
    seen_bindings: set[str] = set()
    binding_summaries = []
    for binding_name, binding_expr in expr.bindings:
        if binding_name in seen_bindings:
            compat._raise_error(
                f"duplicate call binding `{binding_name}`",
                code="workflow_signature_mismatch",
                span=binding_expr.span,
                form_path=binding_expr.form_path,
            )
        seen_bindings.add(binding_name)
        expected_type = expected_bindings.get(binding_name)
        if expected_type is None:
            compat._raise_error(
                f"call binding `{binding_name}` does not match the callee signature",
                code="workflow_signature_mismatch",
                span=binding_expr.span,
                form_path=binding_expr.form_path,
            )
        if isinstance(expected_type, WorkflowRefTypeRef):
            typed_binding = typecheck_workflow_ref_argument(
                binding_expr,
                expected_type=expected_type,
                value_env=dict(context.value_env),
                workflow_catalog=context.workflow_catalog,
                typed_factory=typed_factory,
            )
            binding_summaries.append(typed_binding.effect_summary)
            if not isinstance(binding_expr, (WorkflowRefLiteralExpr, NameExpr, EnumMemberExpr)):
                compat._raise_error(
                    "workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                    code="workflow_ref_literal_required",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            if not type_refs_compatible(expected_type, typed_binding.type_ref):
                compat._raise_error(
                    f"workflow ref argument `{binding_name}` does not match `{expected_type.name}`",
                    code="workflow_ref_signature_invalid",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            continue
        if isinstance(expected_type, ProcRefTypeRef):
            typed_binding, _ = typecheck_proc_ref_argument(
                binding_expr,
                expected_type=expected_type,
                value_env=dict(context.value_env),
                procedure_catalog=context.procedure_catalog,
                proc_ref_resolution_context=context.proc_ref_resolution_context,
                active_proc_ref_value_env=context.session_state.proc_ref_value_env,
                typed_factory=typed_factory,
            )
            binding_summaries.append(typed_binding.effect_summary)
            if not type_refs_compatible(expected_type, typed_binding.type_ref):
                compat._raise_error(
                    f"procedure ref argument `{binding_name}` does not match `{expected_type.name}`",
                    code="proc_ref_signature_invalid",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            continue
        typed_binding = recurse(binding_expr)
        binding_summaries.append(typed_binding.effect_summary)
        if not type_refs_compatible(expected_type, typed_binding.type_ref):
            compat._raise_error(
                f"call binding `{binding_name}` expected `{compat._type_label(expected_type)}`"
                f" but got `{compat._type_label(typed_binding.type_ref)}`",
                code="type_mismatch",
                span=binding_expr.span,
                form_path=binding_expr.form_path,
            )
    missing_bindings = [
        name
        for name, expected_type in ordered_params
        if name not in seen_bindings
        and name not in defaulted_bindings
        and not hidden_context_omission_allowed(
            session_state=context.session_state,
            callee_signature=signature if not isinstance(workflow_ref_type, WorkflowRefTypeRef) else None,
            param_name=name,
            expected_type=expected_type,
            span=expr.span,
            form_path=expr.form_path,
        )
        and not compatibility_bridge_omission_allowed(
            session_state=context.session_state,
            callee_signature=signature if not isinstance(workflow_ref_type, WorkflowRefTypeRef) else None,
            param_name=name,
        )
    ]
    if missing_bindings:
        compat._raise_error(
            f"call is missing required binding `{missing_bindings[0]}`",
            code="workflow_signature_mismatch",
            span=expr.span,
            form_path=expr.form_path,
        )
    call_summary = effect_summary_from_direct(
        direct_effects=(CallsWorkflowEffect(subject=(signature_name,)),)
    )
    return typed_factory(
        expr=expr,
        type_ref=return_type,
        effect=merge_effect_summaries(
            *binding_summaries,
            call_summary,
            context.workflow_effects_by_name.get(signature_name, EMPTY_EFFECT_SUMMARY),
        ),
    )


def typecheck_function_call_expr(
    expr: FunctionCallExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    from . import typecheck as compat

    if context.session_state.function_catalog is None:
        raise TypeError("function_catalog is required for FunctionCallExpr typechecking")
    signature = context.session_state.function_catalog.signatures_by_name.get(expr.callee_name)
    if signature is None:
        compat._raise_error(
            f"unknown function callee `{expr.callee_name}`",
            code="function_call_unknown",
            span=expr.span,
            form_path=expr.form_path,
        )
    if len(expr.args) != len(signature.params):
        compat._raise_error(
            f"function `{expr.callee_name}` expected {len(signature.params)} positional arguments but got {len(expr.args)}",
            code="function_arity_mismatch",
            span=expr.span,
            form_path=expr.form_path,
        )
    arg_summaries = []
    for arg_expr, (param_name, expected_type) in zip(expr.args, signature.params, strict=True):
        typed_arg = recurse(arg_expr)
        arg_summaries.append(typed_arg.effect_summary)
        if not type_refs_compatible(expected_type, typed_arg.type_ref):
            compat._raise_error(
                f"function argument `{param_name}` expected `{compat._type_label(expected_type)}`"
                f" but got `{compat._type_label(typed_arg.type_ref)}`",
                code="type_mismatch",
                span=arg_expr.span,
                form_path=arg_expr.form_path,
            )
    return typed_factory(
        expr=expr,
        type_ref=signature.return_type_ref,
        effect=merge_effect_summaries(*arg_summaries),
    )
