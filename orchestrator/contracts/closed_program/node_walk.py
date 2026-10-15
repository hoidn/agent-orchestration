"""Schema walkers over closed-program AST, bound and value nodes (shared by sites, check and runtime)."""

from __future__ import annotations

from typing import Any


class SiteAssignmentError(ValueError):
    def __init__(self, rule: str, message: str) -> None:
        super().__init__(message)
        self.rule = rule


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
    elif kind == "par-map":
        yield from _value_nodes(body["source"])
        yield from _value_nodes(body["workspace"])
        yield from _ast_nodes(body["body"])
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
        return _command_value_children(node)
    if kind == "agent":
        return [value for value in (node.get("policy") or {}).values() if isinstance(value, dict)]
    if kind in {"provider", "agent_turn"}:
        return _provider_value_children(node)
    if kind == "run_ref":
        commit = [node["commit"]] if "commit" in node else []
        return commit + [row[1] for row in node.get("inputs", [])]
    return []


def _command_value_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = list(node.get("argv", []))
    for plan in node.get("argv_transport", []):
        children.extend(part["value"] for part in plan.get("parts", [])
            if part.get("kind") == "slot")
    children.extend(row[1] for row in node.get("document", []))
    return children


def _provider_value_children(node: dict[str, Any]) -> list[dict[str, Any]]:
    children = [node.get("agent")] if node.get("class") == "agent_turn" else []
    children.extend(row[2] for row in node.get("inputs", []))
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
