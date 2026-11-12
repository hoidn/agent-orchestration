"""The `effect_site_positional` lint: effect sites the compiler numbers by position.

An effect that no authored `let*` binder names gets the site label `#<n>`, its
position among the unnamed effects of its scope (contracts/closed_program/sites.py,
`_Scope.label`). With two such sites in one scope, inserting another unnamed
effect before them renames both, which changes their recorded identities. This
pass mirrors that numbering on the typed body: a scope is a definition body, an
`if`/`cond`/`match` arm, or a loop body or exhaustion result; `let*` does not open
one. An unnamed effect is an effect form, an effectful procedure call, or an
effectful branch in value position (the compiler joins it under `#<n>`), unless
it is the direct value of an authored binder (a hygienic macro binder keeps its
authored label). Loops are labelled by their state
binder, numbered only when that binder is compiler-made. Lifecycle owners (trials, live-provider scopes,
`list/map-effect`) count as named and each of their children opens a scope: the pass
under-reports there rather than over-reports. It reads the typed body only and
changes no program.
"""

from __future__ import annotations

from collections.abc import Iterable

from .conditionals import _EFFECT_EXPRS, _EFFECT_NODE_TYPES
from .expression_traversal import iter_child_exprs
from .expressions import CondExpr, IfExpr, LetStarExpr, LoopRecurExpr, MatchExpr, ProcedureCallExpr
from .lints import required_lint_diagnostic

CODE = "effect_site_positional"
_BRANCHES = (IfExpr, CondExpr, MatchExpr)
# The compiler's own effect-form tables, so a new effect form is covered here too.
_OWNERS = tuple(kind for kind in _EFFECT_NODE_TYPES if kind not in _EFFECT_EXPRS and kind is not LoopRecurExpr)


def effect_site_positional_diagnostics(typed_workflows: Iterable, typed_procedures: Iterable) -> list:
    """One warning per scope with two or more numbered effect sites, at the second.

    A specialization repeats a generic body its defining module already lints
    and is skipped. A call to one of `typed_procedures` without transitive
    effects is not an effect; a call to any other procedure is.
    """

    typed_procedures = tuple(typed_procedures)
    walker = _Walker(frozenset(
        procedure.signature.name for procedure in typed_procedures
        if not procedure.transitive_effect_summary.transitive_effects
    ))
    for definition in (*typed_workflows, *typed_procedures):
        if getattr(definition, "specialization", None) is None:
            walker.scope(definition.typed_body.expr, tail=True)
    return walker.diagnostics


def _authored(name: str, label: str | None) -> bool:
    """Whether the compiler labels this binder by name (`_Scope.label`)."""
    return label is not None or not name.startswith("%")


class _Walker:
    def __init__(self, pure_procedures: frozenset[str]) -> None:
        self.pure = pure_procedures
        self.diagnostics: list = []

    def scope(self, expr, *, tail: bool) -> None:
        numbered: list = []
        self.walk(expr, numbered, bound=False, tail=tail)
        if len(numbered) >= 2:
            first, second = numbered[:2]
            start = first.span.start
            self.diagnostics.append(required_lint_diagnostic(
                CODE,
                message=(
                    f"this effect is site `#2` of its scope and the effect at {start.line}:{start.column} is `#1`; "
                    "an unnamed effect inserted before them renames both and so changes their recorded identities; "
                    "bind each with `let*`"
                ),
                span=second.span, form_path=second.form_path, expansion_stack=second.expansion_stack,
            ))

    def walk(self, expr, numbered: list, *, bound: bool, tail: bool) -> None:
        if isinstance(expr, LetStarExpr):
            labels = expr.binding_labels or (None,) * len(expr.bindings)
            for (name, value), label in zip(expr.bindings, labels):
                self.walk(value, numbered, bound=_authored(name, label), tail=False)
            self.walk(expr.body, numbered, bound=bound, tail=tail)
        elif isinstance(expr, _BRANCHES):
            self.branch(expr, numbered, bound=bound, tail=tail)
        elif isinstance(expr, LoopRecurExpr):
            if not _authored(expr.binding_name, expr.binding_label) and any(
                    self.contains_effect(body) for body in (expr.body_expr, expr.on_exhausted_result_expr)
                    if body is not None):
                numbered.append(expr)
            for operand in (expr.max_iterations_expr, expr.initial_state_expr):
                self.walk(operand, numbered, bound=False, tail=False)
            for body in (expr.body_expr, expr.on_exhausted_result_expr):
                if body is not None:
                    self.scope(body, tail=True)
        elif isinstance(expr, _OWNERS):
            for child in iter_child_exprs(expr):
                self.scope(child, tail=True)
        else:
            if not bound and self.is_effect(expr):
                numbered.append(expr)
            for child in iter_child_exprs(expr):
                self.walk(child, numbered, bound=False, tail=False)

    def branch(self, expr, numbered: list, *, bound: bool, tail: bool) -> None:
        if isinstance(expr, IfExpr):
            conditions, arms = (expr.condition_expr,), (expr.then_expr, expr.else_expr)
        elif isinstance(expr, CondExpr):
            conditions = tuple(c.condition_expr for c in expr.clauses if c.condition_expr is not None)
            arms = tuple(clause.result_expr for clause in expr.clauses)
        else:
            conditions, arms = (expr.subject,), tuple(arm.body for arm in expr.arms)
        for condition in conditions:
            self.walk(condition, numbered, bound=False, tail=False)
        if not bound and not tail and any(self.contains_effect(arm) for arm in arms):
            numbered.append(expr)
        for arm in arms:
            self.scope(arm, tail=True)

    def is_effect(self, expr) -> bool:
        if isinstance(expr, ProcedureCallExpr):
            return expr.callee_name not in self.pure
        return isinstance(expr, _EFFECT_EXPRS)

    def contains_effect(self, expr) -> bool:
        return (self.is_effect(expr) or isinstance(expr, _OWNERS)
                or any(self.contains_effect(child) for child in iter_child_exprs(expr)))
