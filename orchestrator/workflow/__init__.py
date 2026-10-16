"""Workflow execution module."""

from .pointers import PointerResolver

__all__ = ['WorkflowExecutor', 'PointerResolver']


def __getattr__(name):
    if name == 'WorkflowExecutor':
        from .executor import WorkflowExecutor

        return WorkflowExecutor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
