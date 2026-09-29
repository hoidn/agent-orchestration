"""Effect sites (design section 6) and the checked form (P5) of the closed program.

Node kinds of the closed program, all plain JSON:

- body:  let (name, value, body), halt (value), if (cond, then, else),
         case (subject, arms[variant, bind, body]), join (name, params, body, cont),
         jump (join, args), loop (name, param, budget, init, body, exhausted, code),
         continue (loop, args), done (value)
- bound: perform (class, ..., site), call (callee, params, args, body), or a value
- value: lit (v), name (n), field (base, path), record (fields), inject (variant, fields),
         op (payload, args), select (cond, then, else: prefix + value), list (items), block (body)

A site is the lexical path from the entry to a `perform`: the entry's name, then
one segment per enclosing construct. A call is `<binder>=<callee>`, a branch
`then` or `else`, a `case` arm its variant, a loop `loop:<param>[*]` (its
exhaustion body `loop:<param> / exhausted`), a bound control construct its
binder. The effect's own segment is its binder. An unnamed binder (a
generated name, `%<n>`) is `#<k>`, its ordinal among the effectful unnamed
binders of its scope; a repeated name is `<name>#<k>`. An identity is a site
with each `[*]` replaced by the iteration of that loop.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

SEPARATOR = " / "


def _has_effect(node: Any, memo: dict[int, bool]) -> bool:
    key = id(node)
    if key not in memo:
        if isinstance(node, dict):
            memo[key] = node.get("k") == "perform" or any(_has_effect(v, memo) for v in node.values())
        elif isinstance(node, list):
            memo[key] = any(_has_effect(v, memo) for v in node)
        else:
            memo[key] = False
    return memo[key]


class _Scope:
    def __init__(self) -> None:
        self.unnamed = 0
        self.names: Counter[str] = Counter()

    def label(self, name: str) -> str:
        if name.startswith("%"):
            self.unnamed += 1
            return f"#{self.unnamed}"
        self.names[name] += 1
        return name if self.names[name] == 1 else f"{name}#{self.names[name]}"


def assign_sites(tree: dict[str, Any]) -> list[str]:
    """Write `site` on every perform node; return the site table in program order."""

    walker = _SiteWalker()
    walker.walk(tree["body"], [tree["entry"]])
    return walker.sites


class _SiteWalker:
    def __init__(self) -> None:
        self.sites: list[str] = []
        self.memo: dict[int, bool] = {}

    def walk(self, node: dict[str, Any], prefix: list[str]) -> None:
        scope = _Scope()
        while node["k"] in ("let", "join"):
            node = self.let(node, prefix, scope) if node["k"] == "let" else self.join(node, prefix, scope)
        if node["k"] == "if":
            self.walk(node["then"], [*prefix, "then"])
            self.walk(node["else"], [*prefix, "else"])
        elif node["k"] == "case":
            for arm in node["arms"]:
                self.walk(arm["body"], [*prefix, arm["variant"]])
        elif node["k"] == "loop":
            segment = "loop" if node["param"].startswith("%") else f"loop:{node['param']}"
            self.walk(node["body"], [*prefix, segment + "[*]"])
            if node["exhausted"] is not None:
                self.walk(node["exhausted"], [*prefix, segment, "exhausted"])

    def let(self, node: dict[str, Any], prefix: list[str], scope: _Scope) -> dict[str, Any]:
        bound = node["value"]
        if bound["k"] == "perform":
            bound["site"] = SEPARATOR.join([*prefix, scope.label(node["name"])])
            self.sites.append(bound["site"])
        elif bound["k"] == "call" and _has_effect(bound, self.memo):
            self.walk(bound["body"], [*prefix, f"{scope.label(node['name'])}={bound['callee']}"])
        return node["body"]

    def join(self, node: dict[str, Any], prefix: list[str], scope: _Scope) -> dict[str, Any]:
        if _has_effect(node["body"], self.memo):
            self.walk(node["body"], [*prefix, scope.label(node["params"][0])])
        return node["cont"]


class CheckedFormError(ValueError):
    """P5: the closed program is not in its checked form."""


def validate(tree: dict[str, Any]) -> None:
    """Names are bound where used, jumps and continues have a target, every effect has one unique site."""

    _Validator().body(tree["body"], frozenset(name for name, _ in tree["params"]), frozenset(), False)


def _value_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    kind = node["k"]
    if kind == "field":
        return [node["base"]]
    if kind in ("record", "inject"):
        return [item for _, item in node["fields"]]
    return node.get("args", node.get("items", []))


class _Validator:
    def __init__(self) -> None:
        self.seen: set[str] = set()

    def value(self, node: dict[str, Any], names: frozenset[str]) -> None:
        kind = node["k"]
        if kind == "name" and node["n"] not in names:
            raise CheckedFormError(f"unbound name `{node['n']}`")
        if kind == "select":
            self.value(node["cond"], names)
            for arm in (node["then"], node["else"]):
                inner = names
                for let in arm["prefix"]:
                    self.bound(let["value"], inner)
                    inner = inner | {let["name"]}
                self.value(arm["value"], inner)
        elif kind == "block":
            self.body(node["body"], names, frozenset(), False)
        for child in _value_children(node):
            self.value(child, names)

    def bound(self, node: dict[str, Any], names: frozenset[str]) -> None:
        if node["k"] == "perform":
            site = node.get("site")
            if site is None or site in self.seen:
                raise CheckedFormError(f"effect without a unique site: {site}")
            self.seen.add(site)
            operands = [*node.get("argv", []), *node.get("inputs", []), *node.get("policy", {}).values(),
                        *(value for _, value in node.get("document", []))]
            for item in operands + ([node["question"]] if "question" in node else []):
                self.value(item, names)
        elif node["k"] == "call":
            for item in node["args"]:
                self.value(item, names)
            self.body(node["body"], frozenset(node["params"]), frozenset(), False)
        else:
            self.value(node, names)

    def body(self, node: dict[str, Any], names: frozenset[str], joins: frozenset[str], in_loop: bool) -> None:
        while node["k"] == "let":
            self.bound(node["value"], names)
            names = names | {node["name"]}
            node = node["body"]
        tail = getattr(self, "tail_" + node["k"], None)
        if tail is None:
            raise CheckedFormError(f"unknown node kind `{node['k']}`")
        tail(node, names, joins, in_loop)

    def tail_halt(self, node, names, joins, in_loop) -> None:
        self.value(node["value"], names)

    tail_done = tail_halt

    def tail_jump(self, node, names, joins, in_loop) -> None:
        if (node["k"] == "jump" and node["join"] not in joins) or (node["k"] == "continue" and not in_loop):
            raise CheckedFormError(f"`{node['k']}` without an enclosing target")
        for item in node["args"]:
            self.value(item, names)

    tail_continue = tail_jump

    def tail_if(self, node, names, joins, in_loop) -> None:
        self.value(node["cond"], names)
        self.body(node["then"], names, joins, in_loop)
        self.body(node["else"], names, joins, in_loop)

    def tail_case(self, node, names, joins, in_loop) -> None:
        self.value(node["subject"], names)
        for arm in node["arms"]:
            self.body(arm["body"], names | {arm["bind"]}, joins, in_loop)

    def tail_join(self, node, names, joins, in_loop) -> None:
        self.body(node["body"], names, joins | {node["name"]}, in_loop)
        self.body(node["cont"], names | set(node["params"]), joins, in_loop)

    def tail_loop(self, node, names, joins, in_loop) -> None:
        self.value(node["budget"], names)
        self.value(node["init"], names)
        self.body(node["body"], names | {node["param"]}, frozenset(), True)
        if node["exhausted"] is not None:
            self.body(node["exhausted"], names | {node["param"]}, frozenset(), False)
