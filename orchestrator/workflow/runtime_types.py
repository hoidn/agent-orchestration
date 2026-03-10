"""Small internal value types for workflow runtime coordination."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class StepExecutionIdentity:
    """Stable metadata for one executing step visit."""

    name: str
    step_id: str
    step_index: Optional[int] = None
    visit_count: Optional[int] = None


@dataclass(frozen=True)
class NormalizedStepOutcome:
    """Internal typed representation of the persisted outcome payload."""

    status: str
    phase: str
    outcome_class: str
    retryable: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "phase": self.phase,
            "class": self.outcome_class,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class RoutingDecision:
    """Coordinator decision after step routing/finalization handling."""

    next_step_index: Optional[int] = None
    next_node_id: Optional[str] = None
    terminal_status: str = "completed"
    should_break: bool = False
