"""Closed-program checks for the target-2.38 `agent` and `agent_turn` effect classes.

Dependencies: `checker` is the `check._Checker` validating one tree; this module
uses its `fail`, `_value`, `_require_type`, `_same`, `_check_effect_node` and `tree`.
An `agent` perform's result descriptor object is recorded by identity, so an
`agent_turn` whose operand names a `let` bound to that perform (directly or by
alias; the checker's environment carries the same descriptor object) must list
that perform's provider among its `origins` (`agent_origin_mismatch`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .targets import target_dsl_supports_agent_sessions

AGENT_DESCRIPTOR = {"kind": "primitive", "name": "Agent"}
_STRING = {"kind": "primitive", "name": "String"}
_AGENT_KEYS = {"k", "class", "result", "repeat", "site", "@", "provider", "policy"}
_TURN_KEYS = {"k", "class", "result", "repeat", "site", "@", "agent", "origins",
              "prompt", "inputs", "dependencies", "policy", "contract"}
_TURN_REQUIRED = _TURN_KEYS - {"k", "class", "result", "site", "@"}


def _allocated_providers(checker) -> dict[int, str]:
    return vars(checker).setdefault("_agent_result_providers", {})


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


def _check_agent_turn(checker, node, env, walk) -> None:
    if set(node) - _TURN_KEYS or not _TURN_REQUIRED <= set(node):
        checker.fail("effect_shape", "agent turn has missing or class-inappropriate fields", node)
    origins = node["origins"]
    if (not isinstance(origins, list) or not origins
            or not all(isinstance(origin, str) and origin.strip() for origin in origins)
            or origins != sorted(set(origins))):
        checker.fail("effect_shape", "agent turn origins must be a non-empty sorted unique provider list", node)
    if not isinstance(node["policy"], Mapping) or set(node["policy"]) - {"timeout_sec"}:
        checker.fail("effect_shape", "agent turn policy may only carry timeout_sec", node)
    agent = node["agent"]
    checker._require_type(checker._value(agent, env, allow_effect=False, **walk), AGENT_DESCRIPTOR, "type_mismatch", node)
    if isinstance(agent, Mapping) and agent.get("k") == "name" and agent.get("n") in env:
        allocated = _allocated_providers(checker).get(id(env[agent["n"]]))
        if allocated is not None and allocated not in origins:
            checker.fail("agent_origin_mismatch", f"agent turn origins {origins!r} omit its agent's provider "
                         f"{allocated!r}", node)
    provider_view = {key: value for key, value in node.items() if key not in {"agent", "origins"}}
    checker._check_effect_node({**provider_view, "class": "provider", "provider": origins[0]}, env, **walk)
