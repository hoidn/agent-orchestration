"""Pure admission and call accounting over validated closed-program AST edges.

New AST forms require an explicit accounting rule; unknown forms fail closed.
"""

import json
import math
from collections.abc import Mapping
from pathlib import Path

from orchestrator.contracts.closed_program.node_walk import (
    _arm_root_values, _ast_nodes, _effect_value_children, _value_children,
)

UNSUPPORTED = {"provider_phased", "agent", "agent_turn"}
PROVIDER_CLASSES = {"provider", *UNSUPPORTED}
CONTROL_FIELDS = {
    "let": ("value", "body"), "if": ("cond", "then", "else"), "join": ("body", "cont"),
    "halt": ("value",), "done": ("value",), "jump": ("args",), "continue": ("args",),
    "block": ("body",),
}


def closed_program(root: Path, build_key: str) -> dict:
    return json.loads((root / ".orchestrate" / "build" / build_key / "closed_program.json").read_text())


def perform_nodes(program: Mapping) -> list[dict]:
    roots = [program["body"], *(d["body"] for d in program.get("definitions", {}).values() if "body" in d)]
    return [node for root in roots for node in _ast_nodes(root) if node.get("k") == "perform"]


def effect_shape_refusal(program: Mapping) -> dict | None:
    for node in perform_nodes(program):
        if node["class"] in UNSUPPORTED:
            return {"refusal_code": "unsupported_effect_shape",
                    "detail": f"{node.get('site', 'unavailable')}: unsupported effect {node['class']}"}
    return None


def _provider_policy_refusal(policy: Mapping, config) -> dict | None:
    values = {key: value.get("v") for key, value in policy.items() if value.get("k") == "lit"}
    model, effort = values.get("model"), values.get("effort")
    if not (isinstance(model, str) and "fable" not in model.lower() and isinstance(effort, str)
            and effort in config.models.get(model, ())):
        return {"refusal_code": "model_not_allowed", "detail": "model and effort must be allowlisted string literals"}
    timeout = values.get("timeout_sec")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
            or timeout > config.per_call_timeout_sec or set(policy) - {"model", "effort", "timeout_sec", "delivery"}):
        return {"refusal_code": "per_call_ceiling_exceeded",
                "detail": f"timeout_sec must be a positive literal at most {config.per_call_timeout_sec}; "
                          "additional per-call ceilings are not admitted"}
    return None


def qualifiers(program: Mapping) -> set[str]:
    return {name.split("::")[0].rsplit(":", 1)[-1] for key in ("definitions", "types")
            for name in program.get(key, {}) if "::" in name} - {"workflow_lisp/private"}


def compiled_refusal(parent: Mapping, child: Mapping, config) -> dict | None:
    for field in ("params", "result"):
        if parent[field] != child[field]:
            code = "slot_type_changed" if field == "result" and config.condition != "module" else "frozen_surface_changed"
            return {"refusal_code": code, "detail": f"resolved entry {field} of {config.entry_workflow} changed"}
    refusal = effect_shape_refusal(child)
    if refusal or config.condition != "module":
        return refusal
    own_module = config.entry_workflow.split("::")[0]
    if qualifiers(parent) - {own_module} != qualifiers(child) - {own_module}:
        return {"refusal_code": "frozen_surface_changed", "detail": "the resolved imported module graph changed"}
    for node in perform_nodes(child):
        if node["class"] == "provider":
            refusal = _provider_policy_refusal(node.get("policy", {}), config)
            if refusal:
                return {**refusal, "detail": f"{node.get('site', 'unavailable')}: {refusal['detail']}"}
    return None


def _children(node):
    kind = node["k"]
    if kind == "perform":
        return _effect_value_children(node)
    if kind == "case":
        return [node["subject"], *(value for arm in node["arms"] for value in _arm_root_values(arm)),
                *(arm["body"] for arm in node["arms"])]
    if kind == "select":
        return _select_children(node)
    if kind in CONTROL_FIELDS:
        return [child for key in CONTROL_FIELDS[kind]
                for child in (node[key] if isinstance(node[key], list) else [node[key]])]
    return _value_children(node)


def _select_children(node):
    return [node["cond"], *(row["value"] for arm in (node["then"], node["else"]) for row in arm["prefix"]),
            node["then"]["value"], node["else"]["value"]]


def _unbounded(detail):
    from experiments.orc_structural_search.ledger import CallCapExceeded
    raise CallCapExceeded(detail)


def _literal_budget(node):
    if node.get("k") != "lit" or type(node.get("v")) is not int:
        _unbounded("loop budget is not a literal integer")
    return max(0, node["v"])


class _CallBound:
    def __init__(self, program):
        self.definitions = program.get("definitions", {})
        self.costs = {}
        self.active = set()

    def callee(self, name):
        if name not in self.definitions or name in self.active:
            _unbounded(f"unknown or cyclic closed-program callee {name!r}")
        if name not in self.costs:
            self.active.add(name)
            self.costs[name] = self.count(self.definitions[name]["body"])
            self.active.remove(name)
        return self.costs[name]

    def count(self, node):
        if node is None:
            return 0
        kind = node["k"]
        if kind == "call":
            return sum(self.count(arg) for arg in node.get("args", [])) + self.callee(node["callee"])
        if kind == "loop":
            return (self.count(node["budget"]) + self.count(node["init"])
                    + _literal_budget(node["budget"]) * self.count(node["body"])
                    + self.count(node.get("exhausted")))
        if kind == "par-map":
            if type(node.get("max")) is not int or node["max"] < 0:
                _unbounded("parallel map maximum is not a nonnegative integer")
            return self.count(node["source"]) + node["max"] * (self.count(node["workspace"]) + self.count(node["body"]))
        if kind == "list_map":
            return self.list_map(node)
        return (kind == "perform" and node["class"] in PROVIDER_CLASSES) + sum(self.count(c) for c in _children(node))

    def list_map(self, node):
        source, body = node["source"], self.count(node["body"])
        if body and source["k"] != "list":
            _unbounded("effectful list_map source has no provable literal cardinality")
        return self.count(source) + (len(source["items"]) * body if body else 0)


def planned_maximum(program: Mapping) -> int:
    """Upper bound from the entry only, expanding each resolved call once per invocation."""
    try:
        return _CallBound(program).count(program["body"])
    except (KeyError, TypeError, ValueError) as error:
        _unbounded(f"unsupported closed-program accounting shape: {error}")
