"""Match owner for control-family lowering."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..contracts import derive_structured_result_contract, derive_workflow_boundary_fields
from ..expressions import FieldAccessExpr, MatchExpr, NameExpr
from ..spans import SourceSpan
from ..type_env import TypeRef, UnionTypeRef
from . import core as lowering_core
from .context import _copy_context_with_step_prefix, _LoweringContext, _TerminalResult
from .origins import LoweringOrigin, _record_step_origin
from .values import (
    _build_output_step_local_value,
    _flatten_inline_output_refs,
    _normalize_union_field_path,
    _resolve_inline_expr_value,
)


def _compile_error(*args, **kwargs):
    return lowering_core._compile_error(*args, **kwargs)


def _normalize_generated_step_id(*args, **kwargs):
    return lowering_core._normalize_generated_step_id(*args, **kwargs)


def _output_contracts_for_type(*args, **kwargs):
    return lowering_core._output_contracts_for_type(*args, **kwargs)


def _lower_conditional_branch_expr(*args, **kwargs):
    return lowering_core._lower_conditional_branch_expr(*args, **kwargs)


def _surface_contract_from_structured_field(*args, **kwargs):
    return lowering_core._surface_contract_from_structured_field(*args, **kwargs)


def _union_output_contracts(*args, **kwargs):
    return lowering_core._union_output_contracts(*args, **kwargs)


def _boundary_placeholder_literals(*args, **kwargs):
    return lowering_core._boundary_placeholder_literals(*args, **kwargs)


def _conditional_case_outputs(*args, **kwargs):
    return lowering_core._conditional_case_outputs(*args, **kwargs)


def _conditional_output_refs(*args, **kwargs):
    return lowering_core._conditional_output_refs(*args, **kwargs)


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
    step_id = _normalize_generated_step_id(step_name)
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

    match_step_name = f"{context.step_name_prefix}__match_{binding_name}"
    match_step_id = _normalize_generated_step_id(match_step_name)
    output_contracts = _output_contracts_for_type(
        result_type,
        context=context,
        span=match_expr.span,
        form_path=match_expr.form_path,
    )
    cases: dict[str, Any] = {}
    hidden_inputs: dict[str, LoweringOrigin] = {}
    shared_union_bundle_input = (
        f"__write_root__{match_step_id}__result_bundle"
        if isinstance(result_type, UnionTypeRef)
        and not context.is_generated_private_workflow
        else None
    )
    for arm in match_expr.arms:
        case_name = f"{match_step_name}__{arm.variant_name.lower()}"
        case_steps, case_terminal = _lower_conditional_branch_expr(
            arm.body,
            result_type=result_type,
            step_name=case_name,
            context=context,
            local_values=_match_arm_local_values(
                local_values=local_values,
                binding_name=arm.binding_name,
                binding_terminal=binding_terminal,
            ),
        )
        if isinstance(result_type, UnionTypeRef) and shared_union_bundle_input is not None:
            case_steps, case_terminal = _normalize_union_match_case_terminal(
                case_name=case_name,
                case_steps=case_steps,
                case_terminal=case_terminal,
                result_type=result_type,
                variant_name=arm.variant_name,
                shared_bundle_input_name=shared_union_bundle_input,
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
        hidden_inputs.update(case_terminal.hidden_inputs)
        cases[arm.variant_name] = {
            "id": _normalize_generated_step_id(case_name),
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


def _normalize_union_match_case_terminal(
    *,
    case_name: str,
    case_steps: list[dict[str, Any]],
    case_terminal: _TerminalResult,
    result_type: UnionTypeRef,
    variant_name: str,
    shared_bundle_input_name: str,
    context: _LoweringContext,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> tuple[list[dict[str, Any]], _TerminalResult]:
    from .control_loops import _conditional_case_ref, _materialize_values_step

    step_name = f"{case_name}__result_bundle"
    step_id = _normalize_generated_step_id(step_name)
    bundle_contract = derive_structured_result_contract(
        result_type,
        workflow_name=context.workflow_name,
        step_id=step_name,
        span=span,
        form_path=form_path,
    )
    authored_contract = dict(bundle_contract.payload)
    authored_contract["path"] = f"${{inputs.{shared_bundle_input_name}}}"
    context.generated_path_spans[authored_contract["path"]] = LoweringOrigin(span=span, form_path=form_path)
    values = [
        {
            "name": "variant",
            "source": {"literal": variant_name},
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
    for field in authored_contract["variants"][variant_name]["fields"]:
        output_ref = case_terminal.output_refs.get(f"return__{field['name']}")
        if not isinstance(output_ref, str):
            raise _compile_error(
                code="workflow_return_not_exportable",
                message=f"match case did not expose union field `{field['name']}` for `{variant_name}`",
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
        ),
    )


def _control_match_arm_local_values_impl(
    *,
    local_values: Mapping[str, Any],
    binding_name: str,
    binding_terminal: _TerminalResult,
) -> dict[str, Any]:
    localized_output_refs = {
        output_name: _match_subject_scope_value(output_ref)
        for output_name, output_ref in binding_terminal.output_refs.items()
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
            return "root.steps." + value.removeprefix("self.steps.")
        return value
    if isinstance(value, Mapping):
        return {name: _match_subject_scope_value(item) for name, item in value.items()}
    return value
