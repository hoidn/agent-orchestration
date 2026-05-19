"""Frontend-local authored specs for drain stdlib forms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .expressions import ExprNode


@dataclass(frozen=True)
class BacklogDrainSpec:
    drain_name: str
    ctx_expr: "ExprNode"
    selector_name: str
    run_item_name: str
    gap_drafter_name: str
    providers_expr: "ExprNode | None"
    max_iterations_expr: "ExprNode"
