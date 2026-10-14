"""Internal lowering-route contracts for Workflow Lisp Stage 3 compilation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from enum import Enum

from orchestrator.contracts.closed_program.targets import (
    DEFAULT_LOWERING_SCHEMA, LOWERING_SCHEMA_LEGACY, LOWERING_SCHEMA_WCC,
)

class LoweringRoute(str, Enum):
    """Compiler-internal Stage 3 lowering routes."""

    LEGACY = "legacy"
    WCC_M1 = "wcc_m1"
    WCC_M2 = "wcc_m2"
    WCC_M3 = "wcc_m3"
    WCC_M4 = "wcc_m4"


DEFAULT_LOWERING_ROUTE = LoweringRoute.WCC_M4
WORKFLOW_LISP_CONTEXT_KEY = "workflow_lisp"
LOWERING_SCHEMA_CONTEXT_KEY = "lowering_schema_version"
def normalize_lowering_route(route: LoweringRoute | str | None) -> LoweringRoute:
    """Resolve the caller-provided route selector to one enum value."""

    if route is None:
        return DEFAULT_LOWERING_ROUTE
    if isinstance(route, LoweringRoute):
        return route
    return LoweringRoute(route)


def lowering_schema_for_route(route: LoweringRoute | str | None) -> int:
    """Return the route-neutral lowering schema version for a compiler route."""

    normalized = normalize_lowering_route(route)
    if normalized is LoweringRoute.LEGACY:
        return LOWERING_SCHEMA_LEGACY
    return LOWERING_SCHEMA_WCC


def lowering_route_for_schema(schema: int) -> LoweringRoute:
    """Return the internal compatibility route for a persisted schema version."""

    if schema == LOWERING_SCHEMA_LEGACY:
        return LoweringRoute.LEGACY
    if schema == LOWERING_SCHEMA_WCC:
        return LoweringRoute.WCC_M4
    raise ValueError(f"unsupported Workflow Lisp lowering schema: {schema}")


def workflow_lisp_context_with_lowering_schema(context: Mapping[str, Any], schema: int) -> dict[str, Any]:
    """Return run context with route-neutral Workflow Lisp lowering metadata."""

    updated = dict(context)
    lisp_context = dict(updated.get(WORKFLOW_LISP_CONTEXT_KEY) or {})
    lisp_context[LOWERING_SCHEMA_CONTEXT_KEY] = schema
    updated[WORKFLOW_LISP_CONTEXT_KEY] = lisp_context
    return updated


def lowering_schema_from_run_context(context: Mapping[str, Any]) -> int | None:
    """Read a persisted Workflow Lisp lowering schema from run context."""

    lisp_context = context.get(WORKFLOW_LISP_CONTEXT_KEY)
    if not isinstance(lisp_context, Mapping):
        return None
    value = lisp_context.get(LOWERING_SCHEMA_CONTEXT_KEY)
    return value if isinstance(value, int) else None


def effective_persisted_lowering_schema_for_orc(context: Mapping[str, Any]) -> int:
    """Treat missing historical `.orc` lowering schema as schema 1."""

    schema = lowering_schema_from_run_context(context)
    return LOWERING_SCHEMA_LEGACY if schema is None else schema
