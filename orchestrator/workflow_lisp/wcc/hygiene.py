"""Scope hygiene for bindings the elaborator hoists or generates (target 2.33).

WCC binds by spelling (`WccLet.bound_name`); scope is the dominance of a
`WccLet` over its body (design: workflow_lisp_core_calculus_middle_end.md
section 9). When the elaborator places the bindings of a sub-expression around
code that the source does not let see them (a `match` subject's bindings around
the arms, a `let*` binding value's bindings around the rest of the `let*`), a
binding whose name that code refers to would capture the reference. These
helpers keep the source scope: such a binding gets a fresh name and its own
references follow it, and a name the elaborator generates is chosen apart from
every identifier the code in its scope can spell. Freshness is by
construction: a name is checked against the identifiers in scope, not left to
the improbability of a digest.

Dependencies: `expression_traversal` (free names, walks) and, imported lazily
because `elaborate` imports this module, the WCC substitution of `elaborate`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import fields as dataclass_fields, is_dataclass, replace

from ..diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from ..expression_traversal import free_expr_names, walk_expr
from ..expressions import CallExpr, NameExpr, ProcedureCallExpr
from ..type_env import TypeRef
from .model import WccIdentityFactory, WccLet, WccNameAtom, WccPerform, WccValue


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


def _names_seen_by(
    over: Iterable[tuple[object, frozenset[str]]],
    *,
    compile_time_bindings: Mapping[object, object],
) -> set[str]:
    """Names that code in `over`, pairs of (expression, names it binds around itself), refers to.

    Besides free names this includes the names inside the value of every
    compile-time binding the code uses as a value or a callee, because the
    elaborator expands that value in place.
    """

    seen: set[str] = set()
    callees: set[str] = set()
    for expr, bound in over:
        seen |= free_expr_names(expr, bound=bound)
        callees |= {node.callee_name for node in walk_expr(expr) if isinstance(node, (ProcedureCallExpr, CallExpr))}
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
    scopes to it; the caller places `prefix` around `over`, pairs of
    (expression, names it binds around itself). A binding whose name `over`
    refers to gets a fresh name, and its references in the rest of `prefix`
    and in `value` follow it. The other bindings keep their names, so a program
    without such a clash keeps its step identities.
    """

    seen = _names_seen_by(over, compile_time_bindings=compile_time_bindings) if prefix else set()
    if seen.isdisjoint(let_node.bound_name for let_node in prefix):
        return prefix, value
    reserved = _in_scope(value_env, compile_time_bindings) | seen | _strings((prefix, value))
    naming_scope = generated_name_scope(scope)
    renamed: dict[str, WccValue] = {}
    hoisted: list[WccLet] = []
    for let_node in prefix:
        bound_value = _rename(let_node.bound_value, renamed, at=let_node)
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


def _rename(value: object, renamed: Mapping[str, WccValue], *, at: WccLet) -> object:
    """Substitute `renamed` in `value`; refuse, as a compiler defect, if a reference to a renamed name remains.

    The check counts every spelling of a renamed name, so a form that rebinds
    the name inside `value` is refused too: loud, never a captured value.
    """

    if not renamed:
        return value
    from .elaborate import _substitute_wcc_binding_value, _substitute_wcc_opaque_expr

    result = _substitute_wcc_binding_value(value, renamed)
    if isinstance(result, WccPerform) and result.operation_payload is not None:
        # Payloads may hold frontend expressions (a prompt dependency, a view argument).
        result = replace(result, operation_payload=_substitute_wcc_opaque_expr(result.operation_payload, renamed))
    missed = _mentioned_names(result) & renamed.keys()
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
