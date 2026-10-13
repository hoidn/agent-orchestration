"""Assign the closed program's definition-local effect sites and call frames."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

SEPARATOR = " / "
_ESCAPED_LABEL_CHARS = frozenset("%/=#[]")


class SiteAssignmentError(ValueError):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


def _escape_label(label: str) -> str:
    return "".join(
        f"%{ord(char):02X}" if char in _ESCAPED_LABEL_CHARS else char
        for char in label
    )


@dataclass
class _Scope:
    anonymous: int = 0
    named: Counter[str] = field(default_factory=Counter)

    def label(self, name: str, authored: Any = None) -> str:
        effective = name if authored is None else authored
        if authored is None and name.startswith("%"):
            self.anonymous += 1
            return f"#{self.anonymous}"
        self.named[effective] += 1
        escaped = _escape_label(effective)
        return escaped if self.named[effective] == 1 else f"{escaped}#{self.named[effective]}"


def assign_sites(tree: dict[str, Any]) -> list[tuple[str, str]]:
    """Write local `site`/`frame` annotations and return perform rows only."""

    definitions = tree.get("definitions", {})
    if not isinstance(definitions, dict):
        raise SiteAssignmentError("definition_table", "definitions must be a mapping")
    _validate_call_graph(tree, definitions)
    walker = _SiteWalker(tree)
    walker._body_has_effect(tree["body"])
    for definition in definitions.values():
        walker._body_has_effect(definition["body"])
    _clear_annotations(tree["body"])
    for definition in definitions.values():
        _clear_annotations(definition["body"])
    rows: list[tuple[str, str]] = []
    walker.walk_definition(tree["entry"], tree["body"])
    rows.extend((tree["entry"], path) for path in walker.sites)
    for name in _definition_order(tree, definitions):
        definition = definitions[name]
        walker.sites = []
        walker.walk_definition(name, definition["body"])
        rows.extend((name, path) for path in walker.sites)
    return rows


def _definition_order(tree: dict[str, Any], definitions: dict[str, Any]) -> list[str]:
    """Use first-call traversal, then a deterministic order for unreachable rows."""

    ordered: list[str] = []
    seen: set[str] = set()

    def visit(body: dict[str, Any]) -> None:
        for call in _call_nodes(body):
            callee = call["callee"]
            if callee in seen:
                continue
            seen.add(callee)
            ordered.append(callee)
            visit(definitions[callee]["body"])

    visit(tree["body"])
    ordered.extend(sorted(set(definitions) - seen))
    return ordered


def _validate_call_graph(
    tree: dict[str, Any], definitions: dict[str, Any]
) -> None:
    """Check every call edge before effect queries can short-circuit."""

    edges: dict[str, list[str]] = {name: [] for name in definitions}
    bodies = [(name, item["body"]) for name, item in definitions.items()]
    bodies.append((tree["entry"], tree["body"]))
    for owner, body in bodies:
        for call in _call_nodes(body):
            callee = call.get("callee")
            if not isinstance(callee, str) or callee not in definitions:
                raise SiteAssignmentError(
                    "callee_unknown", f"unknown call target {callee!r}"
                )
            if owner in edges:
                edges[owner].append(callee)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise SiteAssignmentError("call_cycle", f"recursive call through {name!r}")
        if name in visited:
            return
        visiting.add(name)
        try:
            for callee in edges[name]:
                visit(callee)
        finally:
            visiting.remove(name)
        visited.add(name)

    for name in definitions:
        visit(name)


def _call_nodes(value: Any):
    """Yield calls by following closed AST edges, never arbitrary JSON data."""

    if not isinstance(value, dict):
        return
    kind = value.get("k")
    if kind == "let":
        yield from _bound_calls(value["value"])
        yield from _call_nodes(value["body"])
    elif kind == "if":
        yield from _value_calls(value["cond"])
        yield from _call_nodes(value["then"])
        yield from _call_nodes(value["else"])
    elif kind == "case":
        yield from _value_calls(value["subject"])
        for arm in value["arms"]:
            for root in _arm_root_values(arm):
                yield from _bound_calls(root)
            yield from _call_nodes(arm["body"])
    elif kind == "join":
        yield from _call_nodes(value["body"])
        yield from _call_nodes(value["cont"])
    elif kind in {"halt", "done"}:
        yield from _value_calls(value["value"])
    elif kind in {"jump", "continue"}:
        for argument in value["args"]:
            yield from _value_calls(argument)
    elif kind == "loop":
        yield from _value_calls(value["init"])
        yield from _value_calls(value["budget"])
        yield from _call_nodes(value["body"])
        if value.get("exhausted") is not None:
            yield from _call_nodes(value["exhausted"])


def _bound_calls(value: dict[str, Any]):
    if value.get("k") == "call":
        yield value
        for argument in value.get("args", []):
            yield from _value_calls(argument)
    elif value.get("k") == "perform":
        for child in _effect_value_children(value):
            yield from _value_calls(child)
    else:
        yield from _value_calls(value)


def _value_calls(value: dict[str, Any]):
    kind = value.get("k")
    if kind == "select":
        yield from _value_calls(value["cond"])
        for arm in (value["then"], value["else"]):
            for row in arm["prefix"]:
                yield from _bound_calls(row["value"])
            yield from _value_calls(arm["value"])
    elif kind == "block":
        yield from _call_nodes(value["body"])
    else:
        for child in _value_children(value):
            yield from _value_calls(child)


def _clear_annotations(body: dict[str, Any]) -> None:
    for node in _ast_nodes(body):
        if node.get("k") == "perform":
            node.pop("site", None)
        elif node.get("k") == "call":
            node.pop("frame", None)


def _ast_nodes(body: dict[str, Any]):
    yield body
    kind = body.get("k")
    if kind == "let":
        yield from _bound_nodes(body["value"])
        yield from _ast_nodes(body["body"])
    elif kind == "if":
        yield from _value_nodes(body["cond"])
        yield from _ast_nodes(body["then"])
        yield from _ast_nodes(body["else"])
    elif kind == "case":
        yield from _value_nodes(body["subject"])
        for arm in body["arms"]:
            for root in _arm_root_values(arm):
                yield from _value_nodes(root)
            yield from _ast_nodes(arm["body"])
    elif kind == "join":
        yield from _ast_nodes(body["body"])
        yield from _ast_nodes(body["cont"])
    elif kind in {"halt", "done"}:
        yield from _value_nodes(body["value"])
    elif kind in {"jump", "continue"}:
        for argument in body["args"]:
            yield from _value_nodes(argument)
    elif kind == "loop":
        yield from _value_nodes(body["init"])
        yield from _value_nodes(body["budget"])
        yield from _ast_nodes(body["body"])
        if body.get("exhausted") is not None:
            yield from _ast_nodes(body["exhausted"])


def _bound_nodes(value: dict[str, Any]):
    yield from _value_nodes(value)


def _value_nodes(value: dict[str, Any]):
    yield value
    kind = value.get("k")
    if kind == "perform":
        for child in _effect_value_children(value):
            yield from _value_nodes(child)
    elif kind == "call":
        for argument in value.get("args", []):
            yield from _value_nodes(argument)
    elif kind == "select":
        yield from _value_nodes(value["cond"])
        for arm in (value["then"], value["else"]):
            for row in arm["prefix"]:
                yield from _bound_nodes(row["value"])
            yield from _value_nodes(arm["value"])
    elif kind == "block":
        yield from _ast_nodes(value["body"])
    else:
        for child in _value_children(value):
            yield from _value_nodes(child)


def _arm_root_values(arm):
    return [row[1] for row in arm.get("command_scope", [])]


def _effect_value_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    """Read expression operands from the explicit effect-node schema."""

    kind = node.get("class")
    if kind == "command":
        children = list(node.get("argv", []))
        for plan in node.get("argv_transport", []):
            children.extend(part["value"] for part in plan.get("parts", [])
                if part.get("kind") == "slot")
        children.extend(row[1] for row in node.get("document", []))
        return children
    if kind == "provider":
        children = [row[2] for row in node.get("inputs", [])]
        prompt = node.get("prompt")
        fills = prompt.get("fills", []) if isinstance(prompt, dict) else []
        if isinstance(fills, list):
            children.extend(row.get("value") for row in fills if isinstance(row, dict))
        dependencies = node.get("dependencies")
        if isinstance(dependencies, dict):
            children.extend(dependencies.get("required", []))
            children.extend(dependencies.get("optional", []))
        policy = node.get("policy")
        if isinstance(policy, dict):
            children.extend(policy.values())
        return [child for child in children if isinstance(child, dict)]
    if kind == "run_ref":
        return [row[1] for row in node.get("inputs", [])]
    return []


class _SiteWalker:
    def __init__(self, tree: dict[str, Any]) -> None:
        self.tree = tree
        self.definitions = tree.get("definitions", {})
        self.sites: list[str] = []
        self.effect_memo: dict[str, bool] = {}
        self.effect_visiting: set[str] = set()

    def _callee_has_effect(self, callee: str) -> bool:
        if callee not in self.definitions:
            raise SiteAssignmentError("callee_unknown", f"unknown call target {callee!r}")
        if callee in self.effect_memo:
            return self.effect_memo[callee]
        if callee in self.effect_visiting:
            raise SiteAssignmentError("call_cycle", f"recursive call through {callee!r}")
        self.effect_visiting.add(callee)
        try:
            effectful = self._body_has_effect(self.definitions[callee]["body"])
        finally:
            self.effect_visiting.remove(callee)
        self.effect_memo[callee] = effectful
        return effectful

    def _body_has_effect(self, node: dict[str, Any]) -> bool:
        kind = node.get("k")
        if kind == "let":
            has_effect = self._bound_has_effect(node["value"])
            return self._body_has_effect(node["body"]) or has_effect
        if kind == "if":
            self._require_pure_value(node["cond"])
            then_effect = self._body_has_effect(node["then"])
            else_effect = self._body_has_effect(node["else"])
            return then_effect or else_effect
        if kind == "case":
            self._require_pure_value(node["subject"])
            for arm in node["arms"]:
                for root in _arm_root_values(arm):
                    self._require_pure_value(root)
            arm_effects = [self._body_has_effect(arm["body"]) for arm in node["arms"]]
            return any(arm_effects)
        if kind == "join":
            body_effect = self._body_has_effect(node["body"])
            cont_effect = self._body_has_effect(node["cont"])
            return body_effect or cont_effect
        if kind == "loop":
            self._require_pure_value(node["budget"])
            self._require_pure_value(node["init"])
            body_effect = self._body_has_effect(node["body"])
            exhausted = node.get("exhausted")
            exhausted_effect = exhausted is not None and self._body_has_effect(exhausted)
            return body_effect or exhausted_effect
        if kind == "halt" or kind == "done":
            self._require_pure_value(node["value"])
            return False
        if kind == "jump" or kind == "continue":
            for argument in node["args"]:
                self._require_pure_value(argument)
            return False
        raise SiteAssignmentError("node_kind", f"unknown body node kind {kind!r}")

    def _bound_has_effect(self, node: dict[str, Any]) -> bool:
        kind = node.get("k")
        if kind == "perform":
            for argument in node.get("args", []):
                self._require_pure_value(argument)
            return True
        if kind == "call":
            for argument in node.get("args", []):
                self._require_pure_value(argument)
            return self._callee_has_effect(node["callee"])
        return self._value_has_effect(node)

    def _value_has_effect(
        self, node: dict[str, Any], *, allow_bound_control: bool = True
    ) -> bool:
        kind = node.get("k")
        if kind in {"perform", "call"}:
            raise SiteAssignmentError(
                "effect_in_value", "effectful binding appears outside a binding"
            )
        if kind == "block":
            has_effect = self._body_has_effect(node["body"])
            if has_effect and not allow_bound_control:
                raise SiteAssignmentError(
                    "effect_in_value", "effectful block appears outside a binding"
                )
            return has_effect
        if kind == "select":
            self._require_pure_value(node["cond"])
            branch_effects: list[bool] = []
            for arm in (node["then"], node["else"]):
                prefix_effects = [
                    self._bound_has_effect(row["value"]) for row in arm["prefix"]
                ]
                result_effect = self._value_has_effect(
                    arm["value"], allow_bound_control=False
                )
                branch_effects.append(any(prefix_effects) or result_effect)
            has_effect = any(branch_effects)
            if has_effect and not allow_bound_control:
                raise SiteAssignmentError(
                    "effect_in_value", "effectful select appears outside a binding"
                )
            return has_effect
        child_effects = [
            self._value_has_effect(child, allow_bound_control=False)
            for child in _value_children(node)
        ]
        has_effect = any(child_effects)
        if has_effect and not allow_bound_control:
            raise SiteAssignmentError(
                "effect_in_value", "effectful value child appears outside a binding"
            )
        return False

    def _require_pure_value(self, value: dict[str, Any]) -> None:
        if self._value_has_effect(value, allow_bound_control=False):
            raise SiteAssignmentError(
                "effect_in_value", "effectful value appears outside a binding"
            )

    def walk_definition(self, definition: str, body: dict[str, Any]) -> None:
        self.walk_body(definition, body, (), _Scope())

    def walk_body(
        self,
        definition: str,
        node: dict[str, Any],
        prefix: tuple[str, ...],
        scope: _Scope,
    ) -> None:
        while node.get("k") == "let":
            self.walk_bound(
                definition,
                node["name"],
                node.get("label"),
                node["value"],
                prefix,
                scope,
            )
            node = node["body"]

        kind = node.get("k")
        if kind == "if":
            self.walk_body(definition, node["then"], (*prefix, "then"), _Scope())
            self.walk_body(definition, node["else"], (*prefix, "else"), _Scope())
        elif kind == "case":
            for arm in node["arms"]:
                self.walk_body(definition, arm["body"], (*prefix, arm["variant"]), _Scope())
        elif kind == "join":
            if self._body_has_effect(node["body"]):
                name, _descriptor = node["params"][0]
                label = scope.label(name, node.get("label"))
                self.walk_body(
                    definition,
                    node["body"],
                    (*prefix, label, "body"),
                    _Scope(),
                )
            self.walk_body(definition, node["cont"], prefix, scope)
        elif kind == "loop":
            body_has_effect = self._body_has_effect(node["body"])
            exhausted = node.get("exhausted")
            exhausted_has_effect = exhausted is not None and self._body_has_effect(exhausted)
            if body_has_effect or exhausted_has_effect:
                label = scope.label(node["param"], node.get("label"))
                segment = f"loop:{label}"
                if body_has_effect:
                    self.walk_body(
                        definition,
                        node["body"],
                        (*prefix, f"{segment}[*]"),
                        _Scope(),
                    )
                if exhausted_has_effect:
                    self.walk_body(
                        definition,
                        exhausted,
                        (*prefix, segment, "exhausted"),
                        _Scope(),
                    )
        elif kind not in {"halt", "jump", "continue", "done"}:
            raise SiteAssignmentError("node_kind", f"unknown body node kind {kind!r}")

    def walk_bound(
        self,
        definition: str,
        name: str,
        authored_label: Any,
        value: dict[str, Any],
        prefix: tuple[str, ...],
        scope: _Scope,
    ) -> None:
        kind = value.get("k")
        if kind == "perform":
            site = SEPARATOR.join((*prefix, scope.label(name, authored_label)))
            value["site"] = site
            self.sites.append(site)
        elif kind == "call":
            if self._callee_has_effect(value["callee"]):
                label = scope.label(name, authored_label)
                frame = SEPARATOR.join((*prefix, f"{label}={value['callee']}"))
                value["frame"] = frame
        elif self._value_has_effect(value):
            label = scope.label(name, authored_label)
            self.walk_value(definition, value, (*prefix, label))

    def walk_value(
        self,
        definition: str,
        node: dict[str, Any],
        prefix: tuple[str, ...],
    ) -> None:
        kind = node.get("k")
        if kind == "select":
            for branch, arm in (("then", node["then"]), ("else", node["else"])):
                branch_prefix = (*prefix, branch)
                scope = _Scope()
                for row in arm["prefix"]:
                    self.walk_bound(
                        definition,
                        row["name"],
                        row.get("label"),
                        row["value"],
                        branch_prefix,
                        scope,
                    )
                self.walk_value(definition, arm["value"], branch_prefix)
        elif kind == "block":
            self.walk_body(definition, node["body"], (*prefix, "block"), _Scope())


def _value_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    kind = node.get("k")
    if kind == "field":
        return [node["base"]]
    if kind in {"record", "inject"}:
        fields = node["fields"]
        if isinstance(fields, dict):
            return list(fields.values())
        return [row[1] for row in fields]
    if kind == "op":
        return list(node["args"])
    if kind == "list":
        return list(node["items"])
    if kind == "list_map":
        return [node["source"], node["body"]]
    if kind == "path_join":
        return [node["base"], node["child"]]
    if kind in {"lit", "name", "context", "result_path"}:
        return []
    raise SiteAssignmentError("value_kind", f"unknown value node kind {kind!r}")
