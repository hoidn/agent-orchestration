"""Review-loop stdlib typecheck ownership and policy guards."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .expressions import StdlibSpecializationExpr
from .phase_stdlib import (
    ReviewLoopLegacyBridgePolicy,
    ensure_review_loop_legacy_bridge_allowed,
)
from .spans import SourceSpan
from .type_env import FrontendTypeEnvironment, UnionTypeRef


def validate_review_loop_result_contract(
    return_type: UnionTypeRef,
    *,
    type_env: FrontendTypeEnvironment,
    span: SourceSpan,
    form_path: tuple[str, ...],
    legacy_validator: Callable[..., None],
) -> None:
    """Delegate the legacy review-loop result-contract check through the owner seam."""

    legacy_validator(
        return_type,
        type_env=type_env,
        span=span,
        form_path=form_path,
    )


def typecheck_stdlib_specialization_expr(
    expr: StdlibSpecializationExpr,
    *,
    review_loop_legacy_bridge_policy: ReviewLoopLegacyBridgePolicy,
    legacy_typechecker: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    """Guard the legacy review-loop bridge before delegating to the compatibility typer."""

    ensure_review_loop_legacy_bridge_allowed(
        review_loop_legacy_bridge_policy=review_loop_legacy_bridge_policy,
        request_kind=expr.request_kind,
        span=expr.span,
        form_path=expr.form_path,
        expansion_stack=expr.expansion_stack,
    )
    return legacy_typechecker(expr, **kwargs)
