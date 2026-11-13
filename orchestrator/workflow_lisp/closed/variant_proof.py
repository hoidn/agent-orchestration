"""Lower a branch-local variant proof of a conditional to a closed `case`.

The typechecker proves that `x` is variant `TAG` in a branch of
`(if (= x.variant TAG) ...)` (frontend specification, section 12); WCC keeps
that fact as `(name, union, tag)` triples on `WccIf` and `WccSelect`. The closed
program narrows only in a `case` arm. A conditional whose branch reads a field
that the whole union does not carry with one type becomes a `case` on `x`: each
arm holds the branch, or the conditional, that the proof leaves possible for its
variant, and a narrowed branch sees `x` as the arm's binder. A conditional with
no such read keeps its plain lowering, so its program and digest do not change.

The closed program has no body for an unreachable arm and no way to share a
branch between arms, so a branch that falls in several arms is copied only when
it is pure and calls nothing; otherwise the conditional is refused with
`closed_program_gap`, which names the `match` form that does lower.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Callable, Mapping

from orchestrator.workflow_lisp.type_env import TypeRef, UnionTypeRef
from orchestrator.workflow_lisp.wcc import model as w

_COPYABLE = (
    w.WccLiteralAtom, w.WccNameAtom, w.WccFieldAccessAtom, w.WccRecordAtom, w.WccList,
    w.WccPureOp, w.WccInject, w.WccSelect, w.WccSelectArm, w.WccHalt, w.WccLet,
)


@dataclass(frozen=True)
class _Plan:
    name: str
    union: UnionTypeRef
    tags: tuple[str | None, str | None]  # then, else: the variant each branch proves
    narrowed: tuple[bool, bool]  # whether that branch reads a field of its variant
    read: w.WccFieldAccessAtom


def _nodes(root: object):
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, (tuple, list)):
            stack.extend(node)
        elif is_dataclass(node) and type(node).__module__ == w.__name__ and not isinstance(node, w.WccNodeMetadata):
            yield node
            stack.extend(getattr(node, item.name) for item in fields(node) if item.name != "metadata")


def _union_wide(union: UnionTypeRef, field: str) -> bool:
    types = [union.variant_field_types.get(row.name, {}).get(field) for row in union.definition.variants]
    return field == "variant" or (None not in types and all(item == types[0] for item in types))


def _variant_read(branch: object, name: str, union: UnionTypeRef) -> w.WccFieldAccessAtom | None:
    for node in _nodes(branch):
        if (isinstance(node, w.WccFieldAccessAtom) and isinstance(node.base, w.WccNameAtom)
                and node.base.name == name and not _union_wide(union, node.fields[0])):
            return node
    return None


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
        reads = [_variant_read(branch, name, union) if tag else None
                 for tag, branch in zip((then_tag, else_tag), branches)]
        read = reads[0] or reads[1]
        if read is not None:
            plans.append(_Plan(name, union, (then_tag, else_tag), (reads[0] is not None, reads[1] is not None), read))
    return plans


def _gap(plan: _Plan, reason: str):
    from .build import ClosedProgramGap

    field, tag = plan.read.fields[0], plan.tags[0] if plan.narrowed[0] else plan.tags[1]
    message = (f"field `{field}` of `{plan.name}` belongs to variant `{tag}`, and {reason}; "
               f"bind the variant with `match`: (match {plan.name} (({tag} v) ... v.{field} ...) ...)")
    return ClosedProgramGap("if", message, span=plan.read.metadata.source_span,
                            form_path=plan.read.metadata.form_path)


def _possible(plan: _Plan) -> list[tuple[str, tuple[bool, bool]]]:
    """Per variant, whether the proof leaves the then and the else branch possible."""
    return [(row.name, (plan.tags[0] in (None, row.name), plan.tags[1] in (None, row.name)))
            for row in plan.union.definition.variants]


def _check_copies(plan: _Plan, node: Any, branches: tuple[object, object]) -> None:
    possible = [sides for _variant, sides in _possible(plan)]
    if not all(any(sides) for sides in possible):
        raise _gap(plan, "the condition leaves a variant in neither branch")
    shared = [branch for side, branch in enumerate(branches) if sum(sides[side] for sides in possible) > 1]
    if sum(all(sides) for sides in possible) > 1:
        shared.append(node.condition)
    if not all(isinstance(item, _COPYABLE) for root in shared for item in _nodes(root)):
        raise _gap(plan, "the branch that more than one variant reaches has an effect or a call")


Scope = tuple[Any, Mapping[str, TypeRef]]
Branch = Callable[[int, Any, Mapping[str, TypeRef]], dict[str, Any]]
Both = Callable[[tuple[Scope, Scope]], dict[str, Any]]


def _arm(builder: Any, plan: _Plan, node: Any, variant: str, sides: tuple[bool, bool],
         d: Any, env: Mapping[str, TypeRef], branch: Branch, both: Both) -> dict[str, Any]:
    local, binder = builder.bind(d, plan.name, label=None)
    identity = plan.read.base.metadata.binding_identity
    if identity is not None:
        local.binding_aliases = {**(local.binding_aliases or {}), identity: plan.name}
    case_type = d.type_env.union_variant(plan.union, variant, span=node.metadata.source_span,
                                         form_path=node.metadata.form_path)
    scopes = tuple((local, {**env, plan.name: case_type})
                   if plan.narrowed[side] and plan.tags[side] == variant else (d, env)
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
    Raises `ClosedProgramGap` for a proof the closed program cannot express.
    """
    plans = _plans(node, branches, env)
    if not plans:
        return None
    plan = plans[0]
    if len(plans) > 1:
        raise _gap(plan, "the condition proves the variants of more than one value")
    _check_copies(plan, node, branches)
    subject = builder.value(plan.read.base, d, env)
    arms = [_arm(builder, plan, node, variant, sides, d, env, branch, both) for variant, sides in _possible(plan)]
    return {"k": "case", "subject": subject, "arms": arms}
