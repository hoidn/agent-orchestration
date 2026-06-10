"""Internal lowering-route contracts for Workflow Lisp Stage 3 compilation."""

from __future__ import annotations

from enum import Enum

from orchestrator.workflow_lisp.expression_traversal import walk_expr

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..effects import EMPTY_EFFECT_SUMMARY
from ..expressions import (
    FieldAccessExpr,
    LetStarExpr,
    LiteralExpr,
    NameExpr,
    RecordExpr,
    UnionVariantExpr,
)
from ..workflows import TypedWorkflowDef


class LoweringRoute(str, Enum):
    """Compiler-internal Stage 3 lowering routes."""

    LEGACY = "legacy"
    WCC_M1 = "wcc_m1"


DEFAULT_LOWERING_ROUTE = LoweringRoute.LEGACY
_PURE_WCC_M1_EXPR_TYPES = (
    LiteralExpr,
    NameExpr,
    FieldAccessExpr,
    RecordExpr,
    UnionVariantExpr,
    LetStarExpr,
)


def normalize_lowering_route(route: LoweringRoute | str | None) -> LoweringRoute:
    """Resolve the caller-provided route selector to one enum value."""

    if route is None:
        return DEFAULT_LOWERING_ROUTE
    if isinstance(route, LoweringRoute):
        return route
    return LoweringRoute(route)


def validate_wcc_m1_route_supported(typed_workflows: tuple[TypedWorkflowDef, ...]) -> None:
    """Reject typed workflows that fall outside the WCC M1 pure subset."""

    for workflow in typed_workflows:
        if workflow.effect_summary != EMPTY_EFFECT_SUMMARY:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="wcc_lowering_route_unsupported",
                        message=(
                            "WCC M1 lowering supports only pure value workflows; "
                            f"`{workflow.definition.name}` carries effects"
                        ),
                        span=workflow.definition.span,
                        form_path=workflow.definition.form_path,
                        expansion_stack=workflow.definition.expansion_stack,
                        phase="lowering",
                    ),
                )
            )
        for node in walk_expr(workflow.typed_body.expr):
            if isinstance(node, _PURE_WCC_M1_EXPR_TYPES):
                continue
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="wcc_lowering_route_unsupported",
                        message=(
                            "WCC M1 lowering supports only the pure value subset; "
                            f"`{workflow.definition.name}` uses unsupported `{type(node).__name__}`"
                        ),
                        span=node.span,
                        form_path=node.form_path,
                        expansion_stack=node.expansion_stack,
                        phase="lowering",
                    ),
                )
            )
