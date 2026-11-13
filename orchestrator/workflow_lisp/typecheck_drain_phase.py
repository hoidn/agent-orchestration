"""Phase-target typecheck ownership for Workflow Lisp."""

from __future__ import annotations

from .effects import EMPTY_EFFECT_SUMMARY
from .expressions import PhaseTargetExpr
from .phase import resolve_phase_target_type
from .typecheck_context import raise_error


def typecheck_phase_target_expr(
    expr: PhaseTargetExpr,
    *,
    context,
    recurse,
    typed_factory,
):
    if context.active_phase_scope is None:
        raise_error(
            "`phase-target` is valid only inside an active `with-phase` scope",
            code="phase_target_outside_with_phase",
            span=expr.span,
            form_path=expr.form_path,
        )
    target_type = resolve_phase_target_type(
        context.active_phase_scope,
        expr.target_name,
        type_env=context.type_env,
        span=expr.span,
        form_path=expr.form_path,
    )
    return typed_factory(expr=expr, type_ref=target_type, effect=EMPTY_EFFECT_SUMMARY)


