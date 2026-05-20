"""Frontend-local authored specs for resource stdlib forms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .expressions import ExprNode


@dataclass(frozen=True)
class ResourceTransitionSpec:
    """Authored arguments for a `resource-transition` stdlib call."""

    transition_name: str
    ctx_expr: "ExprNode"
    when_expr: "ExprNode | None"
    resource_expr: "ExprNode"
    from_queue_name: str
    to_queue_name: str
    ledger_expr: "ExprNode"
    event_name: str


@dataclass(frozen=True)
class FinalizeSelectedItemSpec:
    """Authored fan-in inputs for `finalize-selected-item`."""

    ctx_expr: "ExprNode"
    selected_expr: "ExprNode"
    queue_transition_expr: "ExprNode"
    roadmap_expr: "ExprNode"
    plan_expr: "ExprNode"
    implementation_expr: "ExprNode"
