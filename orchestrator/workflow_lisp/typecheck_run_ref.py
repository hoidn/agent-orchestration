"""Narrow type owner for isolated target-2.24 ``run-ref`` expressions."""

from __future__ import annotations

from dataclasses import replace

from .effects import (
    RunsRefEffect,
    effect_summary_from_direct,
    merge_effect_summaries,
)
from .expressions import RunRefBundleProgram, RunRefExpr, RunRefPathProgram
from .type_env import type_refs_compatible
from .typecheck_context import raise_error


def _require_transportable(type_ref, *, expr, role: str) -> None:
    # Import lazily: contracts owns workflow-signature projection and therefore
    # reaches this dispatch module through the workflow compiler at import time.
    from .contracts import is_transportable_result_type

    if is_transportable_result_type(type_ref):
        return
    raise_error(
        f"`run-ref` {role} type `{type_ref.name}` is not transportable",
        code="workflow_boundary_type_invalid",
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )


def _typecheck_mode_one(expr, *, context, recurse):
    if context.workflow_catalog is None:
        raise TypeError("workflow_catalog is required for bundle-mode run-ref")
    assert isinstance(expr.program, RunRefBundleProgram)
    signature = context.workflow_catalog.signatures_by_name.get(
        expr.program.workflow_name
    )
    if signature is None:
        raise_error(
            f"unknown run-ref bundle workflow `{expr.program.workflow_name}`",
            code="workflow_call_unknown",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )

    expected_inputs = dict(signature.params)
    expected_inputs.update(signature.private_compatibility_bridge_types)
    defaulted = frozenset(signature.param_defaults)
    seen: set[str] = set()
    typed_inputs = []
    input_effects = []
    for name, value_expr in expr.inputs:
        if name in seen:
            raise_error(
                f"duplicate run-ref input `:{name}`",
                code="workflow_signature_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        seen.add(name)
        expected = expected_inputs.get(name)
        if expected is None:
            raise_error(
                f"run-ref input `:{name}` does not match the child signature",
                code="workflow_signature_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        _require_transportable(expected, expr=value_expr, role=f"input `:{name}`")
        typed = recurse(value_expr, expected_type=expected)
        _require_transportable(
            typed.type_ref,
            expr=value_expr,
            role=f"input `:{name}`",
        )
        if not type_refs_compatible(expected, typed.type_ref):
            raise_error(
                f"run-ref input `:{name}` expected `{expected.name}` but got `{typed.type_ref.name}`",
                code="type_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        typed_inputs.append((name, typed.expr))
        input_effects.append(typed.effect_summary)

    missing = [
        name
        for name in expected_inputs
        if name not in seen and name not in defaulted
    ]
    if missing:
        raise_error(
            f"run-ref is missing required child input `:{missing[0]}`",
            code="workflow_signature_mismatch",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
        )
    _require_transportable(
        signature.return_type_ref,
        expr=expr,
        role="child return",
    )
    return signature.return_type_ref, tuple(typed_inputs), tuple(input_effects)


def _typecheck_mode_two(expr, *, context, recurse):
    assert isinstance(expr.program, RunRefPathProgram)
    if expr.returns_type_name is None:
        value_type = context.type_env.resolve_type(
            "Value",
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            session_state=context.session_state,
        )
    else:
        value_type = context.type_env.resolve_type(
            expr.returns_type_name,
            span=expr.span,
            form_path=expr.form_path,
            expansion_stack=expr.expansion_stack,
            session_state=context.session_state,
        )
    _require_transportable(value_type, expr=expr, role="return refinement")

    seen: set[str] = set()
    typed_inputs = []
    input_effects = []
    for name, value_expr in expr.inputs:
        if name in seen:
            raise_error(
                f"duplicate run-ref input `:{name}`",
                code="workflow_signature_mismatch",
                span=value_expr.span,
                form_path=value_expr.form_path,
                expansion_stack=value_expr.expansion_stack,
            )
        seen.add(name)
        typed = recurse(value_expr)
        _require_transportable(
            typed.type_ref,
            expr=value_expr,
            role=f"input `:{name}`",
        )
        typed_inputs.append((name, typed.expr))
        input_effects.append(typed.effect_summary)
    return value_type, tuple(typed_inputs), tuple(input_effects)


def typecheck_run_ref_expr(expr, *, context, recurse, typed_factory):
    """Type one isolated run-ref without registering it as a live form."""

    if isinstance(expr.program, RunRefBundleProgram):
        value_type, typed_inputs, input_effects = _typecheck_mode_one(
            expr,
            context=context,
            recurse=recurse,
        )
        effect_subject = expr.program.workflow_name
    else:
        value_type, typed_inputs, input_effects = _typecheck_mode_two(
            expr,
            context=context,
            recurse=recurse,
        )
        effect_subject = expr.program.entry_name

    run_effect = effect_summary_from_direct(
        direct_effects=(
            RunsRefEffect(subject=tuple(effect_subject.split("."))),
        )
    )
    return typed_factory(
        expr=replace(expr, inputs=typed_inputs),
        type_ref=value_type,
        effect=merge_effect_summaries(*input_effects, run_effect),
    )
