"""Status predicates shared by persistence and reporting consumers."""

from __future__ import annotations


_RUN_TERMINAL_STATUSES = frozenset({"completed", "failed"})
_STEP_SETTLED_STATUSES = frozenset(
    {"completed", "failed", "skipped"}
)


def is_run_terminal(status: object) -> bool:
    """Return whether ``status`` is a terminal run-state value."""
    return (
        isinstance(status, str)
        and status in _RUN_TERMINAL_STATUSES
    )


def is_step_settled(status: object) -> bool:
    """Return whether ``status`` is a settled step-state value."""
    return (
        isinstance(status, str)
        and status in _STEP_SETTLED_STATUSES
    )
