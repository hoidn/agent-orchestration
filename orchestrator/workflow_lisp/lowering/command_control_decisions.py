"""Pure lexical capture facts; generated workflow emission stays with its owner."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..expression_traversal import iter_child_exprs
from ..expressions import FieldAccessExpr, LetStarExpr, MatchExpr, NameExpr
from ..type_env import TypeRef, UnionTypeRef, VariantCaseTypeRef


def projection_artifact_names(output_contracts: Mapping[str, Any]) -> dict[str, str]:
    """Select logical outputs without constructing runtime references."""
    if set(output_contracts) == {"__result__"}:
        return {"return": "__result__"}
    return {name: name for name in output_contracts}


def provider_capture_artifact_names(result_type: Any, *, capture_context: bool) -> dict[str, str] | None:
    from ..context_types import is_contextual_type

    if not capture_context or not is_contextual_type(result_type):
        return None
    return {"return__result": "result", "return__context": "context"}


def binding_projection_output_aliases(boundary_fields: tuple[Any, ...], *, whole_value: bool, pure_call_composition: bool) -> dict[str, str] | None:
    if whole_value or not boundary_fields or not pure_call_composition:
        return None
    return {
        f"return__{'__'.join(boundary.source_path[1:])}": boundary.generated_name
        for boundary in boundary_fields
    }


def selected_phase_scope(context_value: Any, *, phase_name: str, ctx_expr: Any, span: Any, form_path: tuple[str, ...]) -> tuple[Any, Mapping[str, Any]]:
    """Select phase metadata and target availability without deriving paths."""
    from ..phase import IMPLEMENTATION_ATTEMPT_PHASE_NAME, PHASE_TARGET_SPECS, PhaseScope
    from .command_transport_decisions import RUNTIME_REFERENCE, is_direct_reference
    from .context import _compile_error

    if not isinstance(context_value, Mapping):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires the phase context to resolve from workflow inputs",
            span=ctx_expr.span, form_path=ctx_expr.form_path,
        )
    if "implementation_state_bundle_path" not in context_value:
        if not all(is_direct_reference(context_value.get(name)) for name in ("state-root", "artifact-root")):
            raise _compile_error(
                code="phase_translation_body_invalid",
                message="`with-phase` lowering requires generic phase roots to resolve from workflow inputs",
                span=ctx_expr.span, form_path=ctx_expr.form_path,
            )
        return PhaseScope(context_record_name="PhaseCtx", phase_name=phase_name, target_types={}), {
            name: RUNTIME_REFERENCE for name in PHASE_TARGET_SPECS
        }
    if phase_name != IMPLEMENTATION_ATTEMPT_PHASE_NAME:
        raise _compile_error(
            code="phase_context_invalid",
            message="`with-phase` supports only the `implementation` phase in the legacy bridge",
            span=span, form_path=form_path,
        )
    return _selected_implementation_phase_scope(context_value, phase_name=phase_name, ctx_expr=ctx_expr)


def _selected_implementation_phase_scope(context_value: Mapping[str, Any], *, phase_name: str, ctx_expr: Any) -> tuple[Any, Mapping[str, Any]]:
    from ..phase import PhaseScope
    from .command_transport_decisions import is_direct_reference
    from .context import _compile_error

    fields = {"execution-report": "execution_report_target", "progress-report": "progress_report_target"}
    if not all(is_direct_reference(context_value.get(name)) for name in ("implementation_state_bundle_path", *fields.values())):
        raise _compile_error(
            code="phase_translation_body_invalid",
            message="`with-phase` lowering requires bound relpath fields on the phase context",
            span=ctx_expr.span, form_path=ctx_expr.form_path,
        )
    return PhaseScope(
        context_record_name="ImplementationAttemptPhaseCtx", phase_name=phase_name,
        bundle_path_field="implementation_state_bundle_path", target_fields=fields,
    ), {name: context_value[field] for name, field in fields.items()}


def helper_capture_names(expr: Any, *, local_type_bindings: Mapping[str, Any]) -> tuple[str, ...]:
    used_names: set[str] = set()

    def capture(name: str, bound_names: frozenset[str]) -> None:
        if name in local_type_bindings and name not in bound_names:
            used_names.add(name)

    def walk(node: Any, bound_names: frozenset[str]) -> None:
        if isinstance(node, NameExpr):
            capture(node.name, bound_names)
            return
        if isinstance(node, FieldAccessExpr) and isinstance(node.base, NameExpr):
            capture(node.base.name, bound_names)
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

    walk(expr, frozenset())
    return tuple(name for name in local_type_bindings if name in used_names)


def helper_capture_payload(
    capture_type: TypeRef, *, type_env: Any, span: Any, form_path: tuple[str, ...],
) -> tuple[tuple[Any, ...], Mapping[str, TypeRef]] | None:
    """Expose a variant's payload without manufacturing a nominal record type."""
    if not isinstance(capture_type, VariantCaseTypeRef):
        return None
    union_type = type_env.resolve_type(capture_type.union_name, span=span, form_path=form_path)
    assert isinstance(union_type, UnionTypeRef)
    return capture_type.definition.fields, union_type.variant_field_types[capture_type.variant_name]


