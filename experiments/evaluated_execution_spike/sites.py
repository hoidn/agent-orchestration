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

    sites: list[str] = []
    memo: dict[int, bool] = {}

    def walk(node: dict[str, Any] | None, prefix: list[str]) -> None:
        scope = _Scope()
        while node is not None:
            kind = node["k"]
            if kind == "let":
                bound = node["value"]
                if bound.get("k") == "perform":
                    bound["site"] = SEPARATOR.join([*prefix, scope.label(node["name"])])
                    sites.append(bound["site"])
                elif bound.get("k") == "call" and _has_effect(bound, memo):
                    walk(bound["body"], [*prefix, f"{scope.label(node['name'])}={bound['callee']}"])
                node = node["body"]
            elif kind == "join":
                if _has_effect(node["body"], memo):
                    walk(node["body"], [*prefix, scope.label(node["params"][0])])
                node = node["cont"]
            elif kind == "if":
                walk(node["then"], [*prefix, "then"])
                walk(node["else"], [*prefix, "else"])
                return
            elif kind == "case":
                for arm in node["arms"]:
                    walk(arm["body"], [*prefix, arm["variant"]])
                return
            elif kind == "loop":
                segment = "loop" if node["param"].startswith("%") else f"loop:{node['param']}"
                walk(node["body"], [*prefix, segment + "[*]"])
                if node["exhausted"] is not None:
                    walk(node["exhausted"], [*prefix, segment, "exhausted"])
                return
            else:
                return

    walk(tree["body"], [tree["entry"]])
    return sites


class CheckedFormError(ValueError):
    """P5: the closed program is not in its checked form."""


def validate(tree: dict[str, Any]) -> None:
    """Names are bound where used, jumps and continues have a target, every effect has one unique site."""

    seen: set[str] = set()

    def fail(message: str) -> None:
        raise CheckedFormError(message)

    def value(node: dict[str, Any], names: frozenset[str]) -> None:
        kind = node["k"]
        if kind == "name" and node["n"] not in names:
            fail(f"unbound name `{node['n']}`")
        elif kind == "field":
            value(node["base"], names)
        elif kind in ("record", "inject"):
            for _, item in node["fields"]:
                value(item, names)
        elif kind in ("op", "list"):
            for item in node.get("args", node.get("items", [])):
                value(item, names)
        elif kind == "select":
            value(node["cond"], names)
            for arm in (node["then"], node["else"]):
                inner = names
                for let in arm["prefix"]:
                    bound(let["value"], inner)
                    inner = inner | {let["name"]}
                value(arm["value"], inner)
        elif kind == "block":
            body(node["body"], names, frozenset(), False)

    def bound(node: dict[str, Any], names: frozenset[str]) -> None:
        if node["k"] == "perform":
            site = node.get("site")
            if site is None or site in seen:
                fail(f"effect without a unique site: {site}")
            seen.add(site)
            for key in ("argv", "inputs"):
                for item in node.get(key, []):
                    value(item, names)
            for item in [*node.get("policy", {}).values(), *([node["question"]] if "question" in node else [])]:
                value(item, names)
        elif node["k"] == "call":
            for item in node["args"]:
                value(item, names)
            body(node["body"], frozenset(node["params"]), frozenset(), False)
        else:
            value(node, names)

    def body(node: dict[str, Any], names: frozenset[str], joins: frozenset[str], in_loop: bool) -> None:
        while node["k"] == "let":
            bound(node["value"], names)
            names = names | {node["name"]}
            node = node["body"]
        kind = node["k"]
        if kind in ("halt", "done"):
            value(node["value"], names)
        elif kind in ("jump", "continue"):
            if (kind == "jump" and node["join"] not in joins) or (kind == "continue" and not in_loop):
                fail(f"`{kind}` without an enclosing target")
            for item in node["args"]:
                value(item, names)
        elif kind == "if":
            value(node["cond"], names)
            body(node["then"], names, joins, in_loop)
            body(node["else"], names, joins, in_loop)
        elif kind == "case":
            value(node["subject"], names)
            for arm in node["arms"]:
                body(arm["body"], names | {arm["bind"]}, joins, in_loop)
        elif kind == "join":
            body(node["body"], names, joins | {node["name"]}, in_loop)
            body(node["cont"], names | set(node["params"]), joins, in_loop)
        elif kind == "loop":
            value(node["budget"], names)
            value(node["init"], names)
            body(node["body"], names | {node["param"]}, frozenset(), True)
            if node["exhausted"] is not None:
                body(node["exhausted"], names | {node["param"]}, frozenset(), False)
        else:
            fail(f"unknown node kind `{kind}`")

    body(tree["body"], frozenset(name for name, _ in tree["params"]), frozenset(), False)
