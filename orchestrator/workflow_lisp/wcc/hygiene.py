"""Scope hygiene for bindings the elaborator hoists or generates (target 2.33).

WCC binds by spelling (`WccLet.bound_name`); scope is the dominance of a
`WccLet` over its body (design: workflow_lisp_core_calculus_middle_end.md
section 9). When the elaborator places the bindings of a sub-expression around
code that the source does not let see them (a `match` subject's bindings around
the arms, a `let*` binding value's bindings around the rest of the `let*`, an
operand's bindings around the other operands), a binding whose name that code
refers to would capture the reference. These helpers keep the source scope: such
a binding gets a fresh name and its own references follow it, and a name the
elaborator generates is chosen apart from every identifier the code in its
scope can spell. Freshness is by construction: a name is checked against the
identifiers in scope, not left to the improbability of a digest.

Renaming follows binding structure. A reference is renamed when it is free at
its position, so a binder of the same spelling inside the renamed code (a
nested `let*`, a `match` arm, a `list/map` or loop binder, a `let-proc`
parameter, a WCC `let`, `case` arm, join or loop parameter, a provider group
member) starts a scope the renaming does not enter.

Dependencies: `expression_traversal` (free names and renaming of frontend
expressions, which thread their own binders).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import fields as dataclass_fields, is_dataclass, replace

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expression_traversal import free_expr_names, map_expr, walk_expr
from ..expressions import CallExpr, ExprNode, NameExpr, ProcedureCallExpr
from ..type_env import TypeRef
from .model import (
    WccCaseArm,
    WccIdentityFactory,
    WccJoin,
    WccLet,
    WccNameAtom,
    WccNodeMetadata,
    WccProviderPeerGroup,
    WccProviderPeerGroupMember,
    WccProviderSupervision,
    WccRecJoin,
    WccRunRefPayload,
    WccSelectArm,
    WccTrialPayload,
    WccValue,
)

# Nodes that hold no reference to a value name.
_CLOSED = (WccNodeMetadata, WccRunRefPayload, WccTrialPayload)


def _gather(node: object, leaf: Callable[[object], set[str] | None]) -> set[str]:
    """Union of `leaf(x)` over every object reachable from `node` through dataclass fields and containers."""

    found = leaf(node)
    if found is not None:
        return found
    if isinstance(node, Mapping):
        children: Iterable[object] = (*node.keys(), *node.values())
    elif isinstance(node, (tuple, list, set, frozenset)):
        children = node
    elif is_dataclass(node) and not isinstance(node, type):
        children = (getattr(node, field.name) for field in dataclass_fields(node))
    else:
        return set()
    return set().union(*(_gather(child, leaf) for child in children))


def _strings(node: object) -> set[str]:
    """Every string inside `node`: a superset of the identifiers it spells or binds."""

    return _gather(node, lambda item: {item} if isinstance(item, str) else None)


def _mentioned_names(node: object) -> set[str]:
    """Every name that a frontend `NameExpr` or a `WccNameAtom` inside `node` spells, bound or free."""

    return _gather(node, lambda item: {item.name} if isinstance(item, (NameExpr, WccNameAtom)) else None)


# The fields of a WCC node that its own binders scope over, and the names they bind.
_BINDERS: dict[type, tuple[frozenset[str], Callable[[object], Iterable[str]]]] = {
    WccLet: (frozenset({"body"}), lambda node: (node.bound_name,)),
    WccCaseArm: (frozenset({"body"}), lambda node: (node.binding_name,)),
    WccJoin: (frozenset({"continuation"}), lambda node: (param.name for param in node.params)),
    WccRecJoin: (frozenset({"body", "exhaustion"}), lambda node: (param.name for param in node.params)),
    WccProviderSupervision: (frozenset({"settlement_body"}), lambda node: (member.binding_name for member in node.members)),
    WccProviderPeerGroup: (frozenset({"settlement_body"}), lambda node: (member.binding_name for member in node.members)),
}


def _bound_by(node: object, field_name: str) -> frozenset[str]:
    """The names a WCC node binds around its field `field_name`."""

    scoped_fields, names = _BINDERS.get(type(node), (frozenset(), None))
    return frozenset(names(node)) if field_name in scoped_fields else frozenset()


def _free_names(node: object, bound: frozenset[str] = frozenset()) -> set[str]:
    """Names that frontend or WCC code in `node` refers to and does not bind itself."""

    if isinstance(node, WccNameAtom):
        return {node.name} - bound
    if isinstance(node, ExprNode):
        return free_expr_names(node, bound=bound)
    if isinstance(node, WccSelectArm):
        # A select arm is a sequential scope; a prefix `let`'s `body` link is not a path of the arm.
        names: set[str] = set()
        for let_node in node.prefix:
            names |= _free_names(let_node.bound_value, bound)
            bound = bound | {let_node.bound_name}
        return names | _free_names(node.value, bound)
    if isinstance(node, (Mapping, tuple, list)):
        items = node.values() if isinstance(node, Mapping) else node
        return set().union(*(_free_names(item, bound) for item in items))
    if is_dataclass(node) and not isinstance(node, (type, *_CLOSED)):
        return set().union(
            *(_free_names(getattr(node, field.name), bound | _bound_by(node, field.name)) for field in dataclass_fields(node))
        )
    return set()


def _renamed(node: object, renamed: Mapping[str, WccNameAtom], bound: frozenset[str] = frozenset()) -> object:
    """Rebuild `node` with each free reference to a key of `renamed` renamed; unchanged parts stay identical."""

    if renamed.keys() <= bound:
        return node
    if isinstance(node, WccNameAtom):
        return node if node.name in bound else renamed.get(node.name, node)
    if isinstance(node, ExprNode):
        return map_expr(node, lambda name: _renamed_name(name, renamed), bound=bound)
    if isinstance(node, WccSelectArm):
        prefix: list[WccLet] = []
        for let_node in node.prefix:
            prefix.append(replace(let_node, bound_value=_renamed(let_node.bound_value, renamed, bound)))
            bound = bound | {let_node.bound_name}
        return WccSelectArm(prefix=tuple(prefix), value=_renamed(node.value, renamed, bound))
    if isinstance(node, (Mapping, tuple, list)):
        return _renamed_items(node, renamed, bound)
    if is_dataclass(node) and not isinstance(node, (type, *_CLOSED)):
        return _renamed_fields(node, renamed, bound)
    return node


def _renamed_name(name: NameExpr, renamed: Mapping[str, WccNameAtom]) -> NameExpr:
    return replace(name, name=renamed[name.name].name) if name.name in renamed else name


def _renamed_items(node: Mapping | tuple | list, renamed: Mapping[str, WccNameAtom], bound: frozenset[str]) -> object:
    """`_renamed` for the items of a container; an unchanged container stays identical."""

    keys = list(node) if isinstance(node, Mapping) else range(len(node))
    items = [_renamed(node[key], renamed, bound) for key in keys]
    if all(new is node[key] for new, key in zip(items, keys)):
        return node
    if isinstance(node, Mapping):
        return dict(zip(keys, items))
    return tuple(items) if isinstance(node, tuple) else items


def _renamed_fields(node: object, renamed: Mapping[str, WccNameAtom], bound: frozenset[str]) -> object:
    """`_renamed` for the fields of one dataclass node, each under the names the node binds around it."""

    changes = {}
    for field in dataclass_fields(node):
        if field.init:
            old = getattr(node, field.name)
            new = _renamed(old, renamed, bound | _bound_by(node, field.name))
            if new is not old:
                changes[field.name] = new
    live = renamed.keys() - bound
    if isinstance(node, WccProviderPeerGroupMember) and live & set(node.lexical_capture_names):
        # A peer group member spells the environment it captures as strings.
        captures = (renamed[name].name if name in live else name for name in node.lexical_capture_names)
        changes["lexical_capture_names"] = tuple(sorted(captures))
    return replace(node, **changes) if changes else node


def _names_seen_by(
    over: Iterable[tuple[object, frozenset[str]]],
    *,
    compile_time_bindings: Mapping[object, object],
) -> set[str]:
    """Names that code in `over`, pairs of (frontend or WCC code, names it binds around itself), refers to.

    Besides free names this includes the names inside the value of every
    compile-time binding the code uses as a value or a callee, because the
    elaborator expands that value in place.
    """

    seen: set[str] = set()
    callees: set[str] = set()
    for code, bound in over:
        seen |= _free_names(code, bound)
        if isinstance(code, ExprNode):
            callees |= {node.callee_name for node in walk_expr(code) if isinstance(node, (ProcedureCallExpr, CallExpr))}
    pending = {name for name in seen | callees if name in compile_time_bindings}
    expanded: set[str] = set()
    while pending:
        name = pending.pop()
        expanded.add(name)
        names = _mentioned_names(compile_time_bindings[name])
        seen |= names
        pending |= {inner for inner in names if inner in compile_time_bindings} - expanded
    return seen


def _in_scope(value_env: Mapping[str, TypeRef], compile_time_bindings: Mapping[object, object]) -> set[str]:
    return set(value_env) | {name for name in compile_time_bindings if isinstance(name, str)}


def fresh_name(base: str, reserved: set[str]) -> str:
    """Return `base`, or `base` with the smallest numeric suffix not in `reserved`, and reserve it."""

    name, suffix = base, 0
    while name in reserved:
        suffix += 1
        name = f"{base}_{suffix}"
    reserved.add(name)
    return name


def reserved_identifiers(
    expr: object,
    *,
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[object, object],
) -> set[str]:
    """Identifiers that a binding generated around `expr` must not spell.

    The names in scope, every string inside `expr`, and the names reachable
    through the compile-time values `expr` uses.
    """

    return (
        _in_scope(value_env, compile_time_bindings)
        | _strings(expr)
        | _names_seen_by(((expr, frozenset()),), compile_time_bindings=compile_time_bindings)
    )


def generated_name_scope(scope: WccIdentityFactory) -> WccIdentityFactory:
    """The scope that names a generated binding: `scope` and the `case` arms that enclose it."""

    return scope.child_scope("arms", authored_binding_name="/".join(scope.enclosing_variants))


def hoist_without_capture(
    prefix: tuple[WccLet, ...],
    value: WccValue,
    *,
    over: tuple[tuple[object, frozenset[str]], ...],
    scope: WccIdentityFactory,
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[object, object],
) -> tuple[tuple[WccLet, ...], WccValue]:
    """Rename the bindings of `prefix` that the code it is hoisted over can see.

    `prefix` and `value` come from a sub-expression whose bindings the source
    scopes to it; the caller places `prefix` around `over`, pairs of (frontend
    or WCC code, names it binds around itself). A binding whose name `over`
    refers to gets a fresh name, and its references in the rest of `prefix`
    and in `value` follow it. The other bindings keep their names, so a program
    without such a clash keeps its step identities.
    """

    seen = _names_seen_by(over, compile_time_bindings=compile_time_bindings) if prefix else set()
    if seen.isdisjoint(let_node.bound_name for let_node in prefix):
        return prefix, value
    reserved = _in_scope(value_env, compile_time_bindings) | seen | _strings((prefix, value))
    naming_scope = generated_name_scope(scope)
    renamed: dict[str, WccNameAtom] = {}
    hoisted: list[WccLet] = []
    for let_node in prefix:
        bound_value = _rename(let_node.bound_value, renamed, at=let_node)
        # A later binding of a renamed spelling is renamed afresh (`over` sees it
        # too), and the references after it follow the later binding.
        if let_node.bound_name in seen:
            digest = naming_scope.child_scope("hoisted", authored_binding_name=let_node.bound_name).scope_id
            name = fresh_name(f"{let_node.bound_name}_{digest.rsplit(':', 1)[-1]}", reserved)
            renamed[let_node.bound_name] = WccNameAtom(
                metadata=naming_scope.atom_metadata(
                    role=f"name:{name}",
                    type_ref=let_node.bound_type_ref,
                    source_span=let_node.metadata.source_span,
                    form_path=let_node.metadata.form_path,
                    expansion_stack=let_node.metadata.expansion_stack,
                ),
                name=name,
            )
            let_node = replace(let_node, bound_name=name)
        hoisted.append(replace(let_node, bound_value=bound_value))
    return tuple(hoisted), _rename(value, renamed, at=prefix[-1])


def hoist_parts_without_capture(
    parts: Sequence[tuple[tuple[WccLet, ...], WccValue, WccIdentityFactory]],
    *,
    over: tuple[tuple[object, frozenset[str]], ...] = (),
    value_env: Mapping[str, TypeRef],
    compile_time_bindings: Mapping[object, object],
) -> tuple[tuple[WccLet, ...], tuple[WccValue, ...]]:
    """Join the prefixes of sibling operands evaluated left to right, as `hoist_without_capture` does for one.

    `parts` are (prefix, value, scope) in authored order. The caller places
    every prefix, in order, before every value and before `over`, so part i's
    prefix is hoisted over the later parts, the earlier parts' values and
    `over`. Returns the joined prefix and the values in order.
    """

    prefix: list[WccLet] = []
    values: list[WccValue] = []
    for index, (part_prefix, part_value, part_scope) in enumerate(parts):
        # A later part is a sequential scope of lets and a value, as a select arm is.
        later = tuple((WccSelectArm(prefix=p, value=v), frozenset()) for p, v, _ in parts[index + 1 :])
        part_prefix, part_value = hoist_without_capture(
            part_prefix,
            part_value,
            over=(*later, *((value, frozenset()) for value in values), *over),
            scope=part_scope,
            value_env=value_env,
            compile_time_bindings=compile_time_bindings,
        )
        prefix.extend(part_prefix)
        values.append(part_value)
    return tuple(prefix), tuple(values)


def _rename(value: object, renamed: Mapping[str, WccNameAtom], *, at: WccLet) -> object:
    """Rename the free references of `value`; refuse, as a compiler defect, if one is left.

    The renaming reaches every free reference by construction; the check is an
    internal consistency check, not a rule a program can break.
    """

    if not renamed:
        return value
    result = _renamed(value, renamed)
    missed = _free_names(result) & renamed.keys()
    if missed:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="compiler_defect_hoisted_binding_rename",
                    message=(
                        "compiler defect: a binding hoisted out of its source scope was renamed, but a "
                        f"reference to `{sorted(missed)[0]}` in this form was not; the program typechecked, "
                        "so this is a defect of the compiler, not of the program"
                    ),
                    span=at.metadata.source_span,
                    form_path=at.metadata.form_path,
                    expansion_stack=at.metadata.expansion_stack,
                    phase="lowering",
                ),
            )
        )
    return result
