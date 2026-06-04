"""Workflow-call lowering owners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..phase import PHASE_CONTEXT_NAME, RUN_CONTEXT_NAME
from ..type_env import RecordTypeRef, WorkflowRefTypeRef


def _managed_write_root_requirements_for_callable(
    *,
    lowered_callee: Any,
    imported_bundle: Any,
    span,
    form_path: tuple[str, ...],
) -> tuple[str, ...]:
    from .core import _managed_write_root_requirements_for_callable as owner

    return owner(
        lowered_callee=lowered_callee,
        imported_bundle=imported_bundle,
        span=span,
        form_path=form_path,
    )


def _managed_write_root_bindings(
    *,
    caller_workflow_name: str,
    call_step_name: str,
    callee_name: str,
    managed_inputs: tuple[str, ...],
    iteration_scope: str | None = None,
) -> dict[str, str]:
    from .core import _managed_write_root_bindings as owner

    return owner(
        caller_workflow_name=caller_workflow_name,
        call_step_name=call_step_name,
        callee_name=callee_name,
        managed_inputs=managed_inputs,
        iteration_scope=iteration_scope,
    )


def _managed_write_root_binding_step(
    *,
    context: Any,
    source_expr: Any,
    call_step_name: str,
    callee_name: str,
    managed_inputs: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .core import _normalize_generated_step_id, _record_step_origin

    if not managed_inputs:
        return [], {}

    bindings = _managed_write_root_bindings(
        caller_workflow_name=context.workflow_name,
        call_step_name=call_step_name,
        callee_name=callee_name,
        managed_inputs=managed_inputs,
        iteration_scope=context.iteration_scope,
    )
    if context.iteration_scope is None:
        return [], bindings

    prepare_step_name = f"{call_step_name}__managed_write_roots"
    prepare_step_id = _normalize_generated_step_id(prepare_step_name)
    bundle_path = "/".join(
        (
            ".orchestrate/workflow_lisp/call_bindings",
            context.workflow_name,
            call_step_name,
            context.iteration_scope,
            callee_name,
            "__managed_write_roots.json",
        )
    )
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
    _record_step_origin(context, step_name=prepare_step_name, step_id=prepare_step_id, source=source_expr)
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
    from .context import _TerminalResult
    from .core import (
        _compile_error,
        _declare_runtime_context_hidden_inputs,
        _normalize_generated_step_id,
        _record_step_origin,
        _resolved_workflow_ref_value,
    )
    from .values import _flatten_boundary_leaf_paths, _resolve_inline_expr_value

    expr = typed_expr.expr
    signature = context.workflow_catalog.signatures_by_name.get(expr.callee_name)
    resolved_ref = _resolved_workflow_ref_value(
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
                raise _compile_error(
                    code="workflow_signature_mismatch",
                    message=f"call is missing required binding `{param_name}`",
                    span=expr.span,
                    form_path=expr.form_path,
                )
            resolved_binding = _resolved_workflow_ref_value(
                _resolve_inline_expr_value(binding_expr, local_values=local_values) or binding_expr,
                context=context,
                expected_type=param_type,
            )
            if resolved_binding is None:
                raise _compile_error(
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
        raise _compile_error(
            code="workflow_call_unknown",
            message=f"unknown workflow callee `{expr.callee_name}` during lowering",
            span=expr.span,
            form_path=expr.form_path,
        )
    step_name = f"{context.step_name_prefix}__call_{canonical_name}"
    step_id = _normalize_generated_step_id(step_name)
    with_bindings: dict[str, Any] = {}
    assert callee_signature is not None
    from .core import _render_call_binding_ref, _render_record_call_bindings

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
                    raise _compile_error(
                        code=code,
                        message=f"promoted-entry hidden binding metadata is unavailable for `{param_name}`",
                        span=expr.span,
                        form_path=expr.form_path,
                    )
                with_bindings.update(
                    _declare_runtime_context_hidden_inputs(
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
            raise _compile_error(
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
    _record_step_origin(context, step_name=step_name, step_id=step_id, source=expr)
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
            for output_name, _ in _flatten_boundary_leaf_paths(typed_expr.type_ref, generated_name="return")
        },
        output_kind="call",
        hidden_inputs={},
    )
