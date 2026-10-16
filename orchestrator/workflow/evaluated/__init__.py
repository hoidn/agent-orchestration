"""Typed values shared by the evaluated Workflow Lisp runtime."""

from .values import (
    EvaluatedValue,
    EvaluatedValueError,
    LexicalEnvironment,
    coerce_evaluated_value,
    evaluate_closed_value,
)

__all__ = [
    "EvaluatedValue",
    "EvaluatedValueError",
    "EffectHandler",
    "LexicalEnvironment",
    "coerce_evaluated_value",
    "evaluate_closed_value",
    "evaluate_closed_program",
]


def __getattr__(name):
    if name in {"EffectHandler", "evaluate_closed_program"}:
        from . import machine

        return getattr(machine, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
