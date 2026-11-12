"""The demand walk's stop list must stay free of anything that can hold a WCC operand."""

from __future__ import annotations

import dataclasses
import typing

from orchestrator.workflow_lisp.closed.command_templates import _DEMAND_FREE_TYPES
from orchestrator.workflow_lisp import effects, spans, syntax
from orchestrator.workflow_lisp.type_env import RecordTypeRef

_LEAVES = {type(None), str, int, float, bool, bytes}
# Fields typed `object`, by owner and name, whose contents exist before any WCC node does: a
# run-ref result's origin digest (bytes) and the helper expansion frames (`syntax.ExpansionStack`)
# of parsing. Any other `object` field reachable from the stop list fails the test.
_OPAQUE_FIELDS = {(RecordTypeRef, "run_ref_origin"), (effects.ProcedureCallEdge, "expansion_stack"),
                  *((getattr(syntax, name), "expansion_stack") for name in (
                      "SyntaxBool", "SyntaxFloat", "SyntaxIdentifier", "SyntaxInt", "SyntaxKeyword",
                      "SyntaxList", "SyntaxString"))}
_NAMES = {**vars(spans), **vars(syntax)}  # names some modules import only for type checking


def _field_types(hint, owner, name):
    if hint is typing.Any or (hint is object and (owner, name) not in _OPAQUE_FIELDS):
        raise AssertionError(f"{owner.__name__}.{name} is typed {hint!r}, which could hold a WCC operand")
    if typing.get_origin(hint) is typing.Literal or hint is object:
        return
    args = typing.get_args(hint)
    if args:
        for arg in args:
            yield from _field_types(arg, owner, name)
    elif hint is not Ellipsis:
        yield hint


def test_every_type_reachable_from_the_stop_list_is_demand_free():
    seen, pending = set(), list(_DEMAND_FREE_TYPES)
    while pending:
        cls = pending.pop()
        if cls in seen or cls in _LEAVES:
            continue
        seen.add(cls)
        assert dataclasses.is_dataclass(cls), f"{cls!r} is not a dataclass the walk can prove demand free"
        assert not cls.__module__.startswith("orchestrator.workflow_lisp.wcc"), f"{cls!r} is a WCC node"
        for name, hint in typing.get_type_hints(cls, localns=_NAMES).items():
            pending.extend(_field_types(hint, cls, name))
    assert len(seen) > len(_DEMAND_FREE_TYPES) - len(_LEAVES)
