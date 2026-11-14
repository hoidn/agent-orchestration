"""Lower a branch-local variant proof of a conditional to a closed `case`.

The typechecker proves that `x` is variant `TAG` in a branch of
`(if (= x.variant TAG) ...)` (frontend specification, section 12); WCC keeps
that fact as `(name, union, tag)` triples on `WccIf` and `WccSelect`. The closed
program narrows only in a `case` arm. A conditional whose branch reads, from the
tested binding itself (not from a binding that shadows its name), a field that the
whole union does not carry with one type becomes a `case` on `x`. Each arm holds
the branch, or the conditional, that the proof leaves possible for its variant;
in a narrowed branch exactly those reads take the arm's binder, and every other
use of `x` keeps the union value. A conditional with no such read keeps its plain
lowering, so its program, digest and effect sites do not change.

The closed program has no body for an unreachable arm and no way to share a
branch between arms. A branch that falls in several arms is therefore copied, and
copied only when it has no effect and no call; an arm that no branch reaches (the
enclosing conditions excluded its variant) takes a branch that reads no
variant-only field. Otherwise the conditional is refused with `closed_program_gap`,
naming the value, the variant and the `match` form that lowers.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Any, Callable, Mapping

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.type_env import TypeRef, UnionTypeRef
from orchestrator.workflow_lisp.wcc import model as w

# A branch copied into several arms must not hold these: each would be emitted twice.
_NOT_COPYABLE = (w.WccPerform, w.WccCall, w.WccProviderSupervision, w.WccProviderPeerGroup, w.WccParallelMap)
# The children a binder of the tested name hides; a binder not listed hides all of its children.
_SCOPED = {
    w.WccLet: ("body",),
    w.WccCaseArm: ("body", "command_scope"),
    w.WccListMap: ("body",),
    w.WccParallelMap: ("workspace_body", "body"),
    w.WccJoin: ("continuation",),
    w.WccRecJoin: ("body", "exhaustion"),
}


@dataclass(frozen=True)
class _Plan:
    name: str
    union: UnionTypeRef
    tags: tuple[str | None, str | None]  # then, else: the variant each branch proves
    reads: tuple[tuple[w.WccFieldAccessAtom, ...], tuple[w.WccFieldAccessAtom, ...]]  # per branch


def _is_node(node: object) -> bool:
    return is_dataclass(node) and type(node).__module__ == w.__name__ and not isinstance(node, w.WccNodeMetadata)


def _children(node: object, hidden: tuple[str, ...] = ()) -> list[object]:
    """The child values of WCC `node` outside `hidden`, with the operands of an effect's payload
    (prompt fills, request-input `:show`, provider options), which no field of the node holds."""
    children = [getattr(node, item.name) for item in fields(node) if item.name not in ("metadata", *hidden)]
    if isinstance(node, w.WccPerform) and "operation_payload" not in hidden:
        w.map_perform_payload_values(node.perform_kind, node.operation_payload, lambda value: children.append(value) or value)
    return children


def _nodes(root: object):
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, (tuple, list)):
            stack.extend(node)
        elif _is_node(node):
            yield node
            stack.extend(_children(node))


def _bound_names(node: object) -> set[str]:
    names = {getattr(node, item, None) for item in ("bound_name", "binding_name", "binder_name")}
    names.update(param.name for param in getattr(node, "params", ()) if isinstance(param, w.WccJoinParam))
    names.update(member.binding_name for member in getattr(node, "members", ()))
    return names


def _arm_children(arm: w.WccSelectArm, name: str):
    for let in arm.prefix:  # a prefix binding scopes over the rest of its arm only
        yield let.bound_value
        if let.bound_name == name:
            return
    yield arm.value


def _visible(root: object, name: str):
    """The WCC nodes below `root` in which `name` still means the tested binding."""
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, (tuple, list)):
            stack.extend(node)
        elif isinstance(node, w.WccSelectArm):
            stack.extend(_arm_children(node, name))
        elif _is_node(node):
            yield node
            hidden = _SCOPED.get(type(node)) if name in _bound_names(node) else ()
            if hidden is not None:
                stack.extend(_children(node, hidden))


def _union_wide(union: UnionTypeRef, field: str) -> bool:
    types = [union.variant_field_types.get(row.name, {}).get(field) for row in union.definition.variants]
    return field == "variant" or (None not in types and all(item == types[0] for item in types))


def _variant_reads(branch: object, name: str, union: UnionTypeRef) -> tuple[w.WccFieldAccessAtom, ...]:
    return tuple(node for node in _visible(branch, name)
                 if isinstance(node, w.WccFieldAccessAtom) and isinstance(node.base, w.WccNameAtom)
                 and node.base.name == name and not _union_wide(union, node.fields[0]))


def _plans(node: Any, branches: tuple[object, object], env: Mapping[str, TypeRef]) -> list[_Plan]:
    tags: dict[str, list[str | None]] = {}
    for side, proof in enumerate((node.then_proof_context, node.else_proof_context)):
        for name, _union_name, tag in proof:
            tags.setdefault(name, [None, None])[side] = tag
    plans = []
    for name, (then_tag, else_tag) in tags.items():
        union = env.get(name)
        if not isinstance(union, UnionTypeRef):
            continue
        reads = tuple(_variant_reads(branch, name, union) if tag else ()
                      for tag, branch in zip((then_tag, else_tag), branches))
        if any(reads):
            plans.append(_Plan(name, union, (then_tag, else_tag), reads))
    return plans


def _gap(plan: _Plan, reason: str) -> LispFrontendCompileError:
    side = 0 if plan.reads[0] else 1
    read, tag = plan.reads[side][0], plan.tags[side]
    field = read.fields[0]
    owners = " or ".join(f"`{row.name}`" for row in plan.union.definition.variants
                         if field in plan.union.variant_field_types.get(row.name, {}))
    message = (f"this conditional reads field `{field}` of `{plan.name}`, which variant {owners} has, "
               f"and {reason}; write the read with `match`: (match {plan.name} (({tag} v) ... v.{field} ...) ...)")
    return LispFrontendCompileError((LispFrontendDiagnostic(
        code="closed_program_gap", message=message, span=read.metadata.source_span,
        form_path=read.metadata.form_path, phase="lowering"),))


def _arm_sides(plan: _Plan, variant: str) -> tuple[bool, bool]:
    """Which branches the arm of `variant` holds: those its proof leaves possible, or else the branch
    that reads no variant-only field (the enclosing conditions excluded the variant)."""
    sides = (plan.tags[0] in (None, variant), plan.tags[1] in (None, variant))
    if any(sides):
        return sides
    if plan.reads[0] and plan.reads[1]:
        raise _gap(plan, f"both of its branches read a variant-only field after an earlier test excluded "
                         f"variant `{variant}`; in a `cond`, a clause order that tests `{variant}` after the "
                         f"reading clauses also lowers")
    return (not plan.reads[0], bool(plan.reads[0]))


def _check_copies(plan: _Plan, node: Any, branches: tuple[object, object]) -> list[tuple[str, tuple[bool, bool]]]:
    arms = [(row.name, _arm_sides(plan, row.name)) for row in plan.union.definition.variants]
    shared = [branch for side, branch in enumerate(branches) if sum(sides[side] for _, sides in arms) > 1]
    if sum(all(sides) for _, sides in arms) > 1:
        shared.append(node.condition)
    if any(isinstance(item, _NOT_COPYABLE) for root in shared for item in _nodes(root)):
        raise _gap(plan, f"a branch that more than one variant of `{plan.name}` reaches runs an effect "
                         f"(a command, a provider, a request or an effectful procedure call)")
    return arms


Scope = tuple[Any, Mapping[str, TypeRef]]
Branch = Callable[[int, Any, Mapping[str, TypeRef]], dict[str, Any]]
Both = Callable[[tuple[Scope, Scope]], dict[str, Any]]


def _arm(plan: _Plan, variant: str, sides: tuple[bool, bool], d: Any, env: Mapping[str, TypeRef],
         branch: Branch, both: Both) -> dict[str, Any]:
    binder = d.renamer.bind(plan.name, authored_label=None, env=dict(d.names))
    scopes = tuple(
        (replace(d, narrowed_reads={**(d.narrowed_reads or {}), **{id(read): binder for read in plan.reads[side]}}), env)
        if plan.reads[side] and plan.tags[side] == variant else (d, env)
        for side in (0, 1))
    side = 0 if sides[0] else 1
    body = both(scopes) if all(sides) else branch(side, *scopes[side])
    return {"variant": variant, "bind": binder, "body": body}


def variant_case(
    builder: Any,
    node: Any,
    branches: tuple[object, object],
    d: Any,
    env: Mapping[str, TypeRef],
    *,
    branch: Branch,
    both: Both,
) -> dict[str, Any] | None:
    """The closed `case` for a `WccIf`/`WccSelect` whose branch reads a variant field, else None.

    `branch(side, d, env)` lowers one branch (0 then, 1 else) to a body and
    `both(scopes)` lowers the whole conditional to a body under one scope per branch.
    Raises `LispFrontendCompileError` (`closed_program_gap`) for a shape the closed
    program cannot express.
    """
    plans = _plans(node, branches, env)
    if not plans:
        return None
    # A proof of two values comes only from `and`/`or`, which the typechecker refuses before
    # lowering; reaching it here is a compiler defect, reported as one by the unpacking.
    (plan,) = plans
    arms = _check_copies(plan, node, branches)
    subject = builder.value(plan.reads[0 if plan.reads[0] else 1][0].base, d, env)
    return {"k": "case", "subject": subject,
            "arms": [_arm(plan, variant, sides, d, env, branch, both) for variant, sides in arms]}
