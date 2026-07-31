"""Status predicates shared by persistence and reporting consumers."""

from __future__ import annotations

_RUN_TERMINAL_STATUSES = frozenset({"completed", "failed"})
_STEP_SETTLED_STATUSES = frozenset({"completed", "failed", "skipped"})


def _matches(status: object, values: frozenset[str], raise_on_unhashable: bool) -> bool:
    if raise_on_unhashable:
        return status in values
    return status in tuple(values)


def is_run_terminal(status: object, *, raise_on_unhashable: bool = False) -> bool:
    """Return whether ``status`` has the historical run-terminal value."""
    return _matches(status, _RUN_TERMINAL_STATUSES, raise_on_unhashable)


def is_step_settled(status: object, *, raise_on_unhashable: bool = False) -> bool:
    """Return whether ``status`` has the historical step-settled value."""
    return _matches(status, _STEP_SETTLED_STATUSES, raise_on_unhashable)