def resolved_surface_proc_ref(
    value: Any, *, typed_procedures: Mapping[str, Any], local_values: Mapping[str, Any],
    procedure_catalog: Any = None, expected_type: Any = None,
) -> Any:
    from ..expressions import BindProcExpr, ProcRefLiteralExpr
    from ..procedure_refs import ResolvedProcRefValue, resolve_proc_ref_value
    from ..procedures import ProcedureCatalog

    if isinstance(value, ResolvedProcRefValue):
        return value
    if not isinstance(value, (NameExpr, ProcRefLiteralExpr, BindProcExpr)):
        return None
    if procedure_catalog is None:
        procedure_catalog = ProcedureCatalog(
            signatures_by_name={name: proc.signature for name, proc in typed_procedures.items()},
            definitions_by_name={name: proc.definition for name, proc in typed_procedures.items()},
            call_graph={},
        )
    return resolve_proc_ref_value(
        value, procedure_catalog=procedure_catalog,
        proc_ref_env={name: ref for name, ref in local_values.items() if isinstance(ref, ResolvedProcRefValue)},
        expected_type=expected_type,
    )


def resolved_surface_workflow_ref(
    value: Any, *, workflow_catalog: Any, typed_workflows: Mapping[str, Any],
    expected_type: Any = None,
) -> Any:
    from ..expressions import EnumMemberExpr, WorkflowRefLiteralExpr
    from ..workflow_refs import (
        ResolvedWorkflowRef, resolve_workflow_ref_literal, resolve_workflow_ref_name,
        workflow_ref_target_name,
    )
    from ..type_env import WorkflowRefTypeRef
    from .context import _compile_error

    if isinstance(value, ResolvedWorkflowRef):
        return value
    if isinstance(value, WorkflowRefLiteralExpr):
        if expected_type is None:
            signature = workflow_catalog.signatures_by_name.get(value.target_name)
            if signature is None:
                raise _compile_error(
                    code="workflow_ref_unknown", message=f"unknown workflow ref `{value.target_name}`",
                    span=value.span, form_path=value.form_path,
                )
            expected_type = WorkflowRefTypeRef(
                name=f"WorkflowRef[{ ' '.join(type_ref.name for _, type_ref in signature.params) } -> {signature.return_type_ref.name}]",
                param_type_refs=tuple(type_ref for _, type_ref in signature.params),
                return_type_ref=signature.return_type_ref,
            )
        return resolve_workflow_ref_literal(
            value, expected_type=expected_type, workflow_catalog=workflow_catalog,
            typed_workflows_by_name=typed_workflows, allow_extern_rebinding=False,
        )
    if isinstance(value, (NameExpr, EnumMemberExpr)):
        return resolve_workflow_ref_name(
            workflow_ref_target_name(value), workflow_catalog=workflow_catalog,
            span=value.span, form_path=value.form_path, expansion_stack=value.expansion_stack,
            expected_type=expected_type, typed_workflows_by_name=typed_workflows,
            allow_extern_rebinding=False,
        )
    return None


def _surface_procedure_callee(
    call: Any, *, local_values: Mapping[str, Any], typed_procedures: Mapping[str, Any],
    procedure_catalog: Any,
) -> Any:
    from .context import _compile_error

    if call.specialized_callee_name is not None:
        name = call.specialized_callee_name
        code = "procedure_lowering_unresolved"
        message = f"compiler-owned specialization row `{name}` is missing during lowering"
    else:
        bound = resolved_surface_proc_ref(
            local_values.get(call.callee_name), typed_procedures=typed_procedures,
            procedure_catalog=procedure_catalog, local_values=local_values,
        )
        if bound is not None:
            name = bound.call_target_name
            code = "procedure_lowering_unresolved"
            message = f"compiler-owned bound ProcRef specialization row `{name}` is missing during lowering"
        else:
            name = call.callee_name
            code = "procedure_call_unknown"
            message = f"unknown procedure callee `{name}` during lowering"
    procedure = typed_procedures.get(name)
    if procedure is None:
        raise _compile_error(code=code, message=message, span=call.span, form_path=call.form_path)
    return procedure


