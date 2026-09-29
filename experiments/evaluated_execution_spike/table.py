"""The closed program as a table of definitions (design section 6): each callee body stored once.

The tree form attaches a copy of a callee body at every call path. The table form
keeps one body per canonical callee name in `definitions`; a call names its callee
and carries its call site as `frame`. A site is then local to its definition, and an
identity is the activation path (the frames, with loop iterations) and the local site.
The evaluator runs both forms.
"""

from __future__ import annotations

import copy
from typing import Any

from .sites import ClosedProgram, _SiteWalker, assign_sites, canonical_digest, strip_provenance, validate


def _without_sites(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _without_sites(value) for key, value in node.items() if key not in ("site", "frame")}
    if isinstance(node, list):
        return [_without_sites(item) for item in node]
    return node


def resite(program: ClosedProgram, *, count_pure: bool = False) -> ClosedProgram:
    """The tree form with its sites assigned again, under either ordinal rule."""

    tree = _without_sites(copy.deepcopy(program.tree))
    sites = assign_sites(tree, count_pure=count_pure)
    return ClosedProgram(tree=tree, sites=tuple(sites), digest=canonical_digest(strip_provenance(tree)))


def to_table(program: ClosedProgram, *, count_pure: bool = False) -> ClosedProgram:
    tree = _without_sites(copy.deepcopy(program.tree))
    definitions: dict[str, dict[str, Any]] = {}

    def lift(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                lift(item)
            return
        if not isinstance(node, dict):
            return
        if node.get("k") == "call" and "body" in node:
            definition = {"params": node.pop("params"), "body": node.pop("body")}
            lift(definition["body"])
            known = definitions.setdefault(node["callee"], definition)
            if strip_provenance(known) != strip_provenance(definition):
                raise ValueError(f"two bodies for `{node['callee']}`")
        for value in node.values():
            lift(value)

    lift(tree["body"])
    tree["definitions"] = definitions
    walker = _SiteWalker(definitions, count_pure=count_pure)
    walker.walk(tree["body"], [tree["entry"]])
    for name, definition in definitions.items():
        walker.walk(definition["body"], [])
    validate(tree)
    table = [(name, site) for name in [tree["entry"], *definitions] for site in _local_sites(tree, name)]
    return ClosedProgram(tree=tree, sites=tuple(f"{n} :: {s}" for n, s in table),
                         digest=canonical_digest(strip_provenance(tree)))


def _local_sites(tree: dict[str, Any], name: str) -> list[str]:
    body = tree["body"] if name == tree["entry"] else tree["definitions"][name]["body"]
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("k") == "perform":
                found.append(node["site"])
            for key, value in node.items():
                if not (node.get("k") == "call" and key == "body"):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(body)
    return found
