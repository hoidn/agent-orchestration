"""Rename the binders that would capture a name a pure binding reads where it is used.

Lowering keeps a pure binding as a frontend expression and resolves its free
names where the binding is used, by spelling (`defunctionalize`'s local values
and its WCC-to-frontend reconstruction). A binder between the definition and
a use that spells one of those names would capture it. Before lowering, such a
binder gets a fresh name and the references in its scope follow it, so a
binding's free names resolve in the scope of its definition (design:
workflow_lisp_core_calculus_middle_end.md section 9). A body with no such
binder is returned unchanged, so its lowered output does not change.

Dependencies: `hygiene` (free names, renaming that follows binding structure,
fresh names).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import is_dataclass, replace

from ..expressions import ExprNode, LetStarExpr
from .hygiene import _BINDERS, _CLOSED, _field_changes, _free_names, _rebuilt_items, _renamed, _strings, fresh_name
from .model import (
    WccBody,
    WccCall,
    WccCaseArm,
    WccJoin,
    WccLet,
    WccPerform,
    WccProviderPeerGroup,
    WccProviderSupervision,
    WccRecJoin,
    WccSelectArm,
)


# Binding values whose free names lowering resolves where they are bound (effects,
# whose results are step outputs); it may resolve any other value where it is used.
_EFFECTS = (WccPerform, WccCall, WccProviderSupervision, WccProviderPeerGroup)
_RENAMED_BINDERS = (WccLet, WccCaseArm, WccJoin, WccRecJoin)


def names_read_where_used(values: Iterable[object], environment: Mapping[str, object]) -> frozenset[str]:
    """Names that resolving `values` by spelling in `environment` reads, through the values it holds."""

    pending = set().union(*(_free_names(value) for value in values))
    read: set[str] = set()
    while pending:
        name = pending.pop()
        read.add(name)
        pending |= _free_names(environment.get(name)) - read
    return frozenset(read)


def rename_capturing_binders(
    body: WccBody,
    *,
    live: frozenset[str] = frozenset(),
    params: tuple[str, ...] = (),
    reserved: Iterable[str] = (),
) -> tuple[WccBody, dict[str, str]]:
    """Rename every binder in `body` that would capture a name a pure binding reads where it is used.

    A binder (a `let`, frontend `let*` binding, `case` arm, join or loop
    parameter) that spells a name read by a pure binding in scope gets a fresh
    name, and the references in its scope follow it. `live` are the names that
    values from outside `body` read (an inlined procedure's arguments and
    specialization values); `params` are bound around `body` (its parameters
    and specialization bindings), and one in `live` is renamed too. Fresh names avoid every identifier in `body`, `live`,
    `params` and `reserved`. Returns the body, unchanged when no binder
    clashes, and the renamed parameters.
    """

    reserved_names: set[str] | None = None
    retained_reserved_names: set[str] | None = None

    def fresh(base: str) -> str:
        nonlocal reserved_names
        if reserved_names is None:
            reserved_names = _strings(body) | live | set(params) | set(reserved)
        return fresh_name(base, reserved_names)

    def fresh_retained(base: str) -> str:
        nonlocal retained_reserved_names
        if retained_reserved_names is None:
            retained_reserved_names = (
                _strings(body, include_condition_input=True)
                | live
                | set(params)
                | set(reserved)
            )
        return fresh_name(base, retained_reserved_names)

    renamed_params = {name: fresh(name) for name in params if name in live}
    if renamed_params:
        body = _renamed(body, renamed_params)
    return _unshadow(body, live, fresh, retained_fresh=fresh_retained), renamed_params


def _unshadow(
    node: object,
    live: frozenset[str],
    fresh: Callable[[str], str],
    *,
    retained_fresh: Callable[[str], str] | None = None,
) -> object:
    """`rename_capturing_binders` for one node, under the names `live` that pure bindings in scope read."""

    if isinstance(node, (Mapping, tuple, list)):
        return _rebuilt_items(
            node,
            lambda item: _unshadow(
                item,
                live,
                fresh,
                retained_fresh=retained_fresh,
            ),
        )
    if isinstance(node, WccSelectArm):
        return _unshadow_select_arm(node, live, fresh, retained_fresh=retained_fresh)
    if isinstance(node, LetStarExpr):
        return _unshadow_let_star(
            node,
            live,
            fresh,
            retained_fresh=retained_fresh,
        )
    if not is_dataclass(node) or isinstance(node, (type, *_CLOSED)):
        return node
    if isinstance(node, _RENAMED_BINDERS):
        node = _rebound(node, {name: fresh(name) for name in _BINDERS[type(node)][1](node) if name in live})
    changes = _field_changes(
        node,
        lambda name, old: _unshadow(
            old,
            _live_in(node, name, live),
            fresh,
            retained_fresh=retained_fresh,
        ),
    )
    return replace(node, **changes) if changes else node


def _live_in(node: object, field_name: str, live: frozenset[str]) -> frozenset[str]:
    if isinstance(node, WccLet) and field_name == "body" and not isinstance(node.bound_value, _EFFECTS):
        return live | _free_names(node.bound_value)
    return live


def _rebound(node: WccLet | WccCaseArm | WccJoin | WccRecJoin, names: Mapping[str, str]) -> object:
    """`node` with its binders in `names` renamed, and their references in the fields they scope."""

    if not names:
        return node
    changes: dict[str, object] = {field: _renamed(getattr(node, field), names) for field in _BINDERS[type(node)][0]}
    if isinstance(node, WccLet):
        changes["bound_name"] = names[node.bound_name]
    elif isinstance(node, WccCaseArm):
        changes["binding_name"] = names[node.binding_name]
    else:
        changes["params"] = tuple(replace(param, name=names.get(param.name, param.name)) for param in node.params)
    return replace(node, **changes)


def _unshadow_select_arm(
    arm: WccSelectArm,
    live: frozenset[str],
    fresh: Callable[[str], str],
    *,
    retained_fresh: Callable[[str], str] | None = None,
) -> WccSelectArm:
    """`_unshadow` for a select arm: pure `let`s scoped over the rest of the arm (their body links are not)."""

    prefix: list[WccLet] = []
    rest = arm
    while rest.prefix:
        let_node, rest = rest.prefix[0], WccSelectArm(prefix=rest.prefix[1:], value=rest.value)
        let_node = _rebuilt_let(
            let_node,
            _unshadow(
                let_node.bound_value,
                live,
                fresh,
                retained_fresh=retained_fresh,
            ),
        )
        if let_node.bound_name in live:
            renamed = fresh(let_node.bound_name)
            rest, let_node = _renamed(rest, {let_node.bound_name: renamed}), replace(let_node, bound_name=renamed)
        live = live | _free_names(let_node.bound_value)
        prefix.append(let_node)
    value = _unshadow(rest.value, live, fresh, retained_fresh=retained_fresh)
    if value is arm.value and all(new is old for new, old in zip(prefix, arm.prefix)):
        return arm
    return WccSelectArm(prefix=tuple(prefix), value=value)


def _rebuilt_let(let_node: WccLet, bound_value: object) -> WccLet:
    return let_node if bound_value is let_node.bound_value else replace(let_node, bound_value=bound_value)


def _unshadow_let_star(
    expr: LetStarExpr,
    live: frozenset[str],
    fresh: Callable[[str], str],
    *,
    retained_fresh: Callable[[str], str] | None = None,
) -> LetStarExpr:
    """`_unshadow` for a frontend `let*`, which lowering resolves as it does WCC `let`s."""

    retained_input = (
        _unshadow(
            expr.condition_normalization_input,
            live,
            retained_fresh or fresh,
            retained_fresh=retained_fresh or fresh,
        )
        if expr.condition_normalization_input is not None
        else None
    )
    bindings: list[tuple[str, ExprNode]] = []
    rest = replace(expr, condition_normalization_input=None)
    while rest.bindings:
        (name, value), rest = rest.bindings[0], replace(rest, bindings=rest.bindings[1:])
        value = _unshadow(value, live, fresh, retained_fresh=retained_fresh)
        if name in live:
            renamed = fresh(name)
            rest, name = _renamed(rest, {name: renamed}), renamed
        live = live | _free_names(value)
        bindings.append((name, value))
    body = _unshadow(rest.body, live, fresh, retained_fresh=retained_fresh)
    if (
        retained_input is expr.condition_normalization_input
        and body is expr.body
        and all(new[0] == old[0] and new[1] is old[1] for new, old in zip(bindings, expr.bindings))
    ):
        return expr
    return replace(
        expr,
        bindings=tuple(bindings),
        body=body,
        condition_normalization_input=retained_input,
    )