def _surface_procedure_actuals(
    procedure: Any, args: tuple[Any, ...], *, local_values: Mapping[str, Any],
    typed_procedures: Mapping[str, Any], procedure_catalog: Any,
    workflow_catalog: Any, typed_workflows: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], tuple[Any, ...]]:
    from ..expressions import EnumMemberExpr
    from ..type_env import ProcRefTypeRef, WorkflowRefTypeRef
    from .context import _compile_error
    from .values import _resolve_inline_expr_value

    workflow_refs = {}
    proc_refs = {}
    residual = []
    for arg, (name, param_type) in zip(args, procedure.signature.params, strict=True):
        if isinstance(param_type, WorkflowRefTypeRef):
            candidate = arg if isinstance(arg, EnumMemberExpr) else _resolve_inline_expr_value(arg, local_values=local_values) or arg
            resolved = resolved_surface_workflow_ref(
                candidate, workflow_catalog=workflow_catalog, typed_workflows=typed_workflows,
                expected_type=param_type,
            )
            if resolved is None:
                raise _compile_error(
                    code="workflow_ref_literal_required",
                    message="workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                    span=arg.span, form_path=arg.form_path,
                )
            workflow_refs[name] = resolved
            continue
        if isinstance(param_type, ProcRefTypeRef):
            resolved = resolved_surface_proc_ref(
                _resolve_inline_expr_value(arg, local_values=local_values) or arg,
                typed_procedures=typed_procedures, procedure_catalog=procedure_catalog,
                local_values=local_values, expected_type=param_type,
            )
            if resolved is not None:
                proc_refs[name] = resolved
                continue
        residual.append(arg)
    return workflow_refs, proc_refs, tuple(residual)


def select_surface_procedure_call(
    call: Any, *, local_values: Mapping[str, Any], typed_procedures: Mapping[str, Any],
    procedure_catalog: Any, workflow_catalog: Any, typed_workflows: Mapping[str, Any],
) -> tuple[Any, tuple[Any, ...]]:
    from ..procedure_specialization import materialized_specialization_rows
    from .context import _compile_error

    procedure = _surface_procedure_callee(
        call, local_values=local_values, typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog,
    )
    workflow_refs, proc_refs, residual = _surface_procedure_actuals(
        procedure, call.args, local_values=local_values, typed_procedures=typed_procedures,
        procedure_catalog=procedure_catalog, workflow_catalog=workflow_catalog,
        typed_workflows=typed_workflows,
    )
    if not (workflow_refs or proc_refs):
        return procedure, call.args
    rows = materialized_specialization_rows(
        procedure, workflow_ref_bindings=workflow_refs, proc_ref_bindings=proc_refs,
        typed_procedures=typed_procedures,
    )
    if len(rows) != 1:
        raise _compile_error(
            code="procedure_lowering_unresolved",
            message="compiler-owned procedure specialization row with exact compile-time bindings is missing or ambiguous during lowering",
            span=call.span, form_path=call.form_path,
        )
    return rows[0], residual


def inline_procedure_bindings(
    procedure: Any, *, caller_values: Mapping[str, Any], actual_values: tuple[Any, ...],
) -> dict[str, Any]:
    values = dict(caller_values)
    values.update(procedure_specialization_bindings(procedure))
    for value, (name, _) in zip(actual_values, procedure.signature.params, strict=True):
        values[name] = value
    return values


def procedure_specialization_bindings(procedure: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if procedure.specialization is not None:
        for kind in ("workflow_ref_bindings", "proc_ref_bindings", "value_bindings"):
            values.update(dict(getattr(procedure.specialization, kind, {})))
    return values


def inline_output_boundary_fields(expr: Any, *, type_ref: Any, type_env: Any, signature: Any):
    from dataclasses import replace
    from ..contracts import derive_workflow_boundary_fields, root_workflow_boundary_field
    from ..syntax import target_dsl_supports_trial
    from ..type_env import RecordTypeRef

    allow_direct = (
        type_ref == signature.return_type_ref
        and isinstance(getattr(signature, "compiler_direct_result_contract_digest", None), str)
        and target_dsl_supports_trial(type_env.target_dsl_version)
    )
    if isinstance(type_ref, (RecordTypeRef, UnionTypeRef)):
        return derive_workflow_boundary_fields(
            type_ref, generated_name="return", source_path=("return",),
            span=expr.span, form_path=expr.form_path,
            allow_transportable_value=allow_direct, type_env=type_env,
        )
    return (replace(root_workflow_boundary_field(
        type_ref, span=expr.span, form_path=expr.form_path, type_env=type_env,
    ), generated_name="return"),)
