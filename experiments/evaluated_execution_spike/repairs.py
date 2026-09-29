"""Repairs of the elaborator applied to its input, outside the elaborator (criterion 9 of the spike).

Each function stands for a change the elaborator would need for the closed
program to exist. The spike applies it to what the elaborator receives, so the
program runs; the size of the function measures the change. None of them
changes a file under `orchestrator/`.
"""

from __future__ import annotations

import itertools
from dataclasses import fields, is_dataclass, replace
from typing import Any

from orchestrator.workflow_lisp.conditionals import _contains_effect
from orchestrator.workflow_lisp.expressions import DoneExpr, LetStarExpr, MatchExpr, NameExpr

_EXPRESSION_MODULES = frozenset({"orchestrator.workflow_lisp.expressions", "orchestrator.workflow_lisp.prompts"})


def elaboration_return_types(procedures: dict[str, Any]) -> dict[str, Any]:
    """Case e of the decision brief (P1).

    `elaborate_typed_workflow_body` compares the declared return type of a
    generic template (`Maybe[T]`) with the one of its specialization
    (`Maybe[Box]`) and raises "incompatible return types". The comparison
    belongs modulo the template's type parameters; here templates are left out
    of the table, so only the specialization's type is known.
    """

    return {
        name: procedure.signature.return_type_ref
        for name, procedure in procedures.items()
        if procedure.specialization is not None or not procedure.definition.type_params
    }


def bind_done_values(typed_body: Any) -> Any:
    """Defects done-call and done-match of the totality matrix (P2).

    `_elaborate_expr_to_value` has no rule for an effect or a `match` written as
    a `done` value. The change: bind it with `let*` first, as
    `_bind_effectful_loop_state_fields` does for a `continue` state field.
    """

    counter = itertools.count(1)

    def rewrite(node: Any) -> Any:
        if isinstance(node, tuple):
            items = tuple(rewrite(item) for item in node)
            return node if all(a is b for a, b in zip(items, node)) else items
        if not (is_dataclass(node) and type(node).__module__ in _EXPRESSION_MODULES):
            return node
        changes = {}
        for field in fields(node):
            old = getattr(node, field.name)
            new = rewrite(old)
            if new is not old:
                changes[field.name] = new
        node = replace(node, **changes) if changes else node
        if isinstance(node, DoneExpr) and (isinstance(node.result_expr, MatchExpr) or _contains_effect(node.result_expr)):
            name = f"__spike_done_{next(counter)}"
            where = {"span": node.span, "form_path": node.form_path, "expansion_stack": node.expansion_stack}
            return LetStarExpr(
                bindings=((name, node.result_expr),), body=replace(node, result_expr=NameExpr(name=name, **where)), **where
            )
        return node

    expr = rewrite(typed_body.expr)
    return typed_body if expr is typed_body.expr else replace(typed_body, expr=expr)
