"""Workflow-call lowering owners."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.workflow.loaded_bundle import workflow_managed_write_root_inputs
from orchestrator.workflow.state_layout import GeneratedPathAllocation

from ..conditionals import classify_condition_expr, render_condition_predicate
from ..contracts import derive_workflow_boundary_fields
from ..expressions import FieldAccessExpr, LiteralExpr, NameExpr
from ..phase import PHASE_CONTEXT_NAME, RUN_CONTEXT_NAME
from ..workflows import PromotedEntryHiddenContextRequirement
from ..type_env import PrimitiveTypeRef, RecordTypeRef, WorkflowRefTypeRef
from . import core as lowering_core
from .context import _TerminalResult
from .generated_paths import allocate_compatibility_binding_bundle, allocate_reusable_call_write_root
from .values import (
    _flatten_boundary_leaf_paths,
    _record_expr_value_at_path,
    _resolve_inline_expr_value,
    _resolve_nested_local_value,
)


@dataclass(frozen=True)
class LowerableWorkflowCall:
    """Owner-level workflow-call payload shared by frontend and WCC lowering."""

    callee_name: str
    bindings: tuple[tuple[str, Any], ...]
    span: Any
    form_path: tuple[str, ...]
    expansion_stack: tuple[object, ...] = ()


def _managed_inputs_from_mapping(authored_mapping: Mapping[str, object]) -> tuple[str, ...]:
    """Return generated write-root inputs declared by a lowered mapping."""

    inputs = authored_mapping.get("inputs")
    if not isinstance(inputs, Mapping):
        return ()
    return tuple(
        name for name in inputs if isinstance(name, str) and name.startswith("__write_root__")
    )


def _runtime_context_default_value(
    *,
    requirement: PromotedEntryHiddenContextRequirement,
    source_path: tuple[str, ...],
) -> str | None:
    param_name = requirement.param_name
    phase_name = requirement.phase_name
    if source_path == (param_name, "run", "run-id") or source_path == (param_name, "run-id"):
        return None
    if source_path == (param_name, "run", "state-root") or source_path == (param_name, "state-root"):
        return "state/run"
    if source_path == (param_name, "run", "artifact-root") or source_path == (param_name, "artifact-root"):
        return "artifacts/run"
    if requirement.context_kind != PHASE_CONTEXT_NAME or phase_name is None:
        return None
    if source_path == (param_name, "phase-name"):
        return phase_name
    if source_path == (param_name, "state-root"):
        return f"state/{phase_name}"
    if source_path == (param_name, "artifact-root"):
        return f"artifacts/{phase_name}"
    return None


def _declare_runtime_context_hidden_inputs(
    *,
    context: Any,
    param_name: str,
    param_type: RecordTypeRef,
    requirement: PromotedEntryHiddenContextRequirement,
    source_expr: Any,
) -> dict[str, Any]:
    """Declare runtime-owned hidden inputs for one omitted promoted-entry context param."""

    origin = lowering_core._origin_from_context_source(context, source_expr)
    with_bindings: dict[str, Any] = {}
    for flattened_field in derive_workflow_boundary_fields(
        param_type,
        generated_name=param_name,
        source_path=(param_name,),
        span=origin.span,
        form_path=origin.form_path,
    ):
        contract_definition = dict(flattened_field.contract_definition)
        default_value = _runtime_context_default_value(
            requirement=requirement,
            source_path=flattened_field.source_path,
        )
        if default_value is not None:
            contract_definition["default"] = default_value
        context.internal_generated_input_contracts.setdefault(
            flattened_field.generated_name,
            contract_definition,
        )
        context.generated_input_spans.setdefault(flattened_field.generated_name, origin)
        context.internal_generated_input_reasons.setdefault(
            flattened_field.generated_name,
            "runtime_owned_context",
        )
        with_bindings[flattened_field.generated_name] = {
            "ref": f"inputs.{flattened_field.generated_name}",
        }
    return with_bindings


def _managed_inputs_from_bundle(bundle: Any) -> tuple[str, ...]:
    """Return generated write-root inputs declared by an imported bundle."""

    if bundle is None:
        return ()
    return workflow_managed_write_root_inputs(bundle)


def _render_scalar_expr(expr: Any, *, local_values: Mapping[str, Any]) -> str:
    """Render a scalar expression as a literal or workflow substitution."""

    if isinstance(expr, LiteralExpr):
        return str(expr.value)
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, LiteralExpr):
        return str(value.value)
    if isinstance(value, str):
        return "${" + value + "}"
    raise lowering_core._compile_error(
        code="workflow_return_not_exportable",
        message="Stage 3 lowering requires command argv values to resolve to literals or workflow inputs",
        span=expr.span,
        form_path=expr.form_path,
    )


def _render_argv_tail(argv: list[Any], *, local_values: Mapping[str, Any]) -> list[str]:
    """Render frontend command arguments after a stable command prefix."""

    return [_render_scalar_expr(expr, local_values=local_values) for expr in argv]


def _render_repeat_until_max_iterations(expr: Any, *, local_values: Mapping[str, Any]) -> int:
    """Render a repeat limit expression; currently this must be a literal int."""

    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, LiteralExpr):
        return int(value.value)
    raise lowering_core._compile_error(
        code="workflow_return_not_exportable",
        message="`backlog-drain :max-iterations` must lower from a literal integer",
        span=expr.span,
        form_path=expr.form_path,
    )


def _render_boolean_predicate(expr: Any | None, *, local_values: Mapping[str, Any]) -> dict[str, Any] | None:
    """Render an optional boolean frontend expression as a shared predicate."""

    if expr is None:
        return None
    value = _resolve_inline_expr_value(expr, local_values=local_values)
    if isinstance(value, LiteralExpr) and value.literal_kind == "bool":
        return render_condition_predicate(
            classify_condition_expr(value, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
    if isinstance(value, str):
        return {"artifact_bool": {"ref": value}}
    if isinstance(expr, (NameExpr, FieldAccessExpr)):
        return render_condition_predicate(
            classify_condition_expr(expr, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
    if isinstance(expr, LiteralExpr) and expr.literal_kind == "bool":
        return render_condition_predicate(
            classify_condition_expr(expr, type_ref=PrimitiveTypeRef(name="Bool")),
            local_values=local_values,
        )
    raise lowering_core._compile_error(
        code="workflow_return_not_exportable",
        message="boolean guards must lower from literals or workflow inputs/refs",
        span=expr.span,
        form_path=expr.form_path,
    )


def _record_call_binding_label(param_name: str, field_path: tuple[str, ...]) -> str:
    """Render an authored record leaf path for diagnostics."""

    if not field_path:
        return param_name
    return f"{param_name}.{'.'.join(field_path)}"


def _render_call_binding_leaf_ref(
    value: Any,
    *,
    source_expr: Any,
    binding_label: str | None = None,
) -> dict[str, str]:
    """Apply the shared ref-only authority rule for runtime call bindings."""

    if isinstance(value, str):
        return {"ref": value}
    if binding_label is None:
        message = "Stage 3 lowering requires same-file call bindings to resolve to workflow inputs"
    else:
        message = f"record call binding `{binding_label}` must lower from workflow inputs or prior outputs"
    raise lowering_core._compile_error(
        code="workflow_signature_mismatch",
        message=message,
        span=source_expr.span,
        form_path=source_expr.form_path,
    )


def _managed_write_root_requirements_for_callable(
    *,
    lowered_callee: Any,
    imported_bundle: Any,
    span,
    form_path: tuple[str, ...],
) -> tuple[str, ...]:
    if lowered_callee is not None:
        managed_projection_inputs = tuple(
            field.generated_name
            for field in lowered_callee.boundary_projection.generated_internal_inputs
            if field.reason == "managed_write_root" and isinstance(field.generated_name, str)
        )
        if managed_projection_inputs:
            return tuple(sorted(managed_projection_inputs))
        return tuple(sorted(_managed_inputs_from_mapping(lowered_callee.authored_mapping)))
    if imported_bundle is not None:
        return tuple(sorted(_managed_inputs_from_bundle(imported_bundle)))
    raise lowering_core._compile_error(
        code="workflow_call_unknown",
        message="managed write-root discovery requires a lowered callee or imported bundle",
        span=span,
        form_path=form_path,
    )


def _managed_write_root_bindings(
    *,
    context: Any | None = None,
    source_expr: Any | None = None,
    caller_workflow_name: str,
    call_step_name: str,
    callee_name: str,
    managed_inputs: tuple[str, ...],
    iteration_scope: str | None = None,
) -> dict[str, str]:
    if context is not None and source_expr is not None:
        return {
            managed_input: allocate_reusable_call_write_root(
                context=context,
                source_expr=source_expr,
                call_step_name=call_step_name,
                callee_name=callee_name,
                managed_input_name=managed_input,
            ).concrete_path_template
            for managed_input in sorted(managed_inputs)
        }
    base_segments = [
        ".orchestrate/workflow_lisp/calls",
        caller_workflow_name,
        call_step_name,
    ]
    if iteration_scope is not None:
        base_segments.append(iteration_scope)
    base_segments.append(callee_name)
    base_path = "/".join(base_segments)
    return {
        managed_input: f"{base_path}/{managed_input}.json"
        for managed_input in sorted(managed_inputs)
    }


def _managed_write_root_binding_step(
    *,
    context: Any,
    source_expr: Any,
    call_step_name: str,
    callee_name: str,
    managed_inputs: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not managed_inputs:
        return [], {}

    bindings = _managed_write_root_bindings(
        context=context,
        source_expr=source_expr,
        caller_workflow_name=context.workflow_name,
        call_step_name=call_step_name,
        callee_name=callee_name,
        managed_inputs=managed_inputs,
        iteration_scope=context.iteration_scope,
    )
    if context.iteration_scope is None:
        return [], bindings

    prepare_step_name = f"{call_step_name}__managed_write_roots"
    prepare_step_id = lowering_core._normalize_generated_step_id(prepare_step_name)
    bundle_allocation = allocate_compatibility_binding_bundle(
        context=context,
        source_expr=source_expr,
        call_step_name=call_step_name,
        callee_name=callee_name,
    )
    bundle_path = bundle_allocation.concrete_path_template
    command = [
        "python",
        "-c",
        (
            "import json, pathlib, sys; "
            "out = pathlib.Path(sys.argv[1]); "
            "out.parent.mkdir(parents=True, exist_ok=True); "
            "args = sys.argv[2:]; "
            "payload = {args[i]: args[i + 1] for i in range(0, len(args), 2)}; "
            "out.write_text(json.dumps(payload, sort_keys=True) + '\\n', encoding='utf-8')"
        ),
        bundle_path,
    ]
    for managed_input, value in bindings.items():
        command.extend((managed_input, value))

    step = {
        "name": prepare_step_name,
        "id": prepare_step_id,
        "command": command,
        "output_bundle": {
            "path": bundle_path,
            "fields": [
                {
                    "name": managed_input,
                    "json_pointer": f"/{managed_input}",
                    "type": "relpath",
                }
                for managed_input in sorted(managed_inputs)
            ],
        },
    }
    lowering_core._record_step_origin(
        context,
        step_name=prepare_step_name,
        step_id=prepare_step_id,
        source=source_expr,
    )
    return [step], {
        managed_input: {"ref": f"self.steps.{prepare_step_name}.artifacts.{managed_input}"}
        for managed_input in sorted(managed_inputs)
    }


def _lower_call_expr(
    typed_expr: Any,
    *,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    expr = typed_expr.expr
    return _lower_workflow_call(
        LowerableWorkflowCall(
            callee_name=expr.callee_name,
            bindings=tuple(expr.bindings),
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        ),
        result_type=typed_expr.type_ref,
        context=context,
        local_values=local_values,
    )


def _lower_workflow_call(
    expr: LowerableWorkflowCall,
    *,
    result_type: Any,
    context: Any,
    local_values: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], Any]:
    signature = context.workflow_catalog.signatures_by_name.get(expr.callee_name)
    resolved_ref = lowering_core._resolved_workflow_ref_value(
        local_values.get(expr.callee_name),
        context=context,
        expected_type=None,
    )
    binding_by_name = dict(expr.bindings)
    if resolved_ref is not None:
        canonical_name = resolved_ref.workflow_name
        callee_signature = type(
            "WorkflowRefSignature",
            (),
            {"params": resolved_ref.signature_params, "return_type_ref": resolved_ref.return_type_ref},
        )()
        callee = context.lowered_callees.get(canonical_name)
        if callee is None and canonical_name in context.workflows_by_name:
            callee = context.ensure_workflow_lowered(canonical_name)
        imported_bundle = context.imported_workflow_bundles.get(canonical_name)
    elif signature is not None and any(isinstance(type_ref, WorkflowRefTypeRef) for _, type_ref in signature.params):
        workflow_ref_bindings: dict[str, Any] = {}
        for param_name, param_type in signature.params:
            if not isinstance(param_type, WorkflowRefTypeRef):
                continue
            binding_expr = binding_by_name.get(param_name)
            if binding_expr is None:
                raise lowering_core._compile_error(
                    code="workflow_signature_mismatch",
                    message=f"call is missing required binding `{param_name}`",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            resolved_binding = lowering_core._resolved_workflow_ref_value(
                _resolve_inline_expr_value(binding_expr, local_values=local_values) or binding_expr,
                context=context,
                expected_type=param_type,
            )
            if resolved_binding is None:
                raise lowering_core._compile_error(
                    code="workflow_ref_literal_required",
                    message="workflow-ref arguments must be literals or forwarded workflow-ref bindings",
                    span=binding_expr.span,
                    form_path=binding_expr.form_path,
                )
            workflow_ref_bindings[param_name] = resolved_binding
        specialized = context.specialize_workflow(signature.name, workflow_ref_bindings)
        canonical_name = specialized.signature.name
        callee_signature = specialized.signature
        callee = context.ensure_workflow_lowered(canonical_name)
        imported_bundle = context.imported_workflow_bundles.get(canonical_name)
        binding_by_name = {
            name: value
            for name, value in binding_by_name.items()
            if name not in workflow_ref_bindings
        }
    else:
        canonical_name = signature.name if signature is not None else expr.callee_name
        callee = context.lowered_callees.get(canonical_name)
        imported_bundle = context.imported_workflow_bundles.get(canonical_name)
        callee_signature = callee.typed_workflow.signature if callee is not None else signature
        if callee is None and imported_bundle is None and canonical_name in context.workflows_by_name:
            callee = context.ensure_workflow_lowered(canonical_name)
    if callee is None and imported_bundle is None:
        raise lowering_core._compile_error(
            code="workflow_call_unknown",
            message=f"unknown workflow callee `{expr.callee_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = f"{context.step_name_prefix}__call_{canonical_name}"
    step_id = lowering_core._normalize_generated_step_id(step_name)
    with_bindings: dict[str, Any] = {}
    assert callee_signature is not None

    for param_name, param_type in callee_signature.params:
        value_expr = binding_by_name.get(param_name)
        if value_expr is None:
            requirement = getattr(callee_signature, "hidden_context_requirements", {}).get(param_name)
            if (
                getattr(context.signature, "allow_hidden_context_binding", False)
                and isinstance(param_type, RecordTypeRef)
                and param_type.name in {RUN_CONTEXT_NAME, PHASE_CONTEXT_NAME}
            ):
                if requirement is None:
                    code = "promoted_entry_hidden_context_metadata_missing"
                    ambiguities = getattr(callee_signature, "hidden_context_ambiguities", {})
                    if param_name in ambiguities:
                        code = "promoted_entry_hidden_phase_ctx_ambiguous"
                    raise lowering_core._compile_error(
                        code=code,
                        message=f"promoted-entry hidden binding metadata is unavailable for `{param_name}`",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                with_bindings.update(
                    lowering_core._declare_runtime_context_hidden_inputs(
                        context=context,
                        param_name=param_name,
                        param_type=param_type,
                        requirement=requirement,
                        source_expr=expr,
                    )
                )
                continue
            if param_name in callee_signature.param_defaults:
                continue
            raise lowering_core._compile_error(
                code="workflow_signature_mismatch",
                message=f"call is missing required binding `{param_name}`",
                span=expr.span,
                form_path=expr.form_path,
            )
        if isinstance(param_type, RecordTypeRef):
            with_bindings.update(
                _render_record_call_bindings(
                    param_name,
                    param_type,
                    value_expr,
                    local_values=local_values,
                )
            )
            continue
        with_bindings[param_name] = _render_call_binding_ref(value_expr, local_values=local_values)
    managed_inputs = _managed_write_root_requirements_for_callable(
        lowered_callee=callee,
        imported_bundle=imported_bundle,
        span=expr.span,
        form_path=expr.form_path,
    )
    binding_steps, managed_bindings = _managed_write_root_binding_step(
        context=context,
        source_expr=expr,
        call_step_name=step_name,
        callee_name=canonical_name,
        managed_inputs=managed_inputs,
    )
    with_bindings.update(managed_bindings)
    lowering_core._record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
    step = {
        "name": step_name,
        "id": step_id,
        "call": canonical_name,
        "with": with_bindings,
    }
    return [*binding_steps, step], _TerminalResult(
        step_name=step_name,
        step_id=step_id,
        output_refs={
            output_name: f"root.steps.{step_name}.artifacts.{output_name}"
            for output_name, _ in _flatten_boundary_leaf_paths(result_type, generated_name="return")
        },
        output_kind="call",
        hidden_inputs={},
    )


def _render_call_binding_ref(
    expr: Any,
    *,
    local_values: Mapping[str, Any],
    field_path: tuple[str, ...] = (),
) -> Any:
    """Render one frontend expression as a `call.with` binding value."""

    value = lowering_core._resolve_expr_local_value(expr, local_values=local_values)
    if field_path:
        value = _resolve_nested_local_value(value, field_path)
    return lowering_core._render_call_binding_leaf_ref(value, source_expr=expr)


def _render_record_call_bindings(
    param_name: str,
    param_type: RecordTypeRef,
    value_expr: Any,
    *,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    """Lower one record-typed call argument into flattened `call.with` refs."""

    bindings: dict[str, Any] = {}
    resolved_value = _resolve_inline_expr_value(value_expr, local_values=local_values)
    for generated_name, field_path in _flatten_boundary_leaf_paths(param_type, generated_name=param_name):
        leaf_source_expr = value_expr
        if isinstance(resolved_value, Mapping):
            leaf_value = _resolve_nested_local_value(resolved_value, field_path)
        elif isinstance(resolved_value, lowering_core.RecordExpr):
            leaf_source_expr = _record_expr_value_at_path(resolved_value, field_path)
            leaf_value = _resolve_inline_expr_value(leaf_source_expr, local_values=local_values)
        else:
            leaf_value = lowering_core._inline_expr_field_value(
                value_expr,
                field_path=field_path,
                local_values=local_values,
            )
        bindings[generated_name] = _render_call_binding_leaf_ref(
            leaf_value,
            source_expr=leaf_source_expr,
            binding_label=_record_call_binding_label(param_name, field_path),
        )
    return bindings
