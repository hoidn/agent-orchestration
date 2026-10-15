"""Runtime shape of the opaque `Agent` reference descriptor (frontend §8.8 versioned exception).

The descriptor is runtime-owned: `{run_id, identity, provider, policy, config_digest}` with
non-empty string ids, a string-to-string policy and a `sha256:<64 hex>` pinned-configuration digest.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

AGENT_VALUE_KEYS = frozenset({"run_id", "identity", "provider", "policy", "config_digest"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def coerce_agent_value(value: Any, context: str) -> dict[str, Any]:
    """Accept exactly one runtime `Agent` descriptor; refuse anything else."""

    from orchestrator.workflow.pure_expr import _raise

    ok = (
        isinstance(value, Mapping) and set(value) == AGENT_VALUE_KEYS
        and all(isinstance(value[key], str) and value[key] for key in ("run_id", "identity", "provider"))
        and isinstance(value["policy"], Mapping)
        and all(isinstance(key, str) and isinstance(item, str) for key, item in value["policy"].items())
        and isinstance(value["config_digest"], str) and _DIGEST.fullmatch(value["config_digest"]) is not None
    )
    if not ok:
        _raise("pure_expr_operand_type_mismatch", f"{context} must be an Agent reference descriptor")
    return {**value, "policy": dict(value["policy"])}


def reject_agent_operand(arg_types: Sequence[Mapping[str, Any]], operator: str) -> None:
    """Agents have no user-visible equality or printed form."""

    from orchestrator.workflow.pure_expr import _raise

    if any(contains_agent_descriptor(t) for t in arg_types):
        _raise("pure_expr_operand_type_mismatch", f"operator `{operator}` cannot take an Agent operand")


def contains_agent_descriptor(descriptor: Any) -> bool:
    """Find Agent at any depth of a normalized descriptor, including nominal fields."""

    if isinstance(descriptor, Mapping):
        if descriptor.get("kind") == "primitive" and descriptor.get("name") == "Agent":
            return True
        return any(contains_agent_descriptor(value) for value in descriptor.values())
    if isinstance(descriptor, (list, tuple)):
        return any(contains_agent_descriptor(value) for value in descriptor)
    return False
