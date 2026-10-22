"""Closed-program checks for target-2.38 Agent effects and run-local boundaries.

Dependencies: `checker` is the `check._Checker` validating one tree; this module
uses its `fail`, `_value`, `_body`, `_require_type`, `_same`, `_check_effect_node` and `tree`.
An `agent` perform's result descriptor object is recorded by identity, so an
`agent_turn` whose operand names a `let` bound to that perform (directly or by
alias; the checker's environment carries the same descriptor object) must list
that perform's provider among its `origins`; any other operand (parameter, field,
`select` result, join) must list every allocation provider in the tree
(`agent_origin_mismatch`). No `par-map` worker may reach an agent or phased
provider effect through any call edge (`parallel_agent_boundary` or
`parallel_provider_boundary`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from orchestrator.workflow.agent_value import contains_agent_descriptor

from .node_walk import _ast_nodes
from .targets import target_dsl_supports_agent_sessions

AGENT_DESCRIPTOR = {"kind": "primitive", "name": "Agent"}
_STRING = {"kind": "primitive", "name": "String"}
_AGENT_KEYS = {"k", "class", "result", "repeat", "site", "@", "provider", "policy"}
_TURN_KEYS = {"k", "class", "result", "repeat", "site", "@", "agent", "origins",
              "prompt", "inputs", "dependencies", "policy", "contract"}
_TURN_REQUIRED = _TURN_KEYS - {"k", "class", "result", "site", "@"}


def check_agent_target(checker, descriptor, node=None) -> None:
    if (not target_dsl_supports_agent_sessions(checker.tree.get("target", ""))
            and contains_agent_descriptor(descriptor)):
        checker.fail("agent_target_dsl_unsupported", "Agent requires target 2.38", node)


def require_no_agent(checker, descriptor, node=None, *, rule="agent_transport_forbidden") -> None:
    if contains_agent_descriptor(descriptor):
        checker.fail(rule, "a run-local Agent cannot cross this data boundary", node)


def check_workflow_signature(checker, params, result, node=None) -> None:
    require_no_agent(checker, [*(row[1] for row in params), result], node)


def check_key_agents(checker, key) -> None:
    require_no_agent(checker, [row["type"] for row in key[7]])
    if key[1] == "workflow":
        require_no_agent(checker, key[8])


def check_agent_value(checker, node, env) -> None:
    if node.get("k") == "lit":
        require_no_agent(checker, node.get("type"), node)
    elif node.get("k") == "name" and isinstance(node.get("n"), str):
        name = node.get("n")
        for captured in vars(checker).get("_parallel_agent_environments", ()):
            if name in captured and env.get(name) is captured[name]:
                require_no_agent(checker, captured[name], node, rule="parallel_agent_boundary")


def check_parallel_agent_body(checker, body, env, **context):
    """Track actual lexical captures; an unused or shadowed outside Agent is legal."""

    captures = vars(checker).setdefault("_parallel_agent_environments", [])
    captures.append(dict(env))
    try:
        return checker._body(body, env, **context)
    finally:
        captures.pop()


def _allocated_providers(checker) -> dict[int, str]:
    return vars(checker).setdefault("_agent_result_providers", {})


def _all_allocation_providers(checker) -> set[str]:
    """Providers of every `agent` perform in the tree: the bound for an untraced operand."""

    cached = vars(checker).get("_all_allocation_providers")
    if cached is None:
        cached = {node.get("provider") for node in _tree_nodes(checker.tree)
                  if node.get("k") == "perform" and node.get("class") == "agent"}
        checker._all_allocation_providers = cached
    return cached


def _tree_nodes(tree):
    for body in (tree["body"], *(definition["body"] for definition in tree["definitions"].values())):
        yield from _ast_nodes(body)


def find_parallel_effect(
    tree, effect_classes: set[str] | frozenset[str]
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """Find the first parallel worker that reaches one of these effect classes.

    Calls are followed through `tree["definitions"]` transitively (memoised),
    including imported and specialized definitions already present in the tree.
    """

    definitions = tree["definitions"]
    reached: dict[str, Mapping[str, Any] | None] = {}

    def reach(body):
        for node in _ast_nodes(body):
            if node.get("k") == "perform" and node.get("class") in effect_classes:
                return node
            if node.get("k") == "call" and node.get("callee") in definitions:
                callee = node["callee"]
                if callee not in reached:
                    reached[callee] = None  # cycle guard; the call graph is acyclic once checked
                    reached[callee] = reach(definitions[callee]["body"])
                if reached[callee] is not None:
                    return reached[callee]
        return None

    for node in _tree_nodes(tree):
        if node.get("k") == "par-map" and (found := reach(node["body"])) is not None:
            return node, found
    return None


def check_parallel_effects(checker) -> None:
    """Backstop: agent and phased provider effects cannot run in parallel workers."""

    found = find_parallel_effect(checker.tree, {"agent", "agent_turn", "provider_phased", "request_input"})
    if found is not None:
        if found[1].get("class") == "request_input":
            checker.fail("parallel_host_input_boundary", "a parallel worker reaches host input", found[0])
        rule = (
            "parallel_provider_boundary"
            if found[1].get("class") == "provider_phased"
            else "parallel_agent_boundary"
        )
        message = (
            "a parallel worker reaches a phased provider effect"
            if rule == "parallel_provider_boundary"
            else "a parallel worker reaches an agent effect"
        )
        checker.fail(rule, message, found[0])


def _configured(providers: Any, provider: Any) -> bool:
    return provider in providers or any(
        isinstance(row, Mapping) and row.get("provider_id") == provider for row in providers.values())


def check_agent_configuration(checker, node: Mapping[str, Any], scope: Mapping[str, Any], owner: str) -> None:
    """Every provider an agent effect can reach must be configured for its owner."""

    providers = scope["providers"]
    if not isinstance(providers, Mapping):
        checker.fail("configuration_scope", "provider configuration must be an object", node)
    reachable = [node.get("provider")] if node.get("class") == "agent" else node.get("origins", [])
    for provider in reachable:
        if not _configured(providers, provider):
            checker.fail("configuration_scope", f"provider {provider!r} is missing from {owner!r} configuration", node)
    prompt = node.get("prompt")
    if isinstance(prompt, Mapping) and prompt.get("source_kind") in {"asset_file", "input_file"}:
        keyset = {"source_kind", "path"} | ({"asset_base"} if prompt["source_kind"] == "asset_file" else set())
        projected = {key: prompt.get(key) for key in keyset}
        if not any(isinstance(row, Mapping) and checker._same(row, projected) for row in scope["prompts"].values()):
            checker.fail("configuration_scope", "agent turn prompt source differs from resolved prompt configuration", node)


def check_agent_effect_node(checker, node: Mapping[str, Any], env: dict[str, Any], **walk: Any) -> None:
    """Validate one `agent` or `agent_turn` perform against the interface-contract shape."""

    if not target_dsl_supports_agent_sessions(checker.tree.get("target", "")):
        checker.fail("effect_class", f"effect class {node.get('class')!r} requires target 2.38", node)
    if node.get("repeat") != "rerun":
        checker.fail("effect_repeat", "agent effects must rerun", node)
    if node.get("class") == "agent":
        _check_agent(checker, node, env, walk)
    else:
        _check_agent_turn(checker, node, env, walk)


def _check_agent(checker, node, env, walk) -> None:
    if set(node) - _AGENT_KEYS or not {"provider", "policy"} <= set(node):
        checker.fail("effect_shape", "agent effect has missing or class-inappropriate fields", node)
    if not checker._same(node.get("result"), AGENT_DESCRIPTOR):
        checker.fail("effect_result", "agent effect must produce an Agent", node)
    if not isinstance(node["provider"], str) or not node["provider"].strip():
        checker.fail("effect_shape", "agent provider id must be a nonempty string", node)
    policy = node["policy"]
    if not isinstance(policy, Mapping) or set(policy) - {"model", "effort"}:
        checker.fail("effect_shape", "agent policy may only pin model and effort", node)
    for value in policy.values():
        checker._require_type(checker._value(value, env, allow_effect=False, **walk), _STRING, "effect_shape", node)
        if not isinstance(value, Mapping) or value.get("k") not in {"lit", "name", "field"}:
            checker.fail("effect_shape", "agent policy values must be inline String values", node)
    _allocated_providers(checker)[id(node["result"])] = node["provider"]


def _check_agent_origins(checker, node) -> list[str]:
    origins = node["origins"]
    if (not isinstance(origins, list) or not origins
            or not all(isinstance(origin, str) and origin.strip() for origin in origins)
            or origins != sorted(set(origins))):
        checker.fail("effect_shape", "agent turn origins must be a non-empty sorted unique provider list", node)
    return origins


def _check_agent_turn(checker, node, env, walk) -> None:
    if set(node) - _TURN_KEYS or not _TURN_REQUIRED <= set(node):
        checker.fail("effect_shape", "agent turn has missing or class-inappropriate fields", node)
    origins = _check_agent_origins(checker, node)
    if not isinstance(node["policy"], Mapping) or set(node["policy"]) - {"timeout_sec"}:
        checker.fail("effect_shape", "agent turn policy may only carry timeout_sec", node)
    agent = node["agent"]
    checker._require_type(checker._value(agent, env, allow_effect=False, **walk), AGENT_DESCRIPTOR, "type_mismatch", node)
    traced = agent.get("k") == "name" and _allocated_providers(checker).get(id(env.get(agent.get("n"))))
    required = {traced} if traced else _all_allocation_providers(checker)
    if not required <= set(origins):
        checker.fail("agent_origin_mismatch", f"agent turn origins {origins!r} omit reachable providers "
                     f"{sorted(required - set(origins))!r}", node)
    provider_view = {key: value for key, value in node.items() if key not in {"agent", "origins"}}
    checker._check_effect_node({**provider_view, "class": "provider", "provider": origins[0]}, env, **walk)
