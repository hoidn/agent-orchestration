"""Frontend-local authored specs for resource stdlib forms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .expressions import ExprNode


@dataclass(frozen=True)
class ResourceTransitionSpec:
    """Authored arguments for a `resource-transition` stdlib call."""

    mode: str
    transition_name: str | None = None
    ctx_expr: "ExprNode | None" = None
    when_expr: "ExprNode | None" = None
    resource_expr: "ExprNode | None" = None
    from_queue_name: str | None = None
    to_queue_name: str | None = None
    ledger_expr: "ExprNode | None" = None
    event_name: str | None = None
    transition_ref_name: str | None = None
    resource_ref_name: str | None = None
    expected_version_expr: "ExprNode | None" = None
    request_expr: "ExprNode | None" = None


@dataclass(frozen=True)
class FinalizeSelectedItemSpec:
    """Authored fan-in inputs for `finalize-selected-item`."""

    ctx_expr: "ExprNode"
    selected_expr: "ExprNode"
    queue_transition_expr: "ExprNode"
    roadmap_expr: "ExprNode"
    plan_expr: "ExprNode"
    implementation_expr: "ExprNode"
