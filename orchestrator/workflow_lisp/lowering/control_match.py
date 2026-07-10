"""Match owner for control-family lowering."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.state_layout import GeneratedPathSemanticRole

from ..contracts import derive_structured_result_contract, derive_workflow_boundary_fields
from ..definitions import RecordDef, RecordField
from ..effects import EMPTY_EFFECT_SUMMARY
from ..expression_traversal import iter_child_exprs
from ..expressions import FieldAccessExpr, MatchExpr, NameExpr
from ..spans import SourceSpan
from ..type_env import RecordTypeRef, TypeRef, UnionTypeRef, VariantCaseTypeRef, render_type_ref
from ..typecheck import TypedExpr
from ..workflows import TypedWorkflowDef, WorkflowDef, WorkflowParam, WorkflowSignature
from .composition_graph import CompositionScope, build_fragment, fragment_requires_helper_boundary
from .context import (
    _compile_error,
    _copy_context_with_composition_scope,
    _copy_context_with_step_prefix,
    _context_with_local_type_binding,
    _LoweringContext,
    _TerminalResult,
)
from .generated_paths import allocate_generated_result_bundle
from .origins import (
    LoweringOrigin,
    _record_step_origin,
    _register_generated_contract_field_bindings,
)
from .values import (
    _build_output_step_local_value,
    _flatten_inline_output_refs,
    _normalize_union_field_path,
    _resolve_inline_expr_value,
)


def _conditional_case_outputs(*args, **kwargs):
    """Re-export of `core._conditional_case_outputs` for `wcc.defunctionalize`.

    Deferred import avoids the `control_match -> core -> control -> control_match`
    load-time cycle (`core.py` imports `.control`, which imports this module).
    """

    from .core import _conditional_case_outputs as _impl

    return _impl(*args, **kwargs)


def _conditional_output_refs(*args, **kwargs):
    """Re-export of `core._conditional_output_refs`; see `_conditional_case_outputs`."""

    from .core import _conditional_output_refs as _impl

    return _impl(*args, **kwargs)


def _build_match_projection_anchor_step(
    *,
    match_step_name: str,
    variant_name: str,
    case_outputs: Mapping[str, Any],
    context: _LoweringContext,
    span: SourceSpan,
) -> dict[str, Any]:
    anchor_ref = _first_case_output_ref(case_outputs)
    if anchor_ref is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="match return arms must expose at least one exportable field in this Stage 3 slice",
            span=span,
            form_path=context.signature.form_path,
        )
    step_name = f"{match_step_name}__{variant_name.lower()}__projection_anchor"
    step_id = context.normalize_generated_step_id(step_name)
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=LoweringOrigin(span=span, form_path=context.signature.form_path),
    )
    return {
        "name": step_name,
        "id": step_id,
        "assert": {
            "compare": {
                "left": {"ref": anchor_ref},
                "op": "eq",
                "right": {"ref": anchor_ref},
            }
        },
    }


def _first_case_output_ref(case_outputs: Mapping[str, Any]) -> str | None:
    for output in case_outputs.values():
        if not isinstance(output, Mapping):
            continue
        source = output.get("from")
        if isinstance(source, Mapping) and isinstance(source.get("ref"), str):
            return str(source["ref"])
    return None


def _rewrite_nested_case_sibling_refs(
    steps: list[dict[str, Any]],
    *,
    ancestor_sibling_names: tuple[str, ...] = (),
) -> None:
    current_sibling_names = tuple(
        step_name
        for step in steps
        for step_name in (step.get("name"),)
        if isinstance(step_name, str)
    )
    sibling_names = ancestor_sibling_names + tuple(
        name for name in current_sibling_names if name not in ancestor_sibling_names
    )
    for step in steps:
        rewritten = _rewrite_case_sibling_refs_in_value(step, sibling_names=sibling_names)
        step.clear()
        step.update(rewritten)
        for nested_steps in _iter_nested_case_step_lists(step):
            _rewrite_nested_case_sibling_refs(
                nested_steps,
                ancestor_sibling_names=sibling_names,
            )


def _iter_nested_case_step_lists(step: Mapping[str, Any]) -> tuple[list[dict[str, Any]], ...]:
    nested: list[list[dict[str, Any]]] = []
    for branch_name in ("then", "else"):
        branch = step.get(branch_name)
        if isinstance(branch, Mapping) and isinstance(branch.get("steps"), list):
            nested.append(branch["steps"])
    match = step.get("match")
    if isinstance(match, Mapping):
        for case in (match.get("cases") or {}).values():
            if isinstance(case, Mapping) and isinstance(case.get("steps"), list):
                nested.append(case["steps"])
    repeat_until = step.get("repeat_until")
    if isinstance(repeat_until, Mapping) and isinstance(repeat_until.get("steps"), list):
        nested.append(repeat_until["steps"])
    return tuple(nested)


def _rewrite_case_sibling_refs_in_value(value: Any, *, sibling_names: tuple[str, ...]) -> Any:
    if isinstance(value, str):
        for step_name in sibling_names:
            prefix = f"parent.steps.{step_name}."
            if value.startswith(prefix):
                return "self.steps." + value.removeprefix("parent.steps.")
        return value
    if isinstance(value, list):
        return [_rewrite_case_sibling_refs_in_value(item, sibling_names=sibling_names) for item in value]
    if isinstance(value, Mapping):
        rewritten: dict[Any, Any] = {}
        for key, item in value.items():
            if key == "steps" and isinstance(item, list):
                rewritten[key] = item
                continue
            rewritten[key] = _rewrite_case_sibling_refs_in_value(item, sibling_names=sibling_names)
        return rewritten
    return value


def _lower_match_expr(*args, **kwargs):
    return _control_lower_match_expr_impl(*args, **kwargs)


def _binding_terminal_for_match_subject(*args, **kwargs):
    return _control_binding_terminal_for_match_subject_impl(*args, **kwargs)


def _match_arm_local_values(*args, **kwargs):
    return _control_match_arm_local_values_impl(*args, **kwargs)


def _binding_terminal_for_inline_match(*args, **kwargs):
    return _control_binding_terminal_for_inline_match_impl(*args, **kwargs)


def _binding_match_subject_name(subject: Any) -> str:
    if isinstance(subject, NameExpr):
        return subject.name
    if isinstance(subject, FieldAccessExpr):
        return subject.base.name
    return "binding"


def _control_binding_terminal_for_match_subject_impl(
    subject: Any,
    *,
    local_values: Mapping[str, Any],
) -> _TerminalResult | None:
    resolved_subject = _resolve_inline_expr_value(subject, local_values=local_values)
    return _binding_terminal_for_inline_match(resolved_subject)


def _lower_binding_match_expr(
    expr: MatchExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    step_name_prefix: str,
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    binding_terminal = _binding_terminal_for_match_subject(
        expr.subject,
        local_values=local_values,
    )
    if binding_terminal is None:
        raise _compile_error(
            code="workflow_return_not_exportable",
            message="Stage 3 lowering requires match subjects to come from step-backed let* bindings",
            span=expr.subject.span,
            form_path=expr.subject.form_path,
        )
    return _lower_match_expr(
        expr,
        result_type=result_type,
        context=_copy_context_with_step_prefix(
            context,
            step_name_prefix=step_name_prefix,
        ),
        binding_name=_binding_match_subject_name(expr.subject),
        binding_terminal=binding_terminal,
        local_values=local_values,
    )


def _control_lower_match_expr_impl(
    match_expr: MatchExpr,
    *,
    result_type: TypeRef,
    context: _LoweringContext,
    binding_name: str,
    binding_terminal: _TerminalResult,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from .control_loops import _conditional_case_ref
    from .core import _lower_conditional_branch_expr, _output_contracts_for_type

    match_step_name = f"{context.step_name_prefix}__match_{binding_name}"
    match_step_id = context.normalize_generated_step_id(match_step_name)
    output_contracts = _output_contracts_for_type(
        result_type,
        context=context,
        span=match_expr.span,
        form_path=match_expr.form_path,
    )
    cases: dict[str, Any] = {}
    hidden_inputs: dict[str, LoweringOrigin] = {}
    shared_union_bundle_allocation = (
        allocate_generated_result_bundle(
            context=context,
            source_expr=match_expr,
            step_name=match_step_name,
            step_id=match_step_id,
            semantic_role=GeneratedPathSemanticRole.VARIANT_PROJECTION_BUNDLE,
            stable_target="match_union_projection",
        )
        if isinstance(result_type, UnionTypeRef)
        and not context.is_generated_private_workflow
        else None
    )
    subject_type = context.local_type_bindings.get(binding_name)
    for arm in match_expr.arms:
        case_name = f"{match_step_name}__{arm.variant_name.lower()}"
        arm_context = _copy_context_with_composition_scope(
            context,
            scope_id=case_name,
            parent_scope_id=context.composition_scope_id,
            scope_kind="match_case",
            owner_step_name=match_step_name,
        )
        arm_binding_type: TypeRef | None = None
        if isinstance(subject_type, UnionTypeRef):
            arm_binding_type = context.type_env.union_variant(
                subject_type,
                arm.variant_name,
                span=match_expr.subject.span,
                form_path=match_expr.subject.form_path,
            )
            arm_context = _context_with_local_type_binding(
                arm_context,
                binding_name=arm.binding_name,
                binding_type=arm_binding_type,
            )
        case_steps, case_terminal = _lower_conditional_branch_expr(
            arm.body,
            result_type=result_type,
            step_name=case_name,
            context=arm_context,
            local_values=_match_arm_local_values(
                local_values=local_values,
                binding_name=arm.binding_name,
                binding_terminal=binding_terminal,
                binding_type=arm_binding_type,
            ),
        )
        case_fragment = build_fragment(
            emitted_steps=case_steps,
            scope=CompositionScope(
                scope_id=case_name,
                parent_scope_id=context.composition_scope_id,
                kind="match_case",
                owner_step_name=match_step_name,
                resume_identity_hint=case_name,
            ),
            output_refs=case_terminal.output_refs,
            hidden_inputs=case_terminal.hidden_inputs,
            leaf_terminal=case_terminal,
        )
        if fragment_requires_helper_boundary(case_fragment):
            case_steps, case_terminal = _hoist_match_case_fragment_to_helper(
                match_expr=match_expr,
                branch_expr=arm.body,
                pre_hoist_terminal=case_terminal,
                result_type=result_type,
                case_name=case_name,
                context=arm_context,
                local_values=_match_arm_local_values(
                    local_values=local_values,
                    binding_name=arm.binding_name,
                    binding_terminal=binding_terminal,
                    binding_type=arm_binding_type,
                ),
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
        if (
            isinstance(result_type, UnionTypeRef)
            and shared_union_bundle_allocation is not None
            and _match_case_requires_union_projection(case_terminal, result_type=result_type)
        ):
            case_steps, case_terminal = _normalize_union_match_case_terminal(
                case_name=case_name,
                case_steps=case_steps,
                case_terminal=case_terminal,
                result_type=result_type,
                source_variant_name=arm.variant_name,
                subject_union_type=subject_type if isinstance(subject_type, UnionTypeRef) else None,
                shared_bundle_input_name=shared_union_bundle_allocation.generated_input_name,
                shared_bundle_path=shared_union_bundle_allocation.concrete_path_template,
                context=context,
                span=arm.body.span,
                form_path=arm.body.form_path,
            )
        case_outputs = _conditional_case_outputs(
            case_terminal,
            output_contracts=output_contracts,
            span=arm.body.span,
            form_path=arm.body.form_path,
        )
        if not case_steps:
            case_steps.append(
                _build_match_projection_anchor_step(
                    match_step_name=match_step_name,
                    variant_name=arm.variant_name,
                    case_outputs=case_outputs,
                    context=context,
                    span=arm.body.span,
                )
            )
        _rewrite_nested_case_sibling_refs(case_steps)
        hidden_inputs.update(case_terminal.hidden_inputs)
        cases[arm.variant_name] = {
            "id": context.normalize_generated_step_id(case_name),
            "outputs": case_outputs,
            "steps": case_steps,
        }

    _record_step_origin(context, step_name=match_step_name, step_id=match_step_id, source=match_expr)
    match_step = {
        "name": match_step_name,
        "id": match_step_id,
        "match": {
            "ref": _conditional_case_ref(
                binding_terminal.output_refs["return__variant"],
                terminal_step_name=binding_terminal.step_name,
            ),
            "cases": cases,
        },
    }
    return [match_step], _TerminalResult(
        step_name=match_step_name,
        step_id=match_step_id,
        output_refs=_conditional_output_refs(
            step_name=match_step_name,
            output_contracts=output_contracts,
            result_type=result_type,
        ),
        output_kind="match",
        hidden_inputs=hidden_inputs,
    )


def _match_case_requires_union_projection(
    case_terminal: _TerminalResult,
    *,
    result_type: UnionTypeRef,
) -> bool:
    passthrough_union_name = getattr(case_terminal, "passthrough_union_type_name", None)
    if (
        passthrough_union_name is None
        and case_terminal.returned_union_variant_name is None
        and case_terminal.returned_union_type_name is not None
    ):
        passthrough_union_name = case_terminal.returned_union_type_name
    return passthrough_union_name != result_type.name


def _normalize_union_match_case_terminal(
    *,
    case_name: str,
    case_steps: list[dict[str, Any]],
    case_terminal: _TerminalResult,
    result_type: UnionTypeRef,
    source_variant_name: str,
    subject_union_type: UnionTypeRef | None,
    shared_bundle_input_name: str,
    shared_bundle_path: str,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from .control_loops import _conditional_case_ref, _materialize_values_step
    from .phase_scope import _surface_contract_from_structured_field, _union_output_contracts
    from .values import _boundary_placeholder_literals

    resolved_variant_name = _resolve_match_return_union_variant(
        case_terminal=case_terminal,
        result_type=result_type,
        source_variant_name=source_variant_name,
        subject_union_type=subject_union_type,
        span=span,
        form_path=form_path,
    )
    step_name = f"{case_name}__result_bundle"
    step_id = context.normalize_generated_step_id(step_name)
    bundle_contract = derive_structured_result_contract(
        result_type,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=span,
        form_path=form_path,
    )
    _register_generated_contract_field_bindings(context, bundle_contract.field_origins)
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = shared_bundle_path
    context.generated_path_spans.setdefault(authored_contract["path"], LoweringOrigin(span=span, form_path=form_path))
    values = [
        {
            "name": "variant",
            "source": {"literal": resolved_variant_name},
            "contract": _surface_contract_from_structured_field(authored_contract["discriminant"]),
        }
    ]
    normalized_field_names = {"variant"}
    for field in authored_contract.get("shared_fields", ()):
        output_ref = case_terminal.output_refs.get(f"return__{field['name']}")
        if not isinstance(output_ref, str):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"match case did not expose shared union field `{field['name']}`",
                span=span,
                form_path=form_path,
            )
        values.append(
            {
                "name": field["name"],
                "source": {
                    "ref": _conditional_case_ref(output_ref, terminal_step_name=case_terminal.step_name)
                },
                "contract": _surface_contract_from_structured_field(field),
            }
        )
        normalized_field_names.add(field["name"])
    for field in authored_contract["variants"][resolved_variant_name]["fields"]:
        output_ref = case_terminal.output_refs.get(f"return__{field['name']}")
        if not isinstance(output_ref, str):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=(
                    f"match case did not expose union field `{field['name']}` "
                    f"for `{resolved_variant_name}`"
                ),
                span=span,
                form_path=form_path,
            )
        values.append(
            {
                "name": field["name"],
                "source": {
                    "ref": _conditional_case_ref(output_ref, terminal_step_name=case_terminal.step_name)
                },
                "contract": _surface_contract_from_structured_field(field),
            }
        )
        normalized_field_names.add(field["name"])
    placeholders = _boundary_placeholder_literals(
        result_type,
        span=span,
        form_path=form_path,
    )
    for field_name, definition in _union_output_contracts(
        result_type,
        payload=authored_contract,
        span=span,
        form_path=form_path,
    ).items():
        if field_name in normalized_field_names:
            continue
        placeholder_name = f"return__{field_name}"
        if placeholder_name not in placeholders:
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"match case could not synthesize placeholder for union field `{field_name}`",
                span=span,
                form_path=form_path,
            )
        values.append(
            {
                "name": field_name,
                "source": {"literal": placeholders[placeholder_name]},
                "contract": dict(definition),
            }
        )
    step = {
        **_materialize_values_step(step_name=step_name, step_id=step_id, values=values),
        bundle_contract.contract_kind: authored_contract,
    }
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=LoweringOrigin(span=span, form_path=form_path),
    )
    output_refs: dict[str, str] = {}
    for field in derive_workflow_boundary_fields(
        result_type,
        generated_name="return",
        source_path=("return",),
        span=span,
        form_path=form_path,
    ):
        field_path = _normalize_union_field_path(field.source_path[1:])
        output_refs[field.generated_name] = f"root.steps.{step_name}.artifacts.{'__'.join(field_path)}"
    return (
        [*case_steps, step],
        _TerminalResult(
            step_name=step_name,
            step_id=step_id,
            output_refs=output_refs,
            output_kind="step",
            hidden_inputs={
                **case_terminal.hidden_inputs,
                shared_bundle_input_name: LoweringOrigin(span=span, form_path=form_path),
            },
            returned_union_type_name=result_type.name,
            returned_union_variant_name=resolved_variant_name,
        ),
    )


def _resolve_match_return_union_variant(
    *,
    case_terminal: _TerminalResult,
    result_type: UnionTypeRef,
    source_variant_name: str,
    subject_union_type: UnionTypeRef | None,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> str:
    explicit_union_name = case_terminal.returned_union_type_name
    explicit_variant_name = case_terminal.returned_union_variant_name
    if explicit_union_name is not None or explicit_variant_name is not None:
        if explicit_union_name != result_type.name or explicit_variant_name is None:
            observed = explicit_union_name or "<unknown>"
            if explicit_variant_name is not None:
                observed = f"{observed}.{explicit_variant_name}"
            raise _compile_error(
                code="union_return_variant_incompatible",
                message=(
                    f"match branch for source variant `{source_variant_name}` must return `{result_type.name}`; "
                    f"explicit returned-union evidence resolved to `{observed}`"
                ),
                span=span,
                form_path=form_path,
            )
        if explicit_variant_name not in result_type.variant_field_types:
            raise _compile_error(
                code="union_return_variant_incompatible",
                message=(
                    f"match branch for source variant `{source_variant_name}` must return a declared "
                    f"variant of `{result_type.name}`; explicit returned variant "
                    f"`{explicit_variant_name}` is not part of that union"
                ),
                span=span,
                form_path=form_path,
            )
        return explicit_variant_name
    passthrough_union_name = getattr(case_terminal, "passthrough_union_type_name", None)
    if passthrough_union_name is not None and passthrough_union_name != result_type.name:
        raise _compile_error(
            code="union_return_variant_incompatible",
            message=(
                f"match branch for source variant `{source_variant_name}` must return `{result_type.name}`; "
                f"pass-through union evidence resolved to `{passthrough_union_name}`"
            ),
            span=span,
            form_path=form_path,
        )
    if subject_union_type is not None and subject_union_type.name == result_type.name:
        return source_variant_name
    subject_union_name = subject_union_type.name if subject_union_type is not None else "<non-union>"
    raise _compile_error(
        code="union_return_variant_ambiguous",
        message=(
            f"match branch for source variant `{source_variant_name}` must return `{result_type.name}` with "
            "explicit target-variant evidence; opaque dynamic branch output is ambiguous because the matched subject "
            f"union `{subject_union_name}` does not match the target union"
        ),
        span=span,
        form_path=form_path,
    )


def _control_match_arm_local_values_impl(
    *,
    local_values: Mapping[str, Any],
    binding_name: str,
    binding_terminal: _TerminalResult,
    binding_type: TypeRef | None = None,
) -> dict[str, Any]:
    localized_output_refs = {
        output_name: _match_subject_scope_value(output_ref)
        for output_name, output_ref in binding_terminal.output_refs.items()
    }
    if isinstance(binding_type, VariantCaseTypeRef):
        allowed_field_names = {"variant", *(field.name for field in binding_type.definition.fields)}
        localized_output_refs = {
            output_name: output_ref
            for output_name, output_ref in localized_output_refs.items()
            if output_name == "return__variant"
            or output_name.removeprefix("return__").split("__", 1)[0] in allowed_field_names
        }
    return {
        **local_values,
        binding_name: _build_output_step_local_value(localized_output_refs),
    }


def _control_binding_terminal_for_inline_match_impl(local_value: Any) -> _TerminalResult | None:
    output_refs = _flatten_inline_output_refs(local_value)
    if "return__variant" not in output_refs:
        return None
    return _TerminalResult(
        step_name="",
        step_id="",
        output_refs=output_refs,
        output_kind="inline",
        hidden_inputs={},
    )


def _match_subject_scope_value(value: Any) -> Any:
    if isinstance(value, str):
        if value.startswith("self.steps."):
            return "parent.steps." + value.removeprefix("self.steps.")
        return value
    if isinstance(value, Mapping):
        return {name: _match_subject_scope_value(item) for name, item in value.items()}
    return value


def _hoist_match_case_fragment_to_helper(
    *,
    match_expr: MatchExpr,
    branch_expr: Any,
    pre_hoist_terminal: _TerminalResult,
    result_type: TypeRef,
    case_name: str,
    context: _LoweringContext,
    local_values: Mapping[str, Any],
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from ..workflows import analyze_workflow_boundary_type
    from .workflow_calls import (
        _managed_write_root_binding_step,
        _managed_write_root_requirements_for_callable,
        _render_call_binding_ref,
        _render_record_call_bindings,
    )

    capture_names = _helper_capture_names(branch_expr, context=context)
    helper_params: list[tuple[str, TypeRef]] = []
    helper_param_defs: list[WorkflowParam] = []
    for capture_name in capture_names:
        capture_type = context.local_type_bindings.get(capture_name)
        if capture_type is None:
            raise _compile_error(
                code="nested_structured_control_unsupported",
                message=f"helper-hoisted branch capture `{capture_name}` does not have a lowering-time type binding",
                span=span,
                form_path=form_path,
            )
        boundary_type = _helper_capture_boundary_type(
            capture_name,
            capture_type,
            context=context,
            span=span,
            form_path=form_path,
        )
        analysis = analyze_workflow_boundary_type(
            boundary_type,
            source_path=(capture_name,),
            allow_top_level_workflow_ref=True,
        )
        if not analysis.lowerable:
            raise _compile_error(
                code="nested_structured_control_unsupported",
                message=(
                    f"nested structured control cannot hoist branch capture `{capture_name}` "
                    "through the current shared workflow boundary"
                ),
                span=span,
                form_path=form_path,
            )
        helper_params.append((capture_name, boundary_type))
        helper_param_defs.append(
            WorkflowParam(
                name=capture_name,
                type_name=render_type_ref(boundary_type),
                span=span,
                form_path=form_path,
                expansion_stack=getattr(branch_expr, "expansion_stack", ()),
            )
        )

    helper_name = _generated_helper_workflow_name(
        workflow_name=context.workflow_name,
        case_name=case_name,
        span=span,
    )
    helper_workflow = TypedWorkflowDef(
        definition=WorkflowDef(
            name=helper_name,
            params=tuple(helper_param_defs),
            return_type_name=render_type_ref(result_type),
            body=branch_expr,
            span=span,
            form_path=form_path,
            expansion_stack=getattr(branch_expr, "expansion_stack", ()),
        ),
        signature=WorkflowSignature(
            name=helper_name,
            params=tuple(helper_params),
            return_type_ref=result_type,
            span=span,
            form_path=form_path,
        ),
        typed_body=TypedExpr(
            expr=branch_expr,
            type_ref=result_type,
            span=span,
            form_path=form_path,
        ),
        effect_summary=EMPTY_EFFECT_SUMMARY,
    )
    if isinstance(context.workflows_by_name, dict):
        context.workflows_by_name.setdefault(helper_name, helper_workflow)
    if isinstance(context.workflow_catalog.signatures_by_name, dict):
        context.workflow_catalog.signatures_by_name.setdefault(helper_name, helper_workflow.signature)
    if isinstance(context.workflow_catalog.definitions_by_name, dict):
        context.workflow_catalog.definitions_by_name.setdefault(helper_name, helper_workflow.definition)
    lowered_helper = context.lowered_callees.get(helper_name)
    if lowered_helper is None:
        lowered_helper = context.ensure_workflow_lowered(helper_name)
    if lowered_helper is None:
        raise _compile_error(
            code="nested_structured_control_unsupported",
            message=f"generated helper workflow `{helper_name}` could not be lowered",
            span=span,
            form_path=form_path,
        )

    step_name = f"{case_name}__helper_call"
    step_id = context.normalize_generated_step_id(step_name)
    with_bindings: dict[str, Any] = {}
    for param_name, param_type in helper_workflow.signature.params:
        capture_expr = NameExpr(
            name=param_name,
            span=span,
            form_path=form_path,
            expansion_stack=getattr(branch_expr, "expansion_stack", ()),
        )
        if isinstance(param_type, RecordTypeRef):
            with_bindings.update(
                _render_record_call_bindings(
                    param_name,
                    param_type,
                    capture_expr,
                    local_values=local_values,
                )
            )
            continue
        with_bindings[param_name] = _render_call_binding_ref(
            capture_expr,
            local_values=local_values,
        )
    binding_steps, managed_bindings = _managed_write_root_binding_step(
        context=context,
        source_expr=branch_expr,
        call_step_name=step_name,
        callee_name=helper_name,
        managed_inputs=_managed_write_root_requirements_for_callable(
            lowered_callee=lowered_helper,
            imported_bundle=None,
            span=span,
            form_path=form_path,
        ),
    )
    with_bindings.update(managed_bindings)
    _record_step_origin(
        context,
        step_name=step_name,
        step_id=step_id,
        source=LoweringOrigin(
            span=span,
            form_path=form_path,
            notes=(
                f"generated helper workflow `{helper_name}` hoists nested structured control from `{case_name}`",
            ),
        ),
    )
    return [*binding_steps, {"name": step_name, "id": step_id, "call": helper_name, "with": with_bindings}], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs={
            field.generated_name: f"root.steps.{step_name}.artifacts.{field.generated_name}"
            for field in derive_workflow_boundary_fields(
                result_type,
                generated_name="return",
                source_path=("return",),
                span=span,
                form_path=form_path,
            )
        },
        output_kind="call",
        hidden_inputs={},
        returned_union_type_name=pre_hoist_terminal.returned_union_type_name,
        returned_union_variant_name=pre_hoist_terminal.returned_union_variant_name,
    )


def _helper_capture_names(
    expr: Any,
    *,
    context: _LoweringContext,
) -> tuple[str, ...]:
    used_names: set[str] = set()

    def walk(node: Any, bound_names: frozenset[str]) -> None:
        if isinstance(node, NameExpr):
            if node.name in context.local_type_bindings and node.name not in bound_names:
                used_names.add(node.name)
            return
        if isinstance(node, FieldAccessExpr) and isinstance(node.base, NameExpr):
            if node.base.name in context.local_type_bindings and node.base.name not in bound_names:
                used_names.add(node.base.name)
            walk(node.base, bound_names)
            return
        if isinstance(node, LetStarExpr):
            child_bound = set(bound_names)
            for binding_name, binding_expr in node.bindings:
                walk(binding_expr, frozenset(child_bound))
                child_bound.add(binding_name)
            walk(node.body, frozenset(child_bound))
            return
        # schema1_compatibility: legacy branch-local ref analysis walks authored match expressions.
        if isinstance(node, MatchExpr):
            walk(node.subject, bound_names)
            for arm in node.arms:
                walk(arm.body, bound_names | {arm.binding_name})
            return
        for child in iter_child_exprs(node):
            walk(child, bound_names)

    from ..expressions import LetStarExpr

    walk(expr, frozenset())
    return tuple(name for name in context.local_type_bindings if name in used_names)


def _helper_capture_boundary_type(
    capture_name: str,
    capture_type: TypeRef,
    *,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> TypeRef:
    if isinstance(capture_type, VariantCaseTypeRef):
        union_type = context.type_env.resolve_type(
            capture_type.union_name,
            span=span,
            form_path=form_path,
        )
        assert isinstance(union_type, UnionTypeRef)
        record_name = _generated_helper_variant_record_name(
            capture_name=capture_name,
            variant_type=capture_type,
        )
        return RecordTypeRef(
            name=record_name,
            definition=RecordDef(
                name=record_name,
                fields=tuple(
                    RecordField(
                        name=field.name,
                        type_name=field.type_name,
                        span=field.span,
                    )
                    for field in capture_type.definition.fields
                ),
                span=capture_type.definition.span,
            ),
            field_types=dict(union_type.variant_field_types[capture_type.variant_name]),
        )
    return capture_type


def _generated_helper_variant_record_name(
    *,
    capture_name: str,
    variant_type: VariantCaseTypeRef,
) -> str:
    normalized_union = variant_type.union_name.replace("/", ".").replace("::", ".").replace("-", "_")
    return f"%match-arm.{normalized_union}.{variant_type.variant_name.lower()}.{capture_name}"


def _generated_helper_workflow_name(
    *,
    workflow_name: str,
    case_name: str,
    span: SourceSpan,
) -> str:
    digest = hashlib.sha1(
        f"{workflow_name}|{case_name}|{span.start.path}|{span.start.line}|{span.start.column}".encode("utf-8")
    ).hexdigest()[:12]
    normalized_case = case_name.replace("/", ".").replace("::", ".").replace("-", "_")
    return f"%composition.{normalized_case}.{digest}.v1"
